# RethinkLite — Storage Engine

Normative for **storage format version 1**. Describes the on-disk layout, the
commit protocol, recovery and corruption handling of the M0 engine.

Decisions behind this document: `adr/0003-storage-strategy.md`,
`adr/0005-storage-cbor-boundary.md`, `adr/0012-freelist-derivation.md`.

---

## 1. Design in one paragraph

RethinkLite stores everything in **one file** as a **copy-on-write B+tree** with
**two superblock slots**. A commit writes new pages into free space, appends
**log records** (the language-neutral change history used by changefeeds and
later by replication), `fsync`s the data, then atomically flips one superblock
slot with the new tree roots and the new `commit_seq`. There is **no redo
replay**: recovery picks the newest valid superblock and discards everything
that was not committed by it. Readers hold a page generation, which makes a
snapshot free and non-blocking.

## 2. File layout

```
offset 0                 page 0   superblock slot A
offset 4096              page 1   superblock slot B
offset 8192              page 2…  pages (COW trees, overflow chains, log segments)
```

* Page size: **4096 bytes**, fixed for format v1 (recorded in the superblock).
* Page id: `u32`, so the addressable file is 4096 × 2^32 = 16 TiB.
* There is no separate WAL file, no journal file, no sidecar: `example.rtl` is
  the entire database.
* File extension `.rtl` is a convention, not a requirement — the engine reads
  the magic, never the name.

## 3. Superblock

Two slots, written alternately; the valid one with the higher `generation`
wins. A slot is valid if `magic`, `format_version`, `page_size` and
`crc32` check out.

| Field | Type | Meaning |
|---|---|---|
| `magic` | 8 bytes | `"RTHKLITE"` |
| `format_version` | u32 | 1 |
| `page_size` | u32 | 4096 |
| `database_uuid` | 16 bytes | random at create; the identity used by replication |
| `generation` | u64 | increments on every commit; the commit ordering *inside* the file |
| `commit_seq` | u64 | highest committed `commit_seq`; the ordering used by feeds and replication |
| `catalog_root` | u32 + u16 | root page id and height of the catalog tree |
| `log_first_segment` | u32 | head of the log segment chain |
| `log_first_seq` | u64 | lowest `commit_seq` still retained in the log |
| `log_open_segment` | u32 | segment currently being appended to (0 = none) |
| `log_open_offset` | u32 | bytes valid in the open segment; the tail is discardable after a crash |
| `log_open_first_seq` | u64 | first `commit_seq` stored in the open segment |
| `next_free_hint` | u32 | allocator hint (not authoritative) |
| `features` | u64 | format feature bits, reserved (0 in M0) |
| `page_count` | u32 | number of pages in the file at commit time |
| `crc32` | u32 | CRC-32/ISO-HDLC over the slot with this field zeroed |

Everything a reader needs to see a consistent database is in this struct — that
is what makes "the superblock is the only commit point" true.

## 4. Pages

Every page starts with a common header; the checksum covers the whole page with
its own field zeroed.

```
page header (24 bytes):
  page_id       u32
  page_type     u8      1 = leaf, 2 = internal, 3 = overflow, 4 = log segment, 5 = freelist (reserved)
  flags         u8      bit 0: root, bit 1: has_overflow
  n_cells       u16
  free_start    u16     end of the cell pointer array
  free_end      u16     start of the cell payload area
  right_sibling u32     0 = none (leaf chain for range scans)
  parent        u32     for internal navigation and validation
  reserved      u16
  crc32         u32
```

* **Leaf pages** are slotted: a cell pointer array grows from the header,
  cell payloads grow from the end of the page. Each leaf cell is
  `key_len u16 | val_len u16 | key | value`.
* **Internal pages** hold `key_len u16 | child u32 | key` entries plus one
  rightmost child; keys are the *smallest key* of the right subtree.
* **Overflow pages** form a singly linked chain (`next u32` in the payload
  area) holding a value that does not fit inline.
