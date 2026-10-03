# RethinkLite — Error Model

Normative for M0. Defines the error taxonomy shared by the Rust API and the CBOR
protocol, and how language bindings turn it into idiomatic errors.

---

## 1. Principles

1. **One taxonomy, three surfaces.** The same `kind`/`code` pair appears in
   `rethinklite::Error`, in the protocol error object and in every binding's
   exception/error type. Bindings map on `kind` first, `code` second.
2. **`kind` is closed and small.** A dozen coarse categories drive program logic
   and binding-level types (is this retryable? is this my bug?).
3. **`code` is fine-grained and permanent.** Codes are added, never renamed, and
   never reused for a different meaning (`compatibility.md`).
4. **`message` is for humans.** It is unstable, never parsed, and never contains
   document values (only identifiers may appear in `details`).
5. **`retryable` means "the identical request may succeed later".** Conflicts are
   `false`: the caller must change something. `feed_overflow` is `true` because
   resubscribing with the same body can work; `log_truncated` is `false` because
   only a *different* request (a snapshot resync) can succeed.
6. **No panics on input.** Every path that parses user input, CBOR, files or
   queries returns a structured error. Library code uses `?`, never `unwrap()`,
   except on invariants proven immediately above the call.
7. **Corruption fails fast.** Once `corruption` is detected, writes to that
   database stop (`write_aborted`); reads of still-valid pages keep working.
   Nothing is silently repaired.

## 2. `kind` registry (closed)

| `kind` | Meaning | Typical `retryable` | Binding type (guidance) |
|---|---|---|---|
| `io` | operating system, file lock, filesystem limits | sometimes | `IoError` / `OSError` subclass |
| `corruption` | on-disk integrity violated or format not readable | no | `CorruptionError` (fatal) |
| `serialization` | CBOR decode/encode failure including malformed envelope | no | `ProtocolError` subclass |
| `invalid_document` | the document violates the value model | no | `InvalidDocumentError` |
| `invalid_query` | term tree rejected or execution bound exceeded | no | `InvalidQueryError` |
| `not_found` | addressed object does not exist | no | `NotFoundError` |
| `conflict` | request contradicts committed state | no (but caller may retry changed) | `ConflictError` |
| `transaction` | transaction lifecycle failure | sometimes | `TransactionError` |
| `index` | secondary index failure *(reserved in M0)* | no | `IndexError` |
| `changefeed` | feed delivery or retention failure | depends | `FeedError` |
| `protocol` | session/envelope level failure | sometimes | `ProtocolError` |
| `internal` | bug or violated invariant | no | `InternalError` (never catch-and-continue) |

Adding a `kind` is a **breaking** change: it is a closed set that bindings match
on exhaustively, so a new `kind` requires a protocol **major** bump and a new
fixture (`compatibility.md` §1.2). Adding a `code` inside an existing `kind` is
additive.

## 3. `code` registry

`details` lists the machine-readable fields a client may rely on.

### 3.1 `io`

| `code` | Meaning | `retryable` | `details` |
|---|---|---|---|
| `file_not_found` | path does not exist and `create` was not requested | no | `path` |
| `already_open` | exclusive lock held by this or another process | no | `path` |
| `lock_failed` | advisory lock could not be taken | yes | `path`, `errno` |
| `permission_denied` | filesystem refused access | no | `path` |
| `read_failed` / `write_failed` / `fsync_failed` | syscall failed | yes | `errno` |
| `file_too_large` | would exceed the 16 TiB page-id limit | no | `page_count` |

### 3.2 `corruption`

| `code` | Meaning | `retryable` | `details` |
|---|---|---|---|
| `no_valid_superblock` | neither superblock slot validates | no | — |
| `unsupported_format_version` | file written by a newer format version | no | `format_version`, `supported` |
| `bad_page_checksum` | page CRC mismatch | no | `page_id` |
| `bad_record_checksum` | log record CRC mismatch | no | `segment`, `offset` |
| `page_out_of_range` | reference beyond `page_count` | no | `page_id` |
| `double_reference` | page reachable twice | no | `page_id` |
| `cycle_detected` | overflow/sibling/tree cycle | no | `page_id` |
| `malformed_tree_order` | leaf order inconsistent with the key encoding | no | `page_id` |
| `write_aborted` | writes refused after corruption was detected | no | `page_id` |

### 3.3 `serialization`

