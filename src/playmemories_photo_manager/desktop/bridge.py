"""Authenticated JSON-lines bridge for the experimental Electron shell."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sqlite3
import sys
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import TextIO
from uuid import UUID

from playmemories_photo_manager.gallery import GalleryQueries, GalleryQuery
from playmemories_photo_manager.gallery.errors import AssetNotFoundError
from playmemories_photo_manager.library import LibraryError, LibrarySession

MAX_MESSAGE_BYTES = 64 * 1024
MAX_PAGE_SIZE = 50


class BridgeRequestError(ValueError):
    """A request is malformed or outside the bridge allowlist."""


def _json_default(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    raise TypeError(f"unsupported response value: {type(value).__name__}")


_FACET_SOURCES = {
    "tags": ("SELECT id, display_name AS name FROM tag", ()),
    "types": ("SELECT DISTINCT media_type AS id, media_type AS name FROM asset", ()),
    "cameras": (
        "SELECT DISTINCT interpreted_value AS id, interpreted_value AS name FROM metadata "
        "WHERE namespace='exif' AND metadata_key=?",
        ("Model",),
    ),
    "lenses": (
        "SELECT DISTINCT interpreted_value AS id, interpreted_value AS name FROM metadata "
        "WHERE namespace='exif' AND metadata_key=?",
        ("LensModel",),
    ),
}
_FACET_PAGE_SIZE = 24


def _facet_page(connection, facet, keyword="", offset=0):
    source, arguments = _FACET_SOURCES[facet]
    connection.create_function(
        "fold_text", 1, lambda value: (value or "").casefold(), deterministic=True
    )
    rows = connection.execute(
        f"""SELECT id, name FROM ({source})
        WHERE length(name) BETWEEN 1 AND 200 AND instr(fold_text(name), ?) > 0
        ORDER BY fold_text(name), id LIMIT ? OFFSET ?""",
        (*arguments, keyword.casefold(), _FACET_PAGE_SIZE + 1, offset),
    ).fetchall()
    return {
        "options": [{"id": row[0], "name": row[1]} for row in rows[:_FACET_PAGE_SIZE]],
        "next_offset": offset + _FACET_PAGE_SIZE if len(rows) > _FACET_PAGE_SIZE else None,
    }


def _dispatch(
    connection: sqlite3.Connection,
    method: str,
    params: object,
    *,
    demo: bool = False,
    duplicates: object = None,
) -> object:
    if method in {"duplicates.list", "duplicates.group"}:
        from .duplicates import DuplicatePresentation, synthetic_groups, validate_unavailable

        if not demo:
            return validate_unavailable(method, params)
        presentation = (
            duplicates
            if duplicates is not None
            else DuplicatePresentation(*synthetic_groups(connection))
        )
        return presentation.request(method, params)
    if method in {"thumbnail.get", "preview.get", "asset.details"}:
        if not isinstance(params, dict) or set(params) != {"asset_id"}:
            raise BridgeRequestError("expected asset_id only")
        asset_id = params["asset_id"]
        try:
            if not isinstance(asset_id, str) or str(UUID(asset_id)) != asset_id:
                raise ValueError
        except (ValueError, AttributeError):
            raise BridgeRequestError("asset_id must be a canonical UUID") from None
        if method == "asset.details":
            details = asdict(GalleryQueries(connection).get_asset_details(asset_id))
            # Nanoseconds exceed JavaScript's safe integer range. Preserve the
            # observation exactly at the JSON boundary, including explicit null.
            for location in details["locations"]:
                if location["observed_mtime_ns"] is not None:
                    location["observed_mtime_ns"] = str(location["observed_mtime_ns"])
            return details
        if not demo:
            return None
        row = connection.execute("SELECT kind FROM asset WHERE id = ?", (asset_id,)).fetchone()
        if row is None:
            return None
        from .demo import synthetic_thumbnail

        if method == "preview.get":
            return None
        data = synthetic_thumbnail(asset_id, row[0])
        return {
            "media_type": "image/png",
            "width": 256,
            "height": 160,
            "base64": base64.b64encode(data).decode("ascii"),
        }
    if method == "calendar.summary":
        from ..gallery.calendar import summary

        if not isinstance(params, dict) or set(params) - {"period"}:
            raise BridgeRequestError("invalid calendar parameters")
        try:
            return summary(connection, params.get("period"))
        except ValueError:
            raise BridgeRequestError("invalid calendar period") from None
    if method == "gallery.facets":
        if not isinstance(params, dict) or set(params) != {"facet", "keyword", "offset"}:
            raise BridgeRequestError("invalid facet parameters")
        facet, keyword, offset = params["facet"], params["keyword"], params["offset"]
        if (
            not isinstance(facet, str)
            or facet not in _FACET_SOURCES
            or not isinstance(keyword, str)
            or len(keyword) > 200
            or "\0" in keyword
            or type(offset) is not int
            or not 0 <= offset <= 2**53 - 1 - _FACET_PAGE_SIZE
        ):
            raise BridgeRequestError("invalid facet parameters")
        return _facet_page(connection, facet, keyword.strip(), offset)
    if method == "gallery.list":
        if not isinstance(params, dict):
            raise BridgeRequestError("params must be an object")
        unknown = set(params) - {
            "page_size",
            "after",
            "capture_period",
            "favorites_only",
            "root_id",
            "folder_path",
            "album_id",
            "include_roots",
            "include_facets",
            "keyword",
            "tag_id",
            "rating",
            "media_type",
            "camera",
            "lens",
        }
        if unknown:
            raise BridgeRequestError("unsupported gallery parameters")
        page_size = params.get("page_size", 24)
        if isinstance(page_size, bool) or not isinstance(page_size, int):
            raise BridgeRequestError("page_size must be an integer")
        if not 1 <= page_size <= MAX_PAGE_SIZE:
            raise BridgeRequestError("page_size must be between 1 and 50")
        if type(params.get("favorites_only", False)) is not bool:
            raise BridgeRequestError("favorites_only must be boolean")
        after = params.get("after")
        if after is not None and not isinstance(after, str):
            raise BridgeRequestError("after must be text or null")
        if type(params.get("include_roots", False)) is not bool:
            raise BridgeRequestError("include_roots must be boolean")
        root_id = params.get("root_id")
        queries = GalleryQueries(connection)
        page = asdict(
            queries.list_assets(
                GalleryQuery(
                    page_size=page_size,
                    after=after,
                    capture_period=params.get("capture_period"),
                    favorites_only=params.get("favorites_only", False),
                    root_id=root_id,
                    folder_path=params.get("folder_path"),
                    album_id=params.get("album_id"),
                    newest_first=root_id is not None,
                    keyword=params.get("keyword"),
                    tag_id=params.get("tag_id"),
                    rating=params.get("rating"),
                    media_type=params.get("media_type"),
                    camera=params.get("camera"),
                    lens=params.get("lens"),
                )
            )
        )
        if root_id is not None and params.get("folder_path") is not None and after is None:
            page["subfolders"] = queries.list_subfolders(root_id, params["folder_path"])
        if params.get("include_roots"):
            page["roots"] = [
                {"id": row[0], "name": row[1]}
                for row in connection.execute(
                    "SELECT id, display_name FROM library_root ORDER BY display_name, id LIMIT 2000"
                )
            ]
        if type(params.get("include_facets", False)) is not bool:
            raise BridgeRequestError("include_facets must be boolean")
        if params.get("include_facets"):
            facets = {key: _facet_page(connection, key) for key in _FACET_SOURCES}
            page["facets"] = {
                key: result["options"]
                if key == "tags"
                else [item["id"] for item in result["options"]]
                for key, result in facets.items()
            }
            page["facets"]["more"] = [
                key for key, result in facets.items() if result["next_offset"] is not None
            ]
        return page
    if method == "shutdown":
        return {"accepted": True}
    raise BridgeRequestError("unsupported method")


def serve(
    connection: sqlite3.Connection | None,
    token: str,
    source: TextIO = sys.stdin,
    sink: TextIO = sys.stdout,
    *,
    demo: bool = False,
    libraries: object = None,
    lines=None,
) -> int:
    from .duplicates import DuplicatePresentation, synthetic_groups

    duplicates = DuplicatePresentation(*synthetic_groups(connection)) if demo else None
    _write(sink, {"event": "ready", "protocol": 1})
    incoming = (
        iter(lambda: source.readline(MAX_MESSAGE_BYTES + 1), "") if lines is None else iter(lines)
    )
    for raw_line in incoming:
        if len(raw_line.encode("utf-8")) > MAX_MESSAGE_BYTES:
            while not raw_line.endswith("\n"):
                raw_line = next(incoming, "")
                if not raw_line:
                    break
            _write(sink, {"id": None, "ok": False, "error": {"code": "message_too_large"}})
            continue
        request_id: object = None
        try:
            request = json.loads(raw_line, object_pairs_hook=_unique_object)
            if not isinstance(request, dict):
                raise BridgeRequestError("request must be an object")
            if set(request) - {"id", "token", "method", "params"}:
                raise BridgeRequestError("unsupported envelope keys")
            _check_depth(request)
            request_id = request.get("id")
            if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
                raise BridgeRequestError("id must be non-empty text")
            if request.get("token") != token:
                raise BridgeRequestError("authentication failed")
            method = request.get("method")
            if not isinstance(method, str):
                raise BridgeRequestError("method must be text")
            if method == "shutdown":
                if request.get("params", {}) != {}:
                    raise BridgeRequestError("shutdown has no parameters")
                if libraries is not None and not libraries.shutdown():
                    raise LibraryError("busy")
                result = {"accepted": True}
            elif libraries is not None:
                result = libraries.request(method, request.get("params", {}))
            else:
                result = _dispatch(
                    connection, method, request.get("params", {}), demo=demo, duplicates=duplicates
                )
            _write(sink, {"id": request_id, "ok": True, "result": result})
            if method == "shutdown":
                return 0
        except (BridgeRequestError, json.JSONDecodeError, RecursionError):
            _write(
                sink,
                {
                    "id": request_id,
                    "ok": False,
                    "error": {"code": "invalid_request"},
                },
            )
        except LibraryError as error:
            _write(sink, {"id": request_id, "ok": False, "error": {"code": error.code}})
        except AssetNotFoundError:
            _write(sink, {"id": request_id, "ok": False, "error": {"code": "not_found"}})
        except sqlite3.OperationalError as error:
            code = (
                "temporarily_unavailable"
                if getattr(error, "sqlite_errorcode", None)
                in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
                else "backend_failure"
            )
            _write(sink, {"id": request_id, "ok": False, "error": {"code": code}})
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


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise BridgeRequestError("duplicate keys")
        result[key] = value
    return result


def _check_depth(value: object, depth: int = 0) -> None:
    if depth > 12:
        raise BridgeRequestError("excessive depth")
    if isinstance(value, dict):
        for child in value.values():
            _check_depth(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _check_depth(child, depth + 1)


def _write(sink: TextIO, payload: object) -> None:
    line = json.dumps(payload, default=_json_default, separators=(",", ":")) + "\n"
    if len(line.encode("utf-8")) > 256 * 1024:
        request_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(request_id, str) or len(request_id) > 128:
            request_id = None
        line = (
            json.dumps({"id": request_id, "ok": False, "error": {"code": "response_too_large"}})
            + "\n"
        )
    sink.write(line)
    sink.flush()


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--catalog", type=Path)
    mode.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("PLAYMEMORIES_BRIDGE_TOKEN", "")
    if len(token) < 32:
        print("invalid bridge credentials", file=sys.stderr)
        return 2
    if not args.demo and args.catalog is None:
        from .libraries import LibraryDispatcher

        try:
            protected = json.loads(os.environ.get("PLAYMEMORIES_DESKTOP_PROTECTED_PATHS", "[]"))
            if (
                not isinstance(protected, list)
                or len(protected) > 16
                or any(not isinstance(p, str) or len(p) > 4096 for p in protected)
            ):
                raise ValueError
        except (ValueError, TypeError):
            return 3
        libraries = LibraryDispatcher(
            ingestion_enabled=os.environ.get("PLAYMEMORIES_DESKTOP_INGESTION_LAB") == "1",
            protected_paths=tuple(Path(p) for p in protected),
            index_state=os.environ.get("PLAYMEMORIES_DESKTOP_INDEX_STATE"),
        )
        try:
            if sys.platform != "linux":
                return serve(None, token, libraries=libraries)
            from .transport import PipePump, TransportFailure

            pump = PipePump(sys.stdin, sys.stdout)
            try:
                result = serve(
                    None, token, sink=pump, libraries=libraries, lines=pump.lines(libraries.tick)
                )
                libraries.shutdown()
                pump.drain()
                return result
            except TransportFailure:
                return 4
            finally:
                # Never release the process while a preparation child still needs reap.
                import time

                while not libraries.shutdown(timeout=0):
                    libraries.tick()
                    time.sleep(0.01)
                pump.close()
        finally:
            libraries.close()
    external = None
    try:
        if args.demo:
            from .demo import open_demo_catalog

            connection = open_demo_catalog()
        else:
            external = LibrarySession.open(args.catalog)
            connection = external.query_connection
    except Exception:
        print("catalog could not be opened", file=sys.stderr)
        return 3
    try:
        return serve(connection, token, demo=args.demo)
    finally:
        if external is not None:
            external.close()
        else:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
