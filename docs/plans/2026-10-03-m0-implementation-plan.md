# M0 Implementation Plan — Task Breakdown

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to execute one task per fresh subagent with a review between tasks. Commit 1 has a code-level plan (`2026-10-03-m0-commit-1-value-layer.md`); every later task gets its own code-level plan written at the moment it starts, against the interfaces that actually exist by then.

**Goal:** Deliver M0 — a real embedded, reactive document database in one `.rtl` file: value layer, storage engine with crash-safe commits and recovery, collections and documents, transactions, basic queries, the frozen CBOR protocol crate and a CLI, all behind the three quality gates.

**Architecture:** Copy-on-write B+tree with two superblock slots as the only commit point; a durable change log stored as log segments in the same file; snapshot readers; one writer; a synchronous core with no async runtime; CBOR as the language-neutral contract with golden fixtures as the byte-level anchor (`docs/architecture.md`).

**Tech Stack:** Rust edition 2024 (MSRV 1.85) · `minicbor` 2.3 · `half` 2.7 · `thiserror` 2 · `proptest` 1.11 · `crc32fast` 1.5 · `getrandom` (auto-UUIDv7) · no async · no serde on the wire path.

**Spec:** `docs/architecture.md`, `docs/data-model.md`, `docs/cbor-protocol.md`, `docs/query-model.md`, `docs/transactions.md`, `docs/changefeeds.md`, `docs/storage.md`, `docs/error-model.md`, `docs/compatibility.md`, `docs/roadmap.md`, `docs/non-goals.md`, `docs/adr/`.

## Global Constraints

Identical to Commit 1's list and binding for every task below:

