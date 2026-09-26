"""Pure-Python encoders for WebAssembly LEB128 integers."""

from operator import index


def _as_integer(value):
    try:
        return index(value)
    except TypeError as exc:
        raise TypeError("LEB128 values must be integers") from exc


def encode_unsigned(value):
    """Encode a non-negative integer as unsigned LEB128."""
    value = _as_integer(value)
    if value < 0:
        raise ValueError("unsigned LEB128 cannot encode a negative value")

    encoded = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            byte |= 0x80
        encoded.append(byte)
        if not value:
            return bytes(encoded)


def encode_signed(value):
    """Encode an integer as signed LEB128 using the shortest representation."""
    value = _as_integer(value)
    encoded = bytearray()

    while True:
        byte = value & 0x7F
        value >>= 7
        done = (value == 0 and byte & 0x40 == 0) or (
            value == -1 and byte & 0x40 != 0
        )
        if not done:
            byte |= 0x80
        encoded.append(byte)
        if done:
            return bytes(encoded)


class LEB128U:
    """Compatibility wrapper for unsigned LEB128 encoding."""

    encode = staticmethod(encode_unsigned)


class LEB128S:
    """Compatibility wrapper for signed LEB128 encoding."""

    encode = staticmethod(encode_signed)
