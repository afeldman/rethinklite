# Architecture Decision Records

This directory records the architecture decisions behind RethinkLite. Each record
states the forces at play, the decision taken, the alternatives rejected with the
reason they lost, and the consequences accepted. A record is immutable once it is
Accepted.

## Index

| # | Slug | Title | Status |
|---|---|---|---|
| 0001 | [0001-rust-core](0001-rust-core.md) | A single Rust core owns all database semantics | Accepted |
| 0002 | [0002-document-model](0002-document-model.md) | The document model is the CBOR data model | Accepted |
| 0003 | [0003-storage-strategy](0003-storage-strategy.md) | Copy-on-write B+tree with a superblock commit point | Accepted |
| 0004 | [0004-cbor-protocol](0004-cbor-protocol.md) | CBOR is the only cross-language contract | Accepted |
| 0005 | [0005-storage-cbor-boundary](0005-storage-cbor-boundary.md) | The storage engine sees opaque bytes, not CBOR | Accepted |
| 0006 | [0006-embedded-vs-ipc](0006-embedded-vs-ipc.md) | Embedded library first, IPC later, one implementation | Accepted |
| 0007 | [0007-id-and-ordering](0007-id-and-ordering.md) | Document identity and the single total order | Accepted |
| 0008 | [0008-query-expression-encoding](0008-query-expression-encoding.md) | Query expression encoding | Accepted |
| 0009 | [0009-concurrency-model](0009-concurrency-model.md) | Concurrency model | Accepted |
| 0010 | [0010-commit-seq-and-changefeeds](0010-commit-seq-and-changefeeds.md) | commit_seq and changefeeds | Accepted |
| 0011 | [0011-c-abi-ffi](0011-c-abi-ffi.md) | Foreign-function surface (C ABI) | Accepted |
| 0012 | [0012-freelist-derivation](0012-freelist-derivation.md) | Free-page derivation at open | Accepted |

## Adding an ADR

Take the next free number, never edit an Accepted record, and if a decision
changes, write a new record that supersedes the old one and update both
`Supersedes / Superseded by` lines. Keep the record to the shape used here:
status, date, deciders and supersession header, then Context, Decision,
Alternatives considered, Consequences and References.
