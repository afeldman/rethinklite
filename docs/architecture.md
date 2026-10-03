# RethinkLite — Architecture

Status: design baseline for **M0**. Normative documents are linked inline; this
file is the map.

> RethinkLite is a small, robust, embedded and reactive document database
> written in Rust, with CBOR as its language-neutral interoperability contract.

---

## 1. What RethinkLite is

* **Embedded.** A Rust library that opens a local database file. No server
  process, no port, no daemon is required to use it.
* **Local.** One database is one file (`*.rtl`) plus nothing else in the default
  configuration. Distribution is copying that file.
* **Reactive.** Subscriptions over queries are a first-class feature, not a
  polling layer: `watch` delivers an initial snapshot and then ordered change
  events with old and new values.
* **Document-oriented.** Collections of schemaless CBOR documents with explicit
  IDs, ordered scans and (M1) secondary indexes.
* **Language-neutral.** CBOR is not an export format bolted on later; it is the
  frozen contract at the boundary between the Rust core and every other
  language (see `cbor-protocol.md`).

## 2. What RethinkLite is not

See `non-goals.md` for the authoritative list. In one line: RethinkLite is
**not** a distributed database, not a SQL engine, not a JSON layer over SQLite,
and not a smaller RethinkDB.

## 3. Layering

```
        Rust application            Python             Go            (later: Node, C#, C/C++, Java)
              |                        |                |
      native Rust API        C ABI / cffi           C ABI / cgo
              |                        |                |
              |                        +---- CBOR -----+          <- contract boundary
              |                                 |
              |                        rtl-protocol (envelope, ops, errors, negotiation)
              |                                 |
              +------------ rtl-core ------------+
                        (Database, Collection, transactions, query engine, changes)
                                  |
                        rtl-storage  (pager, COW B+tree, superblocks, log segments, recovery)
                                  |
                        rtl-value    (value model, canonical CBOR, memcomparable keys, order)
                                  |
                             one .rtl file
```

Dependency rule (enforced by the workspace, see §7):

```
rtl-value  <-  rtl-storage  <-  rtl-core  <-  { rtl-capi, rtl-cli, rtl-server (M1) }
rtl-value  <-  rtl-protocol
rtl-core   <-  rtl-protocol          (only to map errors; never the reverse)
```

* `rtl-protocol` depends on `rtl-value` **only**. The contract is testable and
  versioned without an engine (golden fixtures run against this crate alone).
* `rtl-storage` **does not know about CBOR**. Its interface is ordered keys and
  opaque byte blobs. Documents happen to be canonical CBOR; the storage engine
  would work identically with any other record encoding, which is what keeps
  the physical format free to change later.
* No crate below `rtl-core` knows that Python, Go or C exist. No language
  binding may implement database semantics; bindings encode requests, decode
  responses and translate errors. Anything else duplicates the core
  (`adr/0001-rust-core.md`).

## 4. Invariants

These hold for every M0 build and every test asserts a subset of them:

| # | Invariant |
|---|---|
| I1 | Exactly one live `Database` instance per file in a process, and one process per file (exclusive `flock`). |
| I2 | A `commit_seq` (u64) is assigned at most once, is strictly increasing, and is shared by all changes of one committed transaction. |
| I3 | The superblock is the only commit point. A commit is visible if and only if its superblock is durable and valid. |
| I4 | Committed state is never lost by a crash; uncommitted state is never visible after recovery. Recovery yields the newest valid superblock, never a partial one. |
| I5 | A reader holding a snapshot observes a state that was committed at some `commit_seq`, and is never blocked by writers. |
| I6 | Documents are stored as deterministically encoded CBOR (RFC 8949 §4.2.1). Byte equality is document identity. |
| I7 | A write whose canonical bytes equal the stored bytes is a no-op: no `rev` bump, no `commit_seq`, no change event. |
| I8 | `commit_seq` ordering of the durable log is the ordering of every changefeed and the future replication offset. |
| I9 | No partial-write corruption escapes: every page, superblock slot and log record is checksummed; a failed checksum is an error, never a silent misread. |
| I10 | The engine never panics on malformed input; every decoding path returns a structured error. |

## 5. Data flow

### 5.1 Write path (one transaction)

```
caller: db.collection("users").insert(doc)
  -> rtl-core: validate document, canonicalize (rtl-value)
  -> rtl-core: transaction layer (single writer lock, snapshot = last commit_seq)
  -> rtl-storage: copy-on-write B+tree updates lease-free page set
  -> rtl-storage: append change records to the open log segment
  -> rtl-storage: fsync data (pages + log)
  -> rtl-storage: flip superblock slot (generation+1, new roots, log head, commit_seq)
  -> rtl-storage: fsync superblock           <-- commit point
  -> rtl-core: publish commit to feeds, release write lock
  -> caller: { id, rev, commit_seq, unchanged }
```

Two `fsync` calls per commit. Group commit (batching several transactions into
one sync) is a documented M1 performance item, not M0 scope.

### 5.2 Read path

```
caller: db.collection("users").get(id)
  -> rtl-core: pin a snapshot (Arc<Generation>): no lock, no blocking
  -> rtl-storage: B+tree lookup in that generation's page set
  -> rtl-core: return stored canonical bytes verbatim (no decode/re-encode)
```

Documents that the engine does not need to inspect are **never decoded**: the
stored bytes are spliced into the response. Decoding happens only for
predicates, sorts, projections and index maintenance.

### 5.3 Feed path

