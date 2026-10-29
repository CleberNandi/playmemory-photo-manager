"""In-memory demo PNG contract and isolation."""

import base64
import builtins
import struct
import zlib

import pytest

from playmemories_photo_manager.desktop.bridge import BridgeRequestError, _dispatch
from playmemories_photo_manager.desktop.demo import open_demo_catalog, synthetic_thumbnail


def test_all_demo_images_are_bounded_deterministic_pngs_without_media_reads(monkeypatch):
    connection = open_demo_catalog()

    def forbidden(*args, **kwargs):
        pytest.fail("attempted filesystem read")

    monkeypatch.setattr(builtins, "open", forbidden)
    images = set()
    try:
        for asset_id, kind in connection.execute("SELECT id, kind FROM asset"):
            params = {"asset_id": asset_id}
            assert _dispatch(connection, "thumbnail.get", params) is None
            result = _dispatch(connection, "thumbnail.get", params, demo=True)
            assert result["media_type"] == "image/png"
            assert (result["width"], result["height"]) == (256, 160)
            assert len(result["base64"]) <= 16384
            image = base64.b64decode(result["base64"], validate=True)
            assert image == synthetic_thumbnail(asset_id, kind)
            assert len(image) <= 12288
            assert image[:8] == b"\x89PNG\r\n\x1a\n"
            assert struct.unpack("!II", image[16:24]) == (256, 160)
            length = struct.unpack("!I", image[33:37])[0]
            assert len(zlib.decompress(image[41 : 41 + length])) == 160 * (256 * 3 + 1)
            images.add(image)
        assert len(images) == 73
        assert (
            _dispatch(
                connection,
                "thumbnail.get",
                {"asset_id": "00000000-0000-4000-8000-000000000000"},
                demo=True,
            )
            is None
        )
    finally:
        connection.close()


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"asset_id": "../photo.jpg"},
        {"asset_id": None},
        {"asset_id": 1},
        {"asset_id": "A" * 36},
        {"asset_id": "00000000-0000-4000-8000-000000000001", "path": "/private"},
    ],
)
def test_thumbnail_rejects_arbitrary_inputs(params):
    connection = open_demo_catalog()
    try:
        with pytest.raises(BridgeRequestError):
            _dispatch(connection, "thumbnail.get", params, demo=True)
    finally:
        connection.close()


def test_renderer_cannot_enable_demo_through_request():
    import io
    import json

    from playmemories_photo_manager.desktop.bridge import serve

    connection = open_demo_catalog()
    try:
        asset_id = connection.execute("SELECT id FROM asset LIMIT 1").fetchone()[0]
        source = io.StringIO(
            json.dumps(
                {
                    "id": "one",
                    "token": "secret",
                    "method": "thumbnail.get",
                    "params": {"asset_id": asset_id},
                }
            )
            + "\n"
        )
        sink = io.StringIO()
        serve(connection, "secret", source, sink)
        assert json.loads(sink.getvalue().splitlines()[1])["result"] is None
        assert synthetic_thumbnail(asset_id, "photo") != synthetic_thumbnail(asset_id, "video")
    finally:
        connection.close()
