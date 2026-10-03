# ADR 0001 — A single Rust core owns all database semantics

- Status: Accepted
- Date: 2026-10-03
- Deciders: project author (Anton Feldmann), architecture phase
- Supersedes / Superseded by: —

## Context

RethinkLite must be usable from Rust, Python and Go first, and later from Node,
C#, C/C++ and Java, with CBOR as the language-neutral contract. The risk is that
each language grows its own interpretation of validation, canonicalization,
ordering and change semantics, and such differences surface only as byte-level or
ordering divergence. The engine must also stay safe at the layers most exposed to
hostile input — the decoder, the pager and recovery. This decides where the
single source of truth lives and in which direction code may depend on it.

## Decision

1. The core is implemented entirely in Rust. Database semantics — document
   validation, canonicalization, the value model and total order, transactions,
   query planning and execution, and changefeed/commit ordering — exist exactly
   once, in the core.
2. Language bindings may only encode requests, decode responses and translate
   errors. A binding must not normalize, validate or rewrite payloads.
3. Dependency direction is fixed: `rtl-value <- rtl-storage <- rtl-core <- {
   rtl-capi, rtl-cli, rtl-server (M1) }`, plus `rtl-value <- rtl-protocol` and
   `rtl-core <- rtl-protocol` only to map errors, never the reverse.
4. `rtl-protocol` depends on `rtl-value` only and knows no engine, so the wire
   contract is testable and versioned without a database.
5. `rtl-storage` does not know CBOR; its interface is ordered keys and opaque
   byte blobs.
6. No crate below `rtl-core` knows that Python, Go or C exist.

## Alternatives considered

* **Per-language core implementations** — each binding ships a native engine kept
  aligned by shared fixtures. Rejected: every semantic rule would be implemented
  N times and could drift, and fixtures catch only the cases someone wrote.
* **A C/C++ core with Rust bindings** — Rust as a client of a portable C engine.
  Rejected: it moves the safety-critical code (bounded CBOR decoder, page
  validation, recovery) out of Rust precisely where memory safety matters most.
* **Embedding semantics in a Python extension** — Python as the reference.
  Rejected: it makes Python a mandatory runtime for every other language's
  semantics and duplicates the engine outside the Rust codebase.

## Consequences

### Positive

* One implementation of every semantic rule; a rule is tested once and holds for
  every language, and bindings can be replaced without touching semantics.
* Cross-language conformance is expressible as byte fixtures, not a shared
  library.
* The decoder, pager and recovery paths keep Rust's safety and no-panic
  guarantee (invariant I10).

### Negative / accepted costs

* Non-Rust languages cross an FFI/C ABI boundary, a second contract to keep
  stable, and a core defect affects every language at once.
* Binding authors cannot work around a missing capability locally; the protocol
  must gain it.

### Follow-up when the cost becomes relevant

* When the C ABI stabilizes (M1), version it and pin the `cbindgen` header.
* When a binding needs behaviour the protocol cannot express, extend the protocol
  additively (protocol major 1) rather than special-casing the binding.

## References

* [Architecture §3, §7, §11](../architecture.md)
* [CBOR protocol §1](../cbor-protocol.md)
* [Query model §5](../query-model.md)
