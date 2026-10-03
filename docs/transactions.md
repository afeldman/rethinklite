# RethinkLite — Transactions

Normative for M0. Defines the transaction model, its isolation level, conflict
behaviour, failure semantics and the visible interaction with changefeeds.

---

## 1. Scope

A transaction spans **one database**. Distributed transactions, two-phase
commit and cross-database atomicity are non-goals (`non-goals.md`).

M0 provides:

| Property | M0 |
|---|---|
| Atomicity | all-or-nothing at the superblock flip |
| Consistency | document/collection invariants enforced on write |
| Isolation | **snapshot isolation** (see §4) — not serializable |
| Durability | `Sync::Full` by default; `Sync::None` is explicitly crash-unsafe |
| Concurrent writers | exactly **one** |
| Nested transactions | no; savepoints *(reserved)* |

## 2. API

Rust, closure form (the idiomatic path — cannot be forgotten, cannot leak):

```rust
let result = db.transaction(|tx| {
    tx.collection("users").update(&id, set(doc! { "active": false }))?;
    tx.collection("events").insert(doc! { "kind": "user.deactivated", "user": id })?;
    Ok(())
})?;
```

Explicit handle form (needed when work spans function boundaries or threads):

```rust
let mut tx = db.begin_write()?;
tx.collection("users").update(&id, set(doc! { "active": false }))?;
tx.commit()?;                 // or tx.rollback()?
```

Rules:

* The closure form commits on `Ok(())` and rolls back on `Err(_)` **or panic**
  (the rollback runs in a drop guard, so a panicking caller cannot leave a write
  transaction open).
* A transaction handle holds the single writer; dropping it without calling
  `commit()` rolls back. There is no "implicit commit on drop".
* Read-only work does not need a transaction: every read is already a snapshot.
  `begin_readonly()` exists for multi-statement read consistency — a sequence of
  reads in a read-only transaction sees one snapshot even if a writer commits in
  between.

## 3. What happens in a transaction

```
begin     pin snapshot at commit_seq S  (copy-on-write generation, storage.md §9)
          take the single writer slot (read_only: no slot)
work      reads:  resolve against the pinned generation
          writes: buffered in memory as a write set
                  { collection, id, op, new canonical bytes, prev bytes, prev rev }
commit    (1) conflict check (§4)
          (2) assign commit_seq = last + 1
          (3) build copy-on-write B+tree paths, append log records
          (4) fsync data, flip superblock, fsync     <- atomic
          (5) publish to readers and feeds
rollback  drop the write set; no commit_seq, no log records, no events
```

Reads inside the transaction **never see its own uncommitted writes in M0**;
`get`/`query` resolve against the pinned snapshot. This is a documented M0
limitation: read-your-own-writes inside a transaction is *(reserved)* for M1 and
will require a read-through overlay on the write set. It is stated here rather
than discovered later because the alternative — pretending reads see the buffer —
would silently change isolation semantics.

## 4. Isolation and conflicts

The isolation level is **snapshot isolation** with **first-committer-wins** on
write-write conflicts:

* Every transaction reads a snapshot pinned at `commit_seq = S`.
* At commit, for every document in the write set, if its current `rev` differs
  from the `prev_rev` recorded when the write was buffered, the transaction
  aborts with `conflict` / `write_conflict` and nothing is applied.
* Conflicts are detected on the units actually written (per document), not per
  collection or per database, so disjoint writers never collide.
* **Write skew is possible.** Two transactions that read overlapping data and
  write disjoint documents can both commit with a result that no serial order
  would produce. RethinkLite does not claim serializability in M0, and no
  mechanism in M0 detects read-write conflicts.
* Explicit guards (`if_rev`) are the caller's tool for optimistic concurrency
  independent of transaction boundaries.

Because there is exactly one writer at a time, the conflict check is cheap: it
compares the buffered `prev_rev` against the value in the last committed
generation.

## 5. Atomicity and durability

* The transaction becomes visible when, and only when, its superblock is
  durable. A crash before that point leaves the previous generation as the
  newest valid superblock: the transaction did not happen (`storage.md` §6).
* A crash after the flip: the transaction happened entirely. There is no partial
  transaction state on disk, ever.
* `Sync::None` disables both `fsync` calls. It is for tests and benchmarks and
  is documented as unsafe for process crashes, let alone power loss.

## 6. Failure semantics

| Situation | Behaviour |
|---|---|
| Operation returns an error (`not_found`, `conflict`, `invalid_*`) | the transaction stays open; the caller decides whether to continue |
| Fatal error (`io`, `corruption`, `internal`) | the transaction is marked aborted; every later request in it fails with `transaction` / `aborted`; rollback is implicit |
| Write set exceeds the memory budget | `transaction` / `too_large`; the transaction stays open, nothing is applied; the caller must split the work |
| `limits.transaction_timeout_ms` (default 30000, 0 = off) exceeded | aborted with `transaction` / `timeout` |
| Session closed, process exits, connection lost | aborted; no durable effect |
| Second `begin_write()` while a writer is active | `conflict` / `writer_busy`, `retryable: true` |

## 7. Changefeeds and transactions

* All changes of a committed transaction share **one** `commit_seq` and are
  delivered together, ordered by collection then key order
  (`changefeeds.md` §6).
* A rolled-back or aborted transaction produces **no** events.
* A no-op transaction (all writes idempotent) consumes no `commit_seq` and emits
  nothing; `transaction.commit` returns `{"commit_seq": null, "written": 0,
  "unchanged": true}`.
* Buffering writes in memory means a subscriber never observes an intermediate
  state of a transaction in progress.

## 8. Bounds

| Bound | M0 value | Notes |
|---|---|---|
| Concurrent read-write transactions | 1 | second writer gets `writer_busy` |
| Concurrent read-only transactions | unbounded (they pin generations) | a very old read transaction grows the file, see `storage.md` §8 |
| Write-set memory | 256 MiB default, configurable | spilling to disk *(reserved)* |
| Transaction duration | 30 s default timeout | prevents a forgotten transaction from pinning pages forever |

Long-lived read snapshots and long-lived writers are the two ways an application
can make the file grow. Both are bounded by explicit limits and both release
their pages when they end.

## 9. Wire mapping

`transaction.begin` → `{"transaction": n, "commit_seq": S, "isolation":
"snapshot"}`; requests inside the transaction carry `"transaction": n` in the
envelope and report `"commit_seq": null`; `transaction.commit` →
`{"commit_seq": m, "written": k, "unchanged": false}`. A single-round-trip
atomic batch (`transaction.execute`) is specified as *(reserved)* and will be
added in M1, because it changes nothing about the semantics above — it only
removes round trips.

## 10. Tests

| Property | Test |
|---|---|
| Atomicity | kill/crash between data sync and superblock flip: reopen must show the pre-transaction state; corruption injected into the second superblock slot must leave the first usable |
| All-or-nothing visibility | a reader polling during a write transaction never observes a partially applied write set (readers hold the previous generation by construction) |
| Rollback | no `commit_seq`, no log record, no event, no `rev` change |
| Conflict | two writers touching the same document → second commit fails with `write_conflict`; disjoint write sets → both succeed |
| Isolation boundary | an intentionally write-skewed pair of transactions is allowed to commit — the test documents the limitation rather than pretending it is absent |
| Timeout | a transaction idle past the timeout aborts and releases the writer slot |
| Idempotence | a transaction whose writes change nothing consumes no `commit_seq` |
