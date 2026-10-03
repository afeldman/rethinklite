# ADR 0006 — Embedded library first, IPC later, one implementation

- Status: Accepted
- Date: 2026-10-03
- Deciders: project author (Anton Feldmann), architecture phase
- Supersedes / Superseded by: —

## Context

RethinkLite aims at SQLite-like distribution: copy one file, open it in-process,
no server to run or administer. At the same time the multi-language requirement
means non-Rust programs need a way to reach the engine without reimplementing it,
and some deployments will prefer a process boundary for isolation or shared
access. The decision is which operating model is primary and how the second one
is reached without forking the semantics.

## Decision

1. The embedded Rust library is the primary operating model: no server process,
   no port, no daemon required, and distribution is copying the database file.
2. A local IPC daemon is supported later, but through the same CBOR protocol, so
   the semantics cannot diverge between the two shapes.
3. In M1 the daemon listens on a Unix domain socket with owner-only permissions.
4. Network operation is out of scope until a dedicated security design exists.
5. A single implementation serves both shapes; `rtl-protocol` is the seam, and
   only the delivery shape differs between them.
6. M0 itself is local-only: no network listener, no authentication, no
   authorization, with file permissions as the only multi-user control.

## Alternatives considered

* **Daemon-first** — rejected because it contradicts the SQLite-like distribution
  goal: a database that requires a running service is not embedded.
* **Two parallel implementations, one embedded and one in the daemon** —
  rejected because their semantics would drift, and the drift would appear
  exactly in the ordering and change guarantees that matter most.
* **In-process only, with no protocol** — rejected because it kills the
  multi-language requirement and would force a bindings-specific contract anyway.

## Consequences

### Positive

* The common case is a single file and no process, which is the point of the
  project.
* The same protocol serves in-process and IPC callers, so one set of fixtures and
  one set of guarantees covers both.
* Adding the daemon does not change engine semantics or the wire contract.

### Negative / accepted costs

* The protocol must be complete enough to carry everything the daemon needs,
  including streaming and errors.
* The in-process Rust API and the wire API must both be maintained and kept in
  step.
* Until M1 there is no way for a non-Rust process to reach a database, so a
  Python or Go user waits for either the C ABI or the daemon.

### Follow-up when the cost becomes relevant

* When the M1 daemon is built, the Unix-socket permission model and the reserved
  `rtl-async`/`rtl-server` shapes are decided then.
* Network support waits for a separate security design and remains an explicit
  non-goal until it exists.

## References

* [Architecture §1, §9, §12](../architecture.md)
* [CBOR protocol §3](../cbor-protocol.md)
* [Non-goals](../non-goals.md)
