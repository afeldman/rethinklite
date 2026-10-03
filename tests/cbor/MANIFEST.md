# Golden CBOR fixtures — manifest

Normative bytes of the RethinkLite protocol v1 contract
(`docs/cbor-protocol.md` §10). Each `.cbor` file is a **CBOR Sequence**
(RFC 8742): one or more self-delimiting items, no length prefix, no header.

Recorded generation: 2026-10-03 ·
python 3.9.6 · cbor2 5.9.0 ·
13 fixtures

## Rules

1. **The bytes are the contract.** Never edit a fixture file by hand and never
   rewrite an existing one in place — that changes the meaning of a released
   contract. Add a new fixture instead.
2. **Regeneration must be byte-identical.** `tests/cbor/generate_fixtures.py`
   reproduces every file here; the SHA-256 values below must not change. If a
   regeneration produces different bytes, the encoding rules changed and the
   change must be deliberate, documented here, and reflected in
   `docs/compatibility.md`.
3. **Canonicality is verified independently.** `tests/cbor/verify_fixtures.py`
   is a hand-written CBOR reader that shares no code with the generator and
   checks: no indefinite-length items (C1), shortest-form arguments (C2),
   shortest-form floats (C3), length-first key order and no duplicate keys (C4),
   well-formed UTF-8 (C5), and the value-model policy that forbids
   `undefined`/`NaN`/`Infinity` (C6). Its ability to fail is itself tested by
   `tests/cbor/selftest_verifier.py` (25 cases).
4. A conformance implementation must decode every fixture, re-encode it
   deterministically and obtain **byte-identical** output.

Commands:

```
python3 tests/cbor/verify_fixtures.py tests/cbor     # canonicality
python3 tests/cbor/selftest_verifier.py              # the checker can fail
python3 tests/cbor/make_manifest.py                  # regenerate this file
/tmp/cborvenv/bin/python tests/cbor/generate_fixtures.py   # needs cbor2
```

## Fixtures

| File | Items | Bytes | SHA-256 | Intent |
|---|---:|---:|---|---|
| `change_event.cbor` | 1 | 147 | `37c0a3b45546a550c09b9bc05657fe01b1a3d979291751359edfae77309beaef` | one changefeed event with old and new values |
| `count_response.cbor` | 1 | 61 | `5bfccb3f7e3b966be9e0e284a66005541860e46e3da7a62f25ecddbf6dfc1383` | collection.count result |
| `error_response.cbor` | 1 | 208 | `1678705e01e92c28469eda950b98b76f0875ee9c04481e6587b8a122b50fc8b0` | error envelope with kind/code/message/retryable/details for revision_conflict |
| `get_response.cbor` | 1 | 153 | `aa57d3b460efc4040e2dc4e08bcd0984aa54003436744440e75ead2e4c9f04ba` | get result: metadata plus the stored document, byte-identical to insert_request's document |
| `hello_request.cbor` | 1 | 151 | `3371f754b887aa910cb164b44b727389cea99a14958ae474fe93f48d63bd0c20` | session handshake: client name, protocol versions, offered features, required features |
| `hello_response.cbor` | 1 | 303 | `d9ce841f1a1b257362e330821dc263cb5088dceb7ed2500e5c303a0648a85ce9` | session handshake: server identity, negotiated protocol, database uuid + format, granted features, limits |
| `insert_request.cbor` | 1 | 175 | `d989dd941cd8db6e6065fc170fbdc8f8c269cbc74d891ff57ebcf5f664c3b45c` | collection.insert with an explicit text id and return_document=false |
| `insert_response.cbor` | 1 | 77 | `d7382c63b0c35a1856467305c35a6f3e3de6648c4736d2cd504322abed57237e` | insert result: id, rev, commit_seq, unchanged flag |
| `query_request.cbor` | 1 | 150 | `5f8a67ab8ff38278c27ff25c5a08fa81f3fe287cde0c4437f65957a7778a2a7b` | collection.query with a term chain filter > sort desc > limit (length-first canonical map) |
| `query_response.cbor` | 1 | 115 | `73f3ecc62924e6263fcc382c08eb4bccd48a1c167d279f72d3058b83f86a2db7` | query result: documents, returned, scanned, truncated |
| `transaction_request.cbor` | 3 | 255 | `f935340e730f40885c83ceeed1920c51b003bd86c3d84d245e2236d370407418` | three items in one CBOR Sequence: transaction.begin, collection.update inside the transaction, transaction.commit |
| `uuid_id_request.cbor` | 1 | 90 | `ab9fff42ffb15bf47be9b858bfbec2d672e7890bf2d0132d529a81f973be3166` | document addressed by a UUID id: CBOR tag 37 over 16 bytes |
| `watch_request.cbor` | 1 | 145 | `e7639e5605068e3250b3fb8b5047d5e2b15963180143cf5af230dbe6bd51a76e` | collection.watch with a filter expression, include_initial and overflow policy |

