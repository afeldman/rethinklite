# RethinkLite — CBOR Protocol Specification (version 1)

Normative. This document defines the boundary between the Rust core and every
other language, process or tool. `rtl-protocol` implements exactly this
document and nothing else.

Protocol version: **1** · Storage format version: **1** · M0 status per
operation: `M0` = implemented in M0, `frozen` = specified and frozen now,
implementation later.

---

## 1. Principles

1. **One contract, no privileged language.** Rust is the reference
   implementation, not a special case. If a construct cannot be expressed with
   a stock CBOR library in another language, it does not belong in the protocol.
2. **No proprietary framing, no proprietary tags.** Streams are CBOR Sequences
   (RFC 8742); tags are IANA-registered or absent (`adr/0004-cbor-protocol.md`).
3. **Readable first.** Field names are full words. A compact profile with
   integer keys and numeric opcodes is *(reserved)* and will be negotiated as a
   capability, never made mandatory.
4. **Additive evolution.** Within protocol major 1, fields may be added and
   operations may be added; existing semantics may not change
   (`compatibility.md`).
5. **The core owns semantics.** Bindings may not normalize, validate or rewrite
   payloads beyond transport concerns.

## 2. Encoding rules

* RethinkLite **emits** deterministically encoded CBOR per RFC 8949 §4.2.1 with
  length-first key ordering (§4.2.3).
* RethinkLite **accepts** non-deterministic CBOR on input (indefinite-length
  items, non-shortest integers, unsorted map keys) and canonicalizes it.
* Map keys in requests and responses are text strings. Documents additionally
  require text keys everywhere (`data-model.md` §2.1).
* Documents inside payloads use exactly the value model of `data-model.md`.

## 3. Transport and framing

The protocol is framed by **CBOR Sequences** (RFC 8742): a concatenation of
self-delimiting CBOR data items, media type `application/cbor-seq`. There is no
length prefix, no delimiter, no header.

| Transport | Rule |
|---|---|
| Byte stream (Unix socket, pipe, file) | items are concatenated; a reader parses one item at a time from its buffer |
| Message transport (WebSocket binary frame, datagram) | exactly one item per message is also valid |
| C ABI | one item in, one item out per call: `(ptr, len)` → `(ptr, len)`; no framing at all |
| Fixture file | a CBOR Sequence; no self-describe tag, bytes are normative |

An implementation that needs explicit boundaries may wrap a whole sequence in
tag 63 ("Encoded CBOR Sequence"), which is standard and transparent. Clients
must not invent their own length prefix: it is unnecessary (CBOR items are
self-delimiting), and it breaks cross-language interop.

## 4. Envelope

### 4.1 Request

```
{
  "protocol":    1,                       # uint, required, must equal 1 here
  "request":     42,                      # uint, required, client-assigned
  "operation":   "collection.insert",     # text, required
  "transaction": 7,                       # uint, optional; explicit txn only
  "body":        { ... }                  # map, optional; op-specific
}
```

| Field | Rules |
|---|---|
| `protocol` | required. A value other than the negotiated version is a `protocol` / `version_unsupported` error. |
| `request` | required, 0 ≤ id < 2^63. Unique among in-flight requests of the same session. Reuse is `protocol` / `duplicate_request`. |
| `operation` | required, one of §6. Unknown names are `protocol` / `unknown_operation`. |
| `transaction` | present if and only if the request participates in an explicit transaction (§8). Unknown or closed id is `protocol` / `unknown_transaction`. |
| `body` | absent, or a map. No other type. |

### 4.2 Response

```
{ "protocol": 1, "request": 42, "status": "ok",    "body":  { ... } }
{ "protocol": 1, "request": 42, "status": "error", "error": { ... } }
```

* Exactly one of `body` / `error` is present, matching `status`.
* Responses may arrive out of order; `request` correlates them.
* One request produces exactly one response **unless** it opens a stream (§7),
  in which case the response opens the stream and items follow.

### 4.3 Error object

```
{
  "kind":      "conflict",              # coarse, closed set: error-model.md §2
  "code":      "document_exists",       # fine-grained, stable, snake_case
  "message":   "document with this id already exists",   # human, unstable
  "retryable": false,                   # identical request may succeed later?
  "details":   { "id": "user-123" }     # optional, code-specific, machine-readable
}
```

