# RethinkLite — Roadmap

Status: design baseline. Scope, exit criteria and explicit non-scope for
milestones M0, M1 and M2, plus what is never scheduled. M0 is the current
milestone: this document describes what will be built, not what exists.

Global milestone rules:

* **No milestone may change an accepted ADR without a new ADR.** A change of
  direction is recorded as a decision (`docs/adr/`), not as an edit.
* **Performance targets are recorded, not asserted, until M1.** M0 benches
  produce numbers; M1 turns a selected subset into enforced gates.
* A milestone is complete only when its exit criteria are met; scope listed as
  non-scope is not pulled in to make a milestone look finished.

---

## M0 — Foundation

### Scope

* Workspace and crates: `rtl-value`, `rtl-storage`, `rtl-core`, the public
  facade `rethinklite`, `rtl-protocol`, `rtl-cli` (`architecture.md` §7).
* Value model, canonical CBOR and order-preserving key codec (`data-model.md`).
* Pager with two superblock slots + copy-on-write B+tree + log segments +
  recovery + free-set derivation (`storage.md`).
* Collections: create, drop, list.
* Documents: insert, get, update, replace, delete.
* Basic query: scan, filter, sort, limit, skip, project, count
  (`query-model.md`).
* Transactions: begin, commit, rollback; snapshot reads; write-write conflict
  detection.
* Protocol crate and golden fixtures (`cbor-protocol.md`, `tests/cbor/`).
* `rtl` CLI: `init`, `insert`, `get`, `query`, `check`, `info`.
  `dump` (fixture-compatible CBOR in/out) is in the M0 plan as an additional
  command; it is a convenience, not an exit criterion.
* Quality gates: `cargo fmt --all --check`,
  `cargo clippy --workspace --all-targets -- -D warnings`,
  `cargo test --workspace`.
* Integration, property, crash-recovery and concurrency tests
  (`architecture.md` §10).

### Exit criteria

* Every M0 operation in `cbor-protocol.md` §6 is implemented and covered by an
  integration test.
* Golden fixtures decode and re-encode byte-identically.
* Crash-recovery tests show recovery yields either the old or the new state,
  never a partial one (invariants I3, I4, I9).
* Concurrency tests show readers are never blocked by a writer (I5).
* The three quality gates pass on a clean checkout.

### Non-scope

`collection.watch` implementation, secondary indexes, replication, network
operation, authentication, DDL migrations, a persisted freelist, and vacuum.
All are scheduled below or excluded in `non-goals.md`.

---

## M1 — Reach

### Scope

* `collection.watch` implementation (snapshot + tail), in-process and streamed,
  per the frozen wire shape (`changefeeds.md`).
* Secondary indexes.
* Cursors.
* Local IPC daemon over a Unix domain socket with owner-only permissions, using
  CBOR Sequence framing (`architecture.md` §9).
* C ABI crate `rtl-capi` plus Python (cffi) and Go (cgo) clients.
* Persisted freelist.
* Group commit.
* `rtl vacuum`.
* Benches with recorded numbers, and enforced performance gates for a selected
  subset.

### Exit criteria

* Snapshot–tail continuity holds under a concurrent writer (property test,
  `changefeeds.md` §11).
* A Python client and a Go client pass the same fixture conformance suite as the
  Rust core.
* The IPC daemon is reachable only through an owner-only socket and never over a
  network interface.
* Recorded bench numbers exist for insert throughput, point lookup, scan and
  feed latency.

### Non-scope

Replication, compression, encryption, multi-process readers and repair tooling.

---

## M2 — Distribution and hardening

### Scope

* Replication between two RethinkLite files using `(database_uuid, commit_seq)`
  as the offset (`changefeeds.md` §12).
* An async façade **outside** the core (the core stays synchronous,
  `architecture.md` §6).
* Compression and encryption treated as separate ADRs before any code.
* Multi-process readers.
* Repair tooling (`storage.md` §11).

### Exit criteria

* A replica converges to the primary's committed state using only the change
  log, with no new ordering concept.
* The async façade adds no async runtime dependency to `rtl-core`.
* Repair tooling reports and never silently rewrites.

### Non-scope

Clustering, consensus, a cloud service, SQL compatibility — all excluded
permanently.

---

## Never

The following are not scheduled in any milestone and are documented with their
architectural reasons in `non-goals.md`: clustering, consensus, a cloud service
and SQL compatibility.

---

## Recording numbers

M0 records bench numbers in `benches/` without asserting them. M1 selects which
numbers become enforced gates. A number that is not reproducible by the three
quality gates is an observation, not a guarantee, and is labelled as such.