## Bytes

### `change_event.cbor`

```
00000000  a2 64 66 65 65 64 03 65 65 76 65 6e 74 a7 62 69  .dfeed.eevent.bi
00000010  64 68 75 73 65 72 2d 31 32 33 63 6e 65 77 a3 62  dhuser-123cnew.b
00000020  69 64 68 75 73 65 72 2d 31 32 33 64 6e 61 6d 65  idhuser-123dname
00000030  65 41 6e 74 6f 6e 66 61 63 74 69 76 65 f4 63 6f  eAntonfactive.co
00000040  6c 64 a3 62 69 64 68 75 73 65 72 2d 31 32 33 64  ld.bidhuser-123d
00000050  6e 61 6d 65 65 41 6e 74 6f 6e 66 61 63 74 69 76  nameeAntonfactiv
00000060  65 f5 63 72 65 76 02 64 74 79 70 65 67 75 70 64  e.crev.dtypegupd
00000070  61 74 65 64 6a 63 6f 6c 6c 65 63 74 69 6f 6e 65  atedjcollectione
00000080  75 73 65 72 73 6a 63 6f 6d 6d 69 74 5f 73 65 71  usersjcommit_seq
00000090  19 12 67                                         ..g
```

### `count_response.cbor`

```
00000000  a4 64 62 6f 64 79 a3 65 63 6f 75 6e 74 18 29 65  .dbody.ecount.)e
00000010  65 78 61 63 74 f5 67 73 63 61 6e 6e 65 64 18 80  exact.gscanned..
00000020  66 73 74 61 74 75 73 62 6f 6b 67 72 65 71 75 65  fstatusbokgreque
00000030  73 74 06 68 70 72 6f 74 6f 63 6f 6c 01           st.hprotocol.
```

### `error_response.cbor`

```
00000000  a4 65 65 72 72 6f 72 a5 64 63 6f 64 65 71 72 65  .eerror.dcodeqre
00000010  76 69 73 69 6f 6e 5f 63 6f 6e 66 6c 69 63 74 64  vision_conflictd
00000020  6b 69 6e 64 68 63 6f 6e 66 6c 69 63 74 67 64 65  kindhconflictgde
00000030  74 61 69 6c 73 a4 62 69 64 68 75 73 65 72 2d 31  tails.bidhuser-1
00000040  32 33 66 61 63 74 75 61 6c 04 68 65 78 70 65 63  23factual.hexpec
00000050  74 65 64 03 6a 63 6f 6c 6c 65 63 74 69 6f 6e 65  ted.jcollectione
00000060  75 73 65 72 73 67 6d 65 73 73 61 67 65 78 36 64  usersgmessagex6d
00000070  6f 63 75 6d 65 6e 74 20 72 65 76 69 73 69 6f 6e  ocument revision
00000080  20 64 6f 65 73 20 6e 6f 74 20 6d 61 74 63 68 20   does not match 
00000090  74 68 65 20 65 78 70 65 63 74 65 64 20 72 65 76  the expected rev
000000a0  69 73 69 6f 6e 69 72 65 74 72 79 61 62 6c 65 f4  isioniretryable.
000000b0  66 73 74 61 74 75 73 65 65 72 72 6f 72 67 72 65  fstatuseerrorgre
000000c0  71 75 65 73 74 08 68 70 72 6f 74 6f 63 6f 6c 01  quest.hprotocol.
```

### `get_response.cbor`

