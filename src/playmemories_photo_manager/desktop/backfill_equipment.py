"""One-time, explicit maintenance of camera and lens observations in a catalog."""

import argparse
import os
import stat
import sys
from pathlib import Path

from PIL import Image

from ..catalog_ingestion.capture import extract_capture, persist_equipment
from ..catalog_ingestion.images import MAX_BYTES
from ..catalog_ingestion.media import _file_state
from ..library import LibraryError, LibrarySession
from .media_location import held_location


def backfill_equipment(session):
    counts = {"verificadas": 0, "atualizadas": 0, "indisponiveis": 0}
    binding = session.catalog_binding
    after = ""
    with session.command_connection() as connection:
        while True:
            rows = connection.execute(
                """SELECT a.id FROM asset a
                WHERE a.id > ? AND a.kind='photo' AND a.status='active'
                  AND (SELECT count(DISTINCT m.metadata_key) FROM metadata m
                       WHERE m.asset_id=a.id AND m.namespace='exif'
                         AND m.metadata_key IN ('Model','LensModel')
                         AND m.interpreted_value IS NOT NULL) < 2
                ORDER BY a.id LIMIT 100""",
                (after,),
            ).fetchall()
            if not rows:
                return counts
            after = rows[-1][0]
            for (asset_id,) in rows:
                counts["verificadas"] += 1
                if session.catalog_binding != binding:
                    raise LibraryError("stale_session")
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    try:
                        with held_location(connection, asset_id) as (
                            _,
                            dirs,
                            parent,
                            fd,
                            info,
                            path,
                        ):
                            if not 0 < info.st_size <= MAX_BYTES:
                                counts["indisponiveis"] += 1
                                continue
                            with os.fdopen(fd, "rb", closefd=False) as source:
                                observations = extract_capture(source)
                            linked = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                            if (
                                not stat.S_ISREG(linked.st_mode)
                                or _file_state(info) != _file_state(linked)
                                or _file_state(info) != _file_state(os.fstat(fd))
                            ):
                                raise LibraryError("unsafe_location")
                            dirs.check()
                    except (LibraryError, Image.DecompressionBombError):
                        counts["indisponiveis"] += 1
                        continue
                    counts["atualizadas"] += bool(
                        persist_equipment(connection, asset_id, observations)
                    )


def main():
    parser = argparse.ArgumentParser(description="Preenche câmera e lente de fotos já catalogadas.")
    parser.add_argument(
        "catalogo", type=Path, help="Arquivo SQLite existente. Feche o aplicativo antes."
    )
    args = parser.parse_args()
    try:
        with LibrarySession.open(args.catalogo.expanduser().absolute()) as session:
            counts = backfill_equipment(session)
    except LibraryError as error:
        print(f"Atualização interrompida ({error.code}).", file=sys.stderr)
        return 1
    print(
        f"Fotos verificadas: {counts['verificadas']} · "
        f"Atualizadas: {counts['atualizadas']} · "
        f"Indisponíveis, alteradas ou fora do limite: {counts['indisponiveis']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
