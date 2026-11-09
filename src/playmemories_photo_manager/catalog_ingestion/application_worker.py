"""One private Linux application process; no renderer paths or dynamic deserialization."""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import signal
import sys
from pathlib import Path

from ..catalog import Catalog
from ..library import LibrarySession
from .preparation import PreparationInput, _validate_input
from .scoped_application import apply_scoped_ingestion
from .scoped_authorization import authorize_scoped_ingestion
from .worker_wire import (
    MAX_FRAME_BYTES,
    MAX_RESULT_BYTES,
    decode_result,
    encode_result,
    unique_object,
)


def main():
    if sys.platform != "linux" or len(sys.argv) != 4:
        return 2
    command_id, parent, fd = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != parent:
        return 2
    cancelled = False

    def cancel(_signal, _frame):
        nonlocal cancelled
        cancelled = True

    signal.signal(signal.SIGUSR1, cancel)

    def emit(kind, **values):
        raw = (
            json.dumps(
                {"operation_id": command_id, "kind": kind, **values},
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode()
            + b"\n"
        )
        if len(raw) > MAX_FRAME_BYTES:
            raise ValueError("frame too large")
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()

    try:
        emit("ready")
        raw = sys.stdin.buffer.readline(MAX_FRAME_BYTES + 1)
        if len(raw) > MAX_FRAME_BYTES or not raw.endswith(b"\n"):
            raise ValueError
        request = json.loads(raw, object_pairs_hook=unique_object)
        if set(request) != {"source", "candidate_ids", "decision_fingerprint"}:
            raise ValueError
        fields = request["source"]
        source = PreparationInput(
            **(
                fields
                | {
                    "catalog_identity": tuple(fields["catalog_identity"]),
                    "root_identity": tuple(fields["root_identity"]),
                }
            )
        )
        _validate_input(source)
        with os.fdopen(fd, "rb") as memory:
            scoped = decode_result(memory.read(MAX_RESULT_BYTES + 1))
        if (
            scoped.original.plan.library_root_id,
            scoped.original.scan_result.root.absolute_path,
        ) != (source.root_id, source.root_path):
            raise ValueError
        identity = scoped.original.scan_result.root.physical_identity
        if (identity.device, identity.file_id) != source.root_identity:
            raise ValueError
        authorization = authorize_scoped_ingestion(scoped, tuple(request["candidate_ids"]))
        if authorization.decision_fingerprint != request["decision_fingerprint"]:
            raise ValueError
        with LibrarySession.open(
            Path(source.catalog_path), known_media_roots=(Path(source.root_path),)
        ) as library:
            expected = (Path(source.catalog_path), source.catalog_identity)
            if library.catalog_binding != expected:
                raise ValueError
            with library.command_connection() as connection:
                report = apply_scoped_ingestion(
                    Catalog(connection),
                    scoped,
                    authorization,
                    expected_root_mount=source.mount_id,
                    cancellation_requested=lambda: cancelled,
                )
            if library.catalog_binding != expected:
                raise ValueError
        payload = encode_result(report)
        emit("result_begin", size=len(payload))
        for sequence, position in enumerate(range(0, len(payload), 32768)):
            emit(
                "chunk",
                sequence=sequence,
                data=base64.b64encode(payload[position : position + 32768]).decode("ascii"),
            )
        emit("result_end", digest=hashlib.sha256(payload).hexdigest())
        return 0
    except Exception:
        # Even an early failure is conservatively unknown after parent admission.
        emit("failure", reason="protocol_failure")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