```
00000000  a4 64 62 6f 64 79 a4 62 69 64 68 75 73 65 72 2d  .dbody.bidhuser-
00000010  31 32 33 63 72 65 76 01 68 64 6f 63 75 6d 65 6e  123crev.hdocumen
00000020  74 a6 62 69 64 68 75 73 65 72 2d 31 32 33 63 61  t.bidhuser-123ca
00000030  67 65 18 29 64 6e 61 6d 65 65 41 6e 74 6f 6e 64  ge.)dnameeAntond
00000040  74 61 67 73 82 64 72 75 73 74 68 64 61 74 61 62  tags.drusthdatab
00000050  61 73 65 66 61 63 74 69 76 65 f5 67 70 72 6f 66  asefactive.gprof
00000060  69 6c 65 a1 67 63 6f 75 6e 74 72 79 62 44 45 6a  ile.gcountrybDEj
00000070  63 6f 6d 6d 69 74 5f 73 65 71 18 2a 66 73 74 61  commit_seq.*fsta
00000080  74 75 73 62 6f 6b 67 72 65 71 75 65 73 74 03 68  tusbokgrequest.h
00000090  70 72 6f 74 6f 63 6f 6c 01                       protocol.
```

### `hello_request.cbor`

```
00000000  a4 64 62 6f 64 79 a4 66 63 6c 69 65 6e 74 a2 64  .dbody.fclient.d
00000010  6e 61 6d 65 72 72 65 74 68 69 6e 6b 6c 69 74 65  namerrethinklite
00000020  2d 70 79 74 68 6f 6e 67 76 65 72 73 69 6f 6e 65  -pythongversione
00000030  30 2e 31 2e 30 68 66 65 61 74 75 72 65 73 82 6c  0.1.0hfeatures.l
00000040  74 72 61 6e 73 61 63 74 69 6f 6e 73 65 77 61 74  transactionsewat
00000050  63 68 68 70 72 6f 74 6f 63 6f 6c 81 01 68 72 65  chhprotocol..hre
00000060  71 75 69 72 65 64 81 6c 74 72 61 6e 73 61 63 74  quired.ltransact
00000070  69 6f 6e 73 67 72 65 71 75 65 73 74 01 68 70 72  ionsgrequest.hpr
00000080  6f 74 6f 63 6f 6c 01 69 6f 70 65 72 61 74 69 6f  otocol.ioperatio
00000090  6e 65 68 65 6c 6c 6f                             nehello
```

### `hello_response.cbor`

```
00000000  a4 64 62 6f 64 79 a5 66 6c 69 6d 69 74 73 a5 6a  .dbody.flimits.j
00000010  66 65 65 64 5f 71 75 65 75 65 19 04 00 6d 71 75  feed_queue...mqu
00000020  65 72 79 5f 72 65 73 75 6c 74 73 1a 00 01 86 a0  ery_results.....
00000030  6e 64 6f 63 75 6d 65 6e 74 5f 62 79 74 65 73 1a  ndocument_bytes.
00000040  01 00 00 00 73 6c 6f 67 5f 72 65 74 65 6e 74 69  ....slog_retenti
00000050  6f 6e 5f 62 79 74 65 73 1a 04 00 00 00 76 74 72  on_bytes.....vtr
00000060  61 6e 73 61 63 74 69 6f 6e 5f 74 69 6d 65 6f 75  ansaction_timeou
00000070  74 5f 6d 73 19 75 30 66 73 65 72 76 65 72 a3 64  t_ms.u0fserver.d
00000080  6e 61 6d 65 6b 72 65 74 68 69 6e 6b 6c 69 74 65  namekrethinklite
00000090  66 65 6e 67 69 6e 65 65 30 2e 31 2e 30 67 76 65  fenginee0.1.0gve
000000a0  72 73 69 6f 6e 65 30 2e 31 2e 30 68 64 61 74 61  rsione0.1.0hdata
000000b0  62 61 73 65 a3 64 70 61 74 68 6b 65 78 61 6d 70  base.dpathkexamp
000000c0  6c 65 2e 72 74 6c 64 75 75 69 64 50 01 8f 5f 9a  le.rtlduuidP.._.
000000d0  1b 2c 7d ef 81 23 45 67 89 ab cd ef 66 66 6f 72  .,}..#Eg....ffor
000000e0  6d 61 74 01 68 66 65 61 74 75 72 65 73 83 66 63  mat.hfeatures.fc
000000f0  61 6e 63 65 6c 65 63 6f 75 6e 74 6c 74 72 61 6e  ancelecountltran
00000100  73 61 63 74 69 6f 6e 73 68 70 72 6f 74 6f 63 6f  sactionshprotoco
00000110  6c 01 66 73 74 61 74 75 73 62 6f 6b 67 72 65 71  l.fstatusbokgreq
00000120  75 65 73 74 01 68 70 72 6f 74 6f 63 6f 6c 01     uest.hprotocol.
```