`message` is for humans and must never be parsed. `kind` is closed and drives
binding-level error types. `retryable` refers to *the identical request*;
conflicts (`document_exists`, `revision_conflict`) are `false` because the
client must change something.

## 5. Handshake and capability negotiation

Every session starts with `hello`. Embedding a single-shot call without a
handshake is allowed, in which case protocol version 1 and the default feature
set are assumed — but a client that wants to detect features MUST send `hello`
first.

**Request**

```
{ "protocol": 1, "request": 1, "operation": "hello",
  "body": {
    "client":   { "name": "rethinklite-python", "version": "0.1.0" },
    "protocol": [1],                       # versions the client can speak
    "features": ["transactions", "watch"], # features the client can use
    "required": ["transactions"]           # features it cannot work without
  } }
```

**Response**

```
{ "protocol": 1, "request": 1, "status": "ok",
  "body": {
    "server":   { "name": "rethinklite", "version": "0.1.0", "engine": "0.1.0" },
    "protocol": 1,
    "database": { "uuid": h'018f...', "format": 1, "path": "example.rtl" },
    "features": ["transactions", "count", "cancel"],
    "limits": {
      "document_bytes": 16777216,        # max document size
      "query_results": 100000,           # max documents per query response
      "feed_queue": 1024,                # max queued events per feed
      "log_retention_bytes": 67108864,   # durable change-log retention
      "transaction_timeout_ms": 30000    # 0 = no timeout
    }
  } }
```

Rules:

* Version selection: the highest version in `protocol` ∩ supported. No overlap →
  `protocol` / `version_unsupported` (the response then uses protocol 0 to be
  parseable by the peer's major-version-agnostic reader: `{"protocol":0,
  "request":n,"status":"error","error":{...}}`).
* `features` is the intersection of what the client offered and what the engine
  supports; both sides MUST ignore features they do not know and MUST fail with
  `protocol` / `feature_required` if a member of `required` is not granted.
* Unknown fields in `hello` (and everywhere else) are ignored, never rejected.
* Feature registry (v1): `transactions` (M0), `count` (M0), `cancel` (M0),
  `watch` (frozen, M1), `cursors` (reserved), `indexes` (reserved),
  `strict_cbor` (reserved), `compact_profile` (reserved).

## 6. Operations

`collection` is always a collection name (text, §7 of `data-model.md`).

### 6.1 Session

| Operation | Body in | Body out | M0 |
|---|---|---|---|
| `hello` | §5 | §5 | M0 |
| `close` | — | `{}` | M0 |
| `cancel` | `{"request": <uint>}` | `{"request":n,"cancelled":<bool>}` | M0 |

`close` flushes, releases the file lock and (in a daemon) ends the session.
Pending feeds end with `reason: "closed"`; open transactions abort.

`cancel` requests cancellation of an in-flight request by its id. Cancellation
is cooperative and checked between work units; a query that has already
produced its response reports `"cancelled": false`.

### 6.2 Collections

| Operation | Body in | Body out | M0 |
|---|---|---|---|
| `collection.create` | `{"collection":n,"if_not_exists":<bool>?}` | `{"collection":n,"collection_id":<uint>,"commit_seq":<uint>}` | M0 |
| `collection.drop` | `{"collection":n,"if_exists":<bool>?}` | `{"collection":n,"collection_id":<uint>,"commit_seq":<uint>}` | M0 |
| `collection.list` | `{}` | `{"collections":[{"name":n,"collection_id":<uint>,"documents":<uint>,"created_seq":<uint>}, …]}` | M0 |

`collection_id` is a monotonically assigned `uint` that is never reused for the
lifetime of the database — the stable identifier later needed for replication.
DDL is transactional like any other write and consumes one `commit_seq`.

### 6.3 Documents

**`collection.insert`**

```
in : { "collection": "users",
       "document":   { "name": "Anton", "active": true },   # `id` optional
       "return_document": false }
out: { "id": <id>, "rev": 1, "commit_seq": 42, "unchanged": false,
       "document": { ... } }                                  # if requested