* Values ≤ **1024 bytes** are inlined in the leaf; larger values use overflow
  pages. The threshold is fixed in format v1.

Page types are deliberately few. There is no page-level compression, no
per-cell checksum and no encryption in M0; each is *(reserved)* because it needs
its own design (compression interacts with the 1024-byte inline threshold,
encryption with page identity and recovery).

## 5. Keys

Tree keys are **order-preserving encodings** produced by `rtl-value`, so that a
byte-wise comparison inside the storage engine is always the semantic
comparison of `data-model.md` §6. The engine never calls a comparator.

| Tree | Key layout |
|---|---|
| catalog | `0x01 | text(name)` |
| collection | `0x02 | u64 collection_id | id_key` |
| metadata (per collection counters) | `0x03 | u64 collection_id` |

### 5.1 Encoding primitives

* **Type rank byte, `0x01..0x09`**, in the order of `data-model.md` §6:
  `null` `0x01`, bool `0x02`, number `0x03`, uuid `0x04`, text `0x05`,
  bytes `0x06`, array `0x07`, map `0x08`, tagged `0x09`. `0x00` is reserved as a
  sequence terminator, which is why the ranks do not start at zero.
* **Integer** *(uuid `0x04`)* — fixed 16 raw bytes; fixed length, so bytewise
  order is the value order.
* **Integer** `0x03` — `i64` encoded as `(i as u64) ^ (1 << 63)` in big-endian:
  the sign flip makes bytewise order equal numeric order over the whole `i64`
  range, including negatives.
* **Text / bytes** — the content bytes with `0x00` escaped as `0x00 0xFF`,
  terminated by a single `0x00`. No length prefix: a length prefix would sort
  `"b"` before `"aa"`, which contradicts the bytewise text order of
  `data-model.md` §6. Escaping plus terminator gives bytewise order (identical
  to Unicode code point order for UTF-8) *and* makes a prefix sort before any
  extension of itself, which is what prefix scans need.
* **Array** — type rank, then each element recursively encoded, then `0x00`.

### 5.2 Scope in M0

Exactly what M0 needs: `encode_catalog_key`, `encode_collection_key`,
`encode_metadata_key` and `encode_id_key` (Int, Uuid, Text). Values are not
encoded as keys in M0 because M0 has no secondary indexes.

A general value-key encoder is therefore *(reserved)*. Its known hard part is
recorded here so that it is not discovered later: `data-model.md` §6 places Int
and Float in one numeric class, so a key encoding for values must map floats
order-preservingly into the same byte order as integers (IEEE-754 total-order
transformation with an inverted sign bit for negatives), or the numeric class
must be split — a decision that belongs to the secondary-index design in M1, not
to M0.

This is what allows `sort`, range scans and (M1) secondary indexes to be built
on the storage engine without teaching it the value model.

## 6. Transactions and the commit protocol

M0 has exactly **one writer at a time**, serialized in `rtl-core`.

```
1. build          allocate new pages for every touched B+tree path (copy-on-write)
                  from the free set; if exhausted, extend the file by one page
2. log            append change records to the open log segment
                  (or allocate a new segment, then append)
3. sync data      fsync(file)                 <- pages + log records are durable
4. flip           write the *other* superblock slot with generation+1,
                  new roots, new commit_seq, log head/offset, page_count
                  then fsync(file)            <- COMMIT POINT
5. publish        release the write lock, publish the generation to readers,
                  hand the log records to the feed registry
```

* A crashed step 1–3 leaves no trace in the database: the previous superblock is
  still the newest valid one, and the pages written in step 1 become **orphans**
  that are reclaimed when the free set is derived at the next open (§8). No
  rollback pass exists because nothing was rolled forward.
* A crash during step 4 leaves either the old or the new slot valid; the
  invalid one fails its checksum and is ignored.
* Two `fsync` calls per commit. Group commit — batching several transactions
  into one sync — is an M1 performance item; the protocol already accounts for
  it because `commit_seq` assignment is independent of the sync cadence.

