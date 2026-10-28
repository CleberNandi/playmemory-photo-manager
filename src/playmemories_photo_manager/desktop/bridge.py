"""Authenticated JSON-lines bridge for the experimental Electron shell."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import TextIO

from playmemories_photo_manager.catalog import initialize_database
from playmemories_photo_manager.gallery import GalleryQueries, GalleryQuery

MAX_MESSAGE_BYTES = 64 * 1024
MAX_PAGE_SIZE = 50


class BridgeRequestError(ValueError):
    """A request is malformed or outside the bridge allowlist."""


def _json_default(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"unsupported response value: {type(value).__name__}")


def _open_catalog(path: Path | None) -> sqlite3.Connection:
    if path is None:
        return initialize_database(":memory:")
    resolved = path.expanduser().resolve(strict=True)
    # Path.as_uri() percent-encodes URI delimiters in filenames (notably # and ?).
    # SQLite receives an unambiguous file URI while mode=ro prevents journals or
    # accidental side databases from being created beside the catalog.
    uri = f"{resolved.as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version != 2:
        connection.close()
        raise RuntimeError("catalog schema is not supported by this desktop preview")
    return connection


def _dispatch(connection: sqlite3.Connection, method: str, params: object) -> object:
    if method == "gallery.list":
        if not isinstance(params, dict):
            raise BridgeRequestError("params must be an object")
        unknown = set(params) - {"page_size", "after"}
        if unknown:
            raise BridgeRequestError("unsupported gallery parameters")
        page_size = params.get("page_size", 24)
        if isinstance(page_size, bool) or not isinstance(page_size, int):
            raise BridgeRequestError("page_size must be an integer")
        if not 1 <= page_size <= MAX_PAGE_SIZE:
            raise BridgeRequestError("page_size must be between 1 and 50")
        after = params.get("after")
        if after is not None and not isinstance(after, str):
            raise BridgeRequestError("after must be text or null")
        return asdict(
            GalleryQueries(connection).list_assets(GalleryQuery(page_size=page_size, after=after))
        )
    if method == "shutdown":
        return {"accepted": True}
    raise BridgeRequestError("unsupported method")


def serve(
    connection: sqlite3.Connection,
    token: str,
    source: TextIO = sys.stdin,
    sink: TextIO = sys.stdout,
) -> int:
    _write(sink, {"event": "ready", "protocol": 1})
    for raw_line in source:
        if len(raw_line.encode("utf-8")) > MAX_MESSAGE_BYTES:
            _write(sink, {"id": None, "ok": False, "error": {"code": "message_too_large"}})
            continue
        request_id: object = None
        try:
            request = json.loads(raw_line)
            if not isinstance(request, dict):
                raise BridgeRequestError("request must be an object")
            request_id = request.get("id")
            if not isinstance(request_id, str) or not request_id:
                raise BridgeRequestError("id must be non-empty text")
            if request.get("token") != token:
                raise BridgeRequestError("authentication failed")
            method = request.get("method")
            if not isinstance(method, str):
                raise BridgeRequestError("method must be text")
            result = _dispatch(connection, method, request.get("params", {}))
            _write(sink, {"id": request_id, "ok": True, "result": result})
            if method == "shutdown":
                return 0
        except (BridgeRequestError, json.JSONDecodeError) as error:
            _write(
                sink,
                {
                    "id": request_id,
                    "ok": False,
                    "error": {"code": "invalid_request", "message": str(error)},
                },
            )
        except Exception:
            _write(
                sink,
                {
                    "id": request_id,
                    "ok": False,
                    "error": {"code": "backend_failure", "message": "gallery read failed"},
                },
            )
    return 0


def _write(sink: TextIO, payload: object) -> None:
    sink.write(json.dumps(payload, default=_json_default, separators=(",", ":")) + "\n")
    sink.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path)
    args = parser.parse_args()
    token = os.environ.get("PLAYMEMORIES_BRIDGE_TOKEN", "")
    if len(token) < 32:
        print("invalid bridge credentials", file=sys.stderr)
        return 2
    try:
        connection = _open_catalog(args.catalog)
    except Exception:
        print("catalog could not be opened", file=sys.stderr)
        return 3
    try:
        return serve(connection, token)
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
