"""Private, bounded JSON transport. No pickle, dynamic import, or callable deserialization."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum

from ..catalog import models as catalog
from ..change_planning import models as planning
from ..evidence import models as evidence
from ..scanner import models as scanner
from . import media, models, scoping

MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_FRAME_BYTES = 64 * 1024
_TYPES = {}
for _module in (catalog, planning, evidence, scanner, models, media, scoping):
    for _value in vars(_module).values():
        if isinstance(_value, type) and (is_dataclass(_value) or issubclass(_value, Enum)):
            _TYPES[_value.__module__ + "." + _value.__qualname__] = _value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate transport field")
        result[key] = value
    return result


def _transform(value, depth=0):
    if depth > 32:
        raise ValueError("transport depth exceeded")
    if isinstance(value, Enum):
        return {
            "enum": type(value).__module__ + "." + type(value).__qualname__,
            "value": value.value,
        }
    if is_dataclass(value):
        return {
            "type": type(value).__module__ + "." + type(value).__qualname__,
            "fields": {
                f.name: _transform(getattr(value, f.name), depth + 1)
                for f in fields(value)
                if f.init
            },
        }
    if isinstance(value, datetime):
        return {"datetime": value.isoformat()}
    if isinstance(value, tuple):
        return [_transform(item, depth + 1) for item in value]
    if value is None or type(value) in (str, int, bool):
        return value
    raise ValueError("unsupported transport type")


def encode_result(value):
    output = bytearray()
    encoder = json.JSONEncoder(ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    for chunk in encoder.iterencode(_transform(value)):
        data = chunk.encode("ascii")
        if len(output) + len(data) > MAX_RESULT_BYTES:
            raise scoping.ProposalResourceLimitError
        output.extend(data)
    return output


def _restore(value, depth=0):
    if depth > 32:
        raise ValueError("transport depth exceeded")
    if isinstance(value, list):
        return tuple(_restore(item, depth + 1) for item in value)
    if not isinstance(value, dict):
        if value is None or type(value) in (str, int, bool):
            return value
        raise ValueError("invalid transport scalar")
    if set(value) == {"datetime"}:
        return datetime.fromisoformat(value["datetime"])
    if set(value) == {"enum", "value"}:
        cls = _TYPES[value["enum"]]
        if not issubclass(cls, Enum):
            raise ValueError("invalid enum")
        return cls(value["value"])
    if set(value) == {"type", "fields"}:
        cls = _TYPES[value["type"]]
        if not is_dataclass(cls) or not isinstance(value["fields"], dict):
            raise ValueError("invalid record")
        if set(value["fields"]) != {f.name for f in fields(cls) if f.init}:
            raise ValueError("invalid record fields")
        return cls(**{key: _restore(item, depth + 1) for key, item in value["fields"].items()})
    raise ValueError("invalid transport tag")


def decode_result(payload):
    if not 0 < len(payload) <= MAX_RESULT_BYTES:
        raise ValueError("invalid transport size")
    result = _restore(json.loads(payload, object_pairs_hook=unique_object))
    if not isinstance(result, scoping.ScopedIngestionProposal):
        raise ValueError("invalid result type")
    expected = scoping.scope_catalogable_proposal(result.original, result.eligibilities)
    if result != expected:
        raise ValueError("result does not match its evidence")
    return result


def decode_application_report(payload):
    if not 0 < len(payload) <= MAX_RESULT_BYTES:
        raise ValueError("invalid report size")
    result = _restore(json.loads(payload, object_pairs_hook=unique_object))
    if not isinstance(result, models.IngestionReport):
        raise ValueError("invalid report type")
    return result
