# ADR 0005 — The storage engine sees opaque bytes, not CBOR

- Status: Accepted
- Date: 2026-10-03
- Deciders: project author (Anton Feldmann), architecture phase
- Supersedes / Superseded by: —

## Context

RethinkLite wants a fast read path that returns a stored document verbatim, and
it wants the freedom to change the physical record layout later — for example
compression or a columnar layout — without renegotiating the wire contract. Both
are only possible if the storage engine does not interpret the record format. The
`get` path is the common case, so anything spent decoding and re-encoding it is
spent on every read.

## Decision

1. Documents are stored as their canonical CBOR bytes.
2. The storage engine does not know CBOR: its interface is an order-preserving
   key plus an opaque byte blob, and values are compared by `memcmp` only.
3. Because values are bytes to the engine, `get` can splice the stored bytes
   straight into the response without decoding; decoding happens only where
   predicates, sorts, projections or index maintenance require it.
4. The physical record encoding may therefore change later (compression, a
   columnar layout) without touching the storage layer.
5. Tree keys are order-preserving encodings produced by `rtl-value`, so a
   byte-wise comparison inside storage is always the semantic comparison of the
   value model's total order.

## Alternatives considered

* **A typed or columnar storage representation** — rejected because it would
  force decode and re-encode at the boundary and couple the physical layout to
  the logical model, discarding the verbatim splice.
* **CBOR as the storage format with storage-level knowledge of it** — rejected
  because it couples the physical format to the wire format, so a change to
  either would force a format bump on both at once.
* **Decoding into an owned value on every read** — rejected because it spends
  CPU and allocation on the common point-lookup path for no benefit.

## Consequences

### Positive

* The read fast path is a byte splice; no decode is paid on point lookups.
* The wire contract and the physical format evolve independently.
* The storage layer is testable with arbitrary blobs and knows nothing about the
  document model.

### Negative / accepted costs

* Storage cannot interpret values, so any value-level question must be answered
  above it.
* The inline/overflow threshold (1024 bytes) is a pure byte threshold, not a
  semantic one.
* Comparisons of opaque tagged values still require the value layer, so storage
  alone cannot order them semantically.

### Follow-up when the cost becomes relevant

* When compression or a columnar layout is introduced, it is taken as a storage
  format bump decided on its own, with the storage interface unchanged.

## References

* [Storage engine §5](../storage.md)
* [Architecture §5.2](../architecture.md)
* [Data model §3.1](../data-model.md)