```

Fails with `conflict` / `document_exists` if the id exists. A generated id is a
UUIDv7 (tag 37), returned as `id`. NOTE: `insert` never overwrites and never
upserts — that is `replace`.

**`collection.get`**

```
in : { "collection": "users", "id": <id> }
out: { "id": <id>, "rev": 3, "commit_seq": 44, "document": { ... } }
```

`not_found` / `document_not_found` when absent. The stored canonical bytes are
returned unchanged.

**`collection.update`** — partial, shallow, `set`/`unset`, requires existence

```
in : { "collection": "users", "id": <id>,
       "set":   { "active": false },       # optional, shallow merge
       "unset": [ "nickname" ],            # optional, top-level key removal
       "if_rev": 3 }                       # optional optimistic guard
out: { "id": <id>, "rev": 4, "commit_seq": 45, "unchanged": false }
```

`set` and `unset` are separate so that `null` is an ordinary value and there is
no null-versus-delete ambiguity. `unset` on a missing key is not an error.
`not_found` if the document does not exist; `conflict` / `revision_conflict` if
`if_rev` does not match.

**`collection.replace`** — insert-or-replace (full document)

```
in : { "collection": "users", "id": <id>, "document": { ... }, "if_rev": 3 }
out: { "id": <id>, "rev": 1, "commit_seq": 45, "created": true,
       "unchanged": false }
```

**`collection.delete`**

```
in : { "collection": "users", "id": <id>, "if_rev": 3 }
out: { "id": <id>, "rev": 3, "commit_seq": 46, "deleted": true }
```

### 6.4 Query and count

```
in : { "collection": "users",
       "expr": [ "limit", 20, [ "sort", ["field","age"], "desc",
                 [ "filter", ["gt", ["field","age"], 30], ["scan"] ] ] ],
       "params": [ ... ],              # optional, bound by ["param", i]
       "include_meta": false }         # optional, adds `meta`
out: { "documents": [ { ... }, ... ],
       "returned": 20, "scanned": 41, "truncated": true,
       "meta": [ {"rev":3,"commit_seq":44}, ... ] }   # if include_meta
```

* `documents` is the result in expression order; documents are spliced in as
  stored bytes (no re-encode).
* `returned` = length of `documents`; `scanned` = documents examined;
  `truncated` = `true` if further matches were dropped by `limit` or by
  `limits.query_results`.
* Exceeding `limits.query_results` is `invalid_query` /
  `result_limit_exceeded` (retryable false, add `limit` or paginate with
  `skip`). Offset pagination is `skip` + `limit` — correct but O(n) in M0.
  Cursors are *(reserved)*.

```
in : { "collection": "users", "expr": <source chain>, "params": [...] }
out: { "count": 41, "scanned": 128, "exact": true }
```

`collection.count` never materializes documents; `exact` is `true` in M0.

### 6.5 Transactions

| Operation | Body in | Body out | M0 |
|---|---|---|---|
| `transaction.begin` | `{"mode":"read_write"\|"read_only"?}` | `{"transaction":<uint>,"commit_seq":<uint>,"isolation":"snapshot"}` | M0 |
| `transaction.commit` | `{"transaction":<uint>}` | `{"commit_seq":<uint>\|null,"written":<uint>,"unchanged":<bool>}` | M0 |
| `transaction.rollback` | `{"transaction":<uint>}` | `{"transaction":<uint>,"rolled_back":true}` | M0 |
| `transaction.execute` | `{"ops":[...],"mode":…}` | as if the ops were sent individually | reserved |

Requests inside a transaction carry `"transaction": <id>` in the envelope.
Details and guarantees: `transactions.md`.

### 6.6 Changefeeds

`collection.watch` is **frozen** in protocol v1 and implemented in M1. Its wire
shape is specified here so that bindings and fixtures can be built now.

```
in : { "collection": "users",
       "expr": [ "filter", ["eq", ["field","active"], true], ["scan"] ],
       "include_initial": true,        # default true
       "from_seq": 4711,               # optional; mutually exclusive with include_initial
       "overflow": "disconnect" }      # "disconnect" (default) | "drop"

out: { "feed": 3, "snapshot_seq": 4710,  # null when include_initial=false
       "database_uuid": h'018f...', "collection": "users" }
```

Then items stream as a CBOR Sequence, one item per event (§7).

## 7. Streaming

A stream is opened by a normal response; items follow it on the same transport
as a CBOR Sequence. Each item:

```
{ "feed": 3,
  "event": { "type": "updated", "commit_seq": 4711, "collection": "users",
             "id": "user-123", "rev": 4,
             "old": { ... }, "new": { ... } } }
