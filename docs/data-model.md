# RethinkLite — Data Model

Status: normative for **protocol version 1** and **storage format version 1**.
Scope: M0. Everything marked *(reserved)* is designed but not implemented in M0.

---

## 1. Collections and documents

A RethinkLite database contains **collections**. A collection contains
**documents**. A document is a CBOR map with text-string keys and exactly one
required field: `id`.

```
Database
 ├── _catalog          (internal: collection metadata)
 ├── users
 ├── projects
 └── events
```

* Collection names are UTF-8, 1–255 bytes, and must not start with `_`
  (prefix `_` is reserved for engine-internal collections).
* A database may hold up to 2^32 − 1 user collections.
* Documents are ordered within a collection by their `id` using the total order
  of §6.

## 2. The value model

The value model is exactly the **CBOR data model** (RFC 8949 §3) restricted to
the following, plus tagged values:

| RethinkLite value | CBOR encoding | Restrictions |
|---|---|---|
| Null | major type 7, `0xf6` | — |
| Bool | major type 7, `0xf4`/`0xf5` | — |
| Int | major types 0/1 | signed 64-bit range |
| Float | major type 7 (f16/f32/f64) | finite only; see §5.3 |
| Text | major type 3 | well-formed UTF-8, ≤ 2^32−1 bytes |
| Bytes | major type 2 | ≤ 2^32−1 bytes |
| Array | major type 4 | ≤ 2^24 elements |
| Map | major type 5 | **text-string keys only** |
| Tagged | major type 6 | whitelist + opaque passthrough, §7 |

Bignums (tags 2/3), indefinite-length items, and simple values other than
`null`/`false`/`true` (`undefined`, `0xf7`) are **accepted on input only where
noted in §5.4** and are otherwise rejected. RethinkLite never *emits* them.

### 2.1 Maps have text keys only

Every map in a document must have text-string keys. Non-text keys (int, bytes,
array, map, tag) are rejected with `invalid_document`
(`non_text_map_key`). This makes path-based queries, sorting, secondary indexes
and JSON interchange well-defined, and it is exactly what CBOR tag 275
("map contains only keys that are of type Text String") declares. RethinkLite
accepts tag 275 on input and always emits documents satisfying its condition.

Rationale and consequences: see `adr/0002-document-model.md`.

### 2.2 No proprietary extensions

RethinkLite defines **no CBOR tags of its own**. All special values use
IANA-registered tags (§7) or plain CBOR. This is what makes the value model
implementable in any language with a CBOR library alone.

## 3. Document identity

### 3.1 The `id` field

`id` is a normal, visible field of the document:

```json
{ "id": "user-123", "name": "Anton", "active": true }
```

Permitted `id` types:

| Kind | CBOR form | Rank | Notes |
|---|---|---|---|
| `Int` | major type 0/1 | 0 | signed 64-bit |
| `Uuid` | tag 37 over 16-byte byte string | 1 | binary UUID, RFC 9562 |
| `Text` | major type 3 | 2 | ≤ 1024 bytes |

`null`, `float`, `bytes` (without tag 37), arrays and maps are not valid IDs.

If `id` is absent on insert, the engine generates a **UUIDv7** (time-ordered,
RFC 9562 §5.7) and returns it as tag 37. `Uuid` is the default auto-ID kind.

Because `id` is part of the document, `get` can return the stored document
verbatim and the wire representation round-trips unchanged.

### 3.2 Metadata outside the document

Two metadata fields exist per document and are **never** written into the
document body:

| Field | Type | Meaning |
|---|---|---|
| `rev` | `uint` | document revision; increments on every effective write (1 on insert) |
| `commit_seq` | `uint` | `commit_seq` of the transaction that produced this revision |

They are returned by `get`, by `collection.query` (when `include_meta` is set),
and are carried in changefeed events. Keeping them out of the document body
means user documents are byte-identical to what the user wrote, and that
`commit_seq`/`rev` cannot collide with user fields.

## 4. Canonical encoding

RethinkLite stores and emits documents as **length-first core deterministically
encoded CBOR** (RFC 8949 §4.2.3): the core deterministic requirements of §4.2.1
plus **length-first map key ordering** instead of the plain bytewise ordering
that §4.2.1 itself prescribes.

Rationale for that specific choice: §4.2.3 is byte-identical to RFC 7049
"Canonical CBOR", which is what stock library canonical modes implement
(`cbor2` with `canonical=True`, `fxamacker/cbor` with canonical enabled). Since
the fixture contract must be reproducible by any language's CBOR library without
hand-written ordering code, matching the widely implemented ordering is worth
more than matching the letter of §4.2.1's map rule. This deviation is deliberate
and recorded; it is the only one.

