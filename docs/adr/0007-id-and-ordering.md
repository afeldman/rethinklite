# ADR 0007 — Document identity and the single total order

- Status: Accepted
- Date: 2026-10-03
- Deciders: project author (Anton Feldmann), architecture phase
- Supersedes / Superseded by: —

## Context

Two requirements that look unrelated are one decision: a document needs an
identity, and every value needs one order. Identity cannot be a hidden row id —
`get` returns the stored bytes verbatim, so `id` round-trips inside the document
(`data-model.md` §3). Scans, `sort`, index keys and canonical map-key order need
one comparison behaving identically in every language, yet the storage engine is
deliberately ignorant of CBOR (`architecture.md` §3, `storage.md` §5): ordering
must be encoded into the bytes it compares, not passed as a callback. Database
and collection identity must support the reserved replication primitives
(`changefeeds.md` §12).

## Decision

1. A document `id` is one of three types and nothing else: `Int` (signed
   64-bit), `Uuid` (CBOR tag 37 over a 16-byte byte string), or `Text`
   (≤ 1024 bytes). `null`, `float`, untagged `bytes`, arrays and maps are not
   valid ids.
2. All order-sensitive operations use one total order (`data-model.md` §6): `null
   < false < true < number < uuid < text < bytes < array < map < tagged`.
3. When `id` is absent on insert the engine generates a UUIDv7 (time-ordered,
   RFC 9562 §5.7), returned as tag 37. `Uuid` is the default auto-ID kind.
4. `id` stays a normal, visible field inside the document; `rev` and
   `commit_seq` are metadata carried outside the body and never written into it.
5. Each database has a random 16-byte `database_uuid`; `collection_id`s are
   assigned monotonically and are never reused for the database's lifetime.
6. The order is implemented exactly once, in `rtl-value`, as an order-preserving
   key encoding. The storage engine compares encoded keys bytewise (`memcmp`)
   and never calls a comparator.
7. Text compares in Unicode code point order, identical to bytewise UTF-8 order
   because UTF-8 preserves code point order.

## Alternatives considered

- **Integer-only identifiers.** Rejected: forces a writer-owned counter and gives
  no language-neutral natural keys or client-side id generation.
- **Random UUIDv4.** Rejected as the auto-id: v4 is unordered, so generated
  documents scatter across the key space and lose insertion locality; UUID stays
  a first-class id type.
- **User-supplied opaque byte ids.** Rejected: `bytes` is not JSON-representable
  and has no query operators, making ordering and future indexing ad hoc.
- **Comparator-based (non-order-preserving) keys.** Rejected: it would force the
  storage engine to know the value model, breaking the layering rule that keeps
  the physical format free to change.
- **Per-type id namespaces.** Rejected: separate key spaces complicate the
  collection key layout and cross-type ordering, where one total order already
  makes every id comparable and addressable.

## Consequences

### Positive
- One order is shared by scans, `sort`, index keys and map canonicalization;
  there is no second comparison to keep in sync.
- The B+tree compares opaque bytes, so the engine never decodes a value; `id`
  round-trips inside the document, so `get` is a byte splice.
- Time-ordered auto-ids keep generated documents local in the key space.

### Negative / accepted costs
- Three id types mean every id consumer handles a small union and must document
  cross-type ordering.
- Time-ordered ids leak creation time and are guessable from their prefix.
- `collection_id` monotonicity requires a durable counter in the metadata tree.

### Follow-up when the cost becomes relevant
- Revisit the auto-id kind if id privacy matters, or the counter width via a
  format bump if collection counts approach the `u32` space.

## References

- [../data-model.md](../data-model.md) §3, §6, §7
- [../storage.md](../storage.md) §5, §12
- [../architecture.md](../architecture.md) §3, §4
- [../changefeeds.md](../changefeeds.md) §12
