# RethinkLite — Compatibility Contract

Status: design baseline for M0. Normative alongside `cbor-protocol.md`
(protocol version 1), `data-model.md` and `storage.md` (storage format version
1). This document states, in one place, what may change and what may not.

Two categories govern everything below:

* A **stable contract** is a byte-level or semantic promise. Changing it breaks
  a client that was correct, so it requires a new protocol or format version.
* An **unstable detail** is an implementation fact clients must never depend on.
  It may change in any release without notice and without a version bump.

---

## 1. What is stable

### 1.1 Protocol v1 (language-neutral, frozen)

| Surface | Promise |
|---|---|
| Request envelope | fields `protocol`, `request`, `operation`, `transaction`, `body` keep name, type and meaning |
| Response envelope | `status` is `ok` or `error`; exactly one of `body`/`error` |
| Operation semantics | every operation and body shape in `cbor-protocol.md` §6 keeps its meaning |
| Term operator names and arity | `cbor-protocol.md` §9, including the array-is-always-a-term rule |
| Canonical fixture bytes | `tests/cbor/*.cbor` are immutable normative bytes |
| Document encoding | length-first core deterministic CBOR, RFC 8949 §4.2.3 (`data-model.md` §4) |
| Total order | `data-model.md` §6, one order for keys, sort and index keys |
| Error object shape | `kind`, `code`, `message`, `retryable`, `details` |
| `hello` negotiation | version intersection, `features`/`required` semantics |

### 1.2 Error kind/code registry

`kind` is a **closed** set. Adding a member is a protocol major change; the
values below are frozen for v1. `code` is fine-grained, snake_case and stable;
codes are added but never removed or repurposed. The normative per-code list is
`docs/error-model.md`.

| `kind` | Meaning |
|---|---|
| `io` | operating-system or file failure |
| `corruption` | failed checksum or invalid on-disk structure |
| `serialization` | CBOR that cannot be decoded or represented |
| `invalid_document` | well-formed CBOR that violates the document model |
| `invalid_query` | malformed term tree or an execution constraint exceeded |
| `not_found` | missing collection or document |
| `conflict` | precondition or concurrency conflict |
| `transaction` | transaction lifecycle error |
| `index` | secondary-index error (kind reserved in M0) |
| `changefeed` | subscription error |
| `protocol` | envelope, session or negotiation error |
| `internal` | engine invariant violated |

`message` is human text and is **not** stable (§2). `retryable` is fixed per
code and may not be flipped once released.

### 1.3 Storage format v1

Semantics of the v1 layout are stable; the physical layout is not (§2).

| Surface | Promise |
|---|---|
| `magic` = `RTHKLITE`, `page_size` = 4096, `format_version` = 1 | fixed for v1 |
| Superblock field meaning | `storage.md` §3 |
| Two-slot flip as the only commit point | invariant I3 |
| Recovery result | newest valid superblock; committed state never lost (I4) |
| Key encoding order | tree-key comparison equals `data-model.md` §6 |
| Document limit 16 MiB, inline threshold 1024 bytes | part of format v1 |

---

## 2. What is explicitly NOT stable

| Surface | Why it is free to change |
|---|---|
| Log record layout | internal (`storage.md` §7); only `commit_seq` order and the log's contents semantics are promised |
| Page layout details | header fields, slotted arrangement, overflow chain representation are engine-internal |
| Allocator behaviour | allocation order and `next_free_hint` are hints; only boundedness is tested |
| `explain()` text | diagnostic only (`query-model.md` §4); never parse it |
| Rust API | pre-1.0; shapes may change between releases |
| Error `message` strings | human-readable; never match on them |
| Bench numbers | recorded, not asserted, until M1 (`roadmap.md`) |

---

## 3. Protocol versioning rules

1. A version is `major.minor`. The wire carries the **major** only, as the
   integer `protocol` field.
2. Within a major version, change is **additive only**: new optional fields, new
   operations, new error codes, new feature flags. Existing semantics never
   change.
3. Unknown fields are **ignored** everywhere, never rejected.
4. An **unknown operation name is an error**: `protocol` /
   `unknown_operation`. It is not silently ignored — a caller that believes it
   wrote data must not be told "ok".
5. Optional behaviour is negotiated through `hello` **feature flags**, never
   inferred from a version number.
6. Deprecation: an operation is announced deprecated in minor `N` and may be
   removed no earlier than minor `N+2`. Removal is itself a minor bump.
7. A removed operation name is **never reused** for a different meaning.
8. A removed error code is **never reused**.
9. The meaning of an existing field or code is **never changed**. A different
   meaning requires a new field, a new code, or a new major version.

---

## 4. Storage format rules

* `format_version` is an integer in the superblock. An engine that does not
  support a file's `format_version` refuses to open it with `corruption` /
  `unsupported_format_version` and does not touch the file (`storage.md` §13).
* The `features` bitmask may carry a change **instead of** a format bump only
  when an older reader can safely ignore it: an optional superblock field whose
  absence degrades to the previous behaviour. Anything that changes page, key or
  record interpretation requires a format bump.
* M0 creates and reads format v1 only. There is **no in-place upgrade**, no
  migration tooling and no downgrade path in M0; migration is reserved.

---

## 5. Golden-fixture compatibility matrix

| Protocol | Fixture set | Decode | Re-encode | Status |
|---|---|---|---|---|
| 1 | `tests/cbor/*.cbor`, `MANIFEST.md` | required | byte-identical required | normative for v1 |
| 1 | new fixtures added in later minors | required | byte-identical required | additive |
| 0 | degenerate error response | required | parseable by a major-agnostic reader | negotiation failure only |
| >1 | future fixtures | required of a future engine | byte-identical required | engine must reject a v1 file if it cannot |

The rule that makes this work:

> Every v1 fixture must **decode and re-encode byte-identically under every
> future protocol version**. New fixtures are **added**; existing bytes are
> **never edited**.

A fixture is edited only by an explicit, documented decision that also bumps the
protocol major — a breaking act, not maintenance.

---

## 6. C ABI stability

* The C ABI exposes **one versioned entry point**; the version is an argument,
  not a separate symbol per release. A binding checks the returned version and
  fails cleanly if it is unsupported.
* Calls carry **CBOR payloads**, not C structs: `(ptr, len)` in, `(ptr, len)`
  out, one item per call. Because the payload is the same CBOR Sequence as every
  other transport, field additions never churn a struct layout.
* There is **one ABI for all languages** (`rtl-capi`, M1). Python, Go and C
  bindings call the same functions; no binding re-implements database semantics
  (`architecture.md` §3, `adr/0001-rust-core.md`).
* The ABI is M1 scope; the protocol it carries is frozen now.

---

## 7. Checklist: adding an operation or term without breaking v1

1. Confirm the capability is additive and does not alter an existing operation's
   result for unchanged input.
2. Add a **new** operation name or term name; never overload an existing one.
3. Reuse existing error `kind`s; add a new `code` only if no existing code fits,
   and never change an existing code's meaning.
4. If the behaviour is optional, gate it behind a `hello` **feature flag** and
   add it to the v1 feature registry; clients that do not ask for it must be
   unaffected.
5. Specify it in `cbor-protocol.md` (and `query-model.md` for a term) **before**
   implementing it.
6. Add **new** golden fixtures under `tests/cbor/`; do not edit existing ones.
7. Add a conformance case that decodes and re-encodes the new fixture
   byte-identically.
8. Version the change as a **minor** bump and, if it supersedes an operation,
   record the deprecation with its removal minor (`N+2`).
