"""Fixed private entry point for one disposable Linux preparation process."""

from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import signal
import sys
from pathlib import Path

from ..change_planning import ChangeClassification, PlanningContext
from ..library import LibraryError
from ..scanner import ScanLimits, ScanOptions, ScanResourceLimitError, ScanScopeChangedError, scan
from .media import (
    MediaPreparationError,
    MediaVerificationCancelled,
    _Directories,
    _identity,
    _mount_id,
    classify_media,
)
from .scoping import ProposalResourceLimitError, scope_catalogable_proposal
from .snapshot import SnapshotResourceLimitError, capture_catalog_snapshot
from .worker_wire import MAX_FRAME_BYTES, encode_result, unique_object


def main() -> int:
    if sys.platform != "linux" or len(sys.argv) != 3:
        return 2
    operation_id, parent = sys.argv[1], int(sys.argv[2])
    # Kill the child on controller death, including the race before prctl is installed.
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != parent:
        return 2
    cancelled = False

    def cancel(_signal, _frame):
        nonlocal cancelled
        cancelled = True

    signal.signal(signal.SIGUSR1, cancel)

    def checkpoint():
        if cancelled:
            raise MediaVerificationCancelled

    def emit(kind, **fields):
        line = (
            json.dumps(
                {"operation_id": operation_id, "kind": kind, **fields},
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("ascii")
            + b"\n"
        )
        if len(line) > MAX_FRAME_BYTES:
            raise ProposalResourceLimitError
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()

    directories = _Directories()
    try:
        emit("ready")
        raw = sys.stdin.buffer.readline(MAX_FRAME_BYTES + 1)
        if len(raw) > MAX_FRAME_BYTES or not raw.endswith(b"\n"):
            raise ValueError
        request = json.loads(raw, object_pairs_hook=unique_object)
        if set(request) != {
            "catalog_path",
            "root_path",
            "root_id",
            "catalog_identity",
            "root_identity",
            "mount_id",
            "additions_only",
        }:
            raise ValueError
        checkpoint()
        emit("progress", phase="snapshot", observed_count=0, verified_count=0, excluded_count=0)
        snapshot = capture_catalog_snapshot(
            Path(request["catalog_path"]),
            request["root_id"],
            expected_catalog_identity=tuple(request["catalog_identity"]),
        )
        if snapshot.library_root.normalized_path != request["root_path"]:
            raise MediaPreparationError("root_changed")
        # No SQLite connection survives capture_catalog_snapshot; only now open media root.
        root_path = Path(request["root_path"])
        if not root_path.is_absolute() or ".." in root_path.parts:
            raise ValueError
        root_fd = directories.start()
        for component in root_path.parts[1:]:
            checkpoint()
            root_fd = directories.child(root_fd, component)
        identity = _identity(os.fstat(root_fd))
        if [identity.device, identity.file_id] != request["root_identity"] or _mount_id(
            root_fd
        ) != request["mount_id"]:
            raise MediaPreparationError("root_changed")
        emit("progress", phase="scanning", observed_count=0, verified_count=0, excluded_count=0)
        observed = scan(
            root_path,
            ScanOptions(
                limits=ScanLimits(),
                mount_id=request["mount_id"],
                cancellation_requested=lambda: cancelled,
            ),
            root_fd=root_fd,
        )
        directories.check()
        checkpoint()
        if not observed.is_complete:
            raise MediaPreparationError("incomplete_coverage")
        count = len(observed.entries)
        emit(
            "progress", phase="verifying", observed_count=count, verified_count=0, excluded_count=0
        )
        context = PlanningContext(
            request["root_id"],
            snapshot.library_root.normalized_path,
            observed.root.absolute_path,
            observed.scope,
        )
        from .service import prepare_from_snapshot

        original = prepare_from_snapshot(snapshot, observed, context)
        decode_paths = frozenset(
            change.relative_path
            for change in original.plan.changes
            if request["additions_only"]
            and change.classification is ChangeClassification.NEW_FILE_CANDIDATE
        )
        eligible = classify_media(
            observed,
            request["root_id"],
            cancellation_requested=lambda: cancelled,
            decode_paths=decode_paths,
        )
        checkpoint()
        if any(item.state == "failed" for item in eligible):
            reason = next(item.reason for item in eligible if item.state == "failed")
            raise MediaPreparationError(
                "root_changed" if reason == "entry_changed_during_verification" else reason
            )
        excluded = sum(item.state == "excluded" for item in eligible)
        emit(
            "progress",
            phase="planning",
            observed_count=count,
            verified_count=count,
            excluded_count=excluded,
        )
        proposal = scope_catalogable_proposal(
            original, eligible, additions_only=request["additions_only"]
        )
        payload = encode_result(proposal)
        checkpoint()
        directories.check()
        emit("result_begin", size=len(payload))
        for sequence, position in enumerate(range(0, len(payload), 32768)):
            checkpoint()
            emit(
                "chunk",
                sequence=sequence,
                data=base64.b64encode(payload[position : position + 32768]).decode("ascii"),
            )
        emit("result_end", digest=hashlib.sha256(payload).hexdigest())
        return 0
    except MediaVerificationCancelled:
        emit("cancelled")
        return 0
    except (ScanResourceLimitError, SnapshotResourceLimitError, ProposalResourceLimitError):
        emit("failure", reason="resource_limit")
        return 0
    except LibraryError as error:
        reason = (
            error.code if error.code in ("permission_denied", "resource_limit") else "root_changed"
        )
        emit("failure", reason=reason)
        return 0
    except MediaPreparationError as error:
        reason = str(error)
        if reason not in (
            "root_changed",
            "read_failed",
            "verification_timeout",
            "incomplete_coverage",
        ):
            reason = "protocol_failure"
        emit("failure", reason=reason)
        return 0
    except (ScanScopeChangedError, OSError):
        emit("failure", reason="root_changed")
        return 0
    except Exception:
        emit("failure", reason="protocol_failure")
        return 0
    finally:
        directories.close()


if __name__ == "__main__":
    raise SystemExit(main())
