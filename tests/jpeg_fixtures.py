"""Tiny baseline JPEGs encoded from constant synthetic 8x8 blocks, no binary fixtures."""


def segment(marker, payload):
    return bytes([255, marker]) + (len(payload) + 2).to_bytes(2, "big") + payload


def frame(*, count=1, width=8, height=8):
    return segment(
        0xC0,
        bytes([8])
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + bytes([count])
        + b"".join(bytes([i + 1, 0x11, 0]) for i in range(count)),
    )


def tables():
    # Single code of length 1 (code 0): category 0 DC, EOB AC.
    huffman = b"\x01" + bytes(15) + b"\x00"
    return segment(0xDB, b"\x00" + b"\x01" * 64) + segment(
        0xC4, b"\x00" + huffman + b"\x10" + huffman
    )


def sos(count=1):
    return segment(
        0xDA, bytes([count]) + b"".join(bytes([i + 1, 0]) for i in range(count)) + b"\x00\x3f\x00"
    )


def jpeg(count=1, *, width=8, height=8, entropy=None, extra=b""):
    if entropy is None:
        # Each block uses zero DC difference + EOB; pad with all-1 bits.
        entropy = b"\x3f" if count == 1 else b"\x03"
    return (
        b"\xff\xd8"
        + extra
        + tables()
        + frame(count=count, width=width, height=height)
        + sos(count)
        + entropy
        + b"\xff\xd9"
    )
