# RethinkLite — Query Model

Normative for M0. Defines the query semantics that every language binding must
share, and how the Rust API lowers onto the CBOR term language of
`cbor-protocol.md` §9.

---

## 1. What the query model is

A query is a **term tree over one collection**. It is not SQL, has no string
syntax, no joins and no optimizer in M0. The tree is the contract: the same tree
built from Rust, Python or Go must produce the same documents in the same order.

```
term tree ──▶ planner (rules) ──▶ execution pipeline ──▶ documents
```

## 2. Rust API

```rust
use rethinklite::{Database, doc};
use rethinklite::query::{field, gt, eq, and};

let db = Database::open("example.rtl")?;
let users = db.collection("users");

let id = users.insert(doc! { "name": "Anton", "age": 41, "active": true })?;

let result = users
    .query()                                   // -> QueryBuilder
    .filter(and(gt(field("age"), 30), eq(field("active"), true)))
    .sort_desc(field("age"))
    .limit(20)
    .collect()?;                               // -> QueryResult

for document in result.documents() {           // borrowed, no re-encoding
    println!("{}", document.id());
}
```

Design rules:

* **The builder only builds a term.** `QueryBuilder::build()` returns a
  `Term`; `collect()`, `count()` and `to_cbor()` are thin wrappers over the
  executor and the protocol encoder. This is why a Python binding and a Rust
  program can be tested against the same fixture.
* **No lifetimes leak.** `Database`, `Collection`, `QueryBuilder`, `WatchHandle`
  are owned values holding `Arc`s. `Document` borrows its `QueryResult`; copying
  out is explicit via `to_vec()`/`into_owned()`.
* **Errors are values.** Every fallible call returns `Result<T, Error>` with the
  `kind`/`code` pair from `error-model.md`.
* **Threading.** `Database`, `Collection`, `QueryBuilder` are `Send + Sync`;
  a query blocking in one thread never blocks another.

## 3. Semantics

### 3.1 Sources

`["scan"]` is the collection named in the request. It yields documents in key
order (the total order of `data-model.md` §6 applied to `id`) — the order is
part of the contract, not an artefact, so a limit without a sort is
reproducible.

`["get", <id>]` resolves a single key.

### 3.2 Filtering

A predicate is evaluated per document in key order. Field access returns `null`
for an absent field, so:

* `gt(field("age"), 30)` is `false` for a document without `age`;
* `eq(field("age"), null)` is `true` for `{"age": null}` **and** for a document
  without `age`;
* `exists(field("age"))` distinguishes the two;
* comparisons mix Int and Float numerically, exact, no epsilon
  (`data-model.md` §5.2).

### 3.3 Sorting

* `sort(key, "asc" | "desc", source)` sorts by the total order; `asc` is the
  order itself, `desc` its exact reverse (so `null` is first ascending, last
  descending).
* The sort is **stable**, and ties are broken by the document key order of
  §3.1. Two runs of the same query over the same state therefore always return
  the same sequence.
* Sorting is in memory in M0, bounded by `query.sort_memory_bytes`
  (default 64 MiB). Exceeding it is `invalid_query` / `sort_memory_exceeded`
  — an honest error, not an out-of-memory crash. External merge sort and
  index-backed ordering are M1.
* Multi-key sorts are *(reserved)*; `sort` takes one key in M0.

### 3.4 Limiting, skipping, counting

* `limit(n)` stops the pipeline after `n` documents; `skip(n)` drops the first
  `n`. `skip` + `limit` is the M0 pagination mechanism.
* `collection.count` runs the same source chain but never materializes
  documents; `exact` is always `true` in M0.
* `result.truncated()` reports whether `limit` or `limits.query_results` cut the
  result short, which is what a client needs to know whether to paginate.

### 3.5 Projection

`project(["name", "age"])` keeps only the listed top-level fields. `id` is
**always** kept: a document without its identity is not a document, and
subscribers/projections must stay addressable. Projection is applied after
filtering and sorting, so predicates and sort keys always see full documents.

Unknown field names in a projection are not an error; the field is simply
absent from the result.

## 4. Execution model (M0)

Deliberately tiny; the rules exist so that behaviour is explainable:

1. **Source.** Catalog lookup → collection root → root-to-leaf descent for
   `get`, or a leaf-chain scan for `scan`.
2. **Predicate pushdown.** `filter` predicates are evaluated during the scan,
   with constant folding of `["param", i]` and `["lit", …]` subtrees. There is
   no reordering of conjunctions in M0.
3. **Early stop.** `limit` stops the scan; `skip` counts past.
4. **Sort.** Materialize then sort, only if a `sort` term is present.
5. **Project.** Applied last.

Consequences worth stating: a `limit` with no `sort` reads only `n` documents;
a `sort` reads all matching documents; a `filter` on a non-indexed field always
costs a full scan (there are no secondary indexes in M0).

`QueryBuilder::explain()` renders this plan as text for tests and diagnostics.
It has no stable format and is not part of the contract.

## 5. What each layer owns

| Concern | Owner |
|---|---|
| Term construction and validation (arity, types) | `rtl-value` / `rtl-core` query module |
| Term ↔ CBOR identity | `rtl-protocol` fixtures (`tests/cbor/query_request.cbor`) |
| Plan rules | `rtl-core` |
| Ordered iteration, key order, page access | `rtl-storage` |
| Value comparison, total order, key encoding | `rtl-value` |

A binding that re-implements any row of this table is wrong by definition
(`adr/0001-rust-core.md`).

## 6. Errors

| Situation | kind / code |
|---|---|
| Unknown operator, bad arity, bad argument type | `invalid_query` / `unknown_operator`, `bad_arity`, `bad_argument_type` |
| Comparison on an opaque tagged value | `invalid_query` / `unsupported_comparison` |
| Result larger than `limits.query_results` | `invalid_query` / `result_limit_exceeded` |
| Sort working set over the memory bound | `invalid_query` / `sort_memory_exceeded` |
| Collection does not exist | `not_found` / `collection_not_found` |
| Cancelled by `cancel` | `invalid_query` / `cancelled` |

## 7. M1 and beyond

| Feature | Note |
|---|---|
| Secondary indexes | index term + planner rule; the `index` error kind is already reserved |
| Index-backed sort and range scans | requires the index term, not a new query model |
| Cursors / streaming results | for large results and IPC; the `cursors` feature flag is reserved |
| Multi-key sort, joins, `group`/reduce | new terms, same tree model |
| Aggregations over `count` | beware turning the query model into SQL |

## 8. Test contract

* **Query contract tests** live in `crates/rtl-core/tests/query.rs` and are
  written against the same term trees as the protocol fixtures.
* For every fixture in `tests/cbor/`, the decoded term must be buildable from
  the Rust API and re-encodable byte-identically — this is the test that keeps
  the builder and the contract from drifting apart.
* Ordering claims (§3.3) are tested with documents inserted in shuffled order.
