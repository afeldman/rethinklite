# ADR 0012 — Free-page derivation at open

- Status: Accepted
- Date: 2026-10-03
- Deciders: project author (Anton Feldmann), architecture phase
- Supersedes / Superseded by: —

## Context

The storage engine is copy-on-write: a commit allocates new pages for every
touched tree path, and a crash before the superblock flip leaves those pages
written but unreferenced (`storage.md` §6). The engine must know which pages it
may reuse when the file is opened next. It also has a strong integrity posture:
every page, superblock slot and log record is checksummed, and a failed checksum
is an error, never a silent misread (`architecture.md` §4, I9). The reserved
`freelist` page type exists in the format but is not authoritative in M0
(`storage.md` §4, §15). The question is where the free set comes from before the
engine is proven.

## Decision

1. In M0 the set of free pages is **derived at open** by marking every page
   reachable from the catalog tree, from each collection tree, from overflow
   chains and from the log segments; the remainder in `[2, page_count)` is
   treated as free (`storage.md` §8).
2. The same walk validates: page CRC, page id matching its position, no page
   referenced twice, no page outside the range, no overflow or sibling cycle,
   and leaf-order consistency in every tree. Any violation yields `corruption`
   with the offending page id.
3. Opening a database therefore doubles as its integrity check. There is no
   separate freelist page to trust or to recover.
4. Orphan pages from an interrupted commit are simply part of the derived free
   set; there is no rollback or cleanup pass because nothing was rolled forward.
5. A persisted freelist is an M1 optimisation. The `freelist` page type stays
   reserved and is not authoritative in M0.

## Alternatives considered

- **A persisted freelist in M0.** Rejected: it is more code and brings its own
  recovery semantics before the storage engine is proven, and it becomes a
  second source of truth that could disagree with the page graph.
- **An in-memory-only freelist with a separate consistency test.** Rejected: it
  would lose the self-validating property that opening a database *is* the
  integrity check, and would leave corruption to be found by a test that might
  not run.
- **Trusting page counts in the superblock.** Rejected: a wrong count would hand
  live pages to the allocator with no corruption detection, violating the
  no-silent-misread invariant.

## Consequences

### Positive
- Open is self-validating: a database that opens is one whose page graph is
  consistent and whose pages all checksum.
- No extra on-disk structure and no separate recovery path for a freelist.
- `rtl check` is nearly free because the walk already exists for recovery
  (`storage.md` §11).
- Interrupted commits leave no garbage that needs a cleanup pass.

### Negative / accepted costs
- Open cost is **O(pages)**. For the M0 target sizes (up to a few GB) this is
  milliseconds to a second, but it grows with the file.
- The validating walk runs on every open, including the common uncorrupted case,
  so there is no cheap-open fast path in M0.
- The free set is rebuilt in memory each time rather than persisted, so it is
  not available without the walk.

### Follow-up when the cost becomes relevant
- When open latency on large files becomes measurable, add a persisted freelist
  as the M1 optimisation, with the derived walk retained as the validating
  fallback.
- Any persisted freelist must remain consistent with the page graph; the walk
  stays available to verify it (`storage.md` §15).

## References

- [../storage.md](../storage.md) §4, §6, §8, §11, §15
- [../architecture.md](../architecture.md) §4, §5.1
