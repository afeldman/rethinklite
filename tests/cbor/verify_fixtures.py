#!/usr/bin/env python3
"""Canonical-encoding verifier for RethinkLite golden CBOR fixtures.

Dependency-free, hand-written CBOR reader. It does not share code with any
encoder, so it is an independent check of the byte contract in
docs/cbor-protocol.md and docs/data-model.md.

Checks per fixture file (a CBOR Sequence: 1..n items, no trailing bytes):

  C1  no indefinite-length items (additional information 31)
  C2  shortest-form arguments for integers, lengths and tags (RFC 8949 §4.2.1)
  C3  shortest-form floats: f32 only if not representable as f16,
      f64 only if not representable as f32
  C4  map keys in length-first core deterministic order (RFC 8949 §4.2.3):
      shorter encoded key first, then bytewise; no duplicate keys
  C5  well-formed UTF-8 text strings
  C6  value-model policy: no NaN/Infinity, no undefined, no unassigned simple
      values (RethinkLite rejects them, so a fixture containing one is wrong)

Usage:  python3 verify_fixtures.py [directory]
Exit:   0 = all fixtures canonical, 1 = at least one violation.
"""

from __future__ import annotations

import hashlib
import struct
import sys
from pathlib import Path

UINT_MIN_WIDTH = {0: 0, 1: 1, 2: 2, 4: 4, 8: 8}
ARG_WIDTH_BY_AI = {24: 1, 25: 2, 26: 4, 27: 8}


class Node:
    __slots__ = ("major", "value", "start", "end", "tag", "keys")

    def __init__(self, major, value, start, end):
        self.major = major
        self.value = value
        self.start = start
        self.end = end
        self.tag = None      # tag number, for major 6
        self.keys = None     # list of (key_span, key_node, value_node), for major 5


class Violation(Exception):
    pass


def _min_width(value: int) -> int:
    if value < 24:
        return 0
    if value < 1 << 8:
        return 1
    if value < 1 << 16:
        return 2
    if value < 1 << 32:
        return 4
    return 8


def _check_arg(width: int, value: int, where: str) -> None:
    expected = _min_width(value)
    if width != expected:
        raise Violation(
            f"C2 {where}: argument {value} encoded with {width} byte(s), "
            f"canonical form needs {expected}"
        )


def _fits_f16(value: float) -> bool:
    try:
        return struct.unpack(">e", struct.pack(">e", value))[0] == value
    except (OverflowError, struct.error):
        return False


def _fits_f32(value: float) -> bool:
    try:
        return struct.unpack(">f", struct.pack(">f", value))[0] == value
    except (OverflowError, struct.error):
        return False


def parse(buf: bytes, i: int, depth: int = 0) -> tuple[Node, int]:
    if depth > 128:
        raise Violation("nesting deeper than the verifier's own bound")
    if i >= len(buf):
        raise Violation("truncated item")
    start = i
    ib = buf[i]
    major, ai = ib >> 5, ib & 0x1F
    i += 1

    if ai == 31:
        raise Violation(f"C1 offset {start}: indefinite-length item")

    if major == 7:
        return _parse_major7(buf, ai, i, start)

    if major in (0, 1, 2, 3, 4, 5, 6):
        if ai < 24:
            arg, width = ai, 0
        elif ai in ARG_WIDTH_BY_AI:
            width = ARG_WIDTH_BY_AI[ai]
            if i + width > len(buf):
                raise Violation(f"offset {start}: truncated argument")
            arg = int.from_bytes(buf[i : i + width], "big")
            i += width
        else:
            raise Violation(f"offset {start}: reserved additional information {ai}")

    if major == 0:
        _check_arg(width, arg, f"offset {start} (uint)")
        return Node(major, arg, start, i), i

    if major == 1:
        _check_arg(width, arg, f"offset {start} (nint)")
        return Node(major, -1 - arg, start, i), i

    if major == 2:
        _check_arg(width, arg, f"offset {start} (byte string length)")
        if i + arg > len(buf):
            raise Violation(f"offset {start}: truncated byte string")
        return Node(major, buf[i : i + arg], start, i + arg), i + arg

    if major == 3:
        _check_arg(width, arg, f"offset {start} (text string length)")
        if i + arg > len(buf):
            raise Violation(f"offset {start}: truncated text string")
        raw = buf[i : i + arg]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise Violation(f"C5 offset {start}: invalid UTF-8 ({exc})") from exc
        return Node(major, text, start, i + arg), i + arg

    if major == 4:
        _check_arg(width, arg, f"offset {start} (array length)")
        items = []
        for _ in range(arg):
            item, i = parse(buf, i, depth + 1)
            items.append(item)
        return Node(major, items, start, i), i

    if major == 5:
        _check_arg(width, arg, f"offset {start} (map length)")
        keys, pairs = [], []
        for _ in range(arg):
            key, i = parse(buf, i, depth + 1)
            value, i = parse(buf, i, depth + 1)
            keys.append(key)
            pairs.append((key, value))
        _check_key_order(buf, keys, start)
        node = Node(major, pairs, start, i)
        node.keys = keys
        return node, i

    if major == 6:
        _check_arg(width, arg, f"offset {start} (tag)")
        inner, i = parse(buf, i, depth + 1)
        node = Node(major, inner, start, i)
        node.tag = arg
        return node, i

    # major 7 is handled by _parse_major7 before the argument block above
    raise Violation(f"internal: unhandled major type {major}")


