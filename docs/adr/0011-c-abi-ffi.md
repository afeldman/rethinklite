# ADR 0011 — Foreign-function surface (C ABI)

- Status: Accepted
- Date: 2026-10-03
- Deciders: project author (Anton Feldmann), architecture phase
- Supersedes / Superseded by: —

## Context

RethinkLite is language-neutral by design: Rust is the reference implementation,
not a special case, and no binding may implement database semantics
(`architecture.md` §3, `cbor-protocol.md` §1). The distribution goal is an
embedded library, not a service (`architecture.md` §2). Yet every non-Rust
language must reach the engine somehow, and the choice of that surface
determines how many code paths can drift from the core. The contract boundary is
CBOR (`cbor-protocol.md` §3, §4), so the surface needs only to move CBOR items,
not to model the database. The target language set is Python and Go first, then
Node, C#, C/C++ and Java.

## Decision

1. A C ABI — a `cdylib` built with `cbindgen`-generated headers — is the single,
   stable foreign-function surface.
2. Every language talks to it with CBOR payloads: one item in, one item out per
   call, `(ptr, len) → (ptr, len)`, with no framing at all
   (`cbor-protocol.md` §3).
3. Python binds via cffi, Go via cgo; Node, C#, Java and C++ follow the same C
   ABI later.
4. PyO3 may exist only as an optional convenience wrapper over the same C ABI,
   never as a second implementation of database semantics.
5. No language is privileged. Bindings encode requests, decode responses and
   translate errors; anything beyond that duplicates the core and is wrong by
   definition.
6. The crate version is exposed through a versioned entry point so bindings can
   detect a mismatch instead of failing obscurely.

## Alternatives considered

- **PyO3 first.** Rejected: it privileges Python, contradicting the
  no-privileged-language principle, and would create a second Rust code path to
  keep in sync with the C ABI.
- **uniffi.** Rejected: it adds a binding generator as a hard dependency and
  imposes its own interface type model, which the CBOR contract already replaces,
  and it constrains which languages can be added.
- **WASM-first.** Rejected: it does not serve the embedded native host use case,
  and it introduces a host/ABI model no target language in the plan requires.
- **Per-language SDKs reimplementing the protocol.** Rejected: this duplicates
  semantics, which the architecture forbids; a binding owns encoding, decoding
  and error translation only.
- **A network daemon as the only interface.** Rejected for M0: the distribution
  goal is a library, not a service. An IPC listener is M1 and must be a thin
  layer over the same core (`architecture.md` §9).

## Consequences

### Positive
- One foreign surface to specify, test and version; a new language is a new
  binding, not a new engine path.
- The C ABI moves opaque bytes, so bindings need no knowledge of the value model
  and can reuse the golden fixtures directly.
- No language is advantaged, which keeps the contract honest.

### Negative / accepted costs
- The C ABI is unsafe by nature; every entry point must validate pointers and
  lengths and must never panic across the boundary.
- cgo and cffi carry call overhead compared with a native binding.
- cbindgen-generated headers become part of the release surface and need their
  own stability discipline.

### Follow-up when the cost becomes relevant
- Optimize the C ABI call shape (batching, handle reuse) if cgo/cffi overhead
  becomes the bottleneck, before considering a second surface. Any PyO3
  convenience layer must call the C entry points so drift is impossible by
  construction.

## References

- [../architecture.md](../architecture.md) §2, §3, §9
- [../cbor-protocol.md](../cbor-protocol.md) §1, §3, §4
- [../data-model.md](../data-model.md) §11
