# RethinkLite — Changefeeds

Normative. Defines what a subscription is, what the engine guarantees, and how
it is carried over CBOR. The wire shape is already frozen in
`cbor-protocol.md` §6.6/§7; this document defines the semantics behind it.

M0 status: the durable log, `commit_seq` and a crate-internal change iterator
are M0 (they are the storage-level primitives). The public `collection.watch`
API and streamed delivery are **M1** — the protocol was frozen now so that
fixtures, bindings and tests can be built against it.

---

## 1. Model

A subscription is opened over an **expression** (the same term tree as a query,
restricted to `scan`, `filter` and `project` in M1) and delivers the stream of
changes to that expression's **result set** — not the stream of changes to the
collection.

```
watch( filter( eq(field("active"), true) ) )
```

emits an event when a document *enters*, *changes within*, or *leaves* the set
of active documents. A change to a document that matches neither before nor
after the change is not an event.

## 2. Lifecycle

```
subscribe ──▶ initial* ──▶ ready ──▶ live* ──▶ end | error
                │                     │
                └── documents matching the expression at snapshot_seq S
                                      └── events with commit_seq > S
```

* `initial` events are sent only when `include_initial` is true (default).
* `ready` marks the transition; it carries `commit_seq = S`. Clients that need
  to distinguish "state" from "δ" have exactly one unambiguous boundary.
* With `include_initial: false` the feed starts at the current position and
  emits only live events; `snapshot_seq` is then `null`.
* `from_seq: N` starts a feed from the durable log instead (resume path, §8);
  `include_initial` and `from_seq` are mutually exclusive.

## 3. Change typing

Membership "before" and "after" decide the event type:

| matched before | matched after | document | event |
|---|---|---|---|
| no | yes | inserted or newly matching | `added` |
| yes | yes | partially updated | `updated` |
| yes | yes | wholly replaced | `replaced` |
| yes | no | deleted or no longer matching | `deleted` |
| no | no | anything | *(no event)* |

`updated` versus `replaced` reflects the operation (`collection.update` versus
`collection.replace`); both carry `old` and `new`.

Only *effective* writes produce events: a write that does not change the
canonical document bytes is a no-op (`data-model.md` §4.1) and emits nothing.
This is what keeps reactive clients from waking up on idempotent retries.

## 4. The snapshot–tail guarantee

**Invariant (normative).** The `initial` events are exactly the documents
matching the expression at `commit_seq = S`, and every subsequent event has
`commit_seq > S`. No document is delivered twice, none is missed.

Why this holds, in two sentences: the `initial` events are produced from a
copy-on-write **snapshot pinned at S** (immutable pages, `storage.md` §9), and
the live events are produced from the **durable ordered log**, filtering
`commit_seq > S`. Because both come from the same total order and S is a commit
boundary, the two halves partition the history — there is no window in which a
write could fall between them and no overlap.

This is the reason the storage design is copy-on-write with an ordered log, and
it is the first property to test (§11).

## 5. Event content

| Field | Meaning |
|---|---|
| `commit_seq` | the commit that produced the change; the feed's position and the replication offset |
| `rev` | the document's revision *after* the change (`new` side) |
| `id` | stable document identity (same encoding as everywhere else) |
| `old` / `new` | canonical document bytes for the before/after side, or `null` |

`old` is filled from the log record, which stores both sides of every change
(`storage.md` §7). That makes a feed self-contained: it never needs to look up a
pre-image in the tree, so a resumed or replicated feed produces exactly the same
`old` values as a live one.

## 6. Ordering and atomicity

* Per feed, `commit_seq` is strictly increasing.
* All events of one committed transaction share one `commit_seq` and are
  delivered together, ordered by collection then key order. A subscriber never
  observes half a transaction.
* Across feeds there is no interleaving guarantee; a client that needs a global
  order across collections uses one feed over the affected collections (M1) or
  sorts by `commit_seq`.
* A rolled-back transaction produces **no** events at all — rollback discards
  buffered changes before a `commit_seq` is ever assigned.

