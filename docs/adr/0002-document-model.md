# ADR 0002 — The document model is the CBOR data model

- Status: Accepted
- Date: 2026-10-03
- Deciders: project author (Anton Feldmann), architecture phase
- Supersedes / Superseded by: —

## Context

Documents must be storable, comparable and addressable identically from every
language, and the same bytes must mean the same document everywhere. The design
needs a value model any CBOR library can build, an identity strong enough to drive
change detection, dedup and replication, and a write rule that is side-effect free
under retry so a reactive client is not woken by an idempotent replay.

## Decision

1. The value model is exactly the CBOR data model (RFC 8949 §3): `null`, `bool`,
   `int` (signed 64-bit), `float`, `text`, `bytes`, `array`, `map` and `tagged`.
2. Every map has text-string keys only; non-text keys are `invalid_document` /
   `non_text_map_key`. This is the condition CBOR tag 275 declares, which the
   engine accepts on input and always satisfies on output.
3. `id` is a normal, visible field, never engine metadata. Permitted kinds are
   `Int`, `Uuid` (tag 37 over a 16-byte string) and `Text` (≤ 1024 bytes).
4. If `id` is absent on insert, the engine generates a UUIDv7 (RFC 9562) and
   returns it as tag 37; `Uuid` is the default auto-ID kind.
5. `rev` and `commit_seq` live outside the body and are never written into it;
   they are returned by `get`, by `query` with `include_meta`, and in feed events.
6. RethinkLite defines no CBOR tags of its own; special values use IANA tags or
   plain CBOR, and unknown tags are preserved verbatim for forward compatibility.
7. Documents are stored and emitted as length-first core deterministically
   encoded CBOR (RFC 8949 §4.2.3; see `data-model.md` §4 for the deliberate
   deviation from §4.2.1's bytewise map-key rule); non-deterministic input is
   re-encoded canonically.
8. Byte identity is document identity: two documents (same collection, same `id`)
   are the same if and only if their canonical bytes are equal.
9. A write whose canonical bytes equal the stored bytes is a no-op — no `rev`
   bump, no `commit_seq`, no changefeed event — and reports `"unchanged": true`.
10. NaN and Infinity are rejected in M0 with `invalid_document` /
    `unsupported_float`.
11. Timestamps are not first-class in M0: tag 1 is seconds (too coarse) and a
    microsecond tag would be proprietary. Engine times are `Int` microseconds
    since the Unix epoch, UTC; client tag 1 values pass through unmodified.

## Alternatives considered

* **JSON as the document model** — rejected: no bytes, no Int/Float distinction,
  no tags, and no canonical byte identity to hang change detection on.
* **Proprietary tags for time or IDs** — rejected: it breaks implementability
  with a stock CBOR library and forward compatibility.
* **`id` as engine metadata** — rejected: `get` could not return the stored
  document verbatim and the wire form would not round-trip unchanged.
* **`rev`/`commit_seq` inside the body** — rejected: they could collide with user
  fields and would make documents non-byte-identical to user input.

## Consequences

### Positive

* The model is buildable in any language with a CBOR library.
* Canonical bytes give one identity usable for hashing, change detection, dedup
  and later replication.
* No-op writes prevent event storms under retry.

### Negative / accepted costs

* Map key order is not preserved and clients must not rely on it.
* Opaque tagged values are preserved but not indexable in M0.
* There is no first-class time type; clients carry microseconds as plain ints.
* Float comparison is exact, with no epsilon anywhere.

### Follow-up when the cost becomes relevant

* A first-class time type is decided in M1 against RFC 9581, not invented ad hoc.
* A strict decoder mode is negotiated later as the `strict_cbor` capability.

## References

* [Data model](../data-model.md)
* [CBOR protocol §2](../cbor-protocol.md)
* [Changefeeds §3](../changefeeds.md)
