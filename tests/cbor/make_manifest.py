#!/usr/bin/env python3
"""Write tests/cbor/MANIFEST.md from the fixture bytes on disk.

Dependency-free. Every fixture is first re-checked with verify_fixtures.py, so
the manifest can never describe a file that is not canonical.

Usage:  python3 tests/cbor/make_manifest.py
"""

from __future__ import annotations

import hashlib
import os
import platform
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from verify_fixtures import Violation, verify_file  # noqa: E402

HERE = Path(__file__).parent

INTENT: dict[str, str] = {
    "hello_request.cbor": "session handshake: client name, protocol versions, offered features, required features",
    "hello_response.cbor": "session handshake: server identity, negotiated protocol, database uuid + format, granted features, limits",
    "insert_request.cbor": "collection.insert with an explicit text id and return_document=false",
    "insert_response.cbor": "insert result: id, rev, commit_seq, unchanged flag",
    "get_response.cbor": "get result: metadata plus the stored document, byte-identical to insert_request's document",
    "uuid_id_request.cbor": "document addressed by a UUID id: CBOR tag 37 over 16 bytes",
    "query_request.cbor": "collection.query with a term chain filter > sort desc > limit (length-first canonical map)",
    "query_response.cbor": "query result: documents, returned, scanned, truncated",
    "count_response.cbor": "collection.count result",
    "transaction_request.cbor": "three items in one CBOR Sequence: transaction.begin, collection.update inside the transaction, transaction.commit",
    "watch_request.cbor": "collection.watch with a filter expression, include_initial and overflow policy",
    "change_event.cbor": "one changefeed event with old and new values",
    "error_response.cbor": "error envelope with kind/code/message/retryable/details for revision_conflict",
}


def hex_dump(blob: bytes, width: int = 16) -> str:
    lines = []
    for offset in range(0, len(blob), width):
        chunk = blob[offset : offset + width]
        hexpart = " ".join(f"{byte:02x}" for byte in chunk)
        text = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        lines.append(f"{offset:08x}  {hexpart:<47}  {text}")
    return "\n".join(lines)


def main() -> int:
    fixtures = sorted(HERE.glob("*.cbor"))
    if not fixtures:
        print("no fixtures found")
        return 1

    rows, dumps = [], []
    for path in fixtures:
        try:
            count, digest = verify_file(path)
        except Violation as exc:
            print(f"refusing to write manifest: {path.name} is not canonical: {exc}")
            return 1
        blob = path.read_bytes()
        intent = INTENT.get(path.name, "(add an intent to INTENT in make_manifest.py)")
        rows.append(
            f"| `{path.name}` | {count} | {len(blob)} | `{digest}` | {intent} |"
        )
        dumps.append(f"### `{path.name}`\n\n```\n{hex_dump(blob)}\n```\n")

    cbor2_version = os.environ.get("CBOR2_VERSION", "")
    if not cbor2_version:
        try:
            from importlib.metadata import PackageNotFoundError, version

            try:
                cbor2_version = version("cbor2")
            except PackageNotFoundError:
                cbor2_version = "not installed in this interpreter (see CBOR2_VERSION)"
        except ImportError:  # pragma: no cover
            cbor2_version = "unknown"

    manifest = f"""# Golden CBOR fixtures — manifest

Normative bytes of the RethinkLite protocol v1 contract
(`docs/cbor-protocol.md` §10). Each `.cbor` file is a **CBOR Sequence**
(RFC 8742): one or more self-delimiting items, no length prefix, no header.

Recorded generation: {date.today().isoformat()} ·
python {platform.python_version()} · cbor2 {cbor2_version} ·
{len(fixtures)} fixtures

## Rules

1. **The bytes are the contract.** Never edit a fixture file by hand and never
   rewrite an existing one in place — that changes the meaning of a released
   contract. Add a new fixture instead.
2. **Regeneration must be byte-identical.** `tests/cbor/generate_fixtures.py`
   reproduces every file here; the SHA-256 values below must not change. If a
   regeneration produces different bytes, the encoding rules changed and the
   change must be deliberate, documented here, and reflected in
   `docs/compatibility.md`.
3. **Canonicality is verified independently.** `tests/cbor/verify_fixtures.py`
   is a hand-written CBOR reader that shares no code with the generator and
   checks: no indefinite-length items (C1), shortest-form arguments (C2),
   shortest-form floats (C3), length-first key order and no duplicate keys (C4),
   well-formed UTF-8 (C5), and the value-model policy that forbids
   `undefined`/`NaN`/`Infinity` (C6). Its ability to fail is itself tested by
   `tests/cbor/selftest_verifier.py` (25 cases).
4. A conformance implementation must decode every fixture, re-encode it
   deterministically and obtain **byte-identical** output.

Commands:

```
python3 tests/cbor/verify_fixtures.py tests/cbor     # canonicality
python3 tests/cbor/selftest_verifier.py              # the checker can fail
python3 tests/cbor/make_manifest.py                  # regenerate this file
/tmp/cborvenv/bin/python tests/cbor/generate_fixtures.py   # needs cbor2
```

## Fixtures

| File | Items | Bytes | SHA-256 | Intent |
|---|---:|---:|---|---|
{chr(10).join(rows)}

## Bytes

{chr(10).join(dumps)}"""

    (HERE / "MANIFEST.md").write_text(manifest, encoding="utf-8")
    print(f"wrote MANIFEST.md describing {len(fixtures)} fixtures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