### `insert_request.cbor`

```
00000000  a4 64 62 6f 64 79 a3 68 64 6f 63 75 6d 65 6e 74  .dbody.hdocument
00000010  a6 62 69 64 68 75 73 65 72 2d 31 32 33 63 61 67  .bidhuser-123cag
00000020  65 18 29 64 6e 61 6d 65 65 41 6e 74 6f 6e 64 74  e.)dnameeAntondt
00000030  61 67 73 82 64 72 75 73 74 68 64 61 74 61 62 61  ags.drusthdataba
00000040  73 65 66 61 63 74 69 76 65 f5 67 70 72 6f 66 69  sefactive.gprofi
00000050  6c 65 a1 67 63 6f 75 6e 74 72 79 62 44 45 6a 63  le.gcountrybDEjc
00000060  6f 6c 6c 65 63 74 69 6f 6e 65 75 73 65 72 73 6f  ollectioneuserso
00000070  72 65 74 75 72 6e 5f 64 6f 63 75 6d 65 6e 74 f4  return_document.
00000080  67 72 65 71 75 65 73 74 02 68 70 72 6f 74 6f 63  grequest.hprotoc
00000090  6f 6c 01 69 6f 70 65 72 61 74 69 6f 6e 71 63 6f  ol.ioperationqco
000000a0  6c 6c 65 63 74 69 6f 6e 2e 69 6e 73 65 72 74     llection.insert
```

### `insert_response.cbor`

```
00000000  a4 64 62 6f 64 79 a4 62 69 64 68 75 73 65 72 2d  .dbody.bidhuser-
00000010  31 32 33 63 72 65 76 01 69 75 6e 63 68 61 6e 67  123crev.iunchang
00000020  65 64 f4 6a 63 6f 6d 6d 69 74 5f 73 65 71 18 2a  ed.jcommit_seq.*
00000030  66 73 74 61 74 75 73 62 6f 6b 67 72 65 71 75 65  fstatusbokgreque
00000040  73 74 02 68 70 72 6f 74 6f 63 6f 6c 01           st.hprotocol.
```

### `query_request.cbor`

```
00000000  a4 64 62 6f 64 79 a3 64 65 78 70 72 83 65 6c 69  .dbody.dexpr.eli
00000010  6d 69 74 14 84 64 73 6f 72 74 82 65 66 69 65 6c  mit..dsort.efiel
00000020  64 63 61 67 65 64 64 65 73 63 83 66 66 69 6c 74  dcageddesc.ffilt
00000030  65 72 83 62 67 74 82 65 66 69 65 6c 64 63 61 67  er.bgt.efieldcag
00000040  65 18 1e 81 64 73 63 61 6e 6a 63 6f 6c 6c 65 63  e...dscanjcollec
00000050  74 69 6f 6e 65 75 73 65 72 73 6c 69 6e 63 6c 75  tioneuserslinclu
00000060  64 65 5f 6d 65 74 61 f4 67 72 65 71 75 65 73 74  de_meta.grequest
00000070  05 68 70 72 6f 74 6f 63 6f 6c 01 69 6f 70 65 72  .hprotocol.ioper
00000080  61 74 69 6f 6e 70 63 6f 6c 6c 65 63 74 69 6f 6e  ationpcollection
00000090  2e 71 75 65 72 79                                .query
```

### `query_response.cbor`

```
00000000  a4 64 62 6f 64 79 a4 67 73 63 61 6e 6e 65 64 03  .dbody.gscanned.
00000010  68 72 65 74 75 72 6e 65 64 01 69 64 6f 63 75 6d  hreturned.idocum
00000020  65 6e 74 73 81 a4 62 69 64 68 75 73 65 72 2d 31  ents..bidhuser-1
00000030  32 33 63 61 67 65 18 29 64 6e 61 6d 65 65 41 6e  23cage.)dnameeAn
00000040  74 6f 6e 66 61 63 74 69 76 65 f5 69 74 72 75 6e  tonfactive.itrun
00000050  63 61 74 65 64 f4 66 73 74 61 74 75 73 62 6f 6b  cated.fstatusbok
00000060  67 72 65 71 75 65 73 74 05 68 70 72 6f 74 6f 63  grequest.hprotoc
00000070  6f 6c 01                                         ol.
```

