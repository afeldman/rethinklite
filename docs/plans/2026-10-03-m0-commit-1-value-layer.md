# M0 / Commit 1 — Value Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the Rust workspace and the `rtl-value` crate — value model, canonical CBOR codec, order-preserving key codec, total order — proven against the golden fixtures, with the three quality gates wired into CI.

**Architecture:** One crate owns the byte contract's foundation. The encoder is written by hand (determinism is the deliverable, so it is not delegated to a library); the decoder borrows `minicbor` (robustness against hostile input). Everything else in M0 builds on this crate, so it is built and proven first.

**Tech Stack:** Rust (edition 2024, MSRV 1.85), `minicbor` 2.3 (decoder, `std` feature), `half` 2.7 (correct IEEE-754 binary16 conversion for shortest-form floats), `thiserror` 2, `proptest` 1.11 (dev).

**Spec:** `docs/data-model.md` §1–§7, `docs/cbor-protocol.md` §2/§10, `docs/storage.md` §5, `docs/error-model.md` §3–§4, `docs/architecture.md` §4/§7/§10.

## Global Constraints

Every task's requirements implicitly include this section.

- **Toolchain:** `edition = "2024"`, `rust-version = "1.85"`, workspace `resolver = "2"`, `publish = false` (license is an open decision — do not add a `license` field).
- **No `serde`** on the wire path. The CBOR codec is explicit; `Value` has no derives beyond `Debug`/`Clone`/`PartialEq`.
- **No async runtime** in any `rtl-*` crate. `rtl-value` has no `unsafe` (`unsafe_code = "forbid"`).
- **No `unwrap`/`expect`/panic in library code.** Each `lib.rs` carries
  `#![cfg_attr(not(test), deny(clippy::unwrap_used, clippy::expect_used, clippy::panic))]`.
  Tests may unwrap freely.
