"""Single background scan for the desktop bridge, scoped to a library session."""

import hashlib
import os
from concurrent.futures import Future
from pathlib import Path, PurePosixPath
from threading import Thread
from uuid import UUID

from ..duplicates.detector import observe_exact_duplicates, read_exact_duplicate_inventory
from ..library import LibrarySession, read_library_connection
from .duplicates import DuplicatePresentation, observed_presentation, validate_unavailable
from .media_location import held_location


def _valid_decide_params(params: object) -> bool:
    if not isinstance(params, dict) or set(params) != {
        "snapshot_id",
        "group_key",
        "keep_location_id",
        "reason",
    }:
        return False
    snapshot_id = params["snapshot_id"]
    group_key = params["group_key"]
    keep_location_id = params["keep_location_id"]
    reason = params["reason"]
    if (
        not isinstance(snapshot_id, str)
        or not 1 <= len(snapshot_id) <= 100
        or not isinstance(group_key, str)
        or not 1 <= len(group_key) <= 100
        or not isinstance(keep_location_id, str)
        or not isinstance(reason, str)
        or not 1 <= len(reason.strip()) <= 200
        or "\0" in reason
    ):
        return False
    try:
        return str(UUID(keep_location_id)) == keep_location_id
    except (ValueError, AttributeError):
        return False


def _valid_remove_params(params: object) -> bool:
    if not isinstance(params, dict) or set(params) != {
        "snapshot_id",
        "group_key",
        "remove_location_id",
    }:
        return False
    snapshot_id = params["snapshot_id"]
    group_key = params["group_key"]
    remove_location_id = params["remove_location_id"]
    if (
        not isinstance(snapshot_id, str)
        or not 1 <= len(snapshot_id) <= 100
        or not isinstance(group_key, str)
        or not 1 <= len(group_key) <= 100
        or not isinstance(remove_location_id, str)
    ):
        return False
    try:
        return str(UUID(remove_location_id)) == remove_location_id
    except (ValueError, AttributeError):
        return False


