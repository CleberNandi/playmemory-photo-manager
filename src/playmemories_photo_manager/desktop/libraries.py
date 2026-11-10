"""Trusted shell commands and session-bound queries; no media observation."""

from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from ..imaging.service import ImageService
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

    def __init__(self, *, ingestion_enabled=False, protected_paths=()):
        self.ingestion_enabled = ingestion_enabled
        self.protected_paths = protected_paths
        self.ingestion = None
        self.images = ImageService()
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
        if method.startswith("ingestion."):
            return self._ingestion_request(method, params)
        if method in ("library.open", "library.create"):
            if set(params) != {"path", "library_handle"}:
                raise LibraryError("invalid_request")
            handle = _uuid(params["library_handle"])
            raw_path = params["path"]
            if not isinstance(raw_path, str) or not 1 <= len(raw_path) <= 4096 or "\0" in raw_path:
                raise LibraryError("invalid_request")
            if self.ingestion is not None and (
                self.ingestion.preparation.busy or self.ingestion.commands.busy
            ):
                self.ingestion.close(timeout=0)
                raise LibraryError("busy")
            if not self.images.shutdown():
                raise LibraryError("busy")
            self.images = ImageService()
            action = self.owner.create if method == "library.create" else self.owner.open
            action(Path(raw_path))
            self.ingestion = None
            self.images = ImageService()
            self.handle = handle
            return self.state()
        if method == "library.close":
            if set(params) != {"session_id"}:
                raise LibraryError("invalid_request")
            self.require_session(params["session_id"])
            if not self.images.shutdown():
                raise LibraryError("busy")
            self.owner.close()
            self.ingestion = None
            self.handle = None
            return self.state()
        if method not in (
            "asset.reveal",
            "annotation.favorite",
            "gallery.list",
            "calendar.summary",
            "asset.details",
            "thumbnail.get",
            "preview.get",
            "duplicates.list",
            "duplicates.group",
        ):
            raise LibraryError("invalid_request")
        if "session_id" not in params:
            raise LibraryError("stale_session")
        active = self.require_session(params["session_id"])
        if self.ingestion is not None and (
            self.ingestion.preparation.busy or self.ingestion.commands.busy
        ):
            raise LibraryError("busy")  # Do not block the monitor on SQLite/media metadata.
        if method == "asset.reveal":
            from .media_location import reveal_location

            if set(params) != {"session_id", "asset_id"}:
                raise LibraryError("invalid_request")
            return reveal_location(active.query_connection, _uuid(params["asset_id"]))
        if method == "annotation.favorite":
            from ..catalog import Catalog
            from ..catalog.errors import CatalogError, InvalidReferenceError

            if (
                set(params) != {"session_id", "asset_id", "favorite"}
                or type(params["favorite"]) is not bool
            ):
                raise LibraryError("invalid_request")
            asset_id = _uuid(params["asset_id"])
            try:
                with active.command_connection() as connection:
                    annotation = Catalog(connection).set_favorite(asset_id, params["favorite"])
                return {"asset_id": asset_id, "favorite": annotation.favorite}
            except InvalidReferenceError:
                raise LibraryError("not_found") from None
            except CatalogError:
                # A lost commit acknowledgement cannot be treated as a proven rollback.
                # The operation sets an explicit boolean; the UI never automatically retries.
                raise LibraryError("outcome_unknown") from None
        if method in ("thumbnail.get", "preview.get"):
            if set(params) != {"session_id", "asset_id"}:
                raise LibraryError("invalid_request")
            if self.images.closed and not self.images.jobs:
                self.images = ImageService()
            asset_id = _uuid(params["asset_id"])
            return self.images.request(
                active.query_connection,
                asset_id,
                "grid" if method == "thumbnail.get" else "preview",
            )
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

    def _ingestion_request(self, method, params):
        from ..catalog_ingestion.preparation import PreparationError
        from ..catalog_ingestion.root_grants import RootGrantService

        if not self.ingestion_enabled:
            raise LibraryError("unavailable")
        active = self.require_session(params.get("session_id"))
        window = _uuid(params.get("window_id"))
        allowed = {
            "ingestion.select_root": {
                "session_id",
                "window_id",
                "path",
                "recursive",
                "identity_reviewed",
            },
            "ingestion.prepare": {
                "session_id",
                "window_id",
                "root_grant_id",
                "recursive",
                "client_request_id",
            },
            "ingestion.apply": {
                "session_id",
                "window_id",
                "proposal_id",
                "candidate_ids",
                "client_request_id",
            },
            "ingestion.application_status": {"session_id", "window_id", "command_id"},
            "ingestion.status": {"session_id", "window_id", "operation_id"},
            "ingestion.cancel": {"session_id", "window_id", "operation_id"},
            "ingestion.page": {"session_id", "window_id", "proposal_id", "cursor", "page_size"},
        }
        if method not in allowed or set(params) != allowed[method]:
            raise LibraryError("invalid_request")
        try:
            if self.ingestion is None:
                if method != "ingestion.select_root":
                    raise LibraryError("stale_session")
                self.ingestion = RootGrantService(
                    active, window, protected_paths=self.protected_paths
                )
            service = self.ingestion
            if window != service.window_id:
                raise LibraryError("stale_session")
            if method == "ingestion.select_root":
                return service.select(params)
            if method == "ingestion.prepare":
                return service.prepare(params)
            if method == "ingestion.apply":
                return service.apply(params)
            if method == "ingestion.application_status":
                return service.application_status(
                    params["session_id"], window, _uuid(params["command_id"])
                )
            controller = service.preparation
            if method == "ingestion.status":
                return controller.status(
                    params["session_id"], window, _uuid(params["operation_id"])
                )
            if method == "ingestion.cancel":
                return controller.cancel(
                    params["session_id"], window, _uuid(params["operation_id"])
                )
            return controller.page(
                params["session_id"],
                window,
                _uuid(params["proposal_id"]),
                params["cursor"],
                params["page_size"],
            )
        except PreparationError as error:
            raise LibraryError(error.code) from None

    def tick(self):
        self.images.tick()
        if self.ingestion is not None:
            self.ingestion.tick()

    def shutdown(self, timeout=2.5):
        if self.ingestion is not None and not self.ingestion.close(timeout=timeout):
            return False
        if not self.images.shutdown():
            return False
        self.owner.close()
        self.ingestion = None
        self.handle = None
        return True

    def require_session(self, value: object):
        identifier = _uuid(value)
        active = self.owner.active
        if active is None or active.descriptor.session_id != identifier:
            raise LibraryError("stale_session")
        return active

    def close(self) -> None:
        if not self.shutdown():
            raise LibraryError("busy")