def _parse_major7(buf: bytes, ai: int, i: int, start: int) -> tuple[Node, int]:
    if ai == 20:
        return Node(7, False, start, i), i
    if ai == 21:
        return Node(7, True, start, i), i
    if ai == 22:
        return Node(7, None, start, i), i
    if ai == 23:
        raise Violation(f"C6 offset {start}: undefined (0xf7) is not a RethinkLite value")
    if ai == 24:
        raise Violation(
            f"C6 offset {start}: simple value 24..255 is not a RethinkLite value"
        )
    if ai in (0, 25, 26, 27):
        if ai == 0:
            raise Violation(
                f"C6 offset {start}: simple value {ai} is not a RethinkLite value"
            )
        width = {25: 2, 26: 4, 27: 8}[ai]
        code = {25: ">e", 26: ">f", 27: ">d"}[ai]
        if i + width > len(buf):
            raise Violation(f"offset {start}: truncated float")
        value = struct.unpack(code, buf[i : i + width])[0]
        _check_float_policy(value, start)
        if ai == 26 and _fits_f16(value):
            raise Violation(f"C3 offset {start}: f32 {value!r} is representable as f16")
        if ai == 27 and _fits_f32(value):
            raise Violation(f"C3 offset {start}: f64 {value!r} is representable as f32")
        return Node(7, value, start, i + width), i + width
    raise Violation(f"C6 offset {start}: simple value with additional information {ai}")


def _check_float_policy(value: float, start: int) -> None:
    if value != value:
        raise Violation(f"C6 offset {start}: NaN is not a RethinkLite value")
    if value in (float("inf"), float("-inf")):
        raise Violation(f"C6 offset {start}: Infinity is not a RethinkLite value")


def _check_key_order(buf: bytes, keys: list[Node], map_start: int) -> None:
    encoded = [buf[k.start : k.end] for k in keys]
    seen = {}
    for raw in encoded:
        if raw in seen:
            raise Violation(f"C4 map at offset {map_start}: duplicate key {raw.hex()}")
        seen[raw] = True
    for previous, current in zip(encoded, encoded[1:]):
        if (len(previous), previous) >= (len(current), current):
            raise Violation(
                f"C4 map at offset {map_start}: keys out of length-first order "
                f"{previous.hex()} then {current.hex()}"
            )


def verify_file(path: Path) -> tuple[int, str]:
    buf = path.read_bytes()
    items, i, count = [], 0, 0
    while i < len(buf):
        node, i = parse(buf, i)
        items.append(node)
        count += 1
    if count == 0:
        raise Violation("empty file: a fixture is a CBOR Sequence with >= 1 item")
    return count, hashlib.sha256(buf).hexdigest()


def main() -> int:
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    fixtures = sorted(p for p in directory.glob("*.cbor"))
    if not fixtures:
        print(f"no .cbor fixtures in {directory}")
        return 1
    failures = 0
    for path in fixtures:
        try:
            count, digest = verify_file(path)
        except Violation as exc:
            failures += 1
            print(f"FAIL {path.name}: {exc}")
        else:
            size = path.stat().st_size
            print(f"ok   {path.name:28} items={count} bytes={size:5} sha256={digest}")
    print(f"\n{len(fixtures) - failures}/{len(fixtures)} fixtures canonical")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
