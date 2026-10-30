import io
import shutil
import subprocess

import pytest
from jpeg_fixtures import frame, jpeg, segment, sos, tables

from playmemories_photo_manager.catalog_ingestion.jpeg import inspect_jpeg


def inspect(data):
    return inspect_jpeg(io.BytesIO(data), len(data), checkpoint=lambda: None)


@pytest.mark.parametrize("count", [1, 3])
def test_valid_synthetic_baseline_and_independent_decoder(tmp_path, count):
    data = jpeg(count)
    result = inspect(data)
    assert result.reason == "eligible_jpeg"
    assert result.detected_format == "jpeg"
    assert (result.width, result.height) == (8, 8)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("independent decoder ffmpeg unavailable; structural assertion ran")
    path = tmp_path / "synthetic.jpg"
    path.write_bytes(data)
    pixel_format = "gray" if count == 1 else "rgb24"
    decoded = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            pixel_format,
            "-",
        ],
        capture_output=True,
        check=True,
        timeout=10,
    )
    assert len(decoded.stdout) == 64 * count
    assert set(decoded.stdout) == {128}


@pytest.mark.parametrize(
    "data,reason",
    [
        (b"", "empty_file"),
        (b"text", "invalid_jpeg_signature"),
        (b"\x89PNG\r\n\x1a\n", "invalid_jpeg_signature"),
        (b"\xff\xd8", "truncated_jpeg"),
        (b"\xff\xd8\xff\xd9", "malformed_jpeg_segment"),
        (b"\xff\xd8\xff\xfe\x00\x00", "malformed_jpeg_segment"),
        (b"\xff\xd8\xff\xfe\x00\x01", "malformed_jpeg_segment"),
        (b"\xff\xd8\xff\xfe\x00\x20short", "truncated_jpeg"),
        (jpeg()[:-2], "truncated_jpeg"),
        (jpeg()[:-1], "truncated_jpeg"),
        (jpeg(entropy=b"\xff\x00")[:-2], "truncated_jpeg"),
        (jpeg() + b"trailer", "malformed_jpeg_segment"),
        (jpeg() + jpeg(), "malformed_jpeg_segment"),
        (jpeg(entropy=b""), "malformed_jpeg_segment"),
        (jpeg(entropy=b"\xff\xd0"), "unsupported_jpeg_frame"),
        (jpeg(extra=segment(0xDD, b"\x00\x01")), "unsupported_jpeg_frame"),
        (jpeg().replace(b"\xff\xc0", b"\xff\xc2"), "unsupported_jpeg_frame"),
        (jpeg(count=4), "unsupported_jpeg_frame"),
        (jpeg(extra=frame()), "malformed_jpeg_segment"),
        (jpeg(entropy=b"\x00" + sos()), "unsupported_jpeg_frame"),
        (jpeg(extra=b"\xff\x01"), "malformed_jpeg_segment"),
        (jpeg(extra=b"\xff\x00"), "malformed_jpeg_segment"),
        (jpeg(extra=segment(0xC8, b"")), "malformed_jpeg_segment"),
    ],
)
def test_malformed_truncated_or_outside_profile(data, reason):
    assert inspect(data).reason == reason


@pytest.mark.parametrize("width,height", [(0, 8), (8, 0), (20000, 8), (7000, 7000)])
def test_dimension_limits(width, height):
    assert inspect(jpeg(width=width, height=height)).reason == "dimension_limit_exceeded"


@pytest.mark.parametrize("width,height", [(16384, 1), (1, 16384), (8000, 5000)])
def test_dimensions_at_boundary_do_not_assert_mcu_decodability(width, height):
    assert inspect(jpeg(width=width, height=height)).reason == "eligible_jpeg"


def test_entropy_corruption_can_pass_the_declared_structural_profile():
    # No MCU/bitstream decoding: this acceptance is intentional and documented.
    assert inspect(jpeg(entropy=b"arbitrary entropy")).reason == "eligible_jpeg"


def test_app_payload_is_opaque_and_stuffed_bytes_are_not_markers():
    assert (
        inspect(jpeg(extra=segment(0xE1, b"\xff\xd9"), entropy=b"\xff\x00")).reason
        == "eligible_jpeg"
    )
    assert inspect(b"\xff\xd8" + segment(0xE1, b"\xff\xd9")).reason == "truncated_jpeg"


