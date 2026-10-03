# ADR 0010 — commit_seq and changefeeds

- Status: Accepted
- Date: 2026-10-03
- Deciders: project author (Anton Feldmann), architecture phase
- Supersedes / Superseded by: —

## Context

Reactive subscriptions are a first-class feature, not a polling layer
(`architecture.md` §1). A subscriber must take an initial snapshot and then
receive every change after it without gaps or duplicates, and a reconnecting
subscriber must resume from where it stopped. That needs one ordering shared by
the durable change log, the changefeeds, and the replication offset the format
reserves (`changefeeds.md` §12). The ordering must be a commit boundary, so it
cannot be a clock, and it must be durable to serve as a resume position. The
storage engine already writes an ordered log; this decision fixes what that
ordering means to subscribers.

## Decision

1. There is one monotonic `u64` `commit_seq` per database, incremented once per
   committing transaction and shared by all the changes of that transaction.
2. The durable change log is ordered by `commit_seq` and is at once the changefeed
   source, the subscriber resume position and the replication offset.
3. A feed is the change stream of an **expression's result set**, typed by
   membership before and after: `added`, `updated`, `replaced`, `deleted`. A
   change to a document matching neither before nor after produces no event.
4. The snapshot-then-tail transition is gapless by construction: the snapshot is
   pinned at `S` and the tail starts at `S + 1` in the same total order, so the
   two halves partition the history.
5. Log records store both the old and the new canonical bytes. A feed is
   therefore self-contained: it never looks up a pre-image in the tree, and a
   resumed feed reproduces the same `old` values as a live one.
6. Retention of the log is bounded. A `from_seq` below the retained head yields
   `changefeed` / `log_truncated` (`retryable: false`), which the client resolves
   by resubscribing with `include_initial: true`.

## Alternatives considered

- **Per-collection sequences.** Rejected: no single order across collections, so
  no consistent resume position and no replication offset.
- **Wall-clock timestamps as sequence numbers.** Rejected: clocks are not
  monotonic across processes and cannot mark a commit boundary; `commit_seq` is
  assigned at commit, the only well-defined point.
- **A pre-image page reference instead of old bytes.** Rejected: pages are
  reclaimed once the last snapshot pinning them is gone, so resumption would
  depend on timing.
- **Polling instead of a feed.** Rejected: polling cannot express membership
  transitions or per-transaction atomic delivery, and cannot be gapless.
- **Feed delivery inside the writer lock.** Rejected: a slow subscriber would
  block writers and other subscribers; fan-out happens after the commit point,
  outside the lock (`changefeeds.md` §7).

## Consequences

### Positive
- One ordering serves feeds, resume and future replication; snapshot–tail
  continuity is structural, both halves coming from one ordered history.
- Idempotent writes consume no `commit_seq` and emit nothing, preventing event
  storms on retried or replicated writes.
- A resumed feed reproduces exactly the events a live one would have produced.

### Negative / accepted costs
- Log records roughly double in volume for updates because `old_bytes` are stored
  rather than referenced.
- Retention is a hard bound: a subscriber behind the head pays for a full snapshot
  resync, and an expensive feed expression is expensive per commit.

### Follow-up when the cost becomes relevant
- Revisit compression of stored change bytes via a format bump if log volume
  becomes the bottleneck, never by dropping `old` bytes; tune
  `limits.log_retention_bytes` per workload before adding new recovery paths.

## References

- [../changefeeds.md](../changefeeds.md) §1, §3, §4, §5, §6, §8, §12
- [../storage.md](../storage.md) §6, §7
- [../cbor-protocol.md](../cbor-protocol.md) §6.6, §7, §8
- [../architecture.md](../architecture.md) §4, §5.3
