# ADR 0003 — Copy-on-write B+tree with a superblock commit point

- Status: Accepted
- Date: 2026-10-03
- Deciders: project author (Anton Feldmann), architecture phase
- Supersedes / Superseded by: —

## Context

RethinkLite is an embedded, single-file database in which readers must never be
blocked by the writer (invariant I5), subscriptions require an ordered durable
history (I8), and recovery must never expose uncommitted state (I3, I4). A
snapshot must be cheap enough to hand to every subscriber without locks. These
forces together rule out in-place pages plus WAL redo and fix what the log stores.

## Decision

1. Everything lives in one file: a copy-on-write B+tree with two superblock
   slots.
2. The superblock flip is the only commit point; a commit is visible if and only
   if its superblock is durable and valid. There is no redo replay.
3. Readers hold a generation (an immutable page set plus roots plus `commit_seq`)
   pinned by `Arc`; they never block and are never blocked.
4. The ordered change log is stored as log segments inside the same file, and
   each record stores both sides of the change (`old_bytes`/`new_bytes`), so the
   log is self-contained for subscription resumption and replication.
5. Recovery selects the newest valid superblock, truncates the log to the offset
   it commits, and derives the free set by walking the catalog, every collection
   tree and every log segment — there is no persisted freelist in M0.
6. A commit performs two `fsync` calls: data (pages plus log) then superblock.
   Group commit is deferred to M1.
7. No `mmap`; positional `pread`/`pwrite` through a bounded page cache, so file
   extension cannot raise `SIGBUS` and crash semantics are testable on a copy.

## Alternatives considered

* **In-place slotted pages plus WAL redo** — rejected because snapshot readers
  would need SQLite-style WAL-index machinery or would have to block the writer,
  contradicting I5, and a redo pass reintroduces a partial-commit state the
  copy-on-write design avoids.
* **An append-only document log with a derived index** — rejected because it
  makes compaction a second engine and creates two sources of truth; point
  lookups would degrade to scanning the derived index.
* **SQLite as the storage backend** — rejected because it bends the document
  model, couples the file format and locking to SQLite, and contradicts the
  explicit non-goal of being a JSON layer over SQLite.
* **An LSM tree** — rejected as disproportionate for an embedded M0; the
  compaction and read-amplification machinery is unnecessary at target sizes.

## Consequences

### Positive

* Reads never block writes and writes never block reads; snapshots are free and
  can be long-lived, which is what makes the snapshot-then-tail feed correct.
* The commit protocol has exactly one atomic step, so there is no partial commit
  and no separate WAL or journal file.
* Recovery is also the integrity check, and orphaned pages from an interrupted
  commit are simply free space.

### Negative / accepted costs

* Write amplification: a commit rewrites the root path, typically 3–4 pages.
* The file grows until pages are reclaimed; `rtl vacuum` is deferred to M1.
* A long-lived reader or slow subscriber pins its generation and can grow the
  file (the cost LMDB also accepts for non-blocking snapshots).
* Open cost is O(pages) because the free set is derived by walking.

### Follow-up when the cost becomes relevant

* Persist the freelist and add `rtl vacuum` in M1 when file growth bites.
* Add group commit when sync latency dominates; `commit_seq` assignment is
  already independent of the sync cadence.
* An `mmap` fast path is M2 and must not change the commit protocol.

## References

* [Storage engine](../storage.md)
* [Architecture §4, §5](../architecture.md)
* [Changefeeds §4](../changefeeds.md)