## 7. Delivery, backpressure and fairness

* Each subscriber has a bounded queue (`limits.feed_queue`, default 1024
  events). Fan-out happens after the commit point, outside the writer's lock, so
  a slow subscriber can never block a writer or another subscriber.
* Overflow policy per feed:
  * `disconnect` (default): the feed ends with `changefeed` / `feed_overflow`
    (`retryable: true`). The client resubscribes by `from_seq` — it does not
    have to re-read a snapshot.
  * `drop`: oldest events are discarded and a `dropped` event with the count is
    emitted. The client's view is now known-partial; the honest default is
    `disconnect`.
* Resource accounting: `limits.feeds` (default 64 concurrent feeds per
  database) and `limits.feed_memory` bound the total queue memory. Exceeding
  them is `changefeed` / `too_many_feeds`.

## 8. Resume, retention and reconnect

The durable log is the resume mechanism. Retention is bounded
(`limits.log_retention_bytes`, default 64 MiB) and additionally bounded below by
the oldest live subscriber and (later) the replication position.

```
client: last_seen = 4711
reconnect: watch(from_seq = 4712)
   ok                -> gap-free continuation, including correct `old` values
   changefeed/log_truncated
                     -> watch(include_initial: true)   # always correct, costs a snapshot
```

`log_truncated` is `retryable: false` on purpose: retrying the identical request
cannot succeed. The client changes the request — that is the difference between
a conflict and a failure, and the protocol says so explicitly.

## 9. Cancellation and lifetime

* Feeds are scoped to a session. Closing the session or the process cancels
  them; `end` with `reason: "closed"` is sent when the transport still allows it.
* `feed.cancel` / `cancel` cancels explicitly; the feed then emits `end` with
  `reason: "cancelled"`.
* In the Rust API, dropping the last `WatchHandle` cancels the feed
  deterministically — no background task keeps running.
* A cancelled feed releases its queue and its pinned snapshot, which matters for
  file growth (`storage.md` §8).

## 10. Rust API

M0 (crate-internal, drives the tests):

```rust
// rtl-core, not public in M0
let mut changes = db.changes_from(commit_seq)?;   // ordered, log-backed
let record = changes.next_commit()?;              // all changes of one commit
```

M1 (public):

```rust
let feed = users.watch().filter(eq(field("active"), true)).include_initial(true).open()?;
for event in feed.iter() {          // blocking iterator, one per event
    match event? { /* added / updated / replaced / deleted / ready / end */ }
}
```

Both shapes exist because the two consumers differ: an embedded Rust program
wants an iterator, the IPC layer wants a callback or a channel per connection.
The semantics are identical; only the delivery shape differs.

## 11. Tests

| Property | Test |
|---|---|
| Snapshot–tail continuity | concurrent writer + `watch(include_initial)`: the union of `initial` and live events must equal a deterministic replay of the write history; no duplicate ids, no missing ids (property test over random histories) |
| Ordering | `commit_seq` strictly increasing per feed; per-commit grouping intact |
| Transaction visibility | rollback emits nothing; a committed transaction emits all its changes with one `commit_seq` |
| Membership typing | all five rows of §3 including "leaves the set by no longer matching" |
| Idempotence | re-writing identical bytes emits nothing |
| Backpressure | a subscriber that never reads triggers `disconnect` (default) or `dropped` (policy `drop`), while the writer's throughput is unaffected |
| Resume | `from_seq` after a simulated subscriber disconnect reproduces exactly the events the subscriber missed, `old` values included |
| Retention | forcing the head forward yields `log_truncated`, and resync via `include_initial` restores correctness |

## 12. Replication reuse

The same log that feeds subscribers is the replication stream: `(database_uuid,
commit_seq)` is a replication offset, and log records carry both sides of every
change. Replication is not M0 (`non-goals.md`), but the primitives are already
in the format: database UUID, stable collection ids, transaction-scoped
`commit_seq`, document revisions, retention/offset. A future replica is a
special subscriber whose position is durable — no new ordering concept is
introduced.