Concretely:

1. Integers use the shortest form (preferred serialization, §4.1). This also
   applies to tags, lengths and every argument.
2. Floats use the shortest form that preserves the value (f16, f32 or f64);
   `1.5` is `0xf93e00`, not a binary64.
3. Map keys are sorted by encoded key length first, then bytewise
   (RFC 8949 §4.2.3, RFC 7049 §3.9).
4. Indefinite-length items are never emitted.
5. Tag presence is normative, never optional: a UUID `id` **is** tag 37 over 16
   bytes; an untagged 16-byte byte string is `bytes`, a different value.
   §4.2.2's warning about giving a tag and its absence the same meaning is thus
   respected by construction.
6. Int and Float are distinct types, so the §4.2.2 question "is `1.0` an integer
   or a float" cannot arise: an integral value encoded as a float stays a float,
   and a value from major type 0/1 stays an integer. Both are emitted in the
   shortest form *of their own type*.
7. `-0.0` and `+0.0` are distinct values with distinct canonical bytes
   (`0xf98000` / `0xf90000`); numeric comparison treats them as equal, exactly
   the split between byte identity and value semantics described in §5.2.
8. Subnormal floats are interchanged as-is; there is no flushing to zero.

Decoder policy: RethinkLite **accepts** non-deterministic CBOR on input
(indefinite-length strings/arrays/maps, non-shortest integers, unsorted keys)
and stores it re-encoded canonically. A strict mode that rejects
non-deterministic input is *(reserved)* and will be negotiated as the
`strict_cbor` capability.

### 4.1 Consequences of canonicalization

* **Map key order is not preserved.** CBOR maps are unordered by definition; a
  document written as `{"b":1,"a":2}` is read back as `{"a":2,"b":1}`. Clients
  must not rely on key order.
* **Document identity is byte identity.** Two documents are the same document
  (same collection, same `id`) if and only if their canonical bytes are equal.
  This makes canonical bytes usable for hashing, change detection, dedup and
  (later) replication without a separate comparison format.
* **Idempotent writes.** If a write produces canonical bytes identical to the
  stored bytes, it is a **no-op**: no `rev` increment, no `commit_seq`
  consumed, no changefeed event; the response reports `"unchanged": true`.
  This prevents event storms in reactive systems and makes replayed writes
  (replication, retries) side-effect free.
* Floating point values are compared exactly; there is no epsilon anywhere.

## 5. Type semantics

### 5.1 Int and Float are distinct types

`1` (Int) and `1.0` (Float) are different values with different canonical bytes.
Both may be stored side by side and both round-trip.

### 5.2 Equality in queries is numeric across Int/Float

For query predicates, `eq(1, 1.0)` is `true` and `lt(1, 1.5)` is `true`:
comparisons operate on the numeric domain. This is deliberately different from
storage identity (§4.1): *value semantics* for querying, *byte semantics* for
storage. Both rules are stable and documented so that a `filter` can never
depend on an implementation detail.

### 5.3 NaN and Infinity are rejected in M0

`NaN`, `+Inf` and `-Inf` cannot be stored or returned: they have no total order
compatible with numeric comparison and no lossless JSON representation. They are
rejected with `invalid_document` (`unsupported_float`). Storing them under a
tagged encoding is *(reserved)* and requires its own decision.

### 5.4 Rejected input

| Input | Result |
|---|---|
| Invalid UTF-8 in a text string | `serialization` / `invalid_utf8` |
| Non-text map key in a document | `invalid_document` / `non_text_map_key` |
| `undefined` (`0xf7`) anywhere | `serialization` / `undefined_value` |
| Indefinite-length item | accepted, re-encoded canonically |
| Unassigned tag | accepted, preserved opaquely (§7) |
| Recursion depth > 100 | `invalid_document` / `depth_exceeded` |
| Document > 16 MiB (default) | `invalid_document` / `document_too_large` |
| Bignum (tag 2/3) | `invalid_document` / `unsupported_bignum` |

## 6. Total order

All order-sensitive operations — primary key order, `sort`, index keys, map key
canonicalization — use one total order over values:

```
null  <  false  <  true  <  number  <  uuid  <  text  <  bytes  <  array  <  map  <  tagged
 0         1        1        2         3         4        5         6        7          8
```

(`false` and `true` share rank 1; `false < true`.)

Within a rank:

* **number**: numeric order over Int and Float combined. Equal numeric values
  tie-break with `Int` before `Float`.
* **uuid**: bytewise order of the 16 bytes.
* **text**: Unicode code point order — identical to bytewise UTF-8 order,
  because UTF-8 preserves code point order.