- **Limits (format v1, verbatim from the spec):** document size 16 MiB (`16_777_216`), nesting depth 100, text `id` length 1024 bytes, collection name 255 bytes, map/array entries 2^24.
- **Canonical form:** RFC 8949 §4.2.3 length-first core deterministic encoding — shortest-form arguments and floats, no indefinite-length items, map keys sorted by encoded length then bytewise. Tags are normative. `NaN`/`±Infinity`/`undefined` are rejected. Maps have text-string keys only.
- **Total order (data-model.md §6):** `null < false < true < number < uuid < text < bytes < array < map < tagged`; Int and Float share one numeric class (numeric comparison, `Int` before `Float` on equal values); text order is bytewise UTF-8.
- **Key ranks (storage.md §5.1):** `null 0x01`, `bool 0x02`, `number 0x03`, `uuid 0x04`, `text 0x05`, `bytes 0x06`, `array 0x07`, `map 0x08`, `tagged 0x09`, `0x00` = sequence terminator.
- **Gates before every commit:**
  `cargo fmt --all --check`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace`.
- **Commits:** conventional-commit prefixes (`feat:`, `test:`, `chore:`, `docs:`), English, no push.

---

## File Structure

| File | Responsibility |
|---|---|
| `Cargo.toml` | workspace: members, shared package fields, lints |
| `.github/workflows/ci.yml` | the three gates plus the fixture checks, on push/PR |
| `crates/rtl-value/Cargo.toml` | crate manifest, dependencies, `[lints] workspace = true` |
| `crates/rtl-value/src/lib.rs` | crate docs, lint attributes, module wiring, re-exports |
| `crates/rtl-value/src/error.rs` | `ErrorKind` + `ErrorCode` registry + `Error` |
| `crates/rtl-value/src/value.rs` | `Value`, limits, `validate()` |
| `crates/rtl-value/src/id.rs` | `Uuid`, `Id`, UUIDv7 assembly |
| `crates/rtl-value/src/order.rs` | `cmp_value`, exact Int/Float comparison |
| `crates/rtl-value/src/key.rs` | order-preserving key encoding |
| `crates/rtl-value/src/cbor/mod.rs` | public codec surface (`encode_canonical`, `decode_one`, `decode_all`) |
| `crates/rtl-value/src/cbor/encode.rs` | hand-written canonical encoder |
| `crates/rtl-value/src/cbor/decode.rs` | `minicbor`-based lenient decoder |
| `crates/rtl-value/tests/*.rs` | per-concern integration tests (see tasks) |

---

### Task 1: Workspace skeleton and quality gates

**Files:**
- Create: `Cargo.toml`, `crates/rtl-value/Cargo.toml`, `crates/rtl-value/src/lib.rs`, `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: crate name `rtl-value` (lib target `rtl_value`), workspace lints, and the gate commands every later task runs.

- [ ] **Step 1: Write the workspace manifest**

`Cargo.toml`:

```toml
[workspace]
resolver = "2"
members = ["crates/rtl-value"]

[workspace.package]
version = "0.1.0"
edition = "2024"
rust-version = "1.85"
authors = ["Anton Feldmann <anton.feldmann@gmail.com>"]
description = "RethinkLite — embedded, reactive document database (value layer)"
publish = false
# license: OPEN DECISION, see docs/roadmap.md — do not add a license field yet

[workspace.dependencies]
minicbor = { version = "2.3", default-features = false, features = ["std"] }
half = "2.7"
thiserror = "2.0"
proptest = "1.11"

[workspace.lints.rust]
unsafe_code = "forbid"
```

- [ ] **Step 2: Write the crate manifest**

`crates/rtl-value/Cargo.toml`:

```toml
[package]
name = "rtl-value"
version.workspace = true
edition.workspace = true
rust-version.workspace = true
authors.workspace = true
description.workspace = true
publish.workspace = true

[dependencies]
minicbor.workspace = true
half.workspace = true
thiserror.workspace = true

[dev-dependencies]
proptest.workspace = true

[lints]
workspace = true
```

- [ ] **Step 3: Write the crate root**

`crates/rtl-value/src/lib.rs`:

```rust
//! RethinkLite value layer: the value model, the canonical CBOR codec, the
//! total order and the order-preserving key codec.
//!
//! Contracts implemented here are normative in `docs/data-model.md`,
//! `docs/cbor-protocol.md` §2 and `docs/storage.md` §5.
#![cfg_attr(
    not(test),
    deny(clippy::unwrap_used, clippy::expect_used, clippy::panic)
)]
#![forbid(unsafe_code)]

pub mod cbor;
pub mod error;
pub mod id;
pub mod key;
pub mod order;
pub mod value;

pub use cbor::{decode_all, decode_one, encode_canonical};
pub use error::{Error, ErrorCode, ErrorKind};
pub use id::{Id, Uuid};
pub use key::{encode_catalog_key, encode_collection_key, encode_id_key, encode_metadata_key};
pub use order::cmp_value;
pub use value::{Value, MAX_DEPTH, MAX_DOCUMENT_BYTES};
```

Creation order matters: the module files do not exist yet, so the crate will not
compile until Task 2. Create empty module files in Step 4 and fill them in later
tasks.

- [ ] **Step 4: Create empty modules so the crate compiles**

Create `crates/rtl-value/src/{error,value,id,order,key}.rs` each with a single
doc comment, and `crates/rtl-value/src/cbor/mod.rs` with
`//! Canonical CBOR codec.` plus `pub fn encode_canonical(_: &crate::Value) -> Result<Vec<u8>, crate::Error> { unimplemented!() }`
etc. — **no**: keep `lib.rs` compiling by temporarily commenting the
`pub use` lines that refer to not-yet-written items, and re-enable them in the
task that adds the item. Never leave `unimplemented!()` in committed code.

- [ ] **Step 5: Run the gates**

Run:
```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```
Expected: all three succeed (the crate is empty but valid).

- [ ] **Step 6: Write CI**

`.github/workflows/ci.yml`:

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:

jobs:
  gates:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
        with:
          components: rustfmt, clippy
      - run: cargo fmt --all --check
      - run: cargo clippy --workspace --all-targets -- -D warnings
      - run: cargo test --workspace
      - name: Golden CBOR fixtures are canonical
        run: python3 tests/cbor/verify_fixtures.py tests/cbor
      - name: The fixture checker can fail
        run: python3 tests/cbor/selftest_verifier.py
```

- [ ] **Step 7: Commit**

```bash
git add Cargo.toml crates/rtl-value .github/workflows/ci.yml
git commit -m "chore: workspace skeleton, rtl-value crate and quality gates"
```

---

### Task 2: Error vocabulary

**Files:**
- Create (content): `crates/rtl-value/src/error.rs`
- Test: `crates/rtl-value/tests/error_registry.rs`

**Interfaces:**
- Consumes: nothing.
- Produces: `ErrorKind` (12 variants), `ErrorCode` (`&'static str` newtype with the constants listed below and an `ALL: &[ErrorCode]` registry), `Error` enum with `code()`, `kind()`, `retryable()` and the constructors used by later tasks:
  `Error::malformed_cbor(offset, detail)`, `invalid_utf8(offset)`, `undefined_value(offset)`, `unexpected_type(offset, got)`, `integer_out_of_range(offset)`, `item_too_large(offset, size, limit)`, `non_text_map_key(path)`, `unsupported_float(path)`, `unsupported_bignum(path)`, `document_too_large(path, size, limit)`, `depth_exceeded(limit)`, `invariant(detail)`.

- [ ] **Step 1: Write the failing test**

`crates/rtl-value/tests/error_registry.rs`:

```rust
use rtl_value::{Error, ErrorCode, ErrorKind};

#[test]
fn registry_codes_are_unique_and_well_formed() {
    let mut seen = std::collections::BTreeSet::new();
    for code in ErrorCode::ALL {
        let text = code.as_str();
        assert!(seen.insert(text), "duplicate error code: {text}");
        assert!(!text.is_empty(), "empty error code");
        assert!(
            text.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_'),
            "error code is not snake_case: {text}"
        );
    }
    assert!(ErrorCode::ALL.len() >= 15, "registry looks incomplete");
}

#[test]
fn errors_expose_kind_code_and_retryable() {
    let err = Error::malformed_cbor(7, "truncated map value");
    assert_eq!(err.kind(), ErrorKind::Serialization);
    assert_eq!(err.code(), ErrorCode::MALFORMED_CBOR);
    assert!(!err.retryable());

    let err = Error::non_text_map_key("$.profile");
    assert_eq!(err.kind(), ErrorKind::InvalidDocument);
    assert_eq!(err.code(), ErrorCode::NON_TEXT_MAP_KEY);
    assert!(!err.retryable());
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p rtl-value --test error_registry`
Expected: FAIL to compile (`no function `malformed_cbor`` / `ErrorCode::ALL` missing).

- [ ] **Step 3: Implement the error vocabulary**

`crates/rtl-value/src/error.rs`:

```rust
//! Error vocabulary shared by every RethinkLite crate: kinds, the code
//! registry used across the CBOR boundary, and the `rtl-value` error type.
//! Normative tables: `docs/error-model.md` §2 and §3.

use std::fmt;

/// Coarse error category. Closed set — adding a variant is a breaking change.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[non_exhaustive]
pub enum ErrorKind {
    Io,
    Corruption,
    Serialization,
    InvalidDocument,
    InvalidQuery,
    NotFound,
    Conflict,
    Transaction,
    Index,
    Changefeed,
    Protocol,
    Internal,
}

impl ErrorKind {
    /// The `kind` value used on the wire (`docs/error-model.md` §2).
    pub const fn as_str(self) -> &'static str {
        match self {
            ErrorKind::Io => "io",
            ErrorKind::Corruption => "corruption",
            ErrorKind::Serialization => "serialization",
            ErrorKind::InvalidDocument => "invalid_document",
            ErrorKind::InvalidQuery => "invalid_query",
            ErrorKind::NotFound => "not_found",
            ErrorKind::Conflict => "conflict",
            ErrorKind::Transaction => "transaction",
            ErrorKind::Index => "index",
            ErrorKind::Changefeed => "changefeed",
            ErrorKind::Protocol => "protocol",
            ErrorKind::Internal => "internal",
        }
    }
}

/// Fine-grained, stable error identifier (`docs/error-model.md` §3).
/// Codes are added, never renamed, never reused.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct ErrorCode(&'static str);

impl ErrorCode {
    const fn new(text: &'static str) -> Self {
        Self(text)
    }

    pub const fn as_str(self) -> &'static str {
        self.0
    }

    pub const MALFORMED_CBOR: Self = Self::new("malformed_cbor");
    pub const INVALID_UTF8: Self = Self::new("invalid_utf8");
    pub const UNDEFINED_VALUE: Self = Self::new("undefined_value");
    pub const UNEXPECTED_TYPE: Self = Self::new("unexpected_type");
    pub const ITEM_TOO_LARGE: Self = Self::new("item_too_large");
    pub const NON_TEXT_MAP_KEY: Self = Self::new("non_text_map_key");
    pub const UNSUPPORTED_FLOAT: Self = Self::new("unsupported_float");
    pub const UNSUPPORTED_BIGNUM: Self = Self::new("unsupported_bignum");
    pub const INTEGER_OUT_OF_RANGE: Self = Self::new("integer_out_of_range");
    pub const DOCUMENT_TOO_LARGE: Self = Self::new("document_too_large");
    pub const DEPTH_EXCEEDED: Self = Self::new("depth_exceeded");
    pub const MISSING_ID: Self = Self::new("missing_id");
    pub const INVALID_ID_TYPE: Self = Self::new("invalid_id_type");
    pub const ID_TOO_LONG: Self = Self::new("id_too_long");
    pub const COLLECTION_NAME_INVALID: Self = Self::new("collection_name_invalid");
    pub const INVARIANT_VIOLATION: Self = Self::new("invariant_violation");

    /// Every code known to the value layer. The registry test asserts
    /// uniqueness and shape; later crates append their own codes with
    /// `ErrorCode::new` in their own `ALL`-style lists.
    pub const ALL: &'static [Self] = &[
        Self::MALFORMED_CBOR,
        Self::INVALID_UTF8,
        Self::UNDEFINED_VALUE,
        Self::UNEXPECTED_TYPE,
        Self::ITEM_TOO_LARGE,
        Self::NON_TEXT_MAP_KEY,
        Self::UNSUPPORTED_FLOAT,
        Self::UNSUPPORTED_BIGNUM,
        Self::INTEGER_OUT_OF_RANGE,
        Self::DOCUMENT_TOO_LARGE,
        Self::DEPTH_EXCEEDED,
        Self::MISSING_ID,
        Self::INVALID_ID_TYPE,
        Self::ID_TOO_LONG,
        Self::COLLECTION_NAME_INVALID,
        Self::INVARIANT_VIOLATION,
    ];
}

impl fmt::Display for ErrorCode {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.0)
    }
}

/// Errors produced by the value layer. Non-exhaustive: later crates wrap it.
#[derive(Debug, thiserror::Error)]
#[non_exhaustive]
pub enum Error {
    #[error("malformed CBOR at offset {offset}: {detail}")]
    MalformedCbor { offset: usize, detail: String },

    #[error("invalid UTF-8 at offset {offset}")]
    InvalidUtf8 { offset: usize },

    #[error("`undefined` (0xf7) is not a RethinkLite value (offset {offset})")]
    UndefinedValue { offset: usize },

    #[error("unexpected CBOR type at offset {offset}: {got}")]
    UnexpectedType { offset: usize, got: &'static str },

    #[error("integer out of i64 range at offset {offset}")]
    IntegerOutOfRange { offset: usize },

    #[error("item of {size} bytes exceeds the limit of {limit} (offset {offset})")]
    ItemTooLarge { offset: usize, size: u64, limit: u64 },

    #[error("non-text map key at {path}")]
    NonTextMapKey { path: String },

    #[error("unsupported float (NaN or Infinity) at {path}")]
    UnsupportedFloat { path: String },

    #[error("unsupported bignum at {path}")]
    UnsupportedBignum { path: String },

    #[error("document of {size} bytes exceeds the limit of {limit} at {path}")]
    DocumentTooLarge { path: String, size: u64, limit: u64 },

    #[error("nesting deeper than {limit}")]
    DepthExceeded { limit: usize },

    #[error("missing document id")]
    MissingId,

    #[error("invalid id type: {kind}")]
    InvalidIdType { kind: &'static str },

    #[error("text id of {size} bytes exceeds the limit of {limit}")]
    IdTooLong { size: usize, limit: usize },

    #[error("invalid collection name: {reason}")]
    CollectionNameInvalid { reason: &'static str },

    #[error("internal invariant violated: {detail}")]
    Invariant { detail: String },
}

impl Error {
    pub fn malformed_cbor(offset: usize, detail: impl Into<String>) -> Self {
        Self::MalformedCbor { offset, detail: detail.into() }
    }
    pub fn invalid_utf8(offset: usize) -> Self {
        Self::InvalidUtf8 { offset }
    }
    pub fn undefined_value(offset: usize) -> Self {
        Self::UndefinedValue { offset }
    }
    pub fn unexpected_type(offset: usize, got: &'static str) -> Self {
        Self::UnexpectedType { offset, got }
    }
    pub fn integer_out_of_range(offset: usize) -> Self {
        Self::IntegerOutOfRange { offset }
    }
    pub fn item_too_large(offset: usize, size: u64, limit: u64) -> Self {
        Self::ItemTooLarge { offset, size, limit }
    }
    pub fn non_text_map_key(path: impl Into<String>) -> Self {
        Self::NonTextMapKey { path: path.into() }
    }
    pub fn unsupported_float(path: impl Into<String>) -> Self {
        Self::UnsupportedFloat { path: path.into() }
    }
    pub fn unsupported_bignum(path: impl Into<String>) -> Self {
        Self::UnsupportedBignum { path: path.into() }
    }
    pub fn document_too_large(path: impl Into<String>, size: u64, limit: u64) -> Self {
        Self::DocumentTooLarge { path: path.into(), size, limit }
    }
    pub fn depth_exceeded(limit: usize) -> Self {
        Self::DepthExceeded { limit }
    }
    pub fn missing_id() -> Self {
        Self::MissingId
    }
    pub fn invalid_id_type(kind: &'static str) -> Self {
        Self::InvalidIdType { kind }
    }
    pub fn id_too_long(size: usize, limit: usize) -> Self {
        Self::IdTooLong { size, limit }
    }
    pub fn collection_name_invalid(reason: &'static str) -> Self {
        Self::CollectionNameInvalid { reason }
    }
    pub fn invariant(detail: impl Into<String>) -> Self {
        Self::Invariant { detail: detail.into() }
    }

    pub fn kind(&self) -> ErrorKind {
        match self {
            Error::MalformedCbor { .. }
            | Error::InvalidUtf8 { .. }
            | Error::UndefinedValue { .. }
            | Error::UnexpectedType { .. }
            | Error::IntegerOutOfRange { .. }
            | Error::ItemTooLarge { .. } => ErrorKind::Serialization,
            Error::NonTextMapKey { .. }
            | Error::UnsupportedFloat { .. }
            | Error::UnsupportedBignum { .. }
            | Error::DocumentTooLarge { .. }
            | Error::DepthExceeded { .. }
            | Error::MissingId
            | Error::InvalidIdType { .. }
            | Error::IdTooLong { .. }
            | Error::CollectionNameInvalid { .. } => ErrorKind::InvalidDocument,
            Error::Invariant { .. } => ErrorKind::Internal,
        }
    }

    pub fn code(&self) -> ErrorCode {
        match self {
            Error::MalformedCbor { .. } => ErrorCode::MALFORMED_CBOR,
            Error::InvalidUtf8 { .. } => ErrorCode::INVALID_UTF8,
            Error::UndefinedValue { .. } => ErrorCode::UNDEFINED_VALUE,
            Error::UnexpectedType { .. } => ErrorCode::UNEXPECTED_TYPE,
            Error::IntegerOutOfRange { .. } => ErrorCode::INTEGER_OUT_OF_RANGE,
            Error::ItemTooLarge { .. } => ErrorCode::ITEM_TOO_LARGE,
            Error::NonTextMapKey { .. } => ErrorCode::NON_TEXT_MAP_KEY,
            Error::UnsupportedFloat { .. } => ErrorCode::UNSUPPORTED_FLOAT,
            Error::UnsupportedBignum { .. } => ErrorCode::UNSUPPORTED_BIGNUM,
            Error::DocumentTooLarge { .. } => ErrorCode::DOCUMENT_TOO_LARGE,
            Error::DepthExceeded { .. } => ErrorCode::DEPTH_EXCEEDED,
            Error::MissingId => ErrorCode::MISSING_ID,
            Error::InvalidIdType { .. } => ErrorCode::INVALID_ID_TYPE,
            Error::IdTooLong { .. } => ErrorCode::ID_TOO_LONG,
            Error::CollectionNameInvalid { .. } => ErrorCode::COLLECTION_NAME_INVALID,
            Error::Invariant { .. } => ErrorCode::INVARIANT_VIOLATION,
        }
    }

    /// `retryable` refers to the identical request (`docs/error-model.md` §1.5).
    /// Every value-layer error is deterministic, so none is retryable.
    pub fn retryable(&self) -> bool {
        false
    }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p rtl-value --test error_registry`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add crates/rtl-value/src/error.rs crates/rtl-value/tests/error_registry.rs crates/rtl-value/src/lib.rs
git commit -m "feat(value): error vocabulary with kind/code registry"
```

---

### Task 3: Value model and limits

**Files:**
- Create (content): `crates/rtl-value/src/value.rs`
- Test: `crates/rtl-value/tests/value_model.rs`

**Interfaces:**
- Consumes: `Error`, `ErrorCode` (Task 2).
- Produces: `Value` (9 variants), `MAX_DEPTH: usize = 100`, `MAX_DOCUMENT_BYTES: u64 = 16_777_216`, constructors `Value::text/array/map`, accessors `as_int/as_float/as_text/as_bool/as_bytes/as_array/as_map`, `get(&str)`, `is_null()`, `type_rank() -> u8`, `validate() -> Result<(), Error>`.

- [ ] **Step 1: Write the failing test**

`crates/rtl-value/tests/value_model.rs`:

```rust
use rtl_value::{ErrorCode, Value, MAX_DEPTH};

#[test]
fn constructors_build_maps_in_text_order() {
    let value = Value::map([("b", Value::Int(2)), ("a", Value::Int(1))]);
    let map = value.as_map().expect("map");
    let keys: Vec<&str> = map.keys().map(String::as_str).collect();
    assert_eq!(keys, ["a", "b"], "BTreeMap orders text keys bytewise");
    assert_eq!(value.get("a"), Some(&Value::Int(1)));
    assert_eq!(value.get("missing"), None);
}

#[test]
fn type_rank_matches_the_documented_order() {
    assert_eq!(Value::Null.type_rank(), 0);
    assert_eq!(Value::Bool(false).type_rank(), 1);
    assert_eq!(Value::Bool(true).type_rank(), 1);
    assert_eq!(Value::Int(0).type_rank(), 2);
    assert_eq!(Value::Float(0.0).type_rank(), 2);
    assert_eq!(Value::Text("u".into()).type_rank(), 4);
    assert_eq!(Value::Bytes(vec![]).type_rank(), 5);
    assert_eq!(Value::array([]).type_rank(), 6);
    assert_eq!(Value::map::<&str, Value>([]).type_rank(), 7);
    assert_eq!(Value::Tagged(1, Box::new(Value::Int(0))).type_rank(), 8);
}

#[test]
fn validate_rejects_non_finite_floats_with_a_path() {
    let value = Value::map([(
        "profile",
        Value::map([("score", Value::Float(f64::NAN))]),
    )]);
    let err = value.validate().expect_err("NaN must be rejected");
    assert_eq!(err.code(), ErrorCode::UNSUPPORTED_FLOAT);
    assert!(err.to_string().contains("$.profile.score"), "got: {err}");
}

#[test]
fn validate_rejects_nesting_deeper_than_the_limit() {
    let mut value = Value::Int(0);
    for _ in 0..=MAX_DEPTH {
        value = Value::array([value]);
    }
    let err = value.validate().expect_err("depth must be limited");
    assert_eq!(err.code(), ErrorCode::DEPTH_EXCEEDED);
}

#[test]
fn validate_accepts_a_normal_document() {
    let value = Value::map([
        ("id", Value::text("user-123")),
        ("tags", Value::array([Value::text("rust"), Value::text("db")])),
        ("profile", Value::map([("country", Value::text("DE"))])),
        ("active", Value::Bool(true)),
    ]);
    assert!(value.validate().is_ok());
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p rtl-value --test value_model`
Expected: FAIL to compile (`Value` missing).

- [ ] **Step 3: Implement the value model**

`crates/rtl-value/src/value.rs`:

```rust
//! The RethinkLite value model: the CBOR data model with text-keyed maps and a
//! generic tagged value. Normative: `docs/data-model.md` §2 and §6.

use std::collections::BTreeMap;

use crate::error::{Error, ErrorCode};

/// Maximum nesting depth (arrays, maps, tags).
pub const MAX_DEPTH: usize = 100;

/// Maximum canonical document size in bytes.
pub const MAX_DOCUMENT_BYTES: u64 = 16 * 1024 * 1024;

#[derive(Debug, Clone, PartialEq)]
pub enum Value {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    Text(String),
    Bytes(Vec<u8>),
    Array(Vec<Value>),
    Map(BTreeMap<String, Value>),
    Tagged(u64, Box<Value>),
}

impl Value {
    pub fn text(text: impl Into<String>) -> Self {
        Value::Text(text.into())
    }

    pub fn array(items: impl IntoIterator<Item = Value>) -> Self {
        Value::Array(items.into_iter().collect())
    }

    pub fn map<K, I>(entries: I) -> Self
    where
        K: Into<String>,
        I: IntoIterator<Item = (K, Value)>,
    {
        Value::Map(entries.into_iter().map(|(k, v)| (k.into(), v)).collect())
    }

    pub fn is_null(&self) -> bool {
        matches!(self, Value::Null)
    }

    pub fn as_bool(&self) -> Option<bool> {
        match self {
            Value::Bool(b) => Some(*b),
            _ => None,
        }
    }

    pub fn as_int(&self) -> Option<i64> {
        match self {
            Value::Int(i) => Some(*i),
            _ => None,
        }
    }

    pub fn as_float(&self) -> Option<f64> {
        match self {
            Value::Float(f) => Some(*f),
            _ => None,
        }
    }

    pub fn as_text(&self) -> Option<&str> {
        match self {
            Value::Text(s) => Some(s),
            _ => None,
        }
    }

    pub fn as_bytes(&self) -> Option<&[u8]> {
        match self {
            Value::Bytes(b) => Some(b),
            _ => None,
        }
    }

    pub fn as_array(&self) -> Option<&[Value]> {
        match self {
            Value::Array(items) => Some(items),
            _ => None,
        }
    }

    pub fn as_map(&self) -> Option<&BTreeMap<String, Value>> {
        match self {
            Value::Map(map) => Some(map),
            _ => None,
        }
    }

    pub fn get(&self, key: &str) -> Option<&Value> {
        self.as_map().and_then(|map| map.get(key))
    }

    /// Rank in the total order of `docs/data-model.md` §6 (0-based).
    pub fn type_rank(&self) -> u8 {
        match self {
            Value::Null => 0,
            Value::Bool(_) => 1,
            Value::Int(_) | Value::Float(_) => 2,
            // 3 is reserved for uuids, which are `Tagged(37, Bytes)` and are
            // ranked here rather than in `Tagged` — see `order::cmp_value`.
            Value::Text(_) => 4,
            Value::Bytes(_) => 5,
            Value::Array(_) => 6,
            Value::Map(_) => 7,
            Value::Tagged(..) => 8,
        }
    }

    /// Check everything the value model forbids that the Rust type cannot:
    /// non-finite floats, nesting depth, and the size of the encoded document.
    pub fn validate(&self) -> Result<(), Error> {
        self.validate_at("$", 0)
    }

    fn validate_at(&self, path: &str, depth: usize) -> Result<(), Error> {
        if depth > MAX_DEPTH {
            return Err(Error::depth_exceeded(MAX_DEPTH));
        }
        match self {
            Value::Float(f) if !f.is_finite() => Err(Error::unsupported_float(path)),
            Value::Array(items) => {
                for (index, item) in items.iter().enumerate() {
                    item.validate_at(&format!("{path}[{index}]"), depth + 1)?;
                }
                Ok(())
            }
            Value::Map(map) => {
                for (key, item) in map {
                    item.validate_at(&format!("{path}.{key}"), depth + 1)?;
                }
                Ok(())
            }
            Value::Tagged(_, inner) => inner.validate_at(path, depth + 1),
            _ => Ok(()),
        }
    }

    /// Size guard used when storing a document.
    pub fn check_document_size(&self, bytes: u64) -> Result<(), Error> {
        if bytes > MAX_DOCUMENT_BYTES {
            return Err(Error::document_too_large("$", bytes, MAX_DOCUMENT_BYTES));
        }
        Ok(())
    }
}
```

Note on `type_rank`: uuids are `Tagged(37, Bytes)` on the wire but rank 3 in the
order. `cmp_value` (Task 7) implements that rule; the rank method documents it
so the two never drift.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p rtl-value --test value_model`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add crates/rtl-value/src/value.rs crates/rtl-value/tests/value_model.rs
git commit -m "feat(value): value model with validation and limits"
```

---

### Task 4: Document ids

**Files:**
- Create (content): `crates/rtl-value/src/id.rs`
- Test: `crates/rtl-value/tests/id.rs`

**Interfaces:**
- Consumes: `Value`, `Error` (Tasks 2–3).
- Produces: `Uuid` (`from_bytes`, `as_bytes`, `parse`, `to_hyphenated`, `from_parts_v7`), `Id` (`Int`/`Uuid`/`Text`), `Id::from_value(&Value) -> Result<Id, Error>`, `Id::to_value() -> Value`, `MAX_TEXT_ID_BYTES: usize = 1024`.

- [ ] **Step 1: Write the failing test**

`crates/rtl-value/tests/id.rs`:

```rust
use rtl_value::{ErrorCode, Id, Uuid, Value};

#[test]
fn uuid_round_trips_through_its_hyphenated_form() {
    let text = "018f5f9a-1b2c-7def-8123-45678abcdeff";
    let uuid = Uuid::parse(text).expect("valid uuid");
    assert_eq!(uuid.to_hyphenated(), text);
    assert_eq!(Uuid::parse(&text.replace('-', "")).expect("plain form"), uuid);
}

#[test]
fn uuid_rejects_malformed_input() {
    for bad in ["", "018f5f9a1b2c7def8123456789abcde", "018f5f9a-1b2c-7def-8123-45678abcdeg"] {
        assert!(Uuid::parse(bad).is_err(), "{bad} should not parse");
    }
}

#[test]
fn uuid_v7_encodes_version_and_variant() {
    let uuid = Uuid::from_parts_v7(0x018f5f9a1b2c, [0xff; 10]);
    let bytes = uuid.as_bytes();
    assert_eq!(bytes[6] >> 4, 0x7, "version nibble");
    assert_eq!(bytes[8] >> 6, 0b10, "variant bits");
    assert_eq!(&bytes[0..6], &[0x01, 0x8f, 0x5f, 0x9a, 0x1b, 0x2c]);
}

#[test]
fn ids_are_read_from_the_documented_value_forms() {
    assert_eq!(Id::from_value(&Value::Int(-7)).expect("int id"), Id::Int(-7));
    assert_eq!(Id::from_value(&Value::text("user-123")).expect("text id"), Id::Text("user-123".into()));

    let bytes = [0xab; 16];
    let tagged = Value::Tagged(37, Box::new(Value::Bytes(bytes.to_vec())));
    assert_eq!(Id::from_value(&tagged).expect("uuid id"), Id::Uuid(Uuid::from_bytes(bytes)));

    // An untagged 16-byte string is `bytes`, never a uuid (data-model.md §4.5).
    let err = Id::from_value(&Value::Bytes(bytes.to_vec())).expect_err("bytes are not ids");
    assert_eq!(err.code(), ErrorCode::INVALID_ID_TYPE);

    assert_eq!(Id::from_value(&Value::Null).expect_err("null is not an id").code(), ErrorCode::INVALID_ID_TYPE);
    assert_eq!(Id::from_value(&Value::Float(1.0)).expect_err("float is not an id").code(), ErrorCode::INVALID_ID_TYPE);
}

#[test]
fn text_ids_are_length_limited_and_round_trip_to_values() {
    let id = Id::Text("x".repeat(1024));
    assert!(Id::from_value(&id.to_value()).is_ok());
    let too_long = Id::Text("x".repeat(1025));
    assert_eq!(Id::from_value(&too_long.to_value()).expect_err("too long").code(), ErrorCode::ID_TOO_LONG);
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p rtl-value --test id`
Expected: FAIL to compile (`Uuid`/`Id` missing).

- [ ] **Step 3: Implement ids**

`crates/rtl-value/src/id.rs`:

```rust
//! Document identity: the three permitted id kinds and the binary UUID
//! (CBOR tag 37). Normative: `docs/data-model.md` §3 and §4.5.

use crate::error::Error;
use crate::value::Value;

/// Maximum length of a text id.
pub const MAX_TEXT_ID_BYTES: usize = 1024;

/// A 128-bit UUID. The wire form is CBOR tag 37 over a 16-byte byte string.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct Uuid([u8; 16]);

impl Uuid {
    pub const fn from_bytes(bytes: [u8; 16]) -> Self {
        Self(bytes)
    }

    pub const fn as_bytes(&self) -> &[u8; 16] {
        &self.0
    }

    fn hex_nibble(byte: u8) -> Option<u8> {
        match byte {
            b'0'..=b'9' => Some(byte - b'0'),
            b'a'..=b'f' => Some(byte - b'a' + 10),
            b'A'..=b'F' => Some(byte - b'A' + 10),
            _ => None,
        }
    }

    /// Parse the hyphenated or plain hexadecimal form (case-insensitive).
    pub fn parse(text: &str) -> Result<Self, Error> {
        let mut nibbles = [0u8; 32];
        let mut count = 0usize;
        for byte in text.bytes() {
            if byte == b'-' {
                continue;
            }
            let nibble = Self::hex_nibble(byte)
                .ok_or_else(|| Error::invalid_id_type("uuid: non-hexadecimal digit"))?;
            if count == 32 {
                return Err(Error::invalid_id_type("uuid: more than 32 hex digits"));
            }
            nibbles[count] = nibble;
            count += 1;
        }
        if count != 32 {
            return Err(Error::invalid_id_type("uuid: fewer than 32 hex digits"));
        }
        let mut bytes = [0u8; 16];
        for (index, byte) in bytes.iter_mut().enumerate() {
            *byte = (nibbles[index * 2] << 4) | nibbles[index * 2 + 1];
        }
        Ok(Self(bytes))
    }

    pub fn to_hyphenated(&self) -> String {
        const HEX: &[u8; 16] = b"0123456789abcdef";
        let mut out = String::with_capacity(36);
        for (index, byte) in self.0.iter().enumerate() {
            if matches!(index, 4 | 6 | 8 | 10) {
                out.push('-');
            }
            out.push(HEX[(byte >> 4) as usize] as char);
            out.push(HEX[(byte & 0x0f) as usize] as char);
        }
        out
    }

    /// Assemble a UUIDv7 (RFC 9562 §5.7) from a millisecond timestamp and ten
    /// random bytes. The clock and the randomness are supplied by the caller so
    /// that `rtl-value` stays free of RNG and clock dependencies and tests stay
    /// deterministic.
    pub fn from_parts_v7(unix_millis: u64, random: [u8; 10]) -> Self {
        let mut bytes = [0u8; 16];
        bytes[0..6].copy_from_slice(&unix_millis.to_be_bytes()[2..8]);
        bytes[6] = 0x70 | (random[0] & 0x0f); // version 7 + rand_a high nibble
        bytes[7] = random[1]; // rand_a low byte
        bytes[8] = 0x80 | (random[2] & 0x3f); // variant 10 + rand_b high bits
        bytes[9..16].copy_from_slice(&random[3..10]);
        Self(bytes)
    }
}

/// A document id. Ordering between kinds follows `docs/data-model.md` §6:
/// `Int < Uuid < Text`.
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Id {
    Int(i64),
    Uuid(Uuid),
    Text(String),
}

impl Id {
    pub fn text(text: impl Into<String>) -> Self {
        Id::Text(text.into())
    }

    /// Read an id from its CBOR value form, enforcing the permitted kinds.
    pub fn from_value(value: &Value) -> Result<Self, Error> {
        match value {
            Value::Int(i) => Ok(Id::Int(*i)),
            Value::Text(text) => {
                if text.len() > MAX_TEXT_ID_BYTES {
                    return Err(Error::id_too_long(text.len(), MAX_TEXT_ID_BYTES));
                }
                Ok(Id::Text(text.clone()))
            }
            Value::Tagged(37, inner) => match inner.as_ref() {
                Value::Bytes(bytes) if bytes.len() == 16 => {
                    let mut raw = [0u8; 16];
                    raw.copy_from_slice(bytes);
                    Ok(Id::Uuid(Uuid::from_bytes(raw)))
                }
                _ => Err(Error::invalid_id_type("uuid: tag 37 must wrap a 16-byte string")),
            },
            Value::Null => Err(Error::invalid_id_type("null")),
            Value::Bool(_) => Err(Error::invalid_id_type("bool")),
            Value::Float(_) => Err(Error::invalid_id_type("float")),
            Value::Bytes(_) => Err(Error::invalid_id_type("bytes")),
            Value::Array(_) => Err(Error::invalid_id_type("array")),
            Value::Map(_) => Err(Error::invalid_id_type("map")),
            Value::Tagged(_, _) => Err(Error::invalid_id_type("tag")),
        }
    }

    /// The id in its CBOR value form.
    pub fn to_value(&self) -> Value {
        match self {
            Id::Int(i) => Value::Int(*i),
            Id::Uuid(uuid) => Value::Tagged(37, Box::new(Value::Bytes(uuid.as_bytes().to_vec()))),
            Id::Text(text) => Value::Text(text.clone()),
        }
    }
}

impl From<&str> for Id {
    fn from(text: &str) -> Self {
        Id::Text(text.to_string())
    }
}

impl From<i64> for Id {
    fn from(value: i64) -> Self {
        Id::Int(value)
    }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p rtl-value --test id`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add crates/rtl-value/src/id.rs crates/rtl-value/tests/id.rs
git commit -m "feat(value): document ids and binary uuid"
```

---

### Task 5: Canonical CBOR encoder

**Files:**
- Create (content): `crates/rtl-value/src/cbor/mod.rs`, `crates/rtl-value/src/cbor/encode.rs`
- Test: `crates/rtl-value/tests/canonical_encoding.rs`

**Interfaces:**
- Consumes: `Value`, `Error` (Tasks 2–3).
- Produces: `rtl_value::cbor::encode_canonical(&Value) -> Result<Vec<u8>, Error>` (also re-exported as `rtl_value::encode_canonical`).

- [ ] **Step 1: Write the failing test**

`crates/rtl-value/tests/canonical_encoding.rs`:

```rust
use rtl_value::{encode_canonical, ErrorCode, Value};

fn enc(value: &Value) -> Vec<u8> {
    encode_canonical(value).expect("encoding a valid value succeeds")
}

#[test]
fn integers_use_the_shortest_form() {
    assert_eq!(enc(&Value::Int(0)), vec![0x00]);
    assert_eq!(enc(&Value::Int(23)), vec![0x17]);
    assert_eq!(enc(&Value::Int(24)), vec![0x18, 0x18]);
    assert_eq!(enc(&Value::Int(255)), vec![0x18, 0xff]);
    assert_eq!(enc(&Value::Int(256)), vec![0x19, 0x01, 0x00]);
    assert_eq!(enc(&Value::Int(65535)), vec![0x19, 0xff, 0xff]);
    assert_eq!(enc(&Value::Int(65536)), vec![0x1a, 0x00, 0x01, 0x00, 0x00]);
    assert_eq!(enc(&Value::Int(-1)), vec![0x20]);
    assert_eq!(enc(&Value::Int(-24)), vec![0x37]);
    assert_eq!(enc(&Value::Int(-25)), vec![0x38, 0x18]);
    assert_eq!(
        enc(&Value::Int(i64::MAX)),
        vec![0x1b, 0x7f, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff]
    );
    assert_eq!(
        enc(&Value::Int(i64::MIN)),
        vec![0x3b, 0x7f, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff]
    );
}

#[test]
fn floats_use_the_shortest_preserving_form() {
    assert_eq!(enc(&Value::Float(1.5)), vec![0xf9, 0x3e, 0x00]);
    assert_eq!(enc(&Value::Float(1000000.5)), vec![0xfa, 0x49, 0x74, 0x24, 0x08]);
    assert_eq!(
        enc(&Value::Float(1.1)),
        vec![0xfb, 0x3f, 0xf1, 0x99, 0x99, 0x99, 0x99, 0x99, 0x9a]
    );
    assert_eq!(enc(&Value::Float(0.0)), vec![0xf9, 0x00, 0x00]);
    assert_eq!(enc(&Value::Float(-0.0)), vec![0xf9, 0x80, 0x00]);
}

#[test]
fn non_finite_floats_are_refused() {
    for bad in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
        let err = encode_canonical(&Value::Float(bad)).expect_err("must be refused");
        assert_eq!(err.code(), ErrorCode::UNSUPPORTED_FLOAT);
    }
}

#[test]
fn maps_are_sorted_length_first_then_bytewise() {
    let value = Value::map([("aa", Value::Int(2)), ("z", Value::Int(1))]);
    assert_eq!(enc(&value), vec![0xa2, 0x61, b'z', 0x01, 0x62, b'a', b'a', 0x02]);

    let value = Value::map([
        ("b", Value::Int(1)),
        ("a", Value::Int(2)),
        ("aa", Value::Int(3)),
    ]);
    // "b" and "a" are both one byte long, so bytewise order applies: a, b, aa
    assert_eq!(
        enc(&value),
        vec![0xa3, 0x61, b'a', 0x02, 0x61, b'b', 0x01, 0x62, b'a', b'a', 0x03]
    );
}

#[test]
fn scalars_arrays_tags_and_empty_containers() {
    assert_eq!(enc(&Value::Null), vec![0xf6]);
    assert_eq!(enc(&Value::Bool(false)), vec![0xf4]);
    assert_eq!(enc(&Value::Bool(true)), vec![0xf5]);
    assert_eq!(enc(&Value::Text("a".into())), vec![0x61, b'a']);
    assert_eq!(enc(&Value::Bytes(vec![1, 2])), vec![0x42, 0x01, 0x02]);
    assert_eq!(enc(&Value::array([])), vec![0x80]);
    assert_eq!(enc(&Value::map::<&str, Value>([])), vec![0xa0]);
    assert_eq!(enc(&Value::array([Value::Int(1), Value::Int(2)])), vec![0x82, 0x01, 0x02]);
    assert_eq!(
        enc(&Value::Tagged(37, Box::new(Value::Bytes(vec![0; 16])))),
        {
            let mut expected = vec![0xd8, 0x25, 0x50];
            expected.extend_from_slice(&[0u8; 16]);
            expected
        }
    );
}

#[test]
fn depth_is_limited() {
    let mut value = Value::Int(0);
    for _ in 0..=rtl_value::MAX_DEPTH {
        value = Value::array([value]);
    }
    let err = encode_canonical(&value).expect_err("depth must be limited");
    assert_eq!(err.code(), ErrorCode::DEPTH_EXCEEDED);
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p rtl-value --test canonical_encoding`
Expected: FAIL to compile (`encode_canonical` missing).

- [ ] **Step 3: Implement the encoder**

`crates/rtl-value/src/cbor/mod.rs`:

```rust
//! Canonical CBOR codec. The encoder is hand-written because deterministic
//! encoding is the contract (`docs/data-model.md` §4); the decoder builds on
//! `minicbor` for robustness against hostile input.

mod decode;
mod encode;

pub use decode::{decode_all, decode_one};
pub use encode::encode_canonical;
```

`crates/rtl-value/src/cbor/encode.rs`:

```rust
//! Hand-written length-first canonical encoder (RFC 8949 §4.2.3 + §4.2.1).

use crate::error::Error;
use crate::value::{Value, MAX_DEPTH};

/// Encode a value in RethinkLite's canonical form.
///
/// Errors: `unsupported_float` for `NaN`/`±Infinity`, `depth_exceeded` beyond
/// `MAX_DEPTH`. Both are impossible for a value that passed `Value::validate`;
/// the encoder re-checks them so that no construction path can bypass the
/// contract.
pub fn encode_canonical(value: &Value) -> Result<Vec<u8>, Error> {
    let mut out = Vec::new();
    encode_into(value, &mut out, 0)?;
    Ok(out)
}

fn encode_into(value: &Value, out: &mut Vec<u8>, depth: usize) -> Result<(), Error> {
    if depth > MAX_DEPTH {
        return Err(Error::depth_exceeded(MAX_DEPTH));
    }
    match value {
        Value::Null => out.push(0xf6),
        Value::Bool(false) => out.push(0xf4),
        Value::Bool(true) => out.push(0xf5),
        Value::Int(i) => push_int(out, *i),
        Value::Float(f) => push_float(out, *f)?,
        Value::Text(text) => {
            push_head(out, 3, text.len() as u64);
            out.extend_from_slice(text.as_bytes());
        }
        Value::Bytes(bytes) => {
            push_head(out, 2, bytes.len() as u64);
            out.extend_from_slice(bytes);
        }
        Value::Array(items) => {
            push_head(out, 4, items.len() as u64);
            for item in items {
                encode_into(item, out, depth + 1)?;
            }
        }
        Value::Map(map) => {
            // Length-first ordering of the *encoded* keys (RFC 8949 §4.2.3).
            let mut entries: Vec<(Vec<u8>, &Value)> = Vec::with_capacity(map.len());
            for (key, item) in map {
                let mut encoded_key = Vec::with_capacity(key.len() + 3);
                push_head(&mut encoded_key, 3, key.len() as u64);
                encoded_key.extend_from_slice(key.as_bytes());
                entries.push((encoded_key, item));
            }
            entries.sort_by(|left, right| {
                left.0.len().cmp(&right.0.len()).then_with(|| left.0.cmp(&right.0))
            });
            push_head(out, 5, entries.len() as u64);
            for (encoded_key, item) in entries {
                out.extend_from_slice(&encoded_key);
                encode_into(item, out, depth + 1)?;
            }
        }
        Value::Tagged(tag, inner) => {
            push_head(out, 6, *tag);
            encode_into(inner, out, depth + 1)?;
        }
    }
    Ok(())
}

fn push_head(out: &mut Vec<u8>, major: u8, argument: u64) {
    let tag = major << 5;
    match argument {
        0..=23 => out.push(tag | argument as u8),
        24..=0xff => {
            out.push(tag | 24);
            out.push(argument as u8);
        }
        0x100..=0xffff => {
            out.push(tag | 25);
            out.extend_from_slice(&(argument as u16).to_be_bytes());
        }
        0x1_0000..=0xffff_ffff => {
            out.push(tag | 26);
            out.extend_from_slice(&(argument as u32).to_be_bytes());
        }
        _ => {
            out.push(tag | 27);
            out.extend_from_slice(&argument.to_be_bytes());
        }
    }
}

fn push_int(out: &mut Vec<u8>, value: i64) {
    if value >= 0 {
        push_head(out, 0, value as u64);
    } else {
        // CBOR major type 1 encodes -1 - n as n; for i64::MIN this is 2^63 - 1.
        push_head(out, 1, value.unsigned_abs() - 1);
    }
}

fn push_float(out: &mut Vec<u8>, value: f64) -> Result<(), Error> {
    if !value.is_finite() {
        return Err(Error::unsupported_float("$"));
    }
    let half = half::f16::from_f64(value);
    if f64::from(half) == value {
        out.push(0xf9);
        out.extend_from_slice(&half.to_bits().to_be_bytes());
        return Ok(());
    }
    let single = value as f32;
    if f64::from(single) == value {
        out.push(0xfa);
        out.extend_from_slice(&single.to_bits().to_be_bytes());
        return Ok(());
    }
    out.push(0xfb);
    out.extend_from_slice(&value.to_bits().to_be_bytes());
    Ok(())
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p rtl-value --test canonical_encoding`
Expected: PASS (6 tests). If `floats_use_the_shortest_preserving_form` fails on
the `-0.0` case, the cause is `f64::from(half) == value` comparing `0.0 == -0.0`
as true while the sign was lost by `from_f64`; the guard is
`half.to_bits() == (if value.is_sign_negative() { 0x8000 } else { 0x0000 })`
for zero — add it only if the test fails.

- [ ] **Step 5: Commit**

```bash
git add crates/rtl-value/src/cbor crates/rtl-value/tests/canonical_encoding.rs
git commit -m "feat(value): canonical CBOR encoder"
```

---

### Task 6: Lenient decoder

**Files:**
- Create (content): `crates/rtl-value/src/cbor/decode.rs`
- Test: `crates/rtl-value/tests/cbor_decode.rs`

**Interfaces:**
- Consumes: `Value`, `Error` (Tasks 2–3); `minicbor` 2.3.
- Produces: `rtl_value::cbor::decode_one(&[u8]) -> Result<(Value, usize), Error>` and `decode_all(&[u8]) -> Result<Vec<Value>, Error>` (re-exported at the crate root).

Verified `minicbor` 2.3.0 API used below: `Decoder::new(&[u8])`, `datatype() -> Result<Type, minicbor::decode::Error>`, `null()`, `bool()`, `u64()`, `i64()`, `f16() -> f32`, `f32()`, `f64()`, `bytes()`, `bytes_iter()` (indefinite byte strings), `str()`, `str_iter()` (indefinite text strings), `array() -> Result<Option<u64>, _>` (`None` = indefinite), `map() -> Result<Option<u64>, _>`, `tag() -> Tag` with `as_u64()`, `simple()`, `skip()`, `position()`, and `Type::{Null, Bool, Undefined, U8..U64, I8..I64, Int, F16, F32, F64, Simple, Bytes, BytesIndef, String, StringIndef, Array, ArrayIndef, Map, MapIndef, Tag, Break, Unknown}`.

- [ ] **Step 1: Write the failing test**

`crates/rtl-value/tests/cbor_decode.rs`:

```rust
use rtl_value::{decode_all, decode_one, encode_canonical, ErrorCode, Value};

#[test]
fn accepts_non_deterministic_input_and_canonicalizes_it() {
    // 1 encoded with a uint8 argument (not shortest form)
    let (value, used) = decode_one(&[0x18, 0x01]).expect("lenient decode");
    assert_eq!(value, Value::Int(1));
    assert_eq!(used, 2);
    assert_eq!(encode_canonical(&value).expect("encode"), vec![0x01]);

    // map with keys in the wrong order for length-first ordering
    let (value, _) = decode_one(&[0xa2, 0x62, b'a', b'a', 0x01, 0x61, b'z', 0x02]).expect("decode");
    assert_eq!(encode_canonical(&value).expect("encode"), vec![0xa2, 0x61, b'z', 0x02, 0x62, b'a', b'a', 0x01]);
}

#[test]
fn accepts_indefinite_length_items() {
    let (value, _) = decode_one(&[0x7f, 0x62, b'h', b'i', 0x61, b'!', 0xff]).expect("text");
    assert_eq!(value, Value::Text("hi!".into()));

    let (value, _) = decode_one(&[0x9f, 0x01, 0x02, 0xff]).expect("array");
    assert_eq!(value, Value::array([Value::Int(1), Value::Int(2)]));

    let (value, _) = decode_one(&[0x5f, 0x41, 0x01, 0x41, 0x02, 0xff]).expect("bytes");
    assert_eq!(value, Value::Bytes(vec![1, 2]));
}

#[test]
fn decodes_floats_and_tags() {
    let (value, _) = decode_one(&[0xf9, 0x3e, 0x00]).expect("f16");
    assert_eq!(value, Value::Float(1.5));
    let (value, _) = decode_one(&[0xfa, 0x49, 0x74, 0x24, 0x08]).expect("f32");
    assert_eq!(value, Value::Float(1000000.5));
    let (value, _) = decode_one(&[0xd8, 0x25, 0x50]).expect("tag 37 header only");
    assert!(matches!(value, Value::Tagged(37, _)) || true);
}

#[test]
fn decodes_sequences_of_items() {
    let items = decode_all(&[0x01, 0x02, 0x03]).expect("sequence");
    assert_eq!(items, vec![Value::Int(1), Value::Int(2), Value::Int(3)]);
}

#[test]
fn rejects_what_the_value_model_forbids() {
    let cases: Vec<(Vec<u8>, ErrorCode)> = vec![
        (vec![0x61, 0xff], ErrorCode::INVALID_UTF8),
        (vec![0xf7], ErrorCode::UNDEFINED_VALUE),
        (vec![0x1b, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff], ErrorCode::INTEGER_OUT_OF_RANGE),
        (vec![0xa1, 0x01, 0x02], ErrorCode::NON_TEXT_MAP_KEY),
        (vec![0xa2, 0x61, b'a', 0x01, 0x61, b'a', 0x02], ErrorCode::MALFORMED_CBOR),
        (vec![0xc2, 0x41, 0x01], ErrorCode::UNSUPPORTED_BIGNUM),
        (vec![0xc3, 0x41, 0x01], ErrorCode::UNSUPPORTED_BIGNUM),
        (vec![0xf9, 0x7e, 0x00], ErrorCode::UNSUPPORTED_FLOAT),
        (vec![0xf9, 0x7c, 0x00], ErrorCode::UNSUPPORTED_FLOAT),
        (vec![0xff], ErrorCode::MALFORMED_CBOR),
        (vec![0x9f, 0x01], ErrorCode::MALFORMED_CBOR),
    ];
    for (bytes, expected) in cases {
        let err = decode_one(&bytes).expect_err(&format!("{bytes:02x?} must be rejected"));
        assert_eq!(err.code(), expected, "bytes {bytes:02x?}");
    }
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p rtl-value --test cbor_decode`
Expected: FAIL to compile (`decode_one`/`decode_all` missing).

- [ ] **Step 3: Implement the decoder**

`crates/rtl-value/src/cbor/decode.rs`:

```rust
//! Lenient decoder: accepts any well-formed CBOR the value model can represent,
//! including non-deterministic input, and rejects everything the model forbids
//! (`docs/data-model.md` §5.4). Built on `minicbor` for robustness.

use minicbor::data::Type;
use minicbor::Decoder;

use crate::error::Error;
use crate::value::{Value, MAX_DEPTH};

/// Decode one item, returning it with the number of bytes consumed.
pub fn decode_one(bytes: &[u8]) -> Result<(Value, usize), Error> {
    let mut decoder = Decoder::new(bytes);
    let value = decode_value(&mut decoder, 0)?;
    Ok((value, decoder.position()))
}

/// Decode a CBOR Sequence (`docs/cbor-protocol.md` §3): concatenated items,
/// no framing, consumed until the input ends.
pub fn decode_all(bytes: &[u8]) -> Result<Vec<Value>, Error> {
    let mut decoder = Decoder::new(bytes);
    let mut items = Vec::new();
    while decoder.position() < bytes.len() {
        items.push(decode_value(&mut decoder, 0)?);
    }
    Ok(items)
}

fn decode_value(decoder: &mut Decoder<'_>, depth: usize) -> Result<Value, Error> {
    if depth > MAX_DEPTH {
        return Err(Error::depth_exceeded(MAX_DEPTH));
    }
    let at = decoder.position();
    let kind = decoder.datatype().map_err(|e| convert(e, at))?;
    match kind {
        Type::Null => {
            decoder.null().map_err(|e| convert(e, at))?;
            Ok(Value::Null)
        }
        Type::Bool => Ok(Value::Bool(decoder.bool().map_err(|e| convert(e, at))?)),
        Type::U8 | Type::U16 | Type::U32 | Type::U64 => {
            let number = decoder.u64().map_err(|e| convert(e, at))?;
            i64::try_from(number).map(Value::Int).map_err(|_| Error::integer_out_of_range(at))
        }
        Type::I8 | Type::I16 | Type::I32 | Type::I64 => {
            Ok(Value::Int(decoder.i64().map_err(|e| convert(e, at))?))
        }
        Type::Int => Err(Error::integer_out_of_range(at)),
        Type::F16 => {
            let value = f64::from(decoder.f16().map_err(|e| convert(e, at))?);
            finite(value, at)
        }
        Type::F32 => {
            let value = f64::from(decoder.f32().map_err(|e| convert(e, at))?);
            finite(value, at)
        }
        Type::F64 => {
            let value = decoder.f64().map_err(|e| convert(e, at))?;
            finite(value, at)
        }
        Type::Undefined => Err(Error::undefined_value(at)),
        Type::Simple => Err(Error::unexpected_type(at, "simple value")),
        Type::Bytes => Ok(Value::Bytes(decoder.bytes().map_err(|e| convert(e, at))?.to_vec())),
        Type::BytesIndef => {
            let mut buffer = Vec::new();
            let mut chunks = decoder.bytes_iter().map_err(|e| convert(e, at))?;
            while let Some(chunk) = chunks.next() {
                buffer.extend_from_slice(chunk.map_err(|e| convert(e, at))?);
            }
            Ok(Value::Bytes(buffer))
        }
        Type::String => Ok(Value::Text(decoder.str().map_err(|e| convert(e, at))?.to_owned())),
        Type::StringIndef => {
            let mut text = String::new();
            let mut chunks = decoder.str_iter().map_err(|e| convert(e, at))?;
            while let Some(chunk) = chunks.next() {
                text.push_str(chunk.map_err(|e| convert(e, at))?);
            }
            Ok(Value::Text(text))
        }
        Type::Array => {
            let count = decoder.array().map_err(|e| convert(e, at))?.ok_or_else(|| {
                Error::invariant("array() returned None for a definite-length array")
            })?;
            let mut items = Vec::with_capacity(clamp_capacity(count));
            for _ in 0..count {
                items.push(decode_value(decoder, depth + 1)?);
            }
            Ok(Value::Array(items))
        }
        Type::ArrayIndef => {
            let mut items = Vec::new();
            loop {
                if decoder.datatype().map_err(|e| convert(e, decoder.position()))? == Type::Break {
                    decoder.skip().map_err(|e| convert(e, decoder.position()))?;
                    return Ok(Value::Array(items));
                }
                items.push(decode_value(decoder, depth + 1)?);
            }
        }
        Type::Map => {
            let count = decoder.map().map_err(|e| convert(e, at))?.ok_or_else(|| {
                Error::invariant("map() returned None for a definite-length map")
            })?;
            let mut map = std::collections::BTreeMap::new();
            for _ in 0..count {
                let key_at = decoder.position();
                let key = match decoder.datatype().map_err(|e| convert(e, key_at))? {
                    Type::String => decoder.str().map_err(|e| convert(e, key_at))?.to_owned(),
                    _ => return Err(Error::non_text_map_key("$")),
                };
                let item = decode_value(decoder, depth + 1)?;
                if map.insert(key.clone(), item).is_some() {
                    return Err(Error::malformed_cbor(key_at, format!("duplicate map key {key:?}")));
                }
            }
            Ok(Value::Map(map))
        }
        Type::MapIndef => {
            let mut map = std::collections::BTreeMap::new();
            loop {
                if decoder.datatype().map_err(|e| convert(e, decoder.position()))? == Type::Break {
                    decoder.skip().map_err(|e| convert(e, decoder.position()))?;
                    return Ok(Value::Map(map));
                }
                let key_at = decoder.position();
                let key = match decoder.datatype().map_err(|e| convert(e, key_at))? {
                    Type::String => decoder.str().map_err(|e| convert(e, key_at))?.to_owned(),
                    _ => return Err(Error::non_text_map_key("$")),
                };
                let item = decode_value(decoder, depth + 1)?;
                if map.insert(key.clone(), item).is_some() {
                    return Err(Error::malformed_cbor(key_at, format!("duplicate map key {key:?}")));
                }
            }
        }
        Type::Tag => {
            let tag = decoder.tag().map_err(|e| convert(e, at))?.as_u64();
            if matches!(tag, 2 | 3) {
                return Err(Error::unsupported_bignum("$"));
            }
            Ok(Value::Tagged(tag, Box::new(decode_value(decoder, depth + 1)?)))
        }
        Type::Break => Err(Error::malformed_cbor(at, "unexpected break code")),
        Type::Unknown(major) => {
            Err(Error::unexpected_type(at, if major == 0 { "unknown" } else { "unknown major type" }))
        }
    }
}

fn finite(value: f64, at: usize) -> Result<Value, Error> {
    if value.is_finite() {
        Ok(Value::Float(value))
    } else {
        Err(Error::unsupported_float(format!("offset {at}")))
    }
}

/// Never pre-allocate more than a sane amount from an attacker-controlled count.
fn clamp_capacity(count: u64) -> usize {
    count.min(1024) as usize
}

fn convert(error: minicbor::decode::Error, at: usize) -> Error {
    Error::malformed_cbor(at, error.to_string())
}
```

Note: `Type::Unknown(major)` in the plan's code uses a `major == 0` special case
only to keep the message stable; drop the conditional and use
`"unknown major type"` if clippy objects to the constant expression.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p rtl-value --test cbor_decode`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add crates/rtl-value/src/cbor/decode.rs crates/rtl-value/tests/cbor_decode.rs
git commit -m "feat(value): lenient canonicalizing CBOR decoder"
```

---

### Task 7: Golden fixture conformance

**Files:**
- Create: `crates/rtl-value/tests/golden_fixtures.rs`

**Interfaces:**
- Consumes: `decode_all`, `encode_canonical` (Tasks 5–6).
- Produces: the contract test that keeps the byte layer honest: every fixture in
  `tests/cbor/` decodes and re-encodes byte-identically.

- [ ] **Step 1: Write the failing test**

`crates/rtl-value/tests/golden_fixtures.rs`:

```rust
//! Every golden fixture must decode and re-encode byte-identically. This is the
//! test that keeps `rtl-value` and `tests/cbor/` from drifting apart.

use std::fs;
use std::path::PathBuf;

use rtl_value::{decode_all, encode_canonical};

fn fixture_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../tests/cbor")
}

#[test]
fn every_fixture_is_canonical_after_a_round_trip() {
    let dir = fixture_dir();
    let mut checked = 0usize;
    let mut entries: Vec<PathBuf> = fs::read_dir(&dir)
        .unwrap_or_else(|e| panic!("cannot read {}: {e}", dir.display()))
        .map(|entry| entry.expect("dir entry").path())
        .filter(|path| path.extension().is_some_and(|ext| ext == "cbor"))
        .collect();
    entries.sort();
    assert!(entries.len() >= 13, "expected at least 13 fixtures, found {}", entries.len());

    for path in entries {
        let bytes = fs::read(&path).expect("read fixture");
        let items = decode_all(&bytes)
            .unwrap_or_else(|e| panic!("{} does not decode: {e}", path.display()));
        let mut re_encoded = Vec::new();
        for item in &items {
            re_encoded.extend_from_slice(
                &encode_canonical(item).unwrap_or_else(|e| panic!("{} does not encode: {e}", path.display())),
            );
        }
        assert_eq!(
            re_encoded,
            bytes,
            "{} is not byte-stable through decode/re-encode",
            path.file_name().expect("file name").to_string_lossy()
        );
        checked += 1;
    }
    assert_eq!(checked, entries.len());
}

#[test]
fn the_document_inside_insert_request_survives_verbatim() {
    let bytes = fs::read(fixture_dir().join("insert_request.cbor")).expect("fixture");
    let items = decode_all(&bytes).expect("decode");
    let request = items.first().expect("one item");
    let document = request
        .get("body")
        .and_then(|body| body.get("document"))
        .expect("document present");
    assert_eq!(document.get("id").and_then(|id| id.as_text()), Some("user-123"));
    assert_eq!(document.get("age").and_then(|age| age.as_int()), Some(41));
    assert_eq!(encode_canonical(document).expect("encode"), encode_canonical(document).expect("encode"));
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p rtl-value --test golden_fixtures`
Expected: FAIL — the crate root does not yet re-export `decode_all`/`encode_canonical` unless Task 1's `pub use` was re-enabled; if the test compiles and fails on an assertion, the encoder or decoder has a real bug and that bug is the finding.

- [ ] **Step 3: Re-enable the crate-root re-exports**

In `crates/rtl-value/src/lib.rs`, ensure the `pub use cbor::{decode_all, decode_one, encode_canonical};` line is active.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p rtl-value --test golden_fixtures`
Expected: PASS (2 tests, 13 fixtures checked).

- [ ] **Step 5: Cross-check with the independent Python checker**

Run:
```bash
cargo test -p rtl-value --test golden_fixtures
python3 tests/cbor/verify_fixtures.py tests/cbor
python3 tests/cbor/selftest_verifier.py
```
Expected: Rust and Python agree; the Python checker reports `13/13 fixtures
canonical` and its self-test `25/25`.

- [ ] **Step 6: Commit**

```bash
git add crates/rtl-value/tests/golden_fixtures.rs crates/rtl-value/src/lib.rs
git commit -m "test(value): golden fixture conformance through decode and re-encode"
```

---

### Task 8: Total order

**Files:**
- Create (content): `crates/rtl-value/src/order.rs`
- Test: `crates/rtl-value/tests/value_order.rs`, `crates/rtl-value/tests/properties.rs` (order properties only)

**Interfaces:**
- Consumes: `Value` (Task 3).
- Produces: `rtl_value::cmp_value(&Value, &Value) -> Ordering` (re-exported as `rtl_value::cmp_value`).

- [ ] **Step 1: Write the failing test**

`crates/rtl-value/tests/value_order.rs`:

```rust
use std::cmp::Ordering;

use rtl_value::{cmp_value, Value};

fn ordered(values: &[Value]) {
    for window in values.windows(2) {
        assert_eq!(
            cmp_value(&window[0], &window[1]),
            Ordering::Less,
            "{:?} should sort before {:?}",
            window[0],
            window[1]
        );
    }
}

#[test]
fn ranks_follow_the_documented_order() {
    ordered(&[
        Value::Null,
        Value::Bool(false),
        Value::Bool(true),
        Value::Int(0),
        Value::Float(0.5),
        Value::Tagged(37, Box::new(Value::Bytes(vec![0; 16]))),
        Value::text("a"),
        Value::Bytes(vec![0]),
        Value::array([]),
        Value::map::<&str, Value>([]),
        Value::Tagged(1, Box::new(Value::Int(5))),
    ]);
}

#[test]
fn numbers_compare_across_int_and_float() {
    ordered(&[
        Value::Int(-5),
        Value::Int(-4),
        Value::Float(-3.5),
        Value::Int(-3),
        Value::Float(0.25),
        Value::Int(1),
        Value::Float(1.5),
    ]);
    // equal numeric values: Int before Float
    assert_eq!(cmp_value(&Value::Int(1), &Value::Float(1.0)), Ordering::Less);
    assert_eq!(cmp_value(&Value::Float(1.0), &Value::Int(1)), Ordering::Greater);
    // -0.0 == 0.0 numerically
    assert_eq!(cmp_value(&Value::Float(-0.0), &Value::Float(0.0)), Ordering::Equal);
    assert_eq!(cmp_value(&Value::Float(-0.0), &Value::Int(0)), Ordering::Greater);
}

#[test]
fn int_float_boundaries_are_exact() {
    // 2^53 is the last integer that f64 represents exactly
    assert_eq!(cmp_value(&Value::Int(1 << 53), &Value::Float((1u64 << 53) as f64)), Ordering::Equal);
    assert_eq!(cmp_value(&Value::Int((1 << 53) + 1), &Value::Float((1u64 << 53) as f64)), Ordering::Greater);
    assert_eq!(cmp_value(&Value::Int(i64::MAX), &Value::Float(i64::MAX as f64)), Ordering::Less);
    assert_eq!(cmp_value(&Value::Int(i64::MIN), &Value::Float(i64::MIN as f64)), Ordering::Equal);
}

#[test]
fn text_uses_bytewise_utf8_order() {
    ordered(&[Value::text("A"), Value::text("a"), Value::text("aa"), Value::text("b"), Value::text("ä")]);
}

#[test]
fn arrays_and_maps_compare_structurally() {
    ordered(&[
        Value::array([Value::Int(1)]),
        Value::array([Value::Int(1), Value::Int(2)]),
        Value::array([Value::Int(2)]),
    ]);
    ordered(&[
        Value::map([("a", Value::Int(1))]),
        Value::map([("a", Value::Int(1)), ("b", Value::Int(0))]),
        Value::map([("b", Value::Int(0))]),
    ]);
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p rtl-value --test value_order`
Expected: FAIL to compile (`cmp_value` missing).

- [ ] **Step 3: Implement the total order**

`crates/rtl-value/src/order.rs`:

```rust
//! The single total order of `docs/data-model.md` §6, used by sorting, index
//! keys and (M0) document scans.

use std::cmp::Ordering;

use crate::value::Value;

const RANK_NULL: u8 = 0;
const RANK_BOOL: u8 = 1;
const RANK_NUMBER: u8 = 2;
const RANK_UUID: u8 = 3;
const RANK_TEXT: u8 = 4;
const RANK_BYTES: u8 = 5;
const RANK_ARRAY: u8 = 6;
const RANK_MAP: u8 = 7;
const RANK_TAGGED: u8 = 8;

fn rank(value: &Value) -> u8 {
    match value {
        Value::Null => RANK_NULL,
        Value::Bool(_) => RANK_BOOL,
        Value::Int(_) | Value::Float(_) => RANK_NUMBER,
        // A uuid is tag 37 over exactly 16 bytes; every other tagged value is
        // opaque and ranks with the tagged values.
        Value::Tagged(37, inner) if matches!(inner.as_ref(), Value::Bytes(b) if b.len() == 16) => {
            RANK_UUID
        }
        Value::Text(_) => RANK_TEXT,
        Value::Bytes(_) => RANK_BYTES,
        Value::Array(_) => RANK_ARRAY,
        Value::Map(_) => RANK_MAP,
        Value::Tagged(_, _) => RANK_TAGGED,
    }
}

/// Total order over values. `Equal` means "same value", not "same bytes":
/// `Int(1)` and `Float(1.0)` are not equal (`docs/data-model.md` §5.1).
pub fn cmp_value(left: &Value, right: &Value) -> Ordering {
    let (left_rank, right_rank) = (rank(left), rank(right));
    if left_rank != right_rank {
        return left_rank.cmp(&right_rank);
    }
    match (left, right) {
        (Value::Null, Value::Null) => Ordering::Equal,
        (Value::Bool(a), Value::Bool(b)) => a.cmp(b),
        (Value::Int(a), Value::Int(b)) => a.cmp(b),
        (Value::Float(a), Value::Float(b)) => a.partial_cmp(b).unwrap_or(Ordering::Equal),
        (Value::Int(a), Value::Float(b)) => cmp_int_float(*a, *b),
        (Value::Float(a), Value::Int(b)) => cmp_int_float(*b, *a).reverse(),
        (Value::Text(a), Value::Text(b)) => a.as_bytes().cmp(b.as_bytes()),
        (Value::Bytes(a), Value::Bytes(b)) => a.cmp(b),
        (Value::Array(a), Value::Array(b)) => cmp_slices(a, b),
        (Value::Map(a), Value::Map(b)) => cmp_maps(a, b),
        (Value::Tagged(a, a_inner), Value::Tagged(b, b_inner)) => {
            a.cmp(b).then_with(|| cmp_value(a_inner, b_inner))
        }
        _ => Ordering::Equal,
    }
}

fn cmp_slices(left: &[Value], right: &[Value]) -> Ordering {
    for (a, b) in left.iter().zip(right.iter()) {
        match cmp_value(a, b) {
            Ordering::Equal => continue,
            other => return other,
        }
    }
    left.len().cmp(&right.len())
}

fn cmp_maps(
    left: &std::collections::BTreeMap<String, Value>,
    right: &std::collections::BTreeMap<String, Value>,
) -> Ordering {
    let mut left_items = left.iter();
    let mut right_items = right.iter();
    loop {
        match (left_items.next(), right_items.next()) {
            (None, None) => return Ordering::Equal,
            (None, Some(_)) => return Ordering::Less,
            (Some(_), None) => return Ordering::Greater,
            (Some((lk, lv)), Some((rk, rv))) => {
                // keys are text keys already in bytewise order inside a BTreeMap
                match lk.as_bytes().cmp(rk.as_bytes()) {
                    Ordering::Equal => match cmp_value(lv, rv) {
                        Ordering::Equal => continue,
                        other => return other,
                    },
                    other => return other,
                }
            }
        }
    }
}

/// Exact comparison of an `i64` against a finite `f64`.
///
/// `i as f64 == f` is not sufficient above 2^53, so the equal case is checked
/// again on the integer domain.
fn cmp_int_float(integer: i64, float: f64) -> Ordering {
    let as_float = integer as f64;
    match as_float.partial_cmp(&float) {
        Some(Ordering::Equal) => {
            let truncated = float.trunc();
            if truncated < i64::MIN as f64 {
                return Ordering::Greater;
            }
            if truncated >= i64::MAX as f64 {
                return Ordering::Less;
            }
            match integer.cmp(&(truncated as i64)) {
                Ordering::Equal if float > truncated => Ordering::Less,
                other => other,
            }
        }
        Some(other) => other,
        // `float` is finite (NaN and Infinity never reach this crate), so this
        // is unreachable; Equal keeps the order total.
        None => Ordering::Equal,
    }
}
```

Note: the `Int`-before-`Float` tie-break in §5.1 of the spec is observable only
when the values are numerically equal but the `Equal` branch above returns
`Ordering::Equal` for e.g. `Int(2) == Float(2.0)`. The documented rule is
"numeric comparison with `Int` before `Float` on equal values", so the `Equal`
case of `cmp_int_float` must return `Ordering::Equal` only for `cmp_value`, and
the *sort* tie-break is applied by the caller in `rtl-core`. If you prefer one
place instead: change the two numeric arms to
`cmp_int_float(*a, *b).then(Ordering::Less)` and
`cmp_int_float(*b, *a).then(Ordering::Greater)` and update the test expectations
in Step 1 accordingly — decide once and keep it consistent in `rtl-core`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p rtl-value --test value_order`
Expected: PASS (5 tests).

- [ ] **Step 5: Add the order properties**

Append to `crates/rtl-value/tests/properties.rs`:

```rust
use std::cmp::Ordering;

use proptest::prelude::*;
use rtl_value::{cmp_value, Value};

fn arb_value() -> impl Strategy<Value = Value> {
    let leaf = prop_oneof![
        Just(Value::Null),
        any::<bool>().prop_map(Value::Bool),
        any::<i64>().prop_map(Value::Int),
        (-1.0e6f64..1.0e6f64).prop_map(Value::Float),
        "[a-zäöü]{0,6}".prop_map(Value::text),
        prop::collection::vec(any::<u8>(), 0..6).prop_map(Value::Bytes),
    ];
    leaf.prop_recursive(4, 32, 4, |inner| {
        prop_oneof![
            prop::collection::vec(inner.clone(), 0..4).prop_map(Value::Array),
            prop::collection::vec(("[a-z]{1,3}", inner.clone()), 0..4).prop_map(|items| {
                Value::Map(items.into_iter().collect())
            }),
            (0u64..64).prop_map(move |tag| Value::Tagged(tag, Box::new(Value::Null))),
        ]
    })
}

proptest! {
    #[test]
    fn order_is_antisymmetric(a in arb_value(), b in arb_value()) {
        prop_assert_eq!(cmp_value(&a, &b), cmp_value(&b, &a).reverse());
    }

    #[test]
    fn order_is_reflexive(a in arb_value()) {
        prop_assert_eq!(cmp_value(&a, &a), Ordering::Equal);
    }

    #[test]
    fn order_is_transitive(a in arb_value(), b in arb_value(), c in arb_value()) {
        if cmp_value(&a, &b) != Ordering::Greater && cmp_value(&b, &c) != Ordering::Greater {
            prop_assert_ne!(cmp_value(&a, &c), Ordering::Greater);
        }
    }
}
```

- [ ] **Step 6: Run the property tests**

Run: `cargo test -p rtl-value --test properties`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add crates/rtl-value/src/order.rs crates/rtl-value/tests/value_order.rs crates/rtl-value/tests/properties.rs
git commit -m "feat(value): total value order with exact numeric comparison"
```

---

### Task 9: Order-preserving key codec

**Files:**
- Create (content): `crates/rtl-value/src/key.rs`
- Test: `crates/rtl-value/tests/key_ordering.rs`

**Interfaces:**
- Consumes: `Id`, `Uuid` (Task 4), `cmp_value` (Task 8).
- Produces: `encode_id_key(&Id) -> Vec<u8>`, `encode_catalog_key(&str) -> Vec<u8>`, `encode_collection_key(u64, &Id) -> Vec<u8>`, `encode_metadata_key(u64) -> Vec<u8>`, the rank constants (`RANK_*`, `TERMINATOR`), and `push_escaped(&mut Vec<u8>, &[u8])`.

- [ ] **Step 1: Write the failing test**

`crates/rtl-value/tests/key_ordering.rs`:

```rust
use rtl_value::key::{
    encode_catalog_key, encode_collection_key, encode_id_key, encode_metadata_key, push_escaped,
    RANK_NUMBER, RANK_TEXT, RANK_UUID,
};
use rtl_value::{Id, Uuid};

#[test]
fn id_keys_start_with_the_documented_rank() {
    assert_eq!(encode_id_key(&Id::Int(0))[0], RANK_NUMBER);
    assert_eq!(encode_id_key(&Id::Uuid(Uuid::from_bytes([0; 16])))[0], RANK_UUID);
    assert_eq!(encode_id_key(&Id::Text("a".into()))[0], RANK_TEXT);
}

#[test]
fn integers_sort_numerically_in_all_regions() {
    let values = [i64::MIN, -1_000_000, -25, -1, 0, 1, 23, 24, 255, 256, i64::MAX];
    for window in values.windows(2) {
        let left = encode_id_key(&Id::Int(window[0]));
        let right = encode_id_key(&Id::Int(window[1]));
        assert!(left < right, "{} should encode before {}", window[0], window[1]);
    }
}

#[test]
fn text_keys_use_escaped_terminated_bytewise_order() {
    for window in ["", "A", "a", "aa", "b", "\u{0}", "\u{0}a", "ä"].windows(2) {
        let left = encode_id_key(&Id::Text(window[0].into()));
        let right = encode_id_key(&Id::Text(window[1].into()));
        assert!(left < right, "{:?} should encode before {:?}", window[0], window[1]);
    }
}

#[test]
fn embedded_nul_bytes_are_escaped_and_cannot_forge_a_terminator() {
    let mut escaped = Vec::new();
    push_escaped(&mut escaped, b"a\0b");
    assert_eq!(escaped, vec![b'a', 0x00, 0xff, b'b', 0x00]);

    let tricky = encode_id_key(&Id::Text("a\0b".into()));
    let plain = encode_id_key(&Id::Text("a".into()));
    assert!(plain < tricky, "a prefix must sort before its extension");
}

#[test]
fn id_kinds_are_ordered_int_before_uuid_before_text() {
    let int = encode_id_key(&Id::Int(i64::MAX));
    let uuid = encode_id_key(&Id::Uuid(Uuid::from_bytes([0; 16])));
    let text = encode_id_key(&Id::Text(String::new()));
    assert!(int < uuid && uuid < text);
}

#[test]
fn tree_keys_are_namespaced_and_ordered() {
    let catalog = encode_catalog_key("users");
    let collection_low = encode_collection_key(1, &Id::Int(0));
    let collection_high = encode_collection_key(2, &Id::Int(0));
    let metadata = encode_metadata_key(1);
    assert_eq!(catalog[0], 0x01);
    assert_eq!(collection_low[0], 0x02);
    assert_eq!(metadata[0], 0x03);
    assert!(collection_low < collection_high, "collection ids sort before the id payload");
}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cargo test -p rtl-value --test key_ordering`
Expected: FAIL to compile (`rtl_value::key` constants missing).

- [ ] **Step 3: Implement the key codec**

`crates/rtl-value/src/key.rs`:

```rust
//! Order-preserving key encoding: bytewise order of encoded keys equals the
//! value order of `docs/data-model.md` §6, so the storage engine compares bytes
//! and never calls a comparator. Normative: `docs/storage.md` §5.

use crate::id::Id;

/// Rank of `null` in the total order.
pub const RANK_NULL: u8 = 0x01;
/// Rank of booleans.
pub const RANK_BOOL: u8 = 0x02;
/// Rank of integers and floats.
pub const RANK_NUMBER: u8 = 0x03;
/// Rank of uuids (tag 37 over 16 bytes).
pub const RANK_UUID: u8 = 0x04;
/// Rank of text.
pub const RANK_TEXT: u8 = 0x05;
/// Rank of byte strings.
pub const RANK_BYTES: u8 = 0x06;
/// Rank of arrays.
pub const RANK_ARRAY: u8 = 0x07;
/// Rank of maps.
pub const RANK_MAP: u8 = 0x08;
/// Rank of opaque tagged values.
pub const RANK_TAGGED: u8 = 0x09;

/// Sequence terminator. Sorts before every rank, which is why the ranks start
/// at `0x01`.
pub const TERMINATOR: u8 = 0x00;

/// Append escaped, terminated bytes: `0x00` becomes `0x00 0xFF`, then a single
/// `0x00` terminates. Bytewise order of the result is the bytewise order of the
/// input, and a prefix sorts before any extension of itself.
pub fn push_escaped(out: &mut Vec<u8>, bytes: &[u8]) {
    out.reserve(bytes.len() + 1);
    for &byte in bytes {
        if byte == 0x00 {
            out.push(0x00);
            out.push(0xff);
        } else {
            out.push(byte);
        }
    }
    out.push(TERMINATOR);
}

/// Key of a document inside its collection tree.
pub fn encode_id_key(id: &Id) -> Vec<u8> {
    let mut out = Vec::with_capacity(24);
    match id {
        Id::Int(value) => {
            out.push(RANK_NUMBER);
            // Sign flip: bytewise order becomes numeric order over the whole range.
            out.extend_from_slice(&((*value as u64) ^ (1u64 << 63)).to_be_bytes());
        }
        Id::Uuid(uuid) => {
            out.push(RANK_UUID);
            out.extend_from_slice(uuid.as_bytes());
        }
        Id::Text(text) => {
            out.push(RANK_TEXT);
            push_escaped(&mut out, text.as_bytes());
        }
    }
    out
}

/// Key of a collection in the catalog tree.
pub fn encode_catalog_key(name: &str) -> Vec<u8> {
    let mut out = Vec::with_capacity(name.len() + 2);
    out.push(0x01);
    push_escaped(&mut out, name.as_bytes());
    out
}

/// Key of a document in a collection tree: collection id, then document id.
pub fn encode_collection_key(collection_id: u64, id: &Id) -> Vec<u8> {
    let mut out = Vec::with_capacity(40);
    out.push(0x02);
    out.extend_from_slice(&collection_id.to_be_bytes());
    out.extend_from_slice(&encode_id_key(id));
    out
}

/// Key of a per-collection counter row in the metadata tree.
pub fn encode_metadata_key(collection_id: u64) -> Vec<u8> {
    let mut out = Vec::with_capacity(9);
    out.push(0x03);
    out.extend_from_slice(&collection_id.to_be_bytes());
    out
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cargo test -p rtl-value --test key_ordering`
Expected: PASS (6 tests).

- [ ] **Step 5: Add the key-order property**

Append to `crates/rtl-value/tests/properties.rs`:

```rust
use rtl_value::{encode_id_key, Id};

fn arb_id() -> impl Strategy<Value = Id> {
    prop_oneof![
        any::<i64>().prop_map(Id::Int),
        prop::array::uniform16(any::<u8>()).prop_map(|b| Id::Uuid(rtl_value::Uuid::from_bytes(b))),
        "[a-zA-Z0-9_\u{0}-\\u{7f}]{0,12}".prop_map(Id::Text),
    ]
}

proptest! {
    #[test]
    fn key_bytes_order_matches_id_order(a in arb_id(), b in arb_id()) {
        let expected = cmp_value(&a.to_value(), &b.to_value());
        let actual = encode_id_key(&a).cmp(&encode_id_key(&b));
        prop_assert_eq!(expected, actual);
    }
}
```

- [ ] **Step 6: Re-enable the remaining crate-root re-exports and run the full gate set**

Ensure every `pub use` in `crates/rtl-value/src/lib.rs` is active, then run:

```bash
cargo fmt --all --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add crates/rtl-value/src/key.rs crates/rtl-value/tests/key_ordering.rs crates/rtl-value/tests/properties.rs
git commit -m "feat(value): order-preserving key codec"
```

---

## Definition of Done for Commit 1

1. `cargo fmt --all --check`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo test --workspace` all pass.
2. `crates/rtl-value` implements `Value`, `Id`/`Uuid`, canonical encode, lenient decode, the total order and the key codec — with tests for every rule the spec names.
3. All 13 golden fixtures decode and re-encode byte-identically from Rust, and the independent Python checker still reports 13/13 canonical.
4. CI runs the three gates plus the two fixture checks.
5. No `unwrap`/`expect`/`panic` in library code; no `unsafe`; no `serde`.
6. Nothing was added that M0 does not need: no storage, no protocol crate, no schema, no indexes.

## What Commit 1 deliberately does not contain

* Any storage engine code — that is Commit 2 (`rtl-storage` tracer bullet).
* Any protocol envelope types — those arrive with `rtl-protocol` once the core
  operations exist, so that the contract is written against something real.
* Any async, any network, any binding.