| `code` | Meaning | `retryable` | `details` |
|---|---|---|---|
| `malformed_cbor` | not a valid CBOR item / truncated | no | `offset` |
| `invalid_utf8` | malformed UTF-8 in a text string | no | — |
| `undefined_value` | CBOR simple value `undefined` (`0xf7`) | no | — |
| `unexpected_type` | a field has the wrong CBOR type | no | `field` |
| `item_too_large` | declared length exceeds the configured bound | no | `size`, `limit` |

### 3.4 `invalid_document`

| `code` | Meaning | `retryable` | `details` |
|---|---|---|---|
| `non_text_map_key` | a map in the document has a non-text key | no | `path` |
| `unsupported_float` | `NaN` / `±Infinity` | no | `path` |
| `unsupported_bignum` | CBOR tag 2/3 | no | `path` |
| `document_too_large` | exceeds `limits.document_bytes` | no | `size`, `limit` |
| `depth_exceeded` | nesting deeper than 100 | no | `limit` |
| `missing_id` | operation requires an `id` and none was given | no | — |
| `invalid_id_type` | `id` is not Int / Uuid(tag 37) / Text | no | `kind` |
| `id_too_long` | text id longer than 1024 bytes | no | `size`, `limit` |
| `collection_name_invalid` | length/charset/reserved-prefix violation | no | `name` |

### 3.5 `invalid_query`

| `code` | Meaning | `retryable` | `details` |
|---|---|---|---|
| `unknown_operator` | operator name not in the v1 set | no | `operator` |
| `bad_arity` | wrong number of arguments | no | `operator`, `expected`, `got` |
| `bad_argument_type` | argument has the wrong type | no | `operator`, `position` |
| `unsupported_comparison` | comparison on an opaque tagged value | no | — |
| `result_limit_exceeded` | more matches than `limits.query_results` | no | `limit` |
| `sort_memory_exceeded` | in-memory sort over its bound | no | `limit` |
| `expression_too_deep` | term tree nesting bound | no | `limit` |
| `cancelled` | cancelled through `cancel` | no | — |

### 3.6 `not_found`

| `code` | Meaning | `details` |
|---|---|---|
| `document_not_found` | no document with that id | `collection`, `id` |
| `collection_not_found` | no collection with that name | `collection` |
| `transaction_not_found` | unknown or already finished transaction | `transaction` |
| `feed_not_found` | unknown feed id | `feed` |

### 3.7 `conflict`

| `code` | Meaning | `retryable` | `details` |
|---|---|---|---|
| `document_exists` | `insert` on an existing id | no | `collection`, `id` |
| `collection_exists` | `collection.create` without `if_not_exists` | no | `collection` |
| `revision_conflict` | `if_rev` guard did not match | no | `collection`, `id`, `expected`, `actual` |
| `write_conflict` | write-write conflict detected at commit | no | `collection`, `id` |
| `writer_busy` | another read-write transaction is active | **yes** | — |

### 3.8 `transaction`

| `code` | Meaning | `retryable` | `details` |
|---|---|---|---|
| `aborted` | transaction was aborted; further use is invalid | no | `reason` |
| `timeout` | exceeded `limits.transaction_timeout_ms` | yes | `limit` |
| `too_large` | write set exceeds the memory budget | no | `limit` |
| `read_only_violation` | write attempted in a read-only transaction | no | — |
| `nested_not_supported` | `begin` inside a transaction | no | — |

### 3.9 `index` *(all reserved in M0)*

`index_exists`, `index_not_found`, `index_key_too_large`, `index_build_failed`.

### 3.10 `changefeed`

| `code` | Meaning | `retryable` | `details` |
|---|---|---|---|
| `feed_overflow` | subscriber queue overflowed (policy `disconnect`) | **yes** | `feed`, `queue` |
| `log_truncated` | requested `from_seq` is older than retained history | no | `from_seq`, `oldest_seq` |
| `too_many_feeds` | `limits.feeds` reached | yes | `limit` |
| `event_too_large` | a document cannot be streamed under the size limits | no | `id` |
| `expression_not_supported` | a term not allowed in a subscription | no | `operator` |

### 3.11 `protocol`

| `code` | Meaning | `retryable` | `details` |
|---|---|---|---|
| `version_unsupported` | no common protocol version | no | `client`, `server` |
| `feature_required` | a required feature was not granted | no | `feature` |
| `unknown_operation` | operation name not in v1 | no | `operation` |
| `unknown_transaction` | envelope references an unknown transaction | no | `transaction` |
| `duplicate_request` | request id already in flight | no | `request` |
| `malformed_item` | envelope itself unparseable/incomplete | no | `field` |
| `missing_field` / `wrong_field_type` | envelope field problem | no | `field` |
| `response_too_large` | response exceeds `limits.response_bytes` *(reserved)* | no | `limit` |

