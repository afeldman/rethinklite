# ADR 0009 — Concurrency model

- Status: Accepted
- Date: 2026-10-03
- Deciders: project author (Anton Feldmann), architecture phase
- Supersedes / Superseded by: —

## Context

RethinkLite is an embedded library that must be usable as an FFI target. Foreign
function calls are inherently synchronous and block the calling thread, and a
foreign runtime has no way to drive a Rust async executor. The engine must still
support the intended usage — one `Database` shared across threads — and must
satisfy the copy-on-write snapshot requirement that the changefeed design depends
on: a reader holding a snapshot is never blocked by a writer (`architecture.md`
§6, `changefeeds.md` §4). Commits are serialized because M0 has exactly one
writer at a time (`storage.md` §6), and process safety is a single exclusive
`flock` per file (`storage.md` §10).

## Decision

1. The core is synchronous. There is no async runtime and no `tokio` in
   `rtl-core`; calls block, and errors are values.
2. One writer at a time is serialized by a mutex inside `Database`.
3. Readers use copy-on-write snapshots — an `Arc`-pinned immutable
   `Generation` — and are never blocked by writers.
4. `Database`, `Collection` and query handles are `Send + Sync`; sharing a
   `Database` across threads is the intended usage.
5. FFI-friendliness is why async stays outside the core. An async façade and an
   IPC server may exist later as thin layers built on the same synchronous core.
6. Exactly one live `Database` instance per file per process, enforced by an
   exclusive advisory lock; a second open fails with `io` / `already_open`.

## Alternatives considered

- **tokio-based core with async storage I/O.** Rejected: an embedded FFI caller
  is inherently blocking, so an async core would add a runtime dependency that
  every binding would have to reproduce for no gain at embedded scale.
- **Full MVCC with write-conflict detection on every read-write transaction.**
  Rejected: one writer at a time already makes read-write conflicts impossible;
  MVCC would add version bookkeeping that no observable behaviour requires.
- **Lock-free data structures.** Rejected on complexity budget; at embedded
  scale there is not enough contention for them to pay for themselves, and they
  are far harder to test.
- **A reader-writer lock where readers block during commit.** Rejected: it
  breaks the non-blocking snapshots the feed design requires, and would make the
  snapshot–tail guarantee impossible to keep cheap.

## Consequences

### Positive
- No runtime to embed, no executor to spawn; the C ABI is a direct call.
- Readers never block and are never blocked; snapshots are an `Arc` clone.
- The same handle types work from any host thread, which is what makes the
  future IPC and async layers thin.
- One writer removes whole classes of race and makes transaction semantics
  explainable.

### Negative / accepted costs
- Write throughput is limited to one transaction at a time; there is no
  intra-database parallelism for writers.
- Long-lived snapshots pin pages and can grow the file; `rtl vacuum` is an M1
  answer (`storage.md` §8).
- A binding that wants concurrency must expose the mutex/snapshot behaviour
  rather than an async idiom.

### Follow-up when the cost becomes relevant
- When write concurrency becomes a measured bottleneck, revisit whether group
  commit (already an M1 item) is sufficient before considering finer-grained
  writer models.
- When the async façade or IPC server is built, it must remain a thin layer and
  must not move semantics into an async core.

## References

- [../architecture.md](../architecture.md) §4, §6
- [../storage.md](../storage.md) §6, §9, §10
- [../changefeeds.md](../changefeeds.md) §4, §9
