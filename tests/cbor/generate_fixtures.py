#!/usr/bin/env python3
"""Generate the RethinkLite golden CBOR fixtures (docs/cbor-protocol.md §10).

Development-time tool. Requires cbor2, which is NOT a dependency of the Rust
crates:

    python3 -m venv /tmp/cborvenv
    /tmp/cborvenv/bin/pip install cbor2
    /tmp/cborvenv/bin/python tests/cbor/generate_fixtures.py
    python3 tests/cbor/verify_fixtures.py tests/cbor

Every fixture is written with cbor2's canonical mode (RFC 7049 canonical
ordering, which is RFC 8949 §4.2.3 length-first) and immediately re-read and
compared against the intended Python object, so the fixture bytes cannot
silently drift from this file. Canonicality is validated independently by
verify_fixtures.py.

Re-running this generator must reproduce every file byte-for-byte. If it does
not, the byte contract changed: that requires a deliberate edit of MANIFEST.md
and a compatibility note, not a silent rewrite.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import cbor2
from cbor2 import CBORTag

HERE = Path(__file__).parent

# Fixed values so that regeneration is byte-identical everywhere.
DATABASE_UUID = bytes.fromhex("018f5f9a1b2c7def8123456789abcdef")  # UUIDv7-shaped
USER_UUID = bytes.fromhex("018f5f9a1b2c7def812345678abcdeff")

USER_DOC = {
    "id": "user-123",
    "name": "Anton",
    "active": True,
    "age": 41,
    "tags": ["rust", "database"],
    "profile": {"country": "DE"},
}


def fixtures() -> dict[str, list[object]]:
    return {
        # ---- session -----------------------------------------------------
        "hello_request.cbor": [
            {
                "protocol": 1,
                "request": 1,
                "operation": "hello",
                "body": {
                    "client": {"name": "rethinklite-python", "version": "0.1.0"},
                    "protocol": [1],
                    "features": ["transactions", "watch"],
                    "required": ["transactions"],
                },
            }
        ],
        "hello_response.cbor": [
            {
                "protocol": 1,
                "request": 1,
                "status": "ok",
                "body": {
                    "server": {"name": "rethinklite", "version": "0.1.0", "engine": "0.1.0"},
                    "protocol": 1,
                    "database": {"uuid": DATABASE_UUID, "format": 1, "path": "example.rtl"},
                    "features": ["cancel", "count", "transactions"],
                    "limits": {
                        "document_bytes": 16777216,
                        "feed_queue": 1024,
                        "log_retention_bytes": 67108864,
                        "query_results": 100000,
                        "transaction_timeout_ms": 30000,
                    },
                },
            }
        ],
        # ---- documents ---------------------------------------------------
        # The document is stored byte-identically inside the request, so this
        # fixture also pins the canonical form of a small document.
        "insert_request.cbor": [
            {
                "protocol": 1,
                "request": 2,
                "operation": "collection.insert",
                "body": {
                    "collection": "users",
                    "document": USER_DOC,
                    "return_document": False,
                },
            }
        ],
        "insert_response.cbor": [
            {
                "protocol": 1,
                "request": 2,
                "status": "ok",
                "body": {"id": "user-123", "rev": 1, "commit_seq": 42, "unchanged": False},
            }
        ],
        "get_response.cbor": [
            {
                "protocol": 1,
                "request": 3,
                "status": "ok",
                "body": {
                    "id": "user-123",
                    "rev": 1,
                    "commit_seq": 42,
                    "document": USER_DOC,
                },
            }
        ],
        # Documents may be addressed by a UUID id (CBOR tag 37 over 16 bytes).
        "uuid_id_request.cbor": [
            {
                "protocol": 1,
                "request": 4,
                "operation": "collection.get",
                "body": {"collection": "users", "id": CBORTag(37, USER_UUID)},
            }
        ],
        # ---- query -------------------------------------------------------
        "query_request.cbor": [
            {
                "protocol": 1,
                "request": 5,
                "operation": "collection.query",
                "body": {
                    "collection": "users",
                    "include_meta": False,
                    "expr": [
                        "limit",
                        20,
                        [
                            "sort",
                            ["field", "age"],
                            "desc",
                            ["filter", ["gt", ["field", "age"], 30], ["scan"]],
                        ],
                    ],
                },
            }
        ],
        "query_response.cbor": [
            {
                "protocol": 1,
                "request": 5,
                "status": "ok",
                "body": {
                    "documents": [
                        {"id": "user-123", "name": "Anton", "active": True, "age": 41}
                    ],
                    "returned": 1,
                    "scanned": 3,
                    "truncated": False,
                },
            }
        ],
        "count_response.cbor": [
            {
                "protocol": 1,
                "request": 6,
                "status": "ok",
                "body": {"count": 41, "scanned": 128, "exact": True},
            }
        ],
        # ---- transaction: one fixture, three items (a CBOR Sequence) -----
        "transaction_request.cbor": [
            {
                "protocol": 1,
                "request": 7,
                "operation": "transaction.begin",
                "body": {"mode": "read_write"},
            },
            {
                "protocol": 1,
                "request": 8,
                "operation": "collection.update",
                "transaction": 7,
                "body": {
                    "collection": "users",
                    "id": "user-123",
                    "if_rev": 1,
                    "set": {"active": False},
                },
            },
            {
                "protocol": 1,
                "request": 9,
                "operation": "transaction.commit",
                "body": {"transaction": 7},
            },
        ],
        # ---- changefeed --------------------------------------------------
        "watch_request.cbor": [
            {
                "protocol": 1,
                "request": 10,
                "operation": "collection.watch",
                "body": {
                    "collection": "users",
                    "expr": ["filter", ["eq", ["field", "active"], True], ["scan"]],
                    "include_initial": True,
                    "overflow": "disconnect",
                },
            }
        ],
        "change_event.cbor": [
            {
                "feed": 3,
                "event": {
                    "type": "updated",
                    "commit_seq": 4711,
                    "collection": "users",
                    "id": "user-123",
                    "rev": 2,
                    "old": {"id": "user-123", "name": "Anton", "active": True},
                    "new": {"id": "user-123", "name": "Anton", "active": False},
                },
            }
        ],
        # ---- error -------------------------------------------------------
        "error_response.cbor": [
            {
                "protocol": 1,
                "request": 8,
                "status": "error",
                "error": {
                    "kind": "conflict",
                    "code": "revision_conflict",
                    "message": "document revision does not match the expected revision",
                    "retryable": False,
                    "details": {
                        "collection": "users",
                        "id": "user-123",
                        "expected": 3,
                        "actual": 4,
                    },
                },
            }
        ],
    }


def decode_all(blob: bytes) -> list[object]:
    decoder = cbor2.CBORDecoder(io.BytesIO(blob))
    items: list[object] = []
    while True:
        try:
            items.append(decoder.decode())
        except cbor2.CBORDecodeEOF:
            return items


def normalise(obj: object) -> object:
    """Map cbor2's built-in tag handlers back to the raw tagged values.

    cbor2 decodes tag 37 into a uuid.UUID; the contract is the tag over 16
    bytes, so comparisons happen on the normalised form.
    """
    if isinstance(obj, uuid.UUID):
        return CBORTag(37, obj.bytes)
    if isinstance(obj, CBORTag):
        return CBORTag(obj.tag, normalise(obj.value))
    if isinstance(obj, dict):
        return {key: normalise(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [normalise(item) for item in obj]
    return obj


def main() -> int:
    written = 0
    for name, items in fixtures().items():
        path = HERE / name
        blob = b"".join(cbor2.dumps(item, canonical=True) for item in items)
        path.write_bytes(blob)

        decoded = decode_all(blob)
        if normalise(decoded) != normalise(items):
            print(f"ROUND-TRIP FAILED for {name}")
            print(f"  expected: {items!r}")
            print(f"  decoded : {decoded!r}")
            return 1

        written += 1
        print(f"wrote {name:28} items={len(items)} bytes={len(blob)}")
    print(f"\n{written} fixtures written to {HERE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
