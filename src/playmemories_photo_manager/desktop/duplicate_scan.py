"""Single background scan for the desktop bridge, scoped to a library session."""

from concurrent.futures import Future
from pathlib import Path
from threading import Thread

from ..duplicates.detector import observe_exact_duplicates, read_exact_duplicate_inventory
from ..library import LibrarySession, read_library_connection
from .duplicates import DuplicatePresentation, observed_presentation, validate_unavailable


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
            with read_library_connection(path, expected_identity=identity) as connection:
                inventory = read_exact_duplicate_inventory(connection)
            root_names = {row.root_id: row.root_display_name for row in inventory}
            work.set_result(observed_presentation(observe_exact_duplicates(inventory), root_names))
        except Exception as error:
            work.set_exception(error)