- edition 2024, MSRV 1.85, `publish = false`, no license field yet.
- No `serde` on the wire path; no async runtime; `unsafe_code = "forbid"`.
- No `unwrap`/`expect`/`panic` in library code.
- Limits: document 16 MiB, depth 100, text id 1024 B, collection name 255 B, page 4096 B, feed queue 1024, log retention 64 MiB, query results 100 000, transaction timeout 30 000 ms.
- Protocol version 1, storage format version 1.
- Gates before every commit: `cargo fmt --all --check`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace`; plus `python3 tests/cbor/verify_fixtures.py tests/cbor` and `python3 tests/cbor/selftest_verifier.py` whenever fixtures are touched.
- Never edit an existing fixture's bytes; never change a released meaning; an accepted ADR is superseded by a new ADR, never edited.
- Commit style: conventional prefixes, English, one task per commit, no push.

---

## Why the storage tasks have no code in this document

Commit 1's plan could specify exact code because its interfaces are fixed by the
spec and by `minicbor`'s real API. The storage tasks cannot: their interfaces are
*created* by the task before them (a pager cannot be written before the page
layout exists in code), and a plan that invents signatures for unimplemented
modules produces fiction that the implementer then has to fight. Therefore:

* this document fixes **commit boundaries, deliverables, files, tests and exit
  criteria** for every M0 task — the part that must not drift;
* each task receives a code-level plan (Commit-1 style: test first, exact
  signatures, real code) written at task start, against the interfaces that exist
  at that moment, and reviewed before implementation begins.

That split is the honest one. Writing 4 000 lines of speculative storage code now
would violate the "no placeholders" rule far worse than deferring it by one task.

---

## Commit sequence

### Commit 1 — Value layer ✅ planned
`rtl-value`: value model, canonical CBOR encoder, lenient decoder, total order,
order-preserving key codec; workspace + CI gates.
**Exit:** all 13 fixtures round-trip byte-identically from Rust; Python checker agrees; gates green.
**Plan:** `docs/plans/2026-10-03-m0-commit-1-value-layer.md`.

### Commit 2 — Storage tracer bullet
**Deliverable:** open/create a `.rtl` file, put and get one raw key on one page, close, reopen, read it back. No B+tree yet.
**Files:** `crates/rtl-storage/src/{lib,error,superblock,page,pager,file}.rs`.
**Covers:** superblock slot A/B with CRC-32/ISO-HDLC and generation, page header, positional `pread`/`pwrite`, exclusive `flock`, `Database::open`/`create`, `io`/`already_open`/`no_valid_superblock`.
**Tests:** create → write → read → drop → reopen (same process and a child process); corrupt a superblock byte → `no_valid_superblock`; two opens of the same file → `already_open`.
**Exit:** a file written by one process is readable by the next, with the superblock as the only commit point.

### Commit 3 — Copy-on-write B+tree
**Deliverable:** ordered key/value tree with leaf splits, one level of internal growth, point lookup and ordered range scan; *no* rebalance on delete (documented).
**Files:** `crates/rtl-storage/src/{btree,node,split,scan}.rs`.
**Tests:** proptest against a `BTreeMap` oracle (insert/get/delete/range); leaf-chain order; page-count growth bound; a 10 000-key insert then file-size regression check for reinsertion of the same keys.
**Exit:** tree behaviour matches the oracle for random operation sequences; invariant checks in `debug_assert` form.

### Commit 4 — Generations, snapshots, free set, integrity walk
**Deliverable:** `Generation` pinning, reader snapshots that never block a writer, free-set derivation at open, and the validation pass that doubles as `rtl check`.
**Files:** `crates/rtl-storage/src/{generation,alloc,integrity}.rs`.
**Tests:** a reader holding a snapshot sees the old state while a writer commits; double-referenced page, page out of range, overflow cycle, sibling cycle and wrong page id are each detected; orphan pages from an interrupted commit are reclaimed.
**Exit:** "a database that opens is a database whose page graph is consistent" is a test, not a claim.

### Commit 5 — Commit protocol, log segments, crash recovery
**Deliverable:** the two-`fsync` commit (data, then superblock flip), log segments with sealed/open states and retention, recovery that truncates the log to the committed offset, `Sync::Full`/`Sync::None`.
**Files:** `crates/rtl-storage/src/{commit,log,recovery}.rs`.
**Tests:** crash matrix on a *copy* of a real database — truncate at every byte offset around the commit window, flip bytes in the superblock, in a page and in a log record; after every injection the database must reopen to exactly the pre- or post-commit state, never a third one. Retention: force the head forward and assert `log_truncated` semantics at the log level.
**Exit:** the crash matrix passes for hundreds of injection points, and each failure mode maps to a registered error code.

### Commit 6 — Collections and document records
**Deliverable:** catalog tree, `collection_id` assignment from the metadata tree, create/drop/list, document records (`rev`, `commit_seq`, canonical bytes), collection name validation.
**Files:** `crates/rtl-core/src/{lib,error,database,collection,document,record}.rs`, `crates/rethinklite/src/lib.rs` (the public facade: re-exports `rtl-core` and hosts the `doc!` macro, `architecture.md` §7).
**Tests:** create/drop/list; `collection_exists`; reserved name `_`; a dropped collection's pages are reclaimed by the next free-set derivation; document bytes survive verbatim.
**Exit:** documents are stored and read back with `rev`/`commit_seq` intact and byte-identical payloads.

### Commit 7 — Document operations
**Deliverable:** `insert`, `get`, `update` (`set`/`unset`), `replace` (insert-or-replace), `delete`, `if_rev` guards, the idempotent no-op rule, auto UUIDv7 ids.
**Files:** `crates/rtl-core/src/{ops,id_gen}.rs`.
**Tests:** one test per error code in `docs/error-model.md` §3.4/§3.6/§3.7; writing identical bytes consumes no `commit_seq` and bumps no `rev`; `unset` of a missing key is not an error; shallow-merge semantics are asserted explicitly.
**Exit:** every documented operation semantic has a test, including the ones that look like quibbles.

### Commit 8 — Transactions
**Deliverable:** `begin`/`commit`/`rollback`, closure API with rollback-on-`Err`/panic, snapshot reads, write-write conflict detection, one writer at a time (`writer_busy`), timeouts, read-only mode.
**Files:** `crates/rtl-core/src/{tx,conflict}.rs`.
**Tests:** rollback leaves no trace (no `commit_seq`, no log record, no rev change); two writers on the same document → `write_conflict`; disjoint writers both commit; a deliberately write-skewed pair commits, documenting the isolation limit instead of hiding it; timeout releases the writer slot.
**Exit:** `docs/transactions.md` §10 is executable.

### Commit 9 — Query engine
**Deliverable:** term tree (`scan`, `filter`, `project`, `sort`, `limit`, `skip`, `get`, comparisons, boolean operators, `in`, `contains`, `exists`, `field`), pipeline execution, `count`, `explain()`, limit enforcement (`result_limit_exceeded`, `sort_memory_exceeded`), cancellation token.
**Files:** `crates/rtl-core/src/query/{mod,term,eval,plan,cancel}.rs`.
**Tests:** query contract tests written against the same term trees as the protocol fixtures; ordering claims with shuffled insertion order; predicate null semantics (`exists` versus `eq null`); early stop on `limit` verified by instrumenting the scan count.
**Exit:** `docs/query-model.md` §3 is executable and `explain()` renders the documented pipeline.

### Commit 10 — Protocol crate and contract conformance
**Deliverable:** `rtl-protocol`: envelope encode/decode as `Value` trees, operation name validation, request/response bodies for every M0 operation, error object mapping from `kind`/`code`/`retryable`/`details`, `hello` payload with limits and capability negotiation, watch/feed event encoding (specified now, used in M1).
**Files:** `crates/rtl-protocol/src/{lib,error,request,response,op,error_object,feed,hello}.rs`.
**Tests:** every fixture decodes to the typed structures and re-encodes byte-identically; unknown operations and unknown fields behave as specified; the registry test compares the code list against a checked-in snapshot so a rename fails CI.
**Exit:** `docs/cbor-protocol.md` is executable, and the fixtures are consumed by a second crate — not just by the fixture test.

### Commit 11 — CLI
**Deliverable:** `rtl` with `init`, `insert`, `get`, `query`, `check`, `info`, `dump` (fixture-compatible CBOR in/out).
**Files:** `crates/rtl-cli/src/main.rs` (+ `src/commands/*.rs`), workspace member entry.
**Tests:** end-to-end integration tests driving the binary (`assert_cmd`): create a database, insert, query, `check` reports a clean database, `check` reports a corrupted copy, `info` prints real counts.
**Exit:** every M0 feature is reachable without writing Rust.

### Commit 12 — Hardening and M0 exit
**Deliverable:** the remaining property tests, the full crash matrix as a test, concurrency tests (readers during writers, 8 threads), limit enforcement tests, benches recording numbers, README/roadmap status update, docs/implementation deltas folded back into the design docs.
**Tests:** `cargo test --workspace` plus a documented crash-injection run and a bench run whose numbers are recorded in the milestone report, never asserted.
**Exit:** the M0 checklist in `docs/roadmap.md` is fully green, and every deviation from the design docs is either fixed in the code or recorded in the docs — no silent drift.

---

## Cross-cutting task properties

| Property | Rule |
|---|---|
| Size | one commit per task; a task that grows must be split, not stretched |
| Independence | each task ends with a green gate set and a working artifact |
| Review | a fresh reviewer per task checks the diff against the spec's wording, not against the implementer's summary |
| Reporting | every task reports: Changes / Tests (with the exact commands and their results) / Results / Files / Deviations / Next-safe |
| Fixtures | only Commit 10 may add fixtures; adding one is a contract change and needs a `docs/compatibility.md` note |
| Spec drift | if a task reveals the spec is wrong, fix the spec in the same commit and say so in the report |
| No silent scope | new features discovered mid-task become a task in this plan, never an unannounced addition |

## Risk register

| Risk | Why it matters | Mitigation |
|---|---|---|
| Copy-on-write write amplification | a commit rewrites the root path (typically 3–4 pages) | measured in Commit 12 benches, recorded; grouping and page-size tuning are M1 |
| File growth from pinned generations | a long read transaction or a slow subscriber holds pages | documented limits, timeout on transactions, `rtl vacuum` in M1 |
| Hand-written encoder vs `minicbor` divergence | two implementations of the same bytes | fixture round-trip test plus the independent Python checker in CI from Commit 1 |
| Crash-injection test effort | the honest test of "never a third state" is expensive | injection harness built in Commit 5, reused in Commit 12; a copy of a real database is always the target, never a synthetic file |
| Query sort memory | in-memory sort is a deliberate M0 limit | bounded and reported as `sort_memory_exceeded`; external sort is M1 |
| Spec/implementation drift | a design doc that no longer matches the code is worse than none | every task's report names deviations; Commit 12 folds them back |

## Open decisions (not blockers for Commits 1–8)

1. **License** — before the first public commit.
2. **`write_conflict` granularity** — per document today; per collection is a possible M1 relaxation if measurements demand it.
3. **`Sync::Normal` durability mode** — only with a written failure model; not M0.
4. **Fixture growth** — `rtl-protocol` will add fixtures for the ops that lack one (`collection.list`, `transaction.begin` result, feed `ready`/`end`); each addition needs a compatibility note.
