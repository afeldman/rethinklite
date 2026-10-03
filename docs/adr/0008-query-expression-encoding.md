# ADR 0008 — Query expression encoding

- Status: Accepted
- Date: 2026-10-03
- Deciders: project author (Anton Feldmann), architecture phase
- Supersedes / Superseded by: —

## Context

A query must mean the same thing in Rust, Python and Go. The contract is CBOR
and bindings may only encode requests, decode responses and translate errors;
the core owns semantics (`architecture.md` §3). The security posture requires no
eval, no scripts and no string DSL, and bounds hostile input through a closed
term set with arity and type checks (`architecture.md` §9). At the same time the
protocol values readability and additive evolution (`cbor-protocol.md` §1), and
the term tree must be identity-testable against golden byte fixtures so the Rust
builder and the wire contract cannot drift apart (`query-model.md` §8).

## Decision

1. A term is a CBOR array whose first element is the text operator name, followed
   by its arguments: `["filter", <predicate>, ["scan"]]`.
2. In argument position an array is **always** a term. A literal array is
   therefore lifted explicitly with `["lit", <value>]`, which removes every
   ambiguity, including field names that look like operators.
3. Bound parameters use `["param", <index>]`, indexing the separate top-level
   `params` array of the request body.
4. Operator names are stable identifiers and are part of protocol v1.
5. Arity and argument types are checked before execution; violations return
   `invalid_query` / `bad_arity` or `bad_argument_type`.
6. The operator set is closed. There is no string DSL and no eval; no operator
   performs I/O, calls out, or evaluates code.

## Alternatives considered

- **Numeric opcodes.** Compact but opaque, and each language would need a shared
  registry to map codes back to names. Readability is a stated protocol
  principle, and the compact profile is already reserved as a negotiated
  capability, not the default.
- **Map-form terms with named arguments.** More self-describing per term, but
  verbose and it duplicates the grammar for every operator; the array-with-op
  head is one rule that covers all of them.
- **A mini query DSL parsed by the engine.** Rejected: it introduces a second
  parser, a second error model and an injection/escaping surface in every
  language — precisely what the M0 security posture forbids.
- **Language-specific query objects serialized ad hoc.** Rejected: it makes term
  identity untestable and lets bindings drift from the contract, which the
  byte-identical fixture requirement is designed to prevent.

## Consequences

### Positive
- One grammar for every operator; a term built in Rust and re-encoded must be
  byte-identical to the fixture, which is a cheap conformance test.
- No escaping problem and no injection surface: the tree is data, never code.
- New operators are additive and do not change existing semantics.
- Queries are readable in a hex dump, which speeds up debugging fixtures.

### Negative / accepted costs
- Positional arguments are less self-describing than a named-argument map, so
  arity is a contract the docs must state.
- The array-is-term rule is a subtlety every binding author must internalize;
  forgetting `["lit", …]` for a literal array produces a term, not a value.
- Text operator names cost bytes compared with opcodes.

### Follow-up when the cost becomes relevant
- If payload size becomes a measured problem, the reserved `compact_profile`
  capability can carry opcodes as a negotiated alternative, never a replacement.
- If authoring friction persists, bindings may add idiomatic builders, but they
  must still serialize the array term verbatim.

## References

- [../cbor-protocol.md](../cbor-protocol.md) §1, §9
- [../query-model.md](../query-model.md) §1, §5, §8
- [../architecture.md](../architecture.md) §3, §9