```

The `feed` id allows several concurrent feeds on one connection (essential over
IPC, irrelevant but harmless in-process).

| `type` | Meaning | Fields |
|---|---|---|
| `initial` | one document matching the expression at `snapshot_seq`, sent before `ready` | `commit_seq = snapshot_seq`, `rev`, `new` |
| `added` | document inserted after the snapshot | `old: null`, `new` |
| `updated` | partial update after the snapshot | `old`, `new` |
| `replaced` | full replacement after the snapshot | `old`, `new` |
| `deleted` | document removed after the snapshot | `old`, `new: null` |
| `dropped` | events were discarded (overflow policy `drop`) | `count` |
| `ready` | initial snapshot complete; only `commit_seq > snapshot_seq` follows | `commit_seq` |
| `end` | feed ended normally | `reason`: `cancelled` \| `closed` |
| `error` | feed ended abnormally; always the last item | `kind`, `code`, `message`, `retryable` |

Guarantees (normative, tested):

1. **Snapshot–tail continuity.** The `initial` events are exactly the documents
   matching the expression at `snapshot_seq = S`, and every subsequent event has
   `commit_seq > S`. No document is delivered twice and none is missed across
   the transition, because both parts are read from one ordered history.
2. **Order.** Per feed, `commit_seq` is strictly increasing. Events sharing a
   `commit_seq` are ordered by `collection` then key order, and are exactly the
   changes of one committed transaction.
3. **Atomicity visibility.** A rolled-back transaction produces no events; a
   committed transaction's events all share one `commit_seq`.
4. **History consistency.** `old` of an event equals `new` of the previous event
   for that document within the feed (or the `initial`/`added` document).
5. **Termination.** After `end` or `error`, no further item is sent for that
   feed.

Backpressure and recovery:

* Each feed has a bounded queue (`limits.feed_queue`). Overflow policy
  `disconnect` (default) ends the feed with `changefeed` / `feed_overflow`
  (`retryable: true`); policy `drop` discards oldest events and emits `dropped`
  with the count, after which the client must treat its view as partial.
* The durable log has bounded retention. `from_seq` below the oldest retained
  sequence is `changefeed` / `log_truncated` (`retryable: false`); the client
  recovers by resubscribing with `include_initial: true`.
* Feed ids are scoped to the session. Closing the session cancels its feeds,
  after emitting `end` when the transport still allows it.
* Reconnect procedure for clients: remember the highest `commit_seq` seen and
  resubscribe with `from_seq = last + 1`; if that fails with `log_truncated`,
  resubscribe with `include_initial`, which is always correct.
* Feed event payloads are subject to the same document size limits; a document
  too large to stream is an error only for that document (`changefeed` /
  `event_too_large`), never a silent skip.

`feed.cancel` *(frozen)*: `{"feed": 3}` → `{"feed": 3, "cancelled": true}`,
equivalent to `cancel` on the opening request.

## 8. Transactions over the wire

```
req  transaction.begin           -> {"transaction":7,"commit_seq":44,"isolation":"snapshot"}
req  collection.update  txn:7    -> {...,"commit_seq":null}   # not yet assigned
req  collection.insert  txn:7    -> {...,"commit_seq":null}
req  transaction.commit   txn:7  -> {"commit_seq":45,"written":2,"unchanged":false}
```

* Requests inside a transaction report `commit_seq: null` because the value is
  assigned at commit; responses nonetheless report the document's `rev` as it
  will be after commit (deterministic, buffered).
* A failed request does not abort the transaction, except fatal errors
  (`io`, `corruption`), which abort it and make every later request in that
  transaction fail with `transaction` / `aborted`.
* One read-write transaction at a time. A second `transaction.begin` with
  `mode: read_write` while a writer is active fails with `conflict` /
  `writer_busy` (`retryable: true`).
* Session loss, timeout (`limits.transaction_timeout_ms`), or `close` aborts open
  transactions with no durable effect.
* `transaction.commit` with no effective writes consumes no `commit_seq` and
  returns `{"commit_seq": null, "written": 0, "unchanged": true}`.

## 9. Query expressions (term language)

The expression is a CBOR term tree. Same semantics in every language; a
language binding builds it with idiomatic syntax and serializes it verbatim.

```
term    := [ <text: op>, <argument>… ]      # array, first element is the op name
argument:= term | literal
literal := any CBOR value that is not an array
         | ["lit", <any CBOR value>]        # explicit literal, also for arrays
         | ["param", <uint>]                # index into the request's `params`
