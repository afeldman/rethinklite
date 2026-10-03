# RethinkLite — Non-Goals

Status: design baseline. This document lists what RethinkLite will **not**
build, the architectural reason (not taste), and what would replace it or when
the decision could be reconsidered. A non-goal is a boundary the design depends
on, not an unfinished feature.

---

## 1. Distributed / clustered operation
**Not built.** No multi-node membership, sharding or distributed routing.
**Why.** The commit point is a single superblock flip on one file (invariant
I3). Distribution would require a second commit protocol and destroy the
one-file, one-writer model every other guarantee is built on.
**Instead.** Replication between files (M2) copies committed history; it does
not coordinate writers.

## 2. Consensus
**Not built.** No Raft, Paxos or leader election.
**Why.** Consensus exists to agree on an order across nodes. `commit_seq` is
already a total order produced by one writer; there is nothing to agree on.
**Instead.** A replica adopts the primary's `commit_seq` order verbatim.

## 3. Cloud service
**Not built.** No hosted offering, control plane or managed tier.
**Why.** The product is a library over a local file; a service would add an
operational surface with no architectural support in the engine.
**Instead.** Deployments copy the `.rtl` file; M2 replication handles more.

## 4. Authentication / authorization
**Not built.** No users, roles, permissions or access control.
**Why.** M0 is local-only with no network listener, and the file is protected by
file permissions. Credentials without a network boundary protect nothing.
**Instead.** OS file permissions; a security design would precede any network
mode.

## 5. Network operation
**Not built.** No TCP listener, HTTP API or wire-service endpoint.
**Why.** Network operation requires an authentication and threat model that does
not exist, and would make the contract bound to a service rather than a file.
**Instead.** A local Unix domain socket with owner-only permissions (M1);
network is out of scope until a separate security design exists.

## 6. SQL compatibility
**Not built.** No SQL parser, no SQL dialect, no query-string surface.
**Why.** A string DSL reintroduces parsing and escaping problems the term-tree
model eliminates. The contract is a CBOR structure, checkable before execution.
**Instead.** The term language (`query-model.md`); SQL compatibility would be a
separate translation layer, never a core concern.

## 7. Stored procedures / scripts of any kind
**Not built.** Including a string query DSL. Operators are a closed set.
**Why.** No operator performs I/O, calls out or evaluates code
(`cbor-protocol.md` §9). Executable content would break determinism and the
language-neutral contract.
**Instead.** Compose term trees; validation returns `invalid_query` before
execution.

## 8. Complex query optimizer
**Not built.** No cost model, no join reordering, no plan search.
**Why.** M0 has one source, no joins and no secondary indexes, so there is
nothing to optimize across. Execution rules are deliberately tiny and
explainable (`query-model.md` §4).
**Instead.** Predicate pushdown and early stop as specified; index-backed access
arrives in M1 without a new query model.

## 9. DDL / schema migrations
**Not built.** M0 is schemaless; there is no `ALTER`, no migration runner.
**Why.** Documents are schemaless by design; migration tooling would encode a
schema lifecycle the data model does not have.
**Instead.** Optional schemas are reserved (M2+) and would validate writes
without rewriting existing documents (`data-model.md` §10).

## 10. Secondary indexes in M0
**Not built in M0.** Only the primary id order exists.
**Why.** Correctness first: an index is a derived structure that must stay
consistent with every write and recovery path. It is scheduled (M1), not
squeezed in.
**Instead.** Full scans with `filter`; the `index` error kind is already
reserved.

## 11. Proprietary CBOR tags or framing
**Not built.** No private tags, no length prefix, no custom delimiter.
**Why.** Any language with a stock CBOR library must be able to talk to the
core without a RethinkLite-specific dependency (`data-model.md` §2.2).
**Instead.** IANA-registered tags or plain CBOR; streams are CBOR Sequences
(RFC 8742), never a self-invented boundary.

## 12. JSON as the contract
**Not built.** JSON is a view, never the boundary format.
**Why.** JSON cannot represent bytes, tags or the Int/Float distinction without
lossy conventions; the contract must be lossless (`data-model.md` §11).
**Instead.** CBOR is the contract; clients may render JSON for humans.

## 13. Being a RethinkDB reimplementation
**Not built.** RethinkLite is not a compatibility target for any existing
product.
**Why.** RethinkDB is a server with clustering, drivers and a JSON protocol;
matching it would import goals this project explicitly rejects.
**Instead.** The term-tree and changefeed model is inspired by RethinkDB where
useful and diverges where CBOR and embedded operation demand it.

## 14. Being a JSON layer over SQLite
**Not built.** SQLite is not used and no document-to-relational mapping exists.
**Why.** The storage engine is a purpose-built copy-on-write B+tree whose
generation model makes non-blocking snapshots and snapshot–tail feeds correct.
A SQL layer would hide exactly the primitives the design needs.
**Instead.** `rtl-storage` owns the physical format directly.

## 15. ORM / migration framework
**Not built.** No model classes, no schema versioning framework.
**Why.** The engine is schemaless and documents are byte-identical to what the
caller wrote; an ORM would be a client-side convention with no core support.
**Instead.** Language bindings encode requests and decode responses; modelling
belongs to the application.

## 16. GUI / admin UI
**Not built.** No desktop app, web console or dashboard.
**Why.** There is no server to administer. `rtl check` and `rtl info` cover
inspection on the command line.
**Instead.** The CLI subcommands; any UI would be an external consumer of the
CBOR contract.

## 17. Per-language reimplementation of database semantics
**Not built.** No binding re-implements validation, query or storage logic.
**Why.** Duplicated semantics drift and break the guarantee that the same
expression yields the same result everywhere (`architecture.md` §3).
**Instead.** One Rust core; bindings only encode, decode and translate errors.

## 18. Encryption at rest
**Not built in M0.** No page or file encryption.
**Why.** Encryption interacts with page identity and recovery and needs its own
design; a bolt-on would weaken both.
**Instead.** OS-level file encryption. A dedicated ADR precedes any engine
support (M2).

## 19. Multi-process concurrent writers
**Not built.** One writer per file, enforced by an exclusive lock.
**Why.** Concurrent writers across processes would require the storage engine to
coordinate a commit protocol it does not have; the same-process single-writer
`Mutex` is the entire model.
**Instead.** One process opens the file for writing (I1); a second writer fails
with `io` / `already_open`. Multi-process readers are M2.

## 20. Replication in M0
**Not built in M0.** No replica, no offset application.
**Why.** Replication depends on log, `commit_seq`, database UUID and stable
collection ids being correct first; shipping it early would freeze them
prematurely.
**Instead.** The primitives exist in the format from M0 (`changefeeds.md` §12);
replication is scheduled in M2.

---

## Relationship to the roadmap

Non-goals are permanent or explicitly gated; milestones (`roadmap.md`) are work
that is scheduled. Items 10 and 20 are gated (M1 and M2 respectively); the rest
are not scheduled in any milestone.