```
commit (5.1) completes  ->  log records with commit_seq N are durable
                        ->  feed registry fans out to subscribers whose
                            expression matches, in commit_seq order
subscriber              <-  CBOR Sequence items, one per event (RFC 8742)
```

Subscription start uses a COW snapshot at `commit_seq = S`: the initial
snapshot events and the live events from `S+1` cannot overlap or leave a gap
because both come from the same ordered history (`changefeeds.md`).

## 6. Concurrency model

* **Synchronous core.** No async runtime, no `tokio` in `rtl-core`. Blocking
  calls, `Send + Sync` handles. Rationale: embedded FFI is inherently
  synchronous, and async can be layered on top outside the core
  (`adr/0009-concurrency-model.md`).
* **Single writer.** One read-write transaction at a time, serialized by a
  `Mutex` inside `Database`. Readers are unaffected.
* **Snapshot readers.** Copy-on-write pages give every reader a consistent,
  cheap, long-lived snapshot (`Arc` pin). This is what makes the
  snapshot-then-tail feed pattern correct.
* **Thread safety.** `Database`, `Collection` and `Tx` are `Send + Sync` —
  sharing `Database` across threads is the intended usage.
* **Process safety.** Exclusive advisory file lock; a second open of the same
  file fails with `io` / `already_open`.

## 7. Workspace layout

```
rethinklite/
├── Cargo.toml                 workspace, resolver 2, shared lints
├── README.md
├── crates/
│   ├── rtl-value/             value model, canonical CBOR codec, key codec, order
│   ├── rtl-storage/           pager, COW B+tree, superblock, log segments, recovery
│   ├── rtl-core/              Database/Collection API, transactions, query, changes
│   ├── rtl-protocol/          envelope, operations, errors, negotiation (contract only)
│   ├── rtl-cli/               binary `rtl`
│   └── rtl-capi/              C ABI (cdylib + cbindgen) — M1
├── tests/cbor/                golden CBOR fixtures (contract, language-neutral)
├── tests/                     workspace integration tests (storage, crash, concurrency)
├── benches/
└── docs/                      this design set + docs/adr/
```

Deviations from the sketch in the request: `value`, `cbor`, `document` and
`index` collapse into `rtl-value` + `rtl-core` because they share one type
vocabulary and splitting them would only create re-export churn; `wal` becomes
part of `rtl-storage` (the log segments *are* a storage structure);
`changefeed` lives in `rtl-core` until it needs its own crate; `protocol`
became `rtl-protocol` and is deliberately engine-free.

## 8. Error handling philosophy

* One error enum per layer, non-exhaustive, `thiserror`-based at the top.
* Storage errors (`io`, `corruption`) are terminal for the operation but must
  never be swallowed; corruption marks the database as failed-fast for writes.
* User errors (`invalid_document`, `invalid_query`, `not_found`, `conflict`)
  are values, never panics.
* Every error has a stable `kind` + `code` pair that crosses the CBOR boundary
  unchanged so bindings can raise idiomatic exceptions
  (`error-model.md`).

## 9. Security posture (M0)

M0 is **local-only**: no network listener, no authentication, no authorization.
The threat model that *is* enforced:

| Threat | Mitigation |
|---|---|
| Malformed/hostile CBOR from a client | bounded decoder (depth 100, sizes checked, no unbounded allocation from declared lengths before validation), no `unwrap` on input paths |
| Hostile query expressions | no eval, no scripts, no string DSL; the term tree is a closed set with arity/type checks |
| Accidental data loss | WAL-log + superblock integrity, checksums, `rtl check` |
| Foreign process writing the file | exclusive `flock` |
| Local multi-user access | file permissions only; documented as out of scope for M0 |

A local IPC listener (M1) will be a Unix domain socket with owner-only
permissions; network operation is an explicit non-goal until a separate
security design exists (`non-goals.md`, `adr/0006-embedded-vs-ipc.md`).

## 10. Test strategy

| Layer | Technique |
|---|---|
| Value / CBOR | property tests: encode∘decode = id, canonical re-encode is byte-stable, key order preserved by key codec |
| Storage | property tests on B+tree invariants; torn-write tests by truncating and byte-flipping copies of a real file; recovery must yield either the old or the new state |
| Core | integration tests per operation; concurrency tests (readers during writes); transaction conflict tests |
| Contract | golden fixtures in `tests/cbor/` decoded and re-encoded byte-identically; every fixture is also a cross-language conformance case |
| Performance | benches for insert throughput, point lookup, scan, feed latency (`benches/`, numbers are recorded, not asserted, in M0) |

Quality gates for every commit (`roadmap.md` §gates):

```
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

## 11. Where each decision lives

| Question | Document |
|---|---|
| What is the database, how is it layered? | this file |
| What is a document, an ID, a comparison? | `data-model.md` |
| What does the wire look like? | `cbor-protocol.md` |
| How do queries work? | `query-model.md` |
| What happens inside a transaction? | `transactions.md` |
| How do subscriptions work? | `changefeeds.md` |
| How are bytes made durable? | `storage.md` |
| How do errors propagate? | `error-model.md` |
| What is stable, what may change? | `compatibility.md` |
| What comes after M0, and what never? | `roadmap.md`, `non-goals.md` |
| Why was it decided this way? | `docs/adr/` |

## 12. Open decisions

* **License** — not yet chosen (candidates: `MIT OR Apache-2.0`, consistent
  with the author's other Rust projects). Required before the first public
  commit; not required for M0 implementation.
* **Async façade** (`rtl-async`, `rtl-server`) — M1; shape decided then.