**Durability modes** (`Database::open` option): `Sync::Full` (default: both
syncs) and `Sync::None` (no `fsync`; for tests and benchmarks only, explicitly
documented as crash-unsafe). A `Sync::Normal` mode is *(reserved)* and will only
be added with a documented failure model.

## 7. Log segments

The change log is the durable, ordered history of committed changes. It is a
**chain of log segments**, each a run of pages taken from the same page space as
the trees. Segments are allocated, appended to in place, sealed when full, and
freed once retention and all subscribers have advanced past them.

```
segment header (first page of the run):
  magic u32 | segment_id u32 | capacity_bytes u32 | first_seq u64 | last_seq u64
  ... then log records packed until capacity is exhausted
```

Record layout (internal, **not** part of the wire contract):

```
record:
  len          u32     total record size
  crc32        u32     over the record with this field zeroed
  commit_seq   u64
  n_changes    varint
  changes[]:
    op         u8      1 = put, 2 = delete, 3 = collection_create, 4 = collection_drop
    collection_id u64 varint
    key        bytes   order-preserving encoding of the document id
    prev_rev   varint  0 if absent
    new_rev    varint
    old_bytes  bytes   previous canonical document bytes (empty if absent)
    new_bytes  bytes   new canonical document bytes (empty for delete)
```

`old_bytes` are stored rather than referenced, at the cost of roughly doubling
the log volume for updates. The alternative — storing a page reference to the
pre-image — was rejected because the pages holding the pre-image are reclaimed
as soon as the last snapshot that pinned them is gone, which would make
subscription resumption and replication depend on timing. A change log that
stores the change is self-contained: it is exactly as much information as a
subscriber or a replica needs.

Because records are suffixed by a CRC and a length, the tail of the open segment
can be truncated safely: recovery discards anything past the offset committed by
the superblock.

Retention: `limits.log_retention_bytes` (default 64 MiB) per database, plus a
minimum of the oldest live subscriber position and (later) the replication
offset. When retention forces the head to advance, `log_first_seq` advances with
it, and a subscriber whose position is older receives `log_truncated`.

## 8. Recovery and the derived free set

`Database::open` performs exactly this, in this order:

1. Read both superblock slots; validate magic, format version, page size and
   CRC; if neither is valid → `corruption` / `no_valid_superblock`.
2. Truncate the log logically to `log_open_offset` of the chosen superblock
   (`log_open_offset` for the open segment, the full capacity for sealed ones).
   Records past it are never read and never replayed.
3. **Derive the free set** by marking: walk the catalog tree, every collection
   tree (leaf/internal/overflow chains), and every log segment. Then
   `free = [2, page_count) \ marked`.
4. While marking, **validate**: page CRC, page id matches its position, no page
   referenced twice, no page outside the range, no overflow cycle, no sibling
   chain cycle, leaf order consistency in every tree. Any violation →
   `corruption` with the offending page id.
5. Build the in-memory allocator from the free set. The file is now open.

Consequences, stated honestly:

* Open cost is **O(pages)**. For the M0 target sizes (up to a few GB) this is
  milliseconds to a second; a persisted freelist is the M1 optimisation.
* Recovery is also the integrity check: a database that opens is a database
  whose page graph is consistent and whose pages all checksum. Orphans from an
  interrupted commit are simply part of the free set — the design produces no
  garbage that needs cleanup.
* A long-lived reader pins its generation. Pages superseded by newer generations
  cannot be reused until the last pin on the previous generation is dropped, so
  a long-running read transaction, or a slow subscriber, can grow the file.
  This is a documented, bounded cost of non-blocking snapshots (it is LMDB's
  documented behaviour too) and the reason `rtl vacuum` exists in M1.

## 9. Allocation, generations and reclamation

* A `Generation` is an immutable `(page_set, roots, commit_seq)`. Readers pin it
  with an `Arc`; the pager never rewrites a page belonging to a pinned
  generation.