def test_segment_count_and_fill_boundaries():
    # tables emits two segments, plus SOF/SOS = four; COM adds 252 to reach 256.
    assert inspect(jpeg(extra=segment(0xFE, b"") * 252)).reason == "eligible_jpeg"
    assert inspect(jpeg(extra=segment(0xFE, b"") * 253)).reason == "segment_limit_exceeded"
    assert inspect(jpeg().replace(b"\xff\xc0", b"\xff" * 64 + b"\xc0")).reason == "eligible_jpeg"
    assert (
        inspect(jpeg().replace(b"\xff\xc0", b"\xff" * 65 + b"\xc0")).reason
        == "segment_limit_exceeded"
    )


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\x10" + bytes([1]) * 128,
        b"\x00" + bytes(64),
        b"\x00" + bytes([1]) * 63,
        b"\x04" + bytes([1]) * 64,
    ],
)
def test_invalid_dqt(payload):
    assert (
        inspect(
            jpeg().replace(segment(0xDB, b"\x00" + b"\x01" * 64), segment(0xDB, payload))
        ).reason
        == "malformed_jpeg_segment"
    )


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\x00",
        b"\x00" + bytes(16),
        b"\x00\x02" + bytes(15) + b"\x00\x01",  # Complete tree uses all-1 code.
        b"\x00\x03" + bytes(15) + b"\x00\x01\x02",  # Over-subscribed.
        b"\x00\x01" + bytes(15) + b"\x0c",  # Invalid DC category.
        b"\x10\x01" + bytes(15) + b"\x0b",  # Invalid AC size.
        b"\x00\x00\x02" + bytes(14) + b"\x00\x00",  # Duplicate symbols.
    ],
)
def test_invalid_dht(payload):
    assert inspect(b"\xff\xd8" + segment(0xC4, payload)).reason == "malformed_jpeg_segment"


def test_absent_or_duplicate_tables_and_bad_sos():
    assert (
        inspect(b"\xff\xd8" + frame() + sos() + b"\x3f\xff\xd9").reason == "malformed_jpeg_segment"
    )
    assert inspect(jpeg(extra=tables())).reason == "unsupported_jpeg_frame"
    assert (
        inspect(jpeg().replace(sos(), segment(0xDA, b"\x01\x01\x00\x01\x3f\x00"))).reason
        == "malformed_jpeg_segment"
    )


def test_file_byte_limit_without_reading():
    class Unreadable:
        def read(self, _size):
            pytest.fail("oversize file must not be read")

    assert (
        inspect_jpeg(Unreadable(), 67108865, checkpoint=lambda: None).reason
        == "byte_limit_exceeded"
    )


def test_chunked_source_and_checkpoint_exception():
    class Chunked(io.BytesIO):
        def read(self, size):
            assert 0 < size <= 65536
            return super().read(min(size, 1))

    data = jpeg(extra=segment(0xE0, b"opaque"))
    assert inspect_jpeg(Chunked(data), len(data), checkpoint=lambda: None).reason == "eligible_jpeg"

    def cancelled():
        raise InterruptedError("synthetic cancellation")

    with pytest.raises(InterruptedError):
        inspect_jpeg(io.BytesIO(data), len(data), checkpoint=cancelled)


def test_header_bytes_limit_and_limit_plus_one():
    def padding(total):
        parts = []
        while total:
            size = min(total, 65537)
            if 0 < total - size < 4:
                size -= 4
            parts.append(segment(0xFE, bytes(size - 4)))
            total -= size
        return b"".join(parts)

    budget = 4 * 1024 * 1024 - len(tables() + frame() + sos())
    assert inspect(jpeg(extra=padding(budget))).reason == "eligible_jpeg"
    assert inspect(jpeg(extra=padding(budget + 1))).reason == "segment_limit_exceeded"


def test_byte_limit_exactly_64_mib_admits_a_read():
    class ProbeReached(Exception):
        pass

    class Probe:
        def read(self, size):
            assert size == 65536
            raise ProbeReached

    with pytest.raises(ProbeReached):
        inspect_jpeg(Probe(), 67108864, checkpoint=lambda: None)


@pytest.mark.parametrize(
    "data",
    [
        jpeg().replace(frame(), frame().replace(b"\x01\x11\x00", b"\x01\x00\x00")),
        jpeg().replace(frame(), frame().replace(b"\x01\x11\x00", b"\x01\x51\x00")),
        jpeg().replace(frame(), frame().replace(b"\x01\x11\x00", b"\x01\x11\x04")),
        jpeg(3).replace(b"\x03\x11\x00", b"\x02\x11\x00"),
        jpeg().replace(sos(), sos().replace(b"\x01\x01\x00", b"\x01\x02\x00")),
        jpeg().replace(sos(), sos().replace(b"\x01\x01\x00", b"\x01\x01\x11")),
        jpeg().replace(sos(), sos()[:-1]),
    ],
)
def test_invalid_components_sampling_or_table_selection(data):
    assert inspect(data).reason != "eligible_jpeg"