```

Disambiguation rule: **in argument position, an array is always a term.** A
literal array therefore requires `["lit", …]`. This one rule removes every
ambiguity, including for field names that happen to look like ops.

Operators (v1, M0 unless marked):

| Operator | Arity | Semantics |
|---|---|---|
| `scan` | 0 | the collection named in the request body (the only M0 source) |
| `filter` | predicate, source | keep documents where predicate is true |
| `project` | `["name", …]`, source | keep listed top-level fields; `id` is always kept |
| `sort` | key term, `"asc"\|"desc"`, source | total order per `data-model.md` §6 |
| `limit` | uint, source | at most n documents |
| `skip` | uint, source | drop the first n documents |
| `get` | id, source | the document with that id, if present |
| `eq, ne, gt, ge, lt, le` | value, value | comparison; numeric across Int/Float |
| `and, or` | value… (≥2) | boolean, non-short-circuit may be used |
| `not` | value | boolean negation |
| `in` | value, array-or-sequence | membership |
| `contains` | array-expr, value | array contains value |
| `exists` | field/path term | true if the path exists (distinguishes `null` from absent) |
| `field` | name, source? | top-level field value; `null` if absent |
| `path` *(reserved)* | dotted path | nested access |
| `matches` *(reserved)* | regex, value | regular expression |
| arithmetic (`add`, `sub`, …) *(reserved)*, `now` *(reserved)*, `type_of` *(reserved)* | | |

Rules:

* `["scan"]` is the root of a regular query. `["scan", "other"]` (multi-source)
  is *(reserved)*.
* Arity and argument types are checked before execution; violations are
  `invalid_query` / `bad_arity` or `bad_argument_type`.
* Comparisons on opaque tagged values are `invalid_query` /
  `unsupported_comparison`.
* No operator performs I/O, calls out, or evaluates code. There is no string
  DSL and no escaping problem.
* `project` with an unknown field is not an error; the field is simply absent.

Diagnostic example (a real fixture, `tests/cbor/query_request.cbor`):

```
{ "protocol": 1, "request": 2, "operation": "collection.query",
  "body": { "collection": "users", "include_meta": false,
            "expr": [ "limit", 20,
                      [ "sort", ["field", "age"], "desc",
                        [ "filter", ["gt", ["field","age"], 30], ["scan"] ] ] ] } }
```

## 10. Golden fixtures

`tests/cbor/` contains normative byte fixtures: `insert_request.cbor`,
`insert_response.cbor`, `get_response.cbor`, `query_request.cbor`,
`query_response.cbor`, `count_response.cbor`, `transaction_request.cbor`,
`watch_request.cbor`, `change_event.cbor`, `error_response.cbor`,
`hello_request.cbor`, `hello_response.cbor`, plus `MANIFEST.md` (fixture → bytes
→ SHA-256 → intent).

Conformance requirement for any implementation:

1. decode every request fixture without error;
2. re-encode it deterministically and obtain **byte-identical** output;
3. produce response fixtures that match byte-for-byte where the fixture is
   marked `canonical: exact`.

Because the fixtures are plain CBOR Sequences, a Go program with `fxamacker/cbor`
or a Python program with `cbor2` can be checked against them in a few lines —
that is the point.

## 11. Error mapping

`kind` is the closed coarse set (`io`, `corruption`, `serialization`,
`invalid_document`, `invalid_query`, `not_found`, `conflict`, `transaction`,
`index`, `changefeed`, `protocol`, `internal`). `code` is the fine-grained,
stable identifier. Bindings map `(kind, code)` to native error types, never by
matching `message`. The full tables are in `error-model.md`.

Protocol-level errors are always produced with the envelope itself intact, so a
client can always correlate by `request`; only a malformed *item* (unparseable
CBOR, missing envelope fields) yields the degenerate response
`{"protocol":0|1,"request":0,"status":"error",…}` with
`protocol` / `malformed_item`.