### 3.12 `internal`

| `code` | Meaning |
|---|---|
| `invariant_violation` | a proven invariant did not hold — always a bug, always reported |
| `unimplemented` | a specified-but-unimplemented path was reached (M0 has none) |

## 4. Rust types

`ErrorKind` and `ErrorCode` — the shared vocabulary of §2 and §3 — live in
`rtl-value`, the lowest crate. Every layer defines its **own** error enum
(`rtl_value::Error`, `rtl_storage::Error`, `rtl_core::Error`,
`rtl_protocol::Error`), each non-exhaustive, each implementing `kind()`,
`code()` and `retryable()` from that vocabulary, and each with a `From` impl for
the layer above it. One enum for the whole system was rejected: it would force
`rtl-value` to know about files, queries and feeds.

```rust
// rtl-value
pub enum ErrorKind { Io, Corruption, Serialization, InvalidDocument, InvalidQuery,
                     NotFound, Conflict, Transaction, Index, Changefeed, Protocol, Internal }

pub struct ErrorCode(&'static str);          // registry-checked, see §3
impl ErrorCode { pub const DOCUMENT_TOO_LARGE: ErrorCode = ErrorCode("document_too_large"); /* … */ }

// rtl-core, the type bindings see
#[non_exhaustive]
pub enum Error {
    Io(RtlIoError),
    Corruption { code: ErrorCode, page: Option<u32>, detail: String },
    Serialization { code: ErrorCode, offset: Option<usize> },
    InvalidDocument { code: ErrorCode, path: String },
    InvalidQuery { code: ErrorCode, operator: Option<String> },
    NotFound { code: ErrorCode, collection: Option<String>, id: Option<Id> },
    Conflict { code: ErrorCode, collection: Option<String>, id: Option<Id> },
    Transaction { code: ErrorCode },
    Index { code: ErrorCode },
    Changefeed { code: ErrorCode, feed: Option<u64> },
    Protocol { code: ErrorCode, field: Option<String> },
    Internal { code: ErrorCode, detail: String },
}

impl Error {
    pub fn kind(&self) -> ErrorKind { /* … */ }
    pub fn code(&self) -> ErrorCode { /* … */ }
    pub fn retryable(&self) -> bool { /* from the registry table */ }
}
```

`ErrorCode` is a `&'static str` newtype over the registry of §3; a unit test
asserts uniqueness and that every code reachable in the code base appears in the
registry. Errors implement `std::error::Error` and `Display` with a message that
names the operation and the object, and never quotes document content.

## 5. Protocol representation

```
{ "kind": "conflict", "code": "revision_conflict",
  "message": "document users/user-123 changed since the snapshot",
  "retryable": false,
  "details": { "expected": 3, "actual": 4 } }
```

* `details` is absent when empty; its fields per code are the tables above.
* `message` must not exceed 512 bytes and must not contain document values.
* A degenerate response (`{"protocol": 0|1, "request": 0, "status": "error", …}`)
  is used only when the envelope itself could not be parsed; the code is then
  `protocol` / `malformed_item`.

## 6. Binding guidance

| Language | Mapping |
|---|---|
| Rust | `rethinklite::Error` (non-exhaustive enum) |
| Python | `RethinkLiteError` base with a subclass per `kind`; `err.kind`, `err.code`, `err.details`, `err.retryable` attributes |
| Go | sentinel per `kind` (`ErrConflict`, `ErrNotFound`, …) wrapping a typed `*rtl.Error`; `errors.Is` works on the sentinel, `errors.As` gives the code/details |
| others | same rule: type per `kind`, discriminator per `code` |

Bindings must **not** invent codes for conditions the core reports, and must not
translate a `kind` into a different `kind`.

## 7. Test requirements

1. Registry test: every code is unique, every code in the source appears in the
   registry, every registry entry documents `kind`, `retryable` and `details`.
2. Compatibility test: the code list is compared against `tests/cbor/` fixtures
   and a checked-in snapshot, so a rename fails CI.
3. Per-`kind` fixture: `error_response.cbor` plus one fixture per `kind` at least.
4. Fuzz/negative tests: malformed CBOR, truncated items, deep nesting, huge
   declared lengths, non-text map keys, unknown operators — all must produce the
   documented code and never panic.
5. Panic guard: `#![deny(clippy::unwrap_used)]` in library crates (test code
   excepted), so principle §1.6 is enforced mechanically rather than by review.