### `transaction_request.cbor`

```
00000000  a4 64 62 6f 64 79 a1 64 6d 6f 64 65 6a 72 65 61  .dbody.dmodejrea
00000010  64 5f 77 72 69 74 65 67 72 65 71 75 65 73 74 07  d_writegrequest.
00000020  68 70 72 6f 74 6f 63 6f 6c 01 69 6f 70 65 72 61  hprotocol.iopera
00000030  74 69 6f 6e 71 74 72 61 6e 73 61 63 74 69 6f 6e  tionqtransaction
00000040  2e 62 65 67 69 6e a5 64 62 6f 64 79 a4 62 69 64  .begin.dbody.bid
00000050  68 75 73 65 72 2d 31 32 33 63 73 65 74 a1 66 61  huser-123cset.fa
00000060  63 74 69 76 65 f4 66 69 66 5f 72 65 76 01 6a 63  ctive.fif_rev.jc
00000070  6f 6c 6c 65 63 74 69 6f 6e 65 75 73 65 72 73 67  ollectioneusersg
00000080  72 65 71 75 65 73 74 08 68 70 72 6f 74 6f 63 6f  request.hprotoco
00000090  6c 01 69 6f 70 65 72 61 74 69 6f 6e 71 63 6f 6c  l.ioperationqcol
000000a0  6c 65 63 74 69 6f 6e 2e 75 70 64 61 74 65 6b 74  lection.updatekt
000000b0  72 61 6e 73 61 63 74 69 6f 6e 07 a4 64 62 6f 64  ransaction..dbod
000000c0  79 a1 6b 74 72 61 6e 73 61 63 74 69 6f 6e 07 67  y.ktransaction.g
000000d0  72 65 71 75 65 73 74 09 68 70 72 6f 74 6f 63 6f  request.hprotoco
000000e0  6c 01 69 6f 70 65 72 61 74 69 6f 6e 72 74 72 61  l.ioperationrtra
000000f0  6e 73 61 63 74 69 6f 6e 2e 63 6f 6d 6d 69 74     nsaction.commit
```

### `uuid_id_request.cbor`

```
00000000  a4 64 62 6f 64 79 a2 62 69 64 d8 25 50 01 8f 5f  .dbody.bid.%P.._
00000010  9a 1b 2c 7d ef 81 23 45 67 8a bc de ff 6a 63 6f  ..,}..#Eg....jco
00000020  6c 6c 65 63 74 69 6f 6e 65 75 73 65 72 73 67 72  llectioneusersgr
00000030  65 71 75 65 73 74 04 68 70 72 6f 74 6f 63 6f 6c  equest.hprotocol
00000040  01 69 6f 70 65 72 61 74 69 6f 6e 6e 63 6f 6c 6c  .ioperationncoll
00000050  65 63 74 69 6f 6e 2e 67 65 74                    ection.get
```

### `watch_request.cbor`

```
00000000  a4 64 62 6f 64 79 a4 64 65 78 70 72 83 66 66 69  .dbody.dexpr.ffi
00000010  6c 74 65 72 83 62 65 71 82 65 66 69 65 6c 64 66  lter.beq.efieldf
00000020  61 63 74 69 76 65 f5 81 64 73 63 61 6e 68 6f 76  active..dscanhov
00000030  65 72 66 6c 6f 77 6a 64 69 73 63 6f 6e 6e 65 63  erflowjdisconnec
00000040  74 6a 63 6f 6c 6c 65 63 74 69 6f 6e 65 75 73 65  tjcollectioneuse
00000050  72 73 6f 69 6e 63 6c 75 64 65 5f 69 6e 69 74 69  rsoinclude_initi
00000060  61 6c f5 67 72 65 71 75 65 73 74 0a 68 70 72 6f  al.grequest.hpro
00000070  74 6f 63 6f 6c 01 69 6f 70 65 72 61 74 69 6f 6e  tocol.ioperation
00000080  70 63 6f 6c 6c 65 63 74 69 6f 6e 2e 77 61 74 63  pcollection.watc
00000090  68                                               h
```
