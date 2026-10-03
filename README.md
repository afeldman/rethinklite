# RethinkLite

A small, robust, embedded and reactive document database written in Rust, with
CBOR as its language-neutral interoperability contract.

**This repository currently contains the design baseline and nothing else. The
engine is not implemented yet.** Every document below describes intended
behaviour under protocol version 1 and storage format version 1. No feature
described here works today.

## What it is

* **Embedded.** A Rust library that opens a local database file. No server, port
  or daemon is required to use it.
* **Local.** One database is one `.rtl` file. Distribution is copying that file.
* **Reactive.** Subscriptions over queries are first-class: `watch` delivers an
  initial snapshot followed by ordered change events with old and new values.
* **Document-oriented.** Schemaless CBOR documents with explicit IDs, ordered
  scans and (M1) secondary indexes.
* **Language-neutral.** CBOR is the frozen contract at the boundary between the
  Rust core and every other language, not an export format added later.

## What it is not

Not a distributed database, not a SQL engine, not a JSON layer over SQLite, and
not a smaller RethinkDB. There is no query string, no script, no network
listener in M0, and no per-language reimplementation of database semantics. The
full list with architectural reasons is `docs/non-goals.md`.

## Architecture sketch

```
   Rust application        Python              Go          (later: Node, C#, C/C++, Java)
         |                   |                  |
 native Rust API       C ABI / cffi       C ABI / cgo
         |                   |                  |
         |                   +---- CBOR --------+      <- contract boundary
         |                            |
         |                   rtl-protocol (envelope, operations, errors, negotiation)
         |                            |
         +--------- rtl-core ---------+
              (Database, Collection, transactions, query engine, changes)
                       |
                 rtl-storage  (pager, COW B+tree, superblocks, log segments, recovery)
                       |
                 rtl-value    (value model, canonical CBOR, order-preserving keys, order)
                       |
                  one .rtl file
```

`rtl-storage` does not know about CBOR; its interface is ordered keys and opaque
bytes, which keeps the physical format free to change. No crate below `rtl-core`
knows that another language exists.

## Rust quickstart

```rust
use rethinklite::{Database, doc};
use rethinklite::query::{field, gt, eq, and};

let db = Database::open("example.rtl")?;
let users = db.collection("users");

let id = users.insert(doc! { "name": "Anton", "age": 41, "active": true })?;

let result = users
    .query()                                   // -> QueryBuilder
    .filter(and(gt(field("age"), 30), eq(field("active"), true)))
    .sort_desc(field("age"))
    .limit(20)
    .collect()?;                               // -> QueryResult

for document in result.documents() {           // borrowed, no re-encoding
    println!("{}", document.id());
}
```

`QueryBuilder` builds a term and nothing more; `collect()`, `count()` and
`to_cbor()` are thin wrappers over the executor and the protocol encoder. This
is why a fixture produced by Python and one produced by Rust are comparable
byte-for-byte (`docs/query-model.md`).

## CBOR interop

The contract is the CBOR Sequence described in `docs/cbor-protocol.md`. Any
language with a CBOR library can talk to the core without a RethinkLite-specific
dependency: it encodes a request item, writes it to the transport, reads a
response item and decodes it. There is no length prefix and no proprietary tag.

Documents inside the payload use the value model of `docs/data-model.md`, which
is length-first core deterministic CBOR (RFC 8949 §4.2.3, the ordering stock
library canonical modes emit) with text-keyed maps. Golden fixtures in
`tests/cbor/` are normative bytes: an implementation is conformant when it
decodes each fixture and re-encodes it byte-identically.

## Status

| Area | Milestone |
|---|---|
| Value model, canonical CBOR, key codec | M0 |
| Pager, COW B+tree, log segments, recovery | M0 |
| Collections, CRUD, transactions, basic query | M0 |
| `rtl` CLI | M0 |
| `collection.watch`, secondary indexes, cursors | M1 |
| Unix socket IPC, C ABI, Python/Go clients | M1 |
| Persisted freelist, group commit, `rtl vacuum` | M1 |
| Replication, async façade, multi-process readers, repair | M2 |

Every entry is planned work, not a shipped feature. See `docs/roadmap.md`.

## Documentation map

| Question | Document |
|---|---|
| Layering and invariants | `docs/architecture.md` |
| Documents, IDs, ordering | `docs/data-model.md` |
| Wire contract v1 | `docs/cbor-protocol.md` |
| Queries and term language | `docs/query-model.md` |
| Subscriptions | `docs/changefeeds.md` |
| Durability and recovery | `docs/storage.md` |
| Errors | `docs/error-model.md` |
| Transactions | `docs/transactions.md` |
| Stability policy, plan, non-goals | `docs/compatibility.md`, `docs/roadmap.md`, `docs/non-goals.md` |
| Decisions | `docs/adr/` |

## Build and test

The workspace does not exist yet; these are the commands the project will use
once it does. The three quality gates are:

```
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

## License

Not chosen yet. Candidates are `MIT OR Apache-2.0`, consistent with the author's
other Rust projects. A license is required before the first public commit but
not for M0 implementation (`docs/architecture.md` §12).
