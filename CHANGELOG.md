# Changelog

## [2.1.0] - 2026-10-08

KNN filters on metadata columns, rowids, and primary keys now compare a bound value or literal the way a plain scan of the same `vec0` table does, and more of them apply before the k nearest rows are chosen, so some queries return different rows. Some statements that used to succeed now fail; read `### Changed` before upgrading. Tables created by earlier releases still open, except those with a malformed vector column definition (see `### Changed`).

### Added

- `INSERT OR REPLACE` on a `vec0` table replaces the row with the same rowid or text primary key; it used to fail with a UNIQUE constraint error. Ported from [asg017@b95c05b](https://github.com/asg017/sqlite-vec/commit/b95c05b) via [vlasky@03b429d](https://github.com/vlasky/sqlite-vec/commit/03b429d) ([asg017#127](https://github.com/asg017/sqlite-vec/issues/127)).

### Changed

- `float32` vector input now rejects NaN and ±Inf elements, including JSON numbers that overflow `float32` such as `1e39`, with `invalid float32 vector: element N is NaN` (or `Inf`). This includes stored vectors passed to SQL functions. Ported from [asg017@c4c23bd](https://github.com/asg017/sqlite-vec/commit/c4c23bd).
- `vec_normalize()` of an all-zero vector returns NULL instead of a vector of NaNs, as [vlasky@571ff3a](https://github.com/vlasky/sqlite-vec/commit/571ff3a) does.
- Cosine distance and `vec_normalize()` now sum squared elements in `double`. Vectors with elements below about 3e-23 or above about 2e19 used to get wrong cosine distances, such as 1.0 or NULL, and other cosine distances can differ from 2.0.2 in the last few digits. Ported from [vlasky@d75c245](https://github.com/vlasky/sqlite-vec/commit/d75c245) ([asg017#324](https://github.com/asg017/sqlite-vec/issues/324)).
- KNN filters on metadata columns and `distance` now compare values as SQLite does with an untyped column: `n = '5'` no longer matches the integer 5, `t = 5` no longer matches the text `'5'`, and `n = ?` bound to NULL no longer matches 0. A filter sees only the value, so in a KNN query `t = cast(5 as integer)`, `id = cast(5 as integer)` on a text primary key, and `p is cast(5 as integer)` on a text partition key no longer match the text `'5'`, though a plain scan does. Rowid lookups no longer read NULL, `'abc'`, or `x'00'` as rowid 0 or `5.5` as rowid 5, so `UPDATE` and `DELETE ... WHERE rowid = ?` bound to such a value change no row. Ported from the unmerged [vlasky#12](https://github.com/vlasky/sqlite-vec/pull/12) ([asg017#329](https://github.com/asg017/sqlite-vec/pull/329)).
- KNN `=`, `IS`, `<`, `<=`, `>`, `>=`, and `IN` filters on `text` metadata columns now honor `COLLATE NOCASE` and `COLLATE RTRIM`; they used to compare bytewise. Any other collation fails with `Collation "x" is not supported on the "t" metadata column in a vec0 KNN query.`, and a `!=` or `IS NOT` filter with a collation can return fewer rows than `k`.
- `vec0` declares its `rowid` or integer primary key column `INTEGER`, so comparisons with it convert text to a number as on an ordinary table: `rowid > '3'` used to match no row. `PRAGMA table_info` now reports the type `INTEGER`.
- A text primary key no longer matches a numeric literal or bound number: `id = 5` used to find the key `'5'` in queries, `UPDATE`, `DELETE`, and KNN `id in (...)`. Lookups by text key are slower: 20,000 `id = ?` queries on a 20,000-row table took 105–107 ms instead of 95–100 ms.
- More KNN filters now apply before the k nearest rows are chosen: `rowid = ?`, a primary key's `id = ?`, and a partition key's `IN`, `IS`, `IS NOT`, `IS NULL`, `IS NOT NULL`, `LIKE`, and `GLOB`. A text primary key `id =` or partition key `IS` or `IN` filter that names a collation other than `BINARY` still works as before, and a partition key `IS NOT` with one can return fewer than k rows. SQLite used to apply most of them to the k results, so a query could return fewer than k rows and its `LIMIT` form failed with `A LIMIT or 'k = ?' constraint is required`; a partition key `IN` returned up to k rows per value. A partition key `IN` with more distinct values than SQLite's host parameter limit (32766 by default) now fails with `Error preparing stmtChunk: too many SQL variables`.
- KNN `in (...)` filters on `integer` metadata columns use binary search: a 2,048-value list on a 200,000-row table took 5.2–5.9 ms instead of 109 ms. Ported from the unmerged [vlasky#10](https://github.com/vlasky/sqlite-vec/pull/10) ([asg017#328](https://github.com/asg017/sqlite-vec/pull/328)).
- MMR reranking keeps each candidate's highest similarity as a running maximum and selects the same rows: `k = 200` on a 20,000-row table of `float[384]` vectors took 87 ms instead of 5.3 s. Ported from the unmerged [vlasky#11](https://github.com/vlasky/sqlite-vec/pull/11).
- A KNN query skips reading the vectors of chunks where its rowid and metadata filters keep no row, including fully deleted chunks: on a 100,000-row `float[768]` table, `n = 42` took 1.9 ms instead of 83 ms, and queries that skip no chunk took within 1.5% of their old time. A missing or wrong-size vector blob in a skipped chunk no longer fails the query. Ported from the unmerged [vlasky#13](https://github.com/vlasky/sqlite-vec/pull/13) ([asg017#330](https://github.com/asg017/sqlite-vec/pull/330)).
- Hamming distance between `bit` vectors of 128 or more dimensions uses NEON in the darwin-arm64 binary. Ported from [vlasky@6ad1350](https://github.com/vlasky/sqlite-vec/commit/6ad1350).
- An `UPDATE` that sets a `vec0` table's rowid or integer primary key to a different value now fails with `UPDATEs on vec0 primary key values are not allowed.`, as a changed text primary key already did; it used to apply the statement's other changes and leave the key unchanged. Text key changes the old check missed, such as `'5'` to `5`, fail the same way.
- A KNN query now fails when `k` is not an integer or `mmr_lambda` is not a number, with `k value in knn query must be an integer, provided …` or `mmr_lambda value in knn query must be a number between 0.0 and 1.0, provided …`. It used to read NULL, `'abc'`, or `x'00'` as 0, and `k = 5.5` as 5.
- Writing an integer outside 32 bits, such as 4294967296, to a `boolean` metadata column fails with `Expected 0 or 1 for BOOLEAN metadata column`; it used to store false or true from the low 32 bits.
- A `vec0` query, `INSERT`, `UPDATE`, `DELETE`, or `optimize` interrupted by `sqlite3_interrupt()` or a progress handler now fails with `SQLITE_INTERRUPT` and the message `interrupted`; it often failed with `SQLITE_ERROR`, or with a message such as `chunks iter error` or `Could not open metadata blob`.
- `optimize` on a table with a partition key column now fails with `SQL logic error` when a row's chunk is missing from the `_chunks` shadow table; `sqlite3_step()` used to return `SQLITE_ROW` while SQLite rolled the optimize back.
- `CREATE VIRTUAL TABLE` of a `vec0` table that has a column named like the table, or that is named `distance`, `k`, `mmr_lambda`, or (without a primary key column) `rowid`, now fails with `column name 'emb' conflicts with table name (reserved for command column)` instead of `duplicate column name: emb`, as upstream [asg017@6e2c4c6](https://github.com/asg017/sqlite-vec/commit/6e2c4c6) does.
- `CREATE VIRTUAL TABLE` now rejects partial keywords and extra tokens in partition key, primary key, auxiliary, and metadata column definitions with `Could not parse '…'`. It used to read `id i primary key` as an integer primary key and `x text collate nocase` as a text column without the collation; tables already declared that way still open. Vector column definitions are now parsed strictly too: `5 float[4]` and `a float+4+` used to create vector columns and now fail, and tables declared that way no longer open ([vlasky@13282f4](https://github.com/vlasky/sqlite-vec/commit/13282f4)).
- A table named after an SQL keyword, such as `"order"`, can now be created, and the hidden command column that runs `optimize` on a table named `"my vecs"` is now named `"my vecs"` instead of `my`.
- `vec0`'s `xShadowName` now reports the `_vector_chunksNN` tables, so when SQLite consults it, as after a `VACUUM`, it marks them as shadow tables, which `SQLITE_DBCONFIG_DEFENSIVE` protects from direct writes. Ported from [vlasky@44bded9](https://github.com/vlasky/sqlite-vec/commit/44bded9) and [vlasky@5a4dc73](https://github.com/vlasky/sqlite-vec/commit/5a4dc73) ([asg017#320](https://github.com/asg017/sqlite-vec/issues/320)).
- Three error messages are spelled correctly: `Only integers are allowed` (was `allows`), `vec0 only supports a single primary key column` (was `suports`), and `Partition key type mismatch` (was `Parition`).

### Removed

- Removed the Python, Ruby, Rust, and Lua bindings, which this fork never published. Installing them from `main` no longer works; tags up to v2.0.2 still include them. Use [`asg017/sqlite-vec`](https://github.com/asg017/sqlite-vec) or [`vlasky/sqlite-vec`](https://github.com/vlasky/sqlite-vec) instead.

### Fixed

- Fixed a crash when `vec0` could not prepare the statement that finds a row's chunk, as when the `_rowids` shadow table is missing or an interrupt stops the prepare; such a statement now fails with an error.
- Fixed use of freed memory after a `DROP TABLE` of a `vec0` table fails, as when a shadow table is missing; the table now stays usable.
- Fixed a crash in KNN queries that compare a `text` metadata column with NULL using `<`, `<=`, `>`, or `>=` when a stored value is longer than 12 bytes.
- Fixed KNN `<`, `<=`, `>`, and `>=` filters on `text` metadata columns, which failed with `Could not filter metadata fields` on a stored value of exactly 12 bytes and treated a value longer than 12 bytes as equal to a longer value that starts with it.
- Fixed KNN `LIKE` and `GLOB` filters on `text` metadata columns, which read past the end of a 12-byte stored value, treated `[` as a literal in a prefix pattern such as `'[ab]*'`, and read a prefix pattern past an embedded NUL byte.
- Fixed KNN `=`, `!=`, `IS`, `IS NOT`, and `IN` filters on `text` metadata columns, which compared values only up to an embedded NUL byte.
- Fixed KNN `id in (...)` on a text primary key, which returned no rows when the list contained an id not in the table.
- `UPDATE` and `DELETE` with a KNN `WHERE` clause, and `oid` or `_rowid_` in a KNN query, now work on a table without a primary key column; they failed with `Internal sqlite-vec error: expected point query plan in vec0Rowid`. An `UPDATE` through a full scan or a KNN `WHERE` clause now also works on a table with a partition key or an `int8` or `bit` vector column, if it does not set that column.
- Fixed out-of-bounds reads and writes, an uninitialized row count, and an endless loop in `vec_npy_each` and `vec_npy_file()` on malformed or very large numpy input: a header that lacks `descr`, `fortran_order`, or `shape`, or ends inside a `shape` number or `False`; a `shape` whose data size overflows, now rejected with `shape is too large`; and rows wider than 1,048,576 floats. A valid file with rows of 524,288 floats or more could fail with an out-of-memory error and now reads if it has fewer than 1,024 rows and under about 2 GiB of data; size errors report the full expected size; and a file whose size cannot be determined fails with `Could not determine numpy file size`. Partly ported from [vlasky@e746572](https://github.com/vlasky/sqlite-vec/commit/e746572).
- `vec_npy_file()` now reads files with more than 2 GiB of data, which failed with `numpy array file header length is invalid`, and on Windows opens files in binary mode; text mode dropped or corrupted vectors containing `0x1A` or CRLF bytes.
- Fixed `vec0` tables that older releases allowed to have a column named like the table, or to be named `distance`, `k`, `mmr_lambda`, or (without a primary key column) `rowid`: they failed to open with `duplicate column name`. They now open, and `optimize` works on them after `ALTER TABLE ... RENAME`.
- Fixed inserts into tables created before v0.2.0-alpha after `optimize` had removed a chunk, which failed with `Error opening vector blob`. Ported from [vlasky@3a64182](https://github.com/vlasky/sqlite-vec/commit/3a64182).
- An `INSERT` with a wrongly typed metadata or auxiliary value now fails before writing anything; it used to leave a partial row that a surrounding transaction could commit.
- Fixed memory and handle leaks in auxiliary column `UPDATE`s, failed `CREATE VIRTUAL TABLE`s, failed long-text metadata writes (which made `sqlite3_close()` return `SQLITE_BUSY`), and MMR and text-filter error paths ([vlasky@5ae4fed](https://github.com/vlasky/sqlite-vec/commit/5ae4fed)), and in `ALTER TABLE ... RENAME`. A failed metadata blob write now returns its error instead of success.
- Fixed undefined behavior that upstream fuzzers found: misaligned reads of `float32` blobs, a one-byte over-read in the numpy header parser, an unclamped conversion in `vec_quantize_int8()` that turned `2.0` into `-2` instead of `127` on x86-64 ([asg017@cdbc347](https://github.com/asg017/sqlite-vec/commit/cdbc347), [@2f4c2e4](https://github.com/asg017/sqlite-vec/commit/2f4c2e4), [@1b53b94](https://github.com/asg017/sqlite-vec/commit/1b53b94) via [vlasky@899e98c](https://github.com/vlasky/sqlite-vec/commit/899e98c)), and an integer overflow on JSON numbers with very long exponents ([vlasky@13282f4](https://github.com/vlasky/sqlite-vec/commit/13282f4)).

### Infrastructure

- Ported upstream's fuzz targets ([vlasky@3768246](https://github.com/vlasky/sqlite-vec/commit/3768246)), which `fuzz.yaml` now runs on every push to `main` and nightly, and its vec0 constructor unit tests ([asg017@0659d88](https://github.com/asg017/sqlite-vec/commit/0659d88), [@79d5818](https://github.com/asg017/sqlite-vec/commit/79d5818) via [vlasky@325282a](https://github.com/vlasky/sqlite-vec/commit/325282a); [vlasky@10226cb](https://github.com/vlasky/sqlite-vec/commit/10226cb)). `sqlite-vec.c` no longer triggers GCC 15's `-Wunterminated-string-initialization` ([vlasky@6342fb4](https://github.com/vlasky/sqlite-vec/commit/6342fb4), [asg017#321](https://github.com/asg017/sqlite-vec/issues/321)).

## [2.0.2] - 2026-10-06

Fixes wrong L2 distances between `int8` vectors in the darwin-arm64 binary. Binaries for the other platforms compute the same results as 2.0.1. Stored vectors are unaffected: distances are computed at query time, so upgrading corrects query results without rebuilding any table.

### Fixed

- Fixed L2 distance between `int8` vectors in NEON builds, which include the published darwin-arm64 binary. The NEON kernel squared each element difference in a 16-bit lane, and any difference of 182 or more (for example 127 against −128) overflows it, so `vec_distance_l2()` and `int8` KNN queries using L2 distance returned distances that were too small, or NULL when the wrapped sum went negative. Squares are now widened to 32 bits.
- Fixed `vec_distance_l2()` between long `int8` vectors in NEON builds. The NEON kernel kept its running sum of squares in 32 bits, which overflows once the sum passes 2^31 − 1 (from 33,026 elements at opposite extremes), and returned NULL or a wrong distance. The sum is now kept in 64 bits. vec0 tables allow at most 8,192 dimensions, so KNN queries were not affected.
- The NEON code now compiles with GCC, which rejects implicit conversions between signed and unsigned vector types, and includes `arm64_neon.h` under MSVC on ARM64. Release builds still enable NEON only on darwin-arm64.

## [2.0.1] - 2026-08-27

No functional changes. The extension source, bindings, and packaged files are identical to 2.0.0 — this release only changes how the package is built and published.

### Infrastructure

- Releases are now staged for human approval instead of published directly by CI. `release.yaml` prepares and signs the version commit, rehearses the exact packaging path, and dispatches the tag-bound `publish.yaml`, which rebuilds all eight platform binaries from the signed tag and passes one verified tarball to an isolated job whose only npm authority is `npm stage publish`. A maintainer reviews the staged package and approves it with 2FA before npm makes it public. Previously the package was published from the pre-release `main` commit, so its provenance named a different commit than the one that built the tarball.
- Added `scripts/package-npm.sh`, which enforces the eight-binary artifact set, the package identity, and the exact tarball file boundary. Both the pre-tag rehearsal and the publisher call it, so the release runs the same code it rehearsed rather than a second description of it.
- Dependency and GitHub Action resolution now skips releases published in the last 14 days (`.npmrc`, `.pinact.yaml`, and `tests/pyproject.toml`), and npm no longer runs dependency lifecycle scripts implicitly. This affects only how this repository builds; it does not change what the published package depends on, which remains nothing.
- Added `check-workflows.yaml` to audit every workflow with [zizmor](https://docs.zizmor.sh/) on each push and pull request, and set `persist-credentials: false` on all CI checkouts so the build jobs no longer carry a writable token they never used.

## [2.0.0] - 2026-08-25

### Changed

- **BREAKING:** Raised the minimum supported Node.js to 22.0.0 (`engines.node` was `>=14.0.0`). Node 20 and earlier reached end-of-life on 2026-04-30 and no longer receive security updates. The native extension itself is unchanged — this only tightens what npm will install onto. Node 22 is supported until 2027-04-30 and Node 24 until 2028-04-30.

### Fixed

- Fixed the rowid comparator used by the KNN `rowid IN (...)` filter: it returned the 64-bit rowid difference narrowed to `int`. The subtraction can overflow and the narrowing keeps only the low 32 bits, so unequal rowids could compare as equal or with the wrong sign (e.g. a difference of 2^31 wraps negative, and exactly 2^32 wraps to zero) — an inconsistent ordering for `qsort` (undefined behavior) and silent `bsearch` misses that dropped matching rowids from KNN results. Now uses a proper three-way comparison, verified with rowids spanning more than 2^31 including negatives.
- Fixed error reporting for non-primary-key failures during explicit-rowid inserts: the message was built from a NULL statement handle, so it always read "out of memory" instead of the underlying SQLite error.
- `vec_version()` and the `CREATE_VERSION` recorded in new tables' `_info` shadow rows now report the npm package version (previously stuck at `v0.4.0`, the last release that regenerated `sqlite-vec.h` from `VERSION`).
- Added test coverage for negative and large-magnitude rowids (insert, point lookup, update, delete, KNN, metadata/auxiliary/partition columns, `rowid IN (...)`).

## [1.2.0] - 2026-07-06

### Removed

- Removed the in-tree Go bindings (`bindings/go/`) and the `build-ncruces-go` CI job. The CGO bindings were never published by this fork, and the `ncruces/go-sqlite3` WASM build broke when upstream migrated to [wasm2go](https://github.com/ncruces/wasm2go), which no longer supports injecting a custom C extension at build time. Go users should use upstream [`asg017/sqlite-vec`](https://github.com/asg017/sqlite-vec) or `ncruces/go-sqlite3`'s built-in [`ext/vec1`](https://pkg.go.dev/github.com/ncruces/go-sqlite3/ext/vec1) extension.

### Fixed

- Hardened the `optimize` command (`INSERT INTO t(t) VALUES('optimize')`) against a native crash on tables with metadata columns. `optimize` now validates each metadata chunk's blob size and slot offset before copying and fails as a catchable `SQLITE_ERROR` on malformed internal state, instead of risking heap corruption or a host-process abort (`EXC_BREAKPOINT`/`SIGTRAP`).
- Fixed a per-row memory leak of vector buffers during `optimize` (tens of MB on large compactions).
- Fixed error-masking in the metadata-copy path that could report a failed copy as success, and a related blob-handle leak; guarded a latent double-free of the chunk-validity buffers.
- `DELETE` now propagates metadata-clear failures instead of silently returning success.

## [1.1.1] - 2026-02-28

### Fixed

- Normalize MMR diversity term so `mmr_lambda` behaves consistently across L2/L1/cosine ([vlasky@8d4ef9e](https://github.com/vlasky/sqlite-vec/commit/8d4ef9eb393c4739ef540c4101d1bab377025141))

## [1.1.0] - 2026-02-27

### Added

- **MMR (Maximal Marginal Relevance) reranking for KNN queries** ([vlasky#6](https://github.com/vlasky/sqlite-vec/pull/6), rebased from [asg017#267](https://github.com/asg017/sqlite-vec/pull/267))
  - New `mmr_lambda` hidden column on vec0 tables balances relevance vs. diversity
  - `WHERE embedding MATCH ? AND k = 10 AND mmr_lambda = 0.5`
  - Lambda range [0.0, 1.0]: 1.0 = pure relevance, 0.0 = pure diversity
  - Supports all vector types (float32, int8, bit) and distance metrics
  - Composes with distance constraints and partition keys
  - Zero overhead when `mmr_lambda` is not used

### Fixed

- Fixed potential uninitialized memory read in MMR copy-back when fewer candidates are selected than requested
- Fixed non-deterministic `test_shadow` snapshot (missing `ORDER BY` on `pragma_table_list`)

## [1.0.1] - 2026-02-23

### Infrastructure

- Fixed Windows CI builds in `npm-release.yaml`: corrected MSVC flags (removed invalid GCC flags), fixed DLL output path, added security hardening for both x64 and ARM64
- Removed unused upstream `release.yaml` (would have erroneously published to PyPI/RubyGems/crates.io)
- Cleaned up Makefile: removed dead variables and phantom targets, added `loadable-msvc-x64`/`loadable-msvc-arm64` targets

## [1.0.0] - 2026-02-09

### Changed

- **npm package renamed from `@mceachen/sqlite-vec` to `@photostructure/sqlite-vec`**

### About this fork

This package is a community fork of [Alex Garcia](https://github.com/asg017)'s
excellent [`sqlite-vec`](https://github.com/asg017/sqlite-vec), building on
[Vlad Lasky](https://github.com/vlasky)'s community fork which merged 15+
upstream PRs. We're grateful to both for their foundational work.

[PhotoStructure](https://photostructure.com) depends on sqlite-vec for
production vector search and is committed to maintaining this fork for as long as
we need it. Our current focus is:

- **Stability:** Memory leak fixes, sanitizer-verified error paths, comprehensive test coverage
- **Node.js packaging:** Prebuilt binaries for all major platforms (including Alpine/musl and Windows ARM64), Electron support, no post-install scripts

The version was bumped to 1.0.0 to signal the package rename and avoid confusion
with the `0.x` releases under the previous name. The underlying C extension is
unchanged from 0.4.1.

All code remains open source under the original MIT/Apache-2.0 dual license.

## [0.4.1] - 2026-02-09

### Fixed

- **Remaining memory leaks from upstream PR #258** ([`c9be38c`](https://github.com/mceachen/sqlite-vec/commit/c9be38c))
  - `vec_eachFilter`: Fixed pzErrMsg leak when vector parsing fails with invalid input
  - `vec_slice`: Fixed vector cleanup leaks in INT8 and BIT cases on malloc failure
  - Changed early `return` to `goto done` to ensure cleanup functions are called
  - These leaks only occurred in error paths (invalid input, OOM) not covered by existing tests

### Added

- **Rust example updates for zerocopy 0.8** ([`53aeaeb`](https://github.com/mceachen/sqlite-vec/commit/53aeaeb))
  - Updated `examples/simple-rust/` to use zerocopy 0.8 API
  - Changed `AsBytes` trait to `IntoBytes` (renamed in zerocopy 0.8)
  - Updated documentation in `site/using/rust.md`
  - Incorporates [upstream PR #244](https://github.com/asg017/sqlite-vec/pull/244)

- **Comprehensive error path test coverage** ([`95cc6c8`](https://github.com/mceachen/sqlite-vec/commit/95cc6c8))
  - New `tests/test-error-paths.py` with 30 tests targeting error-handling code paths
  - Tests exercise error conditions that previously went untested (invalid inputs, NULL values, mismatched types/dimensions)
  - Covers `vec_each`, `vec_slice`, `vec_distance_*`, `vec_add`, `vec_sub`, vec0 INSERT/KNN operations
  - Repeated error operations test (50 iterations) to stress-test cleanup paths
  - Ensures sanitizers (ASan/LSan) will catch any reintroduced memory leaks in error paths

### Context

This release completes the integration of upstream PR #258's memory leak fixes. Previous releases (0.3.2, 0.3.3) addressed most issues, but three error paths remained unfixed:
- Error message allocation in `vec_each` with invalid vectors
- Malloc failure handling in `vec_slice` for INT8/BIT vectors

These paths were not detected by sanitizers because they were never executed by the test suite. The new error path tests ensure these code paths are now covered.

## [0.4.0] - 2026-02-07

### Added

- **Electron support** for packaged ASAR apps
  - `getLoadablePath()` now resolves `app.asar` to `app.asar.unpacked` automatically
  - Works transparently — no code changes needed in Electron apps
  - Added README documentation with `electron-builder` and `electron-forge` configuration examples

## [0.3.3] - 2026-02-04

### Fixed

- **Parser logic bugs** ([`45f09c1`](https://github.com/mceachen/sqlite-vec/commit/45f09c1))
  - Fixed `&&`→`||` condition checks in token validation across multiple parsing functions
  - Affected: `vec0_parse_table_option`, `vec0_parse_partition_key_definition`, `vec0_parse_auxiliary_column_definition`, `vec0_parse_primary_key_definition`, `vec0_parse_vector_column`

- **Float precision for f32 distance calculations** ([`45f09c1`](https://github.com/mceachen/sqlite-vec/commit/45f09c1))
  - Use `sqrtf()` instead of `sqrt()` for f32 vectors to avoid unnecessary double precision
  - May result in minor floating-point differences in distance results

- **Memory leaks in metadata and insert operations** ([`f56fdeb`](https://github.com/mceachen/sqlite-vec/commit/f56fdeb))
  - Fixed zSql memory leaks in `vec0_write_metadata_value` (never freed on any path)
  - Fixed zSql leak and missing `sqlite3_finalize` in `vec0Update_Delete_ClearMetadata`
  - Fixed potential crash from uninitialized function pointers on early error in `vec0Update_Insert`
  - Fixed memory leak in `vec_static_blob_entriesClose` (internal rowids/distances arrays)

### Added

- **KNN filtering documentation** ([`fd69fed`](https://github.com/mceachen/sqlite-vec/commit/fd69fed))
  - New documentation explaining when filters are applied during vs. after KNN search
  - Metadata columns, partition keys, and distance constraints filter DURING search
  - JOIN filters and subqueries filter AFTER search (may return fewer than k results)
  - Documented workarounds: use metadata columns or over-fetch with LIMIT

### Infrastructure

- Added clang-tidy static analysis configuration ([`a39311f`](https://github.com/mceachen/sqlite-vec/commit/a39311f))
- Expanded memory testing with UBSan/TSan support and multi-platform CI matrix ([`de0edf3`](https://github.com/mceachen/sqlite-vec/commit/de0edf3))
- Fixed test infrastructure: `make test-all` target, auto-detect pytest, fix test-unit linking ([`c39ada1`](https://github.com/mceachen/sqlite-vec/commit/c39ada1))

## [0.3.2] - 2026-01-04

### Added

- **Memory testing framework** ([`c8654d0`](https://github.com/mceachen/sqlite-vec/commit/c8654d0))
  - Valgrind and AddressSanitizer support via `make test-memory`
  - Catches memory leaks, use-after-free, and buffer overflows

### Fixed

- **Memory leaks in KNN queries** ([`e4d3340`](https://github.com/mceachen/sqlite-vec/commit/e4d3340), [`df2c2fc`](https://github.com/mceachen/sqlite-vec/commit/df2c2fc), [`f05a360`](https://github.com/mceachen/sqlite-vec/commit/f05a360))
  - Fixed leaks in `vec0Filter_knn` metadata IN clause processing
  - Fixed leaks and potential crashes in `vec_static_blob_entries` filter
  - Ensured `knn_data` is freed on error paths

- **Memory leaks in vtab lifecycle** ([`5f667d8`](https://github.com/mceachen/sqlite-vec/commit/5f667d8), [`49dcce7`](https://github.com/mceachen/sqlite-vec/commit/49dcce7))
  - Fixed leaks in `vec0_init` and `vec0Destroy` error paths
  - Added NULL check before blob read to prevent crashes
  - `vec0_free` now properly frees partition, auxiliary, and metadata column names

- **Cosine distance with zero vectors** ([`5d1279b`](https://github.com/mceachen/sqlite-vec/commit/5d1279b))
  - Returns 1.0 (max distance) instead of NaN for zero-magnitude vectors

## [0.3.1] - 2026-01-04

### Added

- **Lua binding with IEEE 754 compliant float serialization** ([`1d3c258`](https://github.com/mceachen/sqlite-vec/commit/1d3c258))

  - New `bindings/lua/sqlite_vec.lua` module for Lua 5.1+
  - `serialize_f32()` for IEEE 754 binary format
  - `serialize_json()` for JSON format
  - Example script in `examples/simple-lua/`
  - Incorporates [upstream PR #237](https://github.com/asg017/sqlite-vec/pull/237) with extensive bugfixes for float encoding

- **Safer automated release workflow** ([`6d06b7d`](https://github.com/mceachen/sqlite-vec/commit/6d06b7d))
  - `prepare-release` job creates a release branch before building
  - All builds use the release branch with correct version baked in
  - Main branch only updated after successful npm publish
  - If any step fails, main is untouched

### Fixed

- **Numpy header parsing**: fixed `&&`→`||` logic bug ([`90e0099`](https://github.com/mceachen/sqlite-vec/commit/90e0099))

- **Go bindings patch updated for new SQLite source** ([`ceb488c`](https://github.com/mceachen/sqlite-vec/commit/ceb488c))

  - Updated `bindings/go/ncruces/go-sqlite3.patch` for compatibility with latest SQLite

- **npm-release workflow improvements**
  - Synchronized VERSION file with package.json during version bump ([`c345dab`](https://github.com/mceachen/sqlite-vec/commit/c345dab), [`baffb9b`](https://github.com/mceachen/sqlite-vec/commit/baffb9b) )
  - Enhanced npm publish to handle prerelease tags (alpha, beta, etc.) ([`0b691fb`](https://github.com/mceachen/sqlite-vec/commit/0b691fb))

## [0.3.0] - 2026-01-04

### Added

- **OIDC npm release workflow with bundled platform binaries** ([`f7ae5c0`](https://github.com/mceachen/sqlite-vec/commit/f7ae5c0))

  - Single npm package contains all platform builds (prebuildify approach)
  - Simpler, more secure, works offline and with disabled scripts
  - Platform binaries: linux-x64, linux-arm64, darwin-x64, darwin-arm64, win32-x64, win32-arm64

- **Alpine/MUSL support** ([`f7ae5c0`](https://github.com/mceachen/sqlite-vec/commit/f7ae5c0))
  - Added linux-x64-musl and linux-arm64-musl builds
  - Uses node:20-alpine Docker images for compilation

### Fixed

- **MSVC-compatible `__builtin_popcountl` implementation** ([`fab929b`](https://github.com/mceachen/sqlite-vec/commit/fab929b))
  - Added fallback for MSVC which lacks GCC/Clang builtins
  - Enables Windows ARM64 and x64 builds

### Changed

- **Node.js package renamed to `@mceachen/sqlite-vec`** ([`fe9f038`](https://github.com/mceachen/sqlite-vec/commit/fe9f038))
  - Published to npm under scoped package name
  - Updated documentation to reflect new package name
  - All other language bindings will continue to reference upstream ([vlasky/sqlite-vec](https://github.com/vlasky/sqlite-vec))

### Infrastructure

- Updated GitHub Actions to pinned versions via pinact ([`b904a1d`](https://github.com/mceachen/sqlite-vec/commit/b904a1d))
- Added `bash`, `curl` and `unzip` to Alpine build dependencies ([`aa7f3e7`](https://github.com/mceachen/sqlite-vec/commit/aa7f3e7), [`9c446c8`](https://github.com/mceachen/sqlite-vec/commit/9c446c8))
- Documentation fixes ([`4d446f7`](https://github.com/mceachen/sqlite-vec/commit/4d446f7), [`3a5b6d7`](https://github.com/mceachen/sqlite-vec/commit/3a5b6d7))

-----

# Earlier releases are from https://github.com/vlasky/sqlite-vec

## [0.2.4-alpha] - 2026-01-03

### Added

- **Lua binding with IEEE 754 compliant float serialization** ([#237](https://github.com/asg017/sqlite-vec/pull/237))
  - `bindings/lua/sqlite_vec.lua` provides `load()`, `serialize_f32()`, and `serialize_json()` functions
  - Lua 5.1+ compatible with lsqlite3
  - IEEE 754 single-precision float encoding with round-half-to-even (banker's rounding)
  - Proper handling of special values: NaN, Inf, -Inf, -0.0, subnormals
  - Example script and runner in `/examples/simple-lua/`

## [0.2.3-alpha] - 2025-12-29

### Added

- **Android 16KB page support** ([#254](https://github.com/asg017/sqlite-vec/pull/254))
  - Added `LDFLAGS` support to Makefile for passing linker-specific flags
  - Enables Android 15+ compatibility via `-Wl,-z,max-page-size=16384`
  - Required for Play Store app submissions on devices with 16KB memory pages

- **Improved shared library build and installation** ([#149](https://github.com/asg017/sqlite-vec/issues/149))
  - Configurable install paths via `INSTALL_PREFIX`, `INSTALL_LIB_DIR`, `INSTALL_INCLUDE_DIR`, `INSTALL_BIN_DIR`
  - Hidden internal symbols with `-fvisibility=hidden`, exposing only public API
  - `EXT_CFLAGS` captures user-provided `CFLAGS` and `CPPFLAGS`

- **Optimize/VACUUM integration test and documentation**
  - Added test demonstrating optimize command with VACUUM for full space reclamation

### Fixed

- **Linux linking error with libm** ([#252](https://github.com/asg017/sqlite-vec/pull/252))
  - Moved `-lm` flag from `CFLAGS` to `LDLIBS` at end of linker command
  - Fixes "undefined symbol: sqrtf" errors on some Linux distributions
  - Linker now correctly resolves math library symbols

### Documentation

- **Fixed incomplete KNN and Matryoshka guides** ([#208](https://github.com/asg017/sqlite-vec/pull/208), [#209](https://github.com/asg017/sqlite-vec/pull/209))
  - Completed unfinished sentence describing manual KNN method trade-offs
  - Added paper citation and Matryoshka naming explanation

## [0.2.2-alpha] - 2025-12-02

### Added

- **GLOB operator for text metadata columns** ([#191](https://github.com/asg017/sqlite-vec/issues/191))
  - Standard SQL pattern matching with `*` (any characters) and `?` (single character) wildcards
  - Case-sensitive matching (unlike LIKE)
  - Fast path optimization for prefix-only patterns (e.g., `'prefix*'`)
  - Full pattern matching with `sqlite3_strglob()` for complex patterns

- **IS/IS NOT/IS NULL/IS NOT NULL operators for metadata columns** ([#190](https://github.com/asg017/sqlite-vec/issues/190))
  - **Note**: sqlite-vec metadata columns do not currently support NULL values. These operators provide syntactic compatibility within this limitation.
  - `IS` behaves like `=` (all metadata values are non-NULL)
  - `IS NOT` behaves like `!=` (all metadata values are non-NULL)
  - `IS NULL` always returns false (no NULL values exist in metadata)
  - `IS NOT NULL` always returns true (all metadata values are non-NULL)
  - Works on all metadata types: INTEGER, FLOAT, TEXT, and BOOLEAN

### Fixed

- **All compilation warnings eliminated**
  - Fixed critical logic bug: `metadataInIdx` type corrected from `size_t` to `int` (prevented -1 wrapping to SIZE_MAX)
  - Fixed 5 sign comparison warnings with proper type casts
  - Fixed 7 uninitialized variable warnings by adding initializers and default cases
  - Clean compilation with `-Wall -Wextra` (zero warnings)

## [0.2.1-alpha] - 2025-12-02

### Added

- **LIKE operator for text metadata columns** ([#197](https://github.com/asg017/sqlite-vec/issues/197))
  - Standard SQL pattern matching with `%` and `_` wildcards
  - Case-insensitive matching (SQLite default)

### Fixed

- **Locale-dependent JSON parsing** ([#241](https://github.com/asg017/sqlite-vec/issues/241))
  - Custom locale-independent float parser fixes JSON parsing in non-C locales
  - No platform dependencies, thread-safe

- **musl libc compilation** (Alpine Linux)
  - Removed non-portable preprocessor macros from vendored sqlite3.c

## [0.2.0-alpha] - 2025-11-28

### Added

- **Distance constraints for KNN queries** ([#166](https://github.com/asg017/sqlite-vec/pull/166))
  - Support GT, GE, LT, LE operators on the `distance` column in KNN queries
  - Enables cursor-based pagination: `WHERE embedding MATCH ? AND k = 10 AND distance > 0.5`
  - Enables range queries: `WHERE embedding MATCH ? AND k = 100 AND distance BETWEEN 0.5 AND 1.0`
  - Works with all vector types (float32, int8, bit)
  - Compatible with partition keys, metadata, and auxiliary columns
  - Comprehensive test coverage (15 tests)
  - Fixed variable shadowing issues from original PR
  - Documented precision handling and pagination caveats

- **Optimize command for space reclamation** ([#210](https://github.com/asg017/sqlite-vec/pull/210))
  - New special command: `INSERT INTO vec_table(vec_table) VALUES('optimize')`
  - Reclaims disk space after DELETE operations by compacting shadow tables
  - Rebuilds vector chunks with only valid rows
  - Updates rowid mappings to maintain data integrity

- **Cosine distance support for binary vectors** ([#212](https://github.com/asg017/sqlite-vec/pull/212))
  - Added `distance_cosine_bit()` function for binary quantized vectors
  - Enables cosine similarity metric on bit-packed vectors
  - Useful for memory-efficient semantic search

- **ALTER TABLE RENAME support** ([#203](https://github.com/asg017/sqlite-vec/pull/203))
  - Implement `vec0Rename()` callback for virtual table module
  - Allows renaming vec0 tables with standard SQL: `ALTER TABLE old_name RENAME TO new_name`
  - Properly renames all shadow tables and internal metadata

- **Language bindings and package configurations for GitHub installation**
  - Go CGO bindings (`bindings/go/cgo/`) with `Auto()` and serialization helpers
  - Python package configuration (`pyproject.toml`, `setup.py`) for `pip install git+...`
  - Node.js package configuration (`package.json`) for `npm install vlasky/sqlite-vec`
  - Ruby gem configuration (`sqlite-vec.gemspec`) for `gem install` from git
  - Rust crate configuration (`Cargo.toml`, `src/lib.rs`) for `cargo add --git`
  - All packages support installing from main branch or specific version tags
  - Documentation in README with installation table for all languages

- **Python loadable extension support documentation**
  - Added note about Python requiring `--enable-loadable-sqlite-extensions` build flag
  - Recommended using `uv` for virtual environments (uses system Python with extension support)
  - Documented workarounds for pyenv and custom Python builds

### Fixed

- **Memory leak on DELETE operations** ([#243](https://github.com/asg017/sqlite-vec/pull/243))
  - Added `vec0Update_Delete_ClearRowid()` to clear deleted rowids
  - Added `vec0Update_Delete_ClearVectors()` to clear deleted vector data
  - Prevents memory accumulation from deleted rows
  - Vectors and rowids now properly zeroed out on deletion

- **CI/CD build infrastructure** ([#228](https://github.com/asg017/sqlite-vec/pull/228))
  - Upgraded deprecated ubuntu-20.04 runners to ubuntu-latest
  - Added native ARM64 builds using ubuntu-24.04-arm
  - Removed cross-compilation dependencies (gcc-aarch64-linux-gnu)
  - Fixed macOS link flags for undefined symbols

## Original Version

This fork is based on [`asg017/sqlite-vec`](https://github.com/asg017/sqlite-vec) v0.1.7-alpha.2.
All features and functionality from the original repository are preserved.
See the [original documentation](https://alexgarcia.xyz/sqlite-vec/) for complete usage information.
