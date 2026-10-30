"""Trusted shell commands and session-bound queries; no media observation."""

from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from ..library import LibraryError, LibraryLifecycle


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        raise LibraryError("invalid_request")
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except ValueError:
        raise LibraryError("invalid_request") from None
    return value


class LibraryDispatcher:
    """Only the authenticated main process can supply a native selection path."""

    def __init__(self):
        self.owner = LibraryLifecycle()
        self.handle: str | None = None

    def state(self) -> dict:
        active = self.owner.active
        return {
            "state": "active" if active else "no_library",
            "session": (
                {
                    **asdict(active.descriptor),
                    "library_handle": self.handle,
                    "generation": self.owner.generation,
                }
                if active
                else None
            ),
        }

    def request(self, method: str, params: object) -> object:
        from .bridge import BridgeRequestError, _dispatch

        if not isinstance(params, dict):
            raise LibraryError("invalid_request")
        if method == "library.state" and not params:
            return self.state()
        if method in ("library.open", "library.create"):
            if set(params) != {"path", "library_handle"}:
                raise LibraryError("invalid_request")
            handle = _uuid(params["library_handle"])
            raw_path = params["path"]
            if not isinstance(raw_path, str) or not 1 <= len(raw_path) <= 4096 or "\0" in raw_path:
                raise LibraryError("invalid_request")
            action = self.owner.create if method == "library.create" else self.owner.open
            action(Path(raw_path))
            self.handle = handle
            return self.state()
        if method == "library.close":
            if set(params) != {"session_id"}:
                raise LibraryError("invalid_request")
            self.require_session(params["session_id"])
            self.owner.close()
            self.handle = None
            return self.state()
        if method not in (
            "gallery.list",
            "asset.details",
            "thumbnail.get",
            "duplicates.list",
            "duplicates.group",
        ):
            raise LibraryError("invalid_request")
        if "session_id" not in params:
            raise LibraryError("stale_session")
        active = self.require_session(params["session_id"])
        try:
            return _dispatch(
                active.query_connection,
                method,
                {k: v for k, v in params.items() if k != "session_id"},
            )
        except BridgeRequestError:
            # `python -m ...bridge` runs its entry point as __main__; translate
            # here so exception identity does not depend on that module alias.
            raise LibraryError("invalid_request") from None

    def require_session(self, value: object):
        identifier = _uuid(value)
        active = self.owner.active
        if active is None or active.descriptor.session_id != identifier:
            raise LibraryError("stale_session")
        return active

    def close(self) -> None:
        self.owner.close()