* Reclamation: when the last pin on a superseded generation is dropped, its
  pages (those not shared with a newer generation — COW means a page is shared
  when it was not copied) become reusable.
* Allocation determinism is not required, but allocation *boundedness* is
  tested: a workload that reuses the same key repeatedly must not grow the file
  without bound (a 10k-iteration regression test).

## 10. Locking and process model

* Exclusive advisory lock (`flock`) on the `.rtl` file for the lifetime of the
  `Database`. A second open in the same process or in another process fails with
  `io` / `already_open`.
* In-process concurrency: one writer (`Mutex`), many readers (no lock).
* No `mmap`. Positional `pread`/`pwrite` through a bounded page cache. Reasons:
  no `SIGBUS` when the file is extended or truncated, uniform behaviour across
  platforms, and crash semantics that are testable by truncating and flipping
  bytes of a file copy. An mmap fast path is *(reserved)* for M2 and must not
  change the commit protocol.

## 11. Integrity, checksums and their limits

* CRC-32/ISO-HDLC (via `crc32fast`) on superblocks, every page and every log
  record. Chosen because it is SIMD-accelerated in Rust *and* available in every
  language that will ever build a fixture-checking tool.
* What it catches: accidental corruption — torn writes, bit flips, truncated
  files, a partially overwritten superblock.
* What it does **not** catch: deliberate tampering. There is no cryptographic
  integrity and no encryption in M0; a local attacker with write access owns the
  file. Both are *(reserved)* and need a separate design.
* `rtl check` opens the database, runs step 3+4 of §8 and reports: page count,
  free pages, per-collection document counts, tree heights, log segments,
  retained sequence range, and any corruption found. Because the walk already
  exists for recovery, `check` is nearly free.
* Behaviour on detected corruption: writes stop (`corruption` / `write_aborted`)
  for the affected database; reads of pages that checksum still work; the
  database is never silently "repaired". Repair tooling is *(reserved)*.

## 12. Collection creation, drop and metadata

`collection.create` writes a catalog entry
`{name, collection_id, root, height, documents, created_seq}` and a metadata
entry holding the per-collection counters; `collection.drop` unlinks the entry
and lets the free-set derivation reclaim its pages (no in-place wiping, so a
dropped collection's bytes may remain until their pages are reused — documented,
because "drop is not a secure erase").

`collection_id` assignment is monotonic and never reused: the counter lives in
the metadata tree under key `0x03 | 0`. This is the primitive later required for
replicating DDL.

## 13. Format versioning

* `format_version` is fixed to 1 in M0. A newer file opened by an older engine
  fails with `corruption` / `unsupported_format_version` — the file is not
  touched.
* Adding a page type, changing a key layout or changing the record layout
  requires a format bump. Adding an optional superblock field with a
  `features` bit does not, if an old reader can ignore it safely.
* Migration tooling is *(reserved)*; M0 can only create format v1.

## 14. Limits (format v1)

| Limit | Value | Enforcement |
|---|---|---|
| Page size | 4096 B | fixed |
| Max file size | 16 TiB | page id width |
| Inline value | 1024 B | larger → overflow chain |
| Max document | 16 MiB | `invalid_document` |
| Max log record | 17 MiB | bounded by document limit |
| Max tree depth | 32 | rejected on insert (would be a bug) |
| Max collections | 2^32 − 1 | `collection_id` width |

## 15. Not in M0

| Item | Why not / when |
|---|---|
| Persisted freelist | open-time derivation is simpler and self-validating; M1 |
| Group commit | performance only; M1 |
| `rtl vacuum` / compaction | correctness first; file growth is documented behaviour; M1 |
| Secondary indexes | M1 (`index` error kind already reserved) |
| Page compression, encryption, mmap fast path | need their own designs; M2 |
| Read-only mode, multi-process readers | M1/M2, needs a lock-and-version story |
| Repair tooling | M2; M0 never repairs silently |