def _sha256_fd(fd: int) -> str:
    with os.fdopen(os.dup(fd), "rb", closefd=True) as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class DuplicateScan:
    def __init__(self) -> None:
        self._session_id: str | None = None
        self._work: Future[DuplicatePresentation] | None = None

    def clear_session(self) -> None:
        self._session_id = None
        if self._work is not None and self._work.done():
            self._work = None

    def request(self, active: LibrarySession, method: str, params: dict) -> dict:
        session_id = active.descriptor.session_id
        work = self._work
        if method == "duplicates.start":
            if params:
                return {"status": "invalid_request"}
            if work is not None and not work.done():
                status = "scanning" if session_id == self._session_id else "temporarily_unavailable"
                return {"status": status}
            path, identity = active.catalog_binding
            work = Future()
            Thread(target=self._scan, args=(work, path, identity), daemon=True).start()
            self._work, self._session_id = work, session_id
            return {"status": "scanning"}
        if method == "duplicates.decide":
            if not _valid_decide_params(params):
                return {"status": "invalid_request"}
            if work is None or session_id != self._session_id:
                return {"status": "analysis_not_available"}
            if not work.done():
                return {"status": "scanning"}
            try:
                presentation = work.result()
            except Exception:
                return {"status": "internal_error"}
            if params["snapshot_id"] != presentation.snapshot_id:
                return {"status": "stale_snapshot"}
            group = next(
                (g for g in presentation.groups if g["group_key"] == params["group_key"]), None
            )
            if group is None:
                return {"status": "not_found"}
            if params["keep_location_id"] not in {m["location_id"] for m in group["members"]}:
                return {"status": "invalid_request"}
            from ..duplicates.review import DuplicateReviewError, save_exact_duplicate_decision

            try:
                with active.command_connection() as write_connection:
                    decision = save_exact_duplicate_decision(
                        write_connection,
                        sha256=group["sha256"],
                        keep_location_id=params["keep_location_id"],
                        reason=params["reason"].strip(),
                    )
            except DuplicateReviewError:
                return {"status": "stale_snapshot"}
            updated = presentation.apply_decision(
                group["group_key"],
                decision.id,
                decision.keep_location_id,
                decision.reason,
                decision.evidence_fingerprint,
            )
            return {"status": "ready", "group": updated}
        if method == "duplicates.remove":
            if not _valid_remove_params(params):
                return {"status": "invalid_request"}
            if work is None or session_id != self._session_id:
                return {"status": "analysis_not_available"}
            if not work.done():
                return {"status": "scanning"}
            try:
                presentation = work.result()
            except Exception:
                return {"status": "internal_error"}
            if params["snapshot_id"] != presentation.snapshot_id:
                return {"status": "stale_snapshot"}
            group = next(
                (g for g in presentation.groups if g["group_key"] == params["group_key"]), None
            )
            if group is None:
                return {"status": "not_found"}
            review = group.get("review")
            if not review or review.get("status") != "current":
                return {"status": "invalid_request"}
            keep_location_id = review["keep_location_id"]
            remove_location_id = params["remove_location_id"]
            if remove_location_id == keep_location_id:
                return {"status": "invalid_request"}
            keep_member = next(
                (m for m in group["members"] if m["location_id"] == keep_location_id), None
            )
            target_member = next(
                (m for m in group["members"] if m["location_id"] == remove_location_id), None
            )
            if keep_member is None or target_member is None:
                return {"status": "not_found"}
            try:
                with (
                    held_location(
                        active.query_connection,
                        keep_member["asset_id"],
                        location_id=keep_location_id,
                    ) as (_k_row, keep_dirs, keep_parent, keep_fd, keep_info, _k_path),
                    held_location(
                        active.query_connection,
                        target_member["asset_id"],
                        location_id=remove_location_id,
                    ) as (t_row, target_dirs, target_parent, target_fd, target_info, _t_path),
                ):
                    if (
                        (keep_info.st_dev, keep_info.st_ino)
                        == (target_info.st_dev, target_info.st_ino)
                        or target_info.st_nlink != 1
                        or keep_info.st_size != int(group["byte_size"])
                        or target_info.st_size != int(group["byte_size"])
                    ):
                        return {"status": "stale_snapshot"}
                    if (
                        _sha256_fd(keep_fd) != group["sha256"]
                        or _sha256_fd(target_fd) != group["sha256"]
                    ):
                        return {"status": "stale_snapshot"}
                    keep_name = PurePosixPath(keep_member["relative_path"]).name
                    target_name = PurePosixPath(t_row["normalized_relative_path"]).name
                    keep_dirs.check()
                    target_dirs.check()
                    keep_current = os.stat(keep_name, dir_fd=keep_parent, follow_symlinks=False)
                    target_current = os.stat(
                        target_name, dir_fd=target_parent, follow_symlinks=False
                    )
                    if (keep_current.st_dev, keep_current.st_ino, keep_current.st_ctime_ns) != (
                        keep_info.st_dev,
                        keep_info.st_ino,
                        keep_info.st_ctime_ns,
                    ) or (
                        target_current.st_dev,
                        target_current.st_ino,
                        target_current.st_ctime_ns,
                    ) != (
                        target_info.st_dev,
                        target_info.st_ino,
                        target_info.st_ctime_ns,
                    ):
                        return {"status": "stale_snapshot"}
                    with active.command_connection() as write_connection:
                        write_connection.execute("BEGIN IMMEDIATE")
                        try:
                            decision_row = write_connection.execute(
                                """SELECT id FROM exact_duplicate_decision
                                WHERE sha256=? AND byte_size=? AND keep_location_id=?
                                  AND status='current'""",
                                (group["sha256"], int(group["byte_size"]), keep_location_id),
                            ).fetchone()
                            if decision_row is None:
                                raise ValueError("missing current decision")
                            os.unlink(target_name, dir_fd=target_parent)
                            write_connection.execute(
                                """UPDATE file_location
                                SET availability='missing'
                                WHERE id=? AND asset_id=?""",
                                (remove_location_id, target_member["asset_id"]),
                            )
                            write_connection.commit()
                        except Exception:
                            write_connection.rollback()
                            raise
            except Exception:
                return {"status": "stale_snapshot"}
            remaining_group = presentation.remove_member(group["group_key"], remove_location_id)
            return {
                "status": "ready",
                "resolved": remaining_group is None,
                "group": remaining_group,
            }
        if work is None or session_id != self._session_id:
            if self._session_id is None and work is not None and work.done():
                self._work = None
            return validate_unavailable(method, params)
        if not work.done():
            validation = validate_unavailable(method, params)
            return (
                validation if validation["status"] == "invalid_request" else {"status": "scanning"}
            )
        try:
            presentation = work.result()
        except Exception:
            return {"status": "internal_error"}
        return presentation.request(method, params)

    @staticmethod
    def _scan(work: Future[DuplicatePresentation], path: Path, identity: tuple[int, int]) -> None:
        try:
            from ..duplicates.review import _review_decisions

            with read_library_connection(path, expected_identity=identity) as connection:
                inventory = tuple(
                    row
                    for row in read_exact_duplicate_inventory(connection)
                    if row.availability != "missing"
                )
                decisions = _review_decisions(connection)
            root_names = {row.root_id: row.root_display_name for row in inventory}
            work.set_result(
                observed_presentation(observe_exact_duplicates(inventory), root_names, decisions)
            )
        except Exception as error:
            work.set_exception(error)
