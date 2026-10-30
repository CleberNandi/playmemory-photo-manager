"""jpeg_structural_v1: a bounded baseline envelope check, never a pixel decoder.

Profile: docs/desktop-mvp-d04-02a.md, based on ITU-T T.81 Annexes B/C.
No filesystem selection or decoding capability belongs in this parser.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import BinaryIO

MAX_JPEG_BYTES = 64 * 1024 * 1024
MAX_HEADER_BYTES = 4 * 1024 * 1024
MAX_SEGMENTS = 256
PROFILE = "jpeg_structural_v1"


@dataclass(frozen=True, slots=True)
class JPEGInspection:
    reason: str
    detected_format: str | None
    width: int | None = None
    height: int | None = None


class _Rejected(Exception):
    def __init__(self, reason):
        self.reason = reason


class _Reader:
    def __init__(self, source: BinaryIO, size: int, checkpoint: Callable[[], None]):
        self.source = source
        self.size = size
        self.checkpoint = checkpoint
        self.position = 0
        self.buffer = b""
        self.index = 0

    def byte(self) -> int:
        if self.index == len(self.buffer):
            self.checkpoint()
            remaining = self.size - self.position
            if remaining <= 0:
                raise _Rejected("truncated_jpeg")
            self.buffer = self.source.read(min(65536, remaining))
            self.index = 0
            if not self.buffer:
                raise _Rejected("truncated_jpeg")
        value = self.buffer[self.index]
        self.index += 1
        self.position += 1
        return value

    def take(self, count: int) -> bytes:
        if count > self.size - self.position:
            raise _Rejected("truncated_jpeg")
        return bytes(self.byte() for _ in range(count))

    def marker(self) -> tuple[int, int]:
        if self.byte() != 0xFF:
            raise _Rejected("malformed_jpeg_segment")
        fills = 1
        marker = self.byte()
        while marker == 0xFF:
            fills += 1
            if fills > 64:
                raise _Rejected("segment_limit_exceeded")
            marker = self.byte()
        if marker == 0:
            raise _Rejected("malformed_jpeg_segment")
        return marker, fills


def _malformed(condition: bool) -> None:
    if condition:
        raise _Rejected("malformed_jpeg_segment")


def _quantization(payload: bytes, tables: set[int]) -> None:
    _malformed(not payload)
    position = 0
    while position < len(payload):
        selector = payload[position]
        _malformed(selector >> 4 != 0 or selector & 15 > 3)
        identifier = selector & 15
        if identifier in tables:
            raise _Rejected("unsupported_jpeg_frame")
        _malformed(position + 65 > len(payload) or 0 in payload[position + 1 : position + 65])
        tables.add(identifier)
        position += 65


def _huffman(payload: bytes, tables: set[tuple[int, int]]) -> None:
    _malformed(not payload)
    position = 0
    while position < len(payload):
        _malformed(position + 17 > len(payload))
        selector = payload[position]
        table_class, identifier = selector >> 4, selector & 15
        _malformed(table_class not in (0, 1) or identifier not in (0, 1))
        if (table_class, identifier) in tables:
            raise _Rejected("unsupported_jpeg_frame")
        counts = payload[position + 1 : position + 17]
        count = sum(counts)
        _malformed(not 1 <= count <= 256 or position + 17 + count > len(payload))
        code = 0
        for bits, amount in enumerate(counts, 1):
            # Reserving all-1 also excludes an over-subscribed canonical tree.
            _malformed(amount > 0 and code + amount >= 1 << bits)
            code = (code + amount) << 1
        symbols = payload[position + 17 : position + 17 + count]
        _malformed(len(set(symbols)) != count)
        for symbol in symbols:
            _malformed(
                symbol > 11
                if table_class == 0
                else symbol not in (0, 0xF0) and not 1 <= symbol & 15 <= 10
            )
        tables.add((table_class, identifier))
        position += 17 + count


def _frame(payload: bytes) -> tuple[int, int, tuple[tuple[int, int], ...]]:
    _malformed(len(payload) < 6)
    precision, height, width, count = (
        payload[0],
        int.from_bytes(payload[1:3], "big"),
        int.from_bytes(payload[3:5], "big"),
        payload[5],
    )
    if precision != 8 or count not in (1, 3):
        raise _Rejected("unsupported_jpeg_frame")
    _malformed(len(payload) != 6 + 3 * count)
    if not 1 <= width <= 16384 or not 1 <= height <= 16384 or width * height > 40000000:
        raise _Rejected("dimension_limit_exceeded")
    identifiers = set()
    components = []
    sampling_sum = 0
    for index in range(count):
        identifier, sampling, table = payload[6 + 3 * index : 9 + 3 * index]
        horizontal, vertical = sampling >> 4, sampling & 15
        _malformed(
            identifier in identifiers
            or not 1 <= horizontal <= 4
            or not 1 <= vertical <= 4
            or table > 3
        )
        if count == 1 and (horizontal, vertical) != (1, 1):
            raise _Rejected("unsupported_jpeg_frame")
        sampling_sum += horizontal * vertical
        identifiers.add(identifier)
        components.append((identifier, table))
    _malformed(sampling_sum > 10)
    return width, height, tuple(components)


def _scan_header(payload: bytes, frame, quantization, huffman) -> None:
    count = len(frame[2])
    _malformed(len(payload) != 4 + 2 * count or payload[0] != count)
    _malformed(payload[-3:] != b"\x00\x3f\x00")
    for index, (identifier, table) in enumerate(frame[2]):
        selected_id, selectors = payload[1 + 2 * index : 3 + 2 * index]
        dc, ac = selectors >> 4, selectors & 15
        _malformed(
            selected_id != identifier
            or table not in quantization
            or (0, dc) not in huffman
            or (1, ac) not in huffman
        )


def _entropy(reader: _Reader) -> None:
    data_bytes = 0
    while True:
        if reader.byte() != 0xFF:
            data_bytes += 1
            continue
        marker = reader.byte()
        if marker == 0:
            data_bytes += 1
            continue
        fills = 1
        while marker == 0xFF:
            fills += 1
            if fills > 64:
                raise _Rejected("segment_limit_exceeded")
            marker = reader.byte()
        _malformed(marker == 0)  # Fill before a stuffed byte is outside this profile.
        if marker != 0xD9:
            raise _Rejected("unsupported_jpeg_frame")
        _malformed(data_bytes == 0 or reader.position != reader.size)
        return


def inspect_jpeg(source: BinaryIO, size: int, *, checkpoint: Callable[[], None]) -> JPEGInspection:
    """Consume at most size bytes in <=64 KiB reads. Caller owns stable fd/deadlines.

    Checkpoint exceptions propagate (cancellation/deadline are not bad formats).
    Correct entropy coding, MCU counts and full decodability remain not_checked.
    """
    if type(size) is not int or size < 0:
        raise ValueError("size must be a non-negative integer")
    if size == 0:
        return JPEGInspection("empty_file", None)
    if size > MAX_JPEG_BYTES:
        return JPEGInspection("byte_limit_exceeded", None)
    reader = _Reader(source, size, checkpoint)
    detected = None
    frame = None
    quantization = set()
    huffman = set()
    segments = header_bytes = 0
    try:
        if reader.take(2) != b"\xff\xd8":
            return JPEGInspection("invalid_jpeg_signature", None)
        detected = "jpeg"
        while True:
            checkpoint()
            marker, fills = reader.marker()
            if marker in (
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
                0xCC,
                0xDC,
                0xDD,
                0xDE,
                0xDF,
            ):
                raise _Rejected("unsupported_jpeg_frame")
            _malformed(marker not in (0xC0, 0xC4, 0xDB, 0xDA, 0xFE) and not 0xE0 <= marker <= 0xEF)
            length = int.from_bytes(reader.take(2), "big")
            _malformed(length < 2)
            segments += 1
            header_bytes += fills + 1 + length
            if segments > MAX_SEGMENTS or header_bytes > MAX_HEADER_BYTES:
                raise _Rejected("segment_limit_exceeded")
            payload = reader.take(length - 2)
            if marker == 0xDB:
                _quantization(payload, quantization)
            elif marker == 0xC4:
                _huffman(payload, huffman)
            elif marker == 0xC0:
                _malformed(frame is not None)
                frame = _frame(payload)
            elif marker == 0xDA:
                _malformed(frame is None)
                _scan_header(payload, frame, quantization, huffman)
                _entropy(reader)
                checkpoint()
                return JPEGInspection("eligible_jpeg", detected, frame[0], frame[1])
    except _Rejected as error:
        return JPEGInspection(error.reason, detected)
