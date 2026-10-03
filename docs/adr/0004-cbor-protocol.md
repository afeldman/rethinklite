# ADR 0004 — CBOR is the only cross-language contract

- Status: Accepted
- Date: 2026-10-03
- Deciders: project author (Anton Feldmann), architecture phase
- Supersedes / Superseded by: —

## Context

Every non-Rust language must speak to one Rust core. The contract has to be
expressible with stock libraries, need no code generation, and have a canonical
form so that identity and golden fixtures are byte-exact. It must also carry
streaming without bespoke framing, tolerate additive evolution, and stay readable
enough to debug by hand.

## Decision

1. CBOR (RFC 8949) is the only cross-language contract — not an export format
   bolted on later.
2. Engine output is length-first core deterministically encoded CBOR (RFC 8949
   §4.2.3, i.e. §4.2.1 with length-first map-key ordering instead of plain
   bytewise ordering — the RFC 7049 "Canonical CBOR" ordering that stock library
   canonical modes emit; see `data-model.md` §4); input may be non-deterministic
   and is re-encoded canonically.
3. Request and response envelopes use full-word text keys; unknown fields are
   ignored, never rejected.
4. Query expressions are term arrays whose first element is a text operator name;
   in argument position an array is always a term, so a literal array requires
   `["lit", ...]`.
5. Streams are CBOR Sequences (RFC 8742), self-delimiting items with media type
   `application/cbor-seq`; a whole sequence may be wrapped in tag 63.
6. `minicbor` is the codec, chosen because it is actively maintained, is
   `no_std`-capable and gives explicit control over tags.
7. No serde on the wire path.
8. No proprietary tags and no proprietary length-prefix framing.

## Alternatives considered

* **A BSON-style custom binary** — rejected as another format to specify, with
  fewer libraries and no canonical encoding.
* **JSON** — rejected: no bytes, no tags, no canonical byte identity; JSON stays
  a view of the model, never the contract.
* **Cap'n Proto / Protobuf / FlatBuffers** — rejected because their schema/IDL
  becomes a second contract and does not map onto schemaless documents.
* **`ciborium`** — rejected: serde-bound and unchanged since 2024-01.
* **`serde_cbor`** — rejected: unmaintained since 2021.
* **Numeric opcodes** — rejected because readable full-word names come first; a
  compact profile is reserved as a negotiated capability.
* **Map-form terms with named arguments** — rejected because positional arrays
  plus the disambiguation rule are simpler and unambiguous.
* **A proprietary length prefix** — rejected because CBOR items are
  self-delimiting and a prefix breaks interop.
* **An indefinite-length array as the stream container** — rejected because
  RFC 8742 sequences are the standard form.

## Consequences

### Positive

* Any language with a CBOR library can build and verify the contract.
* Golden byte fixtures pin behaviour without a shared library and double as
  cross-language conformance cases.
* The same encoding carries documents, envelopes and streams, and evolves
  additively within protocol major 1.

### Negative / accepted costs

* CBOR is less familiar than JSON, and the term-array language must be taught.
* One more dependency (`minicbor`) to maintain on the wire path.

### Follow-up when the cost becomes relevant

* Introduce the compact profile only as a negotiated capability if payload size
  ever matters.
* Revisit the codec only if `minicbor` ceases to be maintained.

## References

* [CBOR protocol specification](../cbor-protocol.md)
* [Data model §4](../data-model.md)
* [Architecture §3](../architecture.md)
