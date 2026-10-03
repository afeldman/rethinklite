#!/usr/bin/env python3
"""Self-test for verify_fixtures.py: the checker must be able to fail.

A canonicality checker that has never rejected anything is not evidence. Each
case below is a deliberately non-canonical or forbidden encoding and must be
reported with the expected rule identifier (C1..C6).

Usage:  python3 tests/cbor/selftest_verifier.py
Exit:   0 = every case rejected with the expected rule, 1 = the checker missed one.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from verify_fixtures import Violation, verify_file  # noqa: E402

CASES: list[tuple[str, bytes, str]] = [
    ("C1 indefinite-length array", b"\x9f\x01\x02\xff", "C1"),
    ("C1 indefinite-length map", b"\xbf\x61a\x01\xff", "C1"),
    ("C1 indefinite-length text", b"\x7f\x61a\xff", "C1"),
    ("C2 non-minimal uint (1 as uint8)", b"\x18\x01", "C2"),
    ("C2 non-minimal uint (23 as uint8)", b"\x18\x17", "C2"),
    ("C2 non-minimal text length", b"\x78\x01a", "C2"),
    ("C2 non-minimal tag", b"\xd8\x01\x01", "C2"),
    ("C3 f64 that fits in f32", b"\xfb\x3f\xf8\x00\x00\x00\x00\x00\x00", "C3"),
    ("C3 f32 that fits in f16", b"\xfa\x3f\xc0\x00\x00", "C3"),
    ("C4 length-first key order violated", b"\xa2\x63aaa\x01\x61b\x02", "C4"),
    ("C4 duplicate key", b"\xa2\x61a\x01\x61a\x02", "C4"),
    ("C5 invalid UTF-8 in text", b"\x61\xff", "C5"),
    ("C6 undefined value", b"\xf7", "C6"),
    ("C6 NaN (f16)", b"\xf9\x7e\x00", "C6"),
    ("C6 Infinity (f16)", b"\xf9\x7c\x00", "C6"),
    ("truncated item", b"\x9f\x01", "C1"),
]

CANONICAL_CASES: list[tuple[str, bytes]] = [
    ("empty map", b"\xa0"),
    ("small int", b"\x17"),
    ("negative int", b"\x20"),
    ("length-first order (z before aa)", b"\xa2\x61z\x01\x62aa\x02"),
    ("bytewise order within one length", b"\xa2\x62aa\x01\x62bb\x02"),
    ("f16 1.5", b"\xf9\x3e\x00"),
    ("f32 1000000.5", b"\xfa\x49\x74\x24\x08"),
    ("array of 24 items", b"\x98\x18" + b"\x01" * 24),
    ("tag 37 over 16 bytes", b"\xd8\x25\x50" + b"\x00" * 16),
]


def main() -> int:
    failures = 0
    tmp = Path("/tmp/rethinklite-selftest.cbor")

    for name, blob, expected_rule in CASES:
        tmp.write_bytes(blob)
        try:
            verify_file(tmp)
        except Violation as exc:
            if str(exc).startswith(expected_rule):
                print(f"ok   rejected: {name} -> {exc}")
            else:
                failures += 1
                print(f"FAIL {name}: expected rule {expected_rule}, got: {exc}")
        else:
            failures += 1
            print(f"FAIL {name}: not rejected at all")

    for name, blob in CANONICAL_CASES:
        tmp.write_bytes(blob)
        try:
            verify_file(tmp)
        except Violation as exc:
            failures += 1
            print(f"FAIL {name}: canonical input rejected: {exc}")
        else:
            print(f"ok   accepted: {name}")

    tmp.unlink(missing_ok=True)
    total = len(CASES) + len(CANONICAL_CASES)
    print(f"\n{total - failures}/{total} verifier self-test cases correct")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
