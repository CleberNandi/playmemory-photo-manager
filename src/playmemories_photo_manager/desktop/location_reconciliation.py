"""Reconcile registered locations against a completed, anchored folder observation."""

import os
import stat
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import NamedTuple

from ..catalog import Catalog
from ..catalog.models import EntryType, LocationAvailability
from ..catalog.repository import CatalogRepository
from ..catalog_ingestion.media import _Directories, _file_state, _mount_id
from ..catalog_ingestion.root_grants import _HeldRoot
from ..library import LibraryError


class EntryState(NamedTuple):
    kind: int
    link_count: int
    device: int
    inode: int
    byte_size: int
    mtime_ns: int
    ctime_ns: int


def entry_state(info):
    return EntryState(stat.S_IFMT(info.st_mode), info.st_nlink, *_file_state(info))


def _identity(state):
    return f"scanner:{state.device}:{state.inode}"


def _matches(location, state):
    return (
        state.kind == stat.S_IFREG
        and location.filesystem_id == _identity(state)
        and (location.observed_byte_size, location.observed_mtime_ns)
        == (state.byte_size, state.mtime_ns)
    )


def _verified_destination(held, relative, state):
    parents = _Directories()
    try:
        path = PurePosixPath(relative)
        parent = held.fd
        for part in path.parts[:-1]:
            parent = parents.child(parent, part, held.mount)
        fd = os.open(path.name, os.O_PATH | os.O_NOFOLLOW, dir_fd=parent)
        try:
            return (
                _mount_id(fd) == held.mount
                and entry_state(os.fstat(fd)) == state
                and entry_state(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) == state
            )
        finally:
            os.close(fd)
            parents.check()
    finally:
        parents.close()


def reconcile_locations(session, root_id, binding, signature, reobserve):
    """Keep the live location ID and retain the previous observation as missing history."""
    locations = CatalogRepository(session.query_connection).list_root_locations(root_id, 2001, 0)
    if len(locations) > 2000:
        raise LibraryError("resource_limit")
    paths = dict(signature)
    present = LocationAvailability.PRESENT
    missing = LocationAvailability.MISSING
    occupied = {
        location.normalized_relative_path
        for location in locations
        if location.availability != missing
    }
    active_identities = Counter(
        location.filesystem_id for location in locations if location.availability != missing
    )
    missing_paths = Counter(
        location.normalized_relative_path
        for location in locations
        if location.availability == missing
    )
    observed_by_id = defaultdict(list)
    for path, state in signature:
        if state.kind == stat.S_IFREG:
            observed_by_id[_identity(state)].append(path)

    changes = []
    destinations = []
    for location in locations:
        if location.entry_type != EntryType.FILE:
            continue
        old = location.normalized_relative_path
        observed = paths.get(old)
        if location.availability == missing:
            if (
                observed is not None
                and old not in occupied
                and missing_paths[old] == 1
                and not active_identities[location.filesystem_id]
                and _matches(location, observed)
            ):
                changes.append((location, old, present))
                destinations.append(old)
            continue
        if location.availability != present or observed is not None:
            continue
        relative = PurePosixPath(old)
        if (
            relative.is_absolute()
            or not relative.parts
            or ".." in relative.parts
            or str(relative) != old
        ):
            continue
        if any(
            parent.as_posix() in paths and paths[parent.as_posix()].kind != stat.S_IFDIR
            for parent in relative.parents
        ):
            continue  # An obstructed ancestor is not evidence of absence.

        matches = observed_by_id[location.filesystem_id]
        if len(matches) == 1 and active_identities[location.filesystem_id] == 1:
            new = matches[0]
            if (
                new not in occupied
                and paths[new].link_count == 1
                and _matches(location, paths[new])
            ):
                changes.append((location, new, present))
                destinations.append(new)
                continue
        changes.append((location, old, missing))

    if not changes:
        return 0
    held = _HeldRoot(Path(binding[0]))
    try:
        if (str(held.path), held.identity, held.mount) != binding:
            raise LibraryError("root_changed")
        if any(not _verified_destination(held, path, paths[path]) for path in destinations):
            raise LibraryError("root_changed")
        if reobserve() != signature:
            raise LibraryError("root_changed")
        held.check()
        with session.command_connection() as connection:
            Catalog(connection).reconcile_monitored_locations(
                root_id,
                expected_root_path=binding[0],
                expected=locations,
                changes=changes,
                observed_at=datetime.now(UTC).isoformat(),
            )
    finally:
        held.close()
    return len(changes)