* **bytes**: bytewise, shorter-is-smaller on prefix.
* **array**: element-wise, shorter-is-smaller on prefix.
* **map**: compare canonical key sets in key order; first differing key decides;
  otherwise compare the corresponding values; fewer keys is smaller.
* **tagged**: order by tag number, then by the tagged value under its own rank.
  Unknown tagged values are orderable here, but see §7.

`null` sorts before everything; this matches RethinkDB's intent (missing and
null are the smallest values) and makes `sort` with nulls predictable.

## 7. Tagged values

| Tag | Name | M0 handling |
|---|---|---|
| 37 | Binary UUID (RFC 9562) | first-class: 16-byte bstr; valid `id`; comparable |
| 1 | Epoch-based date/time | accepted and preserved verbatim; **not** a query type in M0 |
| other | — | preserved verbatim (opaque); comparable by §6 but no operators |

Preserving unknown tags verbatim is deliberate forward compatibility: a client
using a newer encoding extension can still store and retrieve its data through
an older engine. The cost is that opaque tagged values are not indexable in M0
(a `filter` comparing them is rejected with `invalid_query` /
`unsupported_comparison`).

### 7.1 Timestamps are not first-class in M0

RFC 8949 defines tag 1 as **seconds** since the epoch (integer or float) — too
coarse for a database, and a microsecond tag would be proprietary, which §2.2
forbids. Therefore:

* engine-generated time values (e.g. `commit_time` in feed metadata, `now()` in
  queries) are plain `Int` **microseconds** since the Unix epoch, UTC;
* tag 1 values written by clients are stored and returned unchanged;
* a first-class time type with arithmetic and comparison is *(reserved)* and
  will be decided in M1 against RFC 9581 (CBOR tags for date/time), not invented
  ad hoc.

## 8. Write semantics

| Operation | Behaviour |
|---|---|
| `insert` | fails with `conflict` / `document_exists` if `id` exists; auto-assigns `id` if absent |
| `update` | requires an existing document; applies `set` (shallow merge) and `unset` (key removal); fails with `not_found` otherwise |
| `replace` | insert-or-replace (RethinkDB semantics): creates the document if absent, otherwise replaces it entirely |
| `delete` | requires an existing document; fails with `not_found` otherwise |

`update` is deliberately **not** "merge with null meaning delete": `set` and
`unset` are separate, so `null` is an ordinary value and there is no ambiguity.
Deep-path updates (JSON-Pointer-style) are *(reserved)*; in M0 `set`/`unset`
operate on top-level keys only.

Optional optimistic concurrency: `insert`/`update`/`replace`/`delete` accept an
optional `if_rev` guard. If the current `rev` differs, the operation fails with
`conflict` / `revision_conflict` and writes nothing.

## 9. Limits (format v1)

| Limit | Default | Configurable |
|---|---|---|
| Document size | 16 MiB | at create / by request |
| Nesting depth | 100 | no |
| `id` length (text) | 1024 bytes | no |
| Collection name | 255 bytes | no |
| Map entries per document | 2^24 | no |
| Array elements | 2^24 | no |

Limits exist to bound decoder memory and page chains; they are part of
format v1 and may only be relaxed in a later format version.

## 10. Schema validation *(reserved)*

M0 is **schemaless**: any well-formed document per §2 may be stored.

Reserved design constraints for optional schemas (M2+), recorded now so that M0
does not make them impossible:

1. Schemas are engine metadata attached to a collection, not documents.
2. Validation is enforced on write, and violations return `invalid_document`
   with a path to the offending member.
3. Enabling or tightening a schema never rewrites existing documents; it
   affects subsequent writes only.
4. Constraint language, if introduced, is a CBOR structure, never an embedded
   script.
5. Schema changes are versioned and appear in the changefeed as collection
   metadata events, so replicas converge without a separate mechanism.

## 11. JSON interchange (informative)

| JSON | CBOR | Note |
|---|---|---|
| `null`, `true`, `false` | same | — |
| number, integral, `i64` range | Int | `1.0` in JSON input becomes Float unless the client sends an integer |
| number, other | Float | JSON has no int/float distinction; clients choose |
| string | Text | — |
| array | Array | — |
| object | Map (text keys) | JSON guarantees text keys; CBOR documents additionally enforce it |
| — | Bytes | no JSON equivalent; encode as base64 text (convention, not enforced) |
| — | Tagged | no JSON equivalent; JSON clients see an error unless they opt into CBOR |

JSON is therefore a *view* of the data model, never the contract. The contract
is CBOR (`docs/cbor-protocol.md`).
