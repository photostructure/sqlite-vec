# Changelog

## [Unreleased]

### Added

- `INSERT OR REPLACE` on a `vec0` table now replaces an existing row with the same rowid or text primary key, including its vectors, metadata, and auxiliary values. Previously it failed with a UNIQUE constraint error. Ported from [asg017@b95c05b](https://github.com/asg017/sqlite-vec/commit/b95c05b) via [vlasky@03b429d](https://github.com/vlasky/sqlite-vec/commit/03b429d) ([asg017#127](https://github.com/asg017/sqlite-vec/issues/127)).

### Changed

- `vec_normalize()` of an all-zero vector now returns NULL instead of a vector of NaNs, as [vlasky@571ff3a](https://github.com/vlasky/sqlite-vec/commit/571ff3a) does. Cosine distance involving a zero vector still returns 1.0.
- Hamming distance between `bit` vectors of 128 or more dimensions uses NEON popcount instructions in NEON builds, which include the published darwin-arm64 binary. Ported from [vlasky@6ad1350](https://github.com/vlasky/sqlite-vec/commit/6ad1350); its AVX2 variant is not included, because building with `-mavx2` would make the darwin-x64 binary require AVX2.
- `float32` vector input now rejects NaN and ±Inf elements with `invalid float32 vector: element N is NaN` (or `Inf`), ported from [asg017@c4c23bd](https://github.com/asg017/sqlite-vec/commit/c4c23bd). A NaN element makes every distance to that vector NaN, which breaks KNN ordering. This applies to blob and JSON input everywhere a `float32` vector is parsed: `vec0` inserts, updates, and KNN query vectors, and SQL functions such as `vec_distance_l2()` and `vec_to_json()`. JSON numbers that overflow `float32`, such as `1e39`, are rejected as Inf. Vectors already stored in a `vec0` table are not checked when a KNN query scans them, but passing one that contains NaN or Inf to a SQL function now fails.
- `vec0`'s `xShadowName` now reports the `xyz_vector_chunksNN` tables, which it omitted. SQLite matches a new table to its virtual table by the text before the last underscore, so it consults `xShadowName` for these tables only in some cases: up to SQLite 3.53, only after a `VACUUM`. In those cases `PRAGMA table_list` lists them as `shadow`, and under `SQLITE_DBCONFIG_DEFENSIVE` SQL statements can no longer write to or drop them directly, as was already true of the other backing tables. ARCHITECTURE.md now documents how to identify a `vec0` table's backing tables by name. Ported from [vlasky@44bded9](https://github.com/vlasky/sqlite-vec/commit/44bded9) and [vlasky@5a4dc73](https://github.com/vlasky/sqlite-vec/commit/5a4dc73) ([asg017#320](https://github.com/asg017/sqlite-vec/issues/320)).
- The hidden command column that runs `optimize` is now declared with the table's exact name. A table named after an SQL keyword, such as `"order"`, failed to create or, if created before v0.2.0-alpha, to open, with a syntax error, and a table named `"my vecs"` got a command column named `my`, so `INSERT INTO "my vecs"("my vecs") VALUES ('optimize')` failed.
- `CREATE VIRTUAL TABLE` of a `vec0` table with a column named like the table now fails with `vec0 constructor error: column name 'emb' conflicts with table name (reserved for command column)`, as in upstream [asg017@6e2c4c6](https://github.com/asg017/sqlite-vec/commit/6e2c4c6), instead of `could not declare virtual table, 'duplicate column name: emb'`. Tables named `distance`, `k`, `mmr_lambda`, or (without a primary key column) `rowid` get the same error.
- A KNN query's filters on metadata columns and `distance` now compare a value the way SQLite compares it with an untyped column, so for a bound parameter or a literal they keep the rows a plain scan with the same `WHERE` clause keeps. They used to convert the value to the column's type first: on an `integer` column, `n = 'abc'` matched `n = 0`, `n = '5'` and `n = 5.5` matched `5`, and `n = ?` bound to NULL matched `0`; on a `text` column, `t = 5` matched `'5'` and `t in (null)` matched `''`; and `distance >= ?` bound to NULL kept every row. Now NULL matches nothing except under `IS NOT`, a number never equals text, an integer and a real compare exactly, and `in (...)` skips values that equal no row. Text sorts after every number, so on an `integer` column `n > '3'` now keeps no row and `n < '3'` keeps every row. A `distance` filter still rounds a number to `float` before comparing, as before. The rowid lookups, `rowid = ?` in a query without `match` and `rowid in (...)` with two or more values in a KNN query, used to read NULL, `'abc'`, or `x'00'` as rowid 0 and `5.5` as rowid 5; those values now match no row, and the lookups still apply numeric affinity, so `'5'` finds rowid 5. A filter sees only the value, not the expression that produced it, so one case now differs from a plain scan instead: when the other side has numeric affinity, as in `t = cast(5 as integer)` or `t in (select x from other)` with `x` declared `integer`, SQLite converts a `text` column's `'5'` to 5 and matches it, but a KNN filter does not. Text filters still ignore `COLLATE`, as before. Ported from the unmerged [vlasky#12](https://github.com/vlasky/sqlite-vec/pull/12) ([asg017#329](https://github.com/asg017/sqlite-vec/pull/329)).
- `vec0` now declares its `rowid` column, or an integer primary key column such as `id integer primary key`, as `INTEGER`, so SQLite converts a value it compares with that column to a number, as it does for an ordinary table's rowid. On a full scan, `rowid > '3'` used to match no row, and in a KNN query so did `rowid = '5'` and `rowid in ('5')`, while `rowid = '5'` without `match` and `rowid in ('5', 6)` in a KNN query found rowid 5; these now match the rows an ordinary table would, and so do the same filters on an integer primary key. `PRAGMA table_info` now reports that column's type as `INTEGER`.
- A KNN query's `in (...)` filter on an `integer` metadata column now looks up each row's value in the list by binary search instead of scanning the list. On a 200,000-row in-memory table with `float[8]` vectors (AMD Ryzen 9 5950X, gcc 15 and clang 21 builds), a 2,048-value list took 5.2–5.9 ms instead of 109 ms, a 128-value list 2.0–2.4 ms instead of 9.1–9.7 ms, and an 8-value list 1.1 ms instead of 1.3–1.8 ms. Ported from the unmerged [vlasky#10](https://github.com/vlasky/sqlite-vec/pull/10) ([asg017#328](https://github.com/asg017/sqlite-vec/pull/328)), with a branchless search in place of its `bsearch()`, which made short lists slower than the old scan.
- MMR reranking (`mmr_lambda` below 1.0) now keeps each candidate's highest similarity to the results selected so far and raises it once per selection, instead of comparing every candidate with every selected result at each step. It selects the same results. On a 20,000-row in-memory table with `float[384]` cosine vectors (AMD Ryzen 9 5950X), `k = 200` took 87 ms instead of 5.3 s and `k = 50` 17 ms instead of 95 ms; `k = 10` stayed near 9.6 ms. Ported from the unmerged [vlasky#11](https://github.com/vlasky/sqlite-vec/pull/11), without its similarity update after the last selection, which nothing reads.
- Inserting or updating a `boolean` metadata column with an integer outside 32 bits whose low 32 bits are 0 or 1, such as 4294967296, now fails with `Expected 0 or 1 for BOOLEAN metadata column`. It used to store `false` or `true`.
- Inserting a non-integer rowid into a `vec0` table now fails with `Only integers are allowed for primary key values`; the message used to say "are allows".

### Removed

- Removed the Python, Ruby, Rust, and Lua bindings, their packaging (`setup.py`, `pyproject.toml`, `MANIFEST.in`, `sqlite-vec.gemspec`, `extconf.rb`, `lib/sqlite_vec.rb`, `Cargo.toml`, `build.rs`, `src/lib.rs`, `bindings/`), and their examples. This fork publishes only the npm package. Installing those bindings from `main` (for example `pip install git+https://github.com/photostructure/sqlite-vec`, or the `gem` and `cargo --git` equivalents) no longer works; release tags up to v2.0.2 still include them. Use upstream [`asg017/sqlite-vec`](https://github.com/asg017/sqlite-vec) or [`vlasky/sqlite-vec`](https://github.com/vlasky/sqlite-vec) instead.
- Removed the `test.yaml` jobs that built iOS, wasm, pyodide, cosmopolitan, and 32-bit ARM artifacts that no release ships, and the Rust unit-test harness under `tests/`, which nothing ran.

### Fixed

- Fixed `vec0` tables with a column named like the table, such as `CREATE VIRTUAL TABLE emb USING vec0(emb float[4])`, which releases before v0.2.0-alpha created: they failed to open with `duplicate column name: emb`, because the hidden command column that runs `optimize`, added in v0.2.0-alpha, has the table's name. Tables named `distance`, `k`, or (without a primary key column) `rowid` failed the same way, and since v1.1.0 so did tables named `mmr_lambda`. These tables now open without the command column, so `optimize` is unavailable on them until they are renamed with `ALTER TABLE ... RENAME`. Upstream's tests for this case are ported from [asg017@6e2c4c6](https://github.com/asg017/sqlite-vec/commit/6e2c4c6).
- Fixed a memory leak in `ALTER TABLE ... RENAME` of a `vec0` table: the new name of each `_vector_chunksNN` shadow table was never freed.
- Fixed KNN queries on `vec0` tables with a text primary key whose `id IN (...)` list included an id not in the table: the query returned no rows at all, and errors while reading the `IN` list were dropped. A block-scoped `int rc` hid the outer result code; the same declaration is in both upstreams. Unknown ids now match no row, and other errors fail the query.
- Fixed cosine distance between `float32` vectors whose elements are very small or very large. Squared magnitudes were summed in `float`, so elements below about 3e-23 made a magnitude of 0, which this fork reports as distance 1.0, and elements above about 2e19 made it Inf, so `vec_distance_cosine()`, cosine KNN queries, and MMR reranking returned wrong distances for those vectors. `vec_normalize()` had the same problem. Both now sum in `double`, so ordinary cosine distances can differ from 2.0.2 in the last few digits. Ported from [vlasky@d75c245](https://github.com/vlasky/sqlite-vec/commit/d75c245) ([asg017#324](https://github.com/asg017/sqlite-vec/issues/324)).
- Fixed inserts into `vec0` tables created before v0.2.0-alpha after `optimize` had removed a chunk. Those tables declare their `_vector_chunksNN` and `_metadatachunksNN` shadow tables with `rowid PRIMARY KEY` instead of `rowid INTEGER PRIMARY KEY`, so a new chunk's SQLite rowid could differ from its chunk id, and the insert failed with `Error opening vector blob`; KNN and point queries on the table then failed too. New chunks now set both ids. Ported from [vlasky@3a64182](https://github.com/vlasky/sqlite-vec/commit/3a64182).
- An `INSERT` into a `vec0` table with a value of the wrong type for a metadata or auxiliary column now fails before writing anything. It used to fail after writing the row's rowid, vector, and some column values, and a surrounding transaction could commit that partial row, because `vec0` writes its shadow tables through separate statements that a failed `INSERT` does not roll back.
- Fixed memory and handle leaks that [vlasky@5ae4fed](https://github.com/vlasky/sqlite-vec/commit/5ae4fed) fixed in its fork and this fork still had: every `UPDATE` of an auxiliary column leaked its SQL string; a `vec0` constructor that failed after parsing some columns leaked their names; a long-text metadata write that failed left its blob handle open, so `sqlite3_close()` returned `SQLITE_BUSY`; a KNN query leaked its top-k buffers when MMR reranking failed; and text-metadata filtering leaked a rowid buffer when its blob read failed.
- Metadata writes now report a failed blob write instead of returning success.
- Fixed a signed integer overflow when parsing JSON numbers with very long exponents, such as `[1e99999999999999999999]`; the exponent is now clamped and the input is rejected as out of range. Also fixed six vec0 constructor scanner checks that used `&&` where `||` was meant, so a column definition that ended early could be checked against the previous token. Ported from [vlasky@13282f4](https://github.com/vlasky/sqlite-vec/commit/13282f4).
- `vec_npy_each` now rejects a numpy header that lacks any of `descr`, `fortran_order`, or `shape`. Such a header left the row count uninitialized, and a 14-byte input could iterate without end. It also no longer reads past a header that ends partway through `False`. Ported from [vlasky@e746572](https://github.com/vlasky/sqlite-vec/commit/e746572).
- `vec_npy_each` no longer reads past a numpy header that ends in a `shape` number, such as `{'shape':(55555`. It parsed shape numbers with `strtol()`, which reads until a non-digit, but the header is not NUL-terminated, so `strtol()` could read past the end of a blob passed directly, or past the header buffer read from a `vec_npy_file()`. Shape numbers are now parsed from the header bytes only. vlasky/sqlite-vec has the same code.
- `vec_npy_file()` no longer writes past a heap buffer when a file's rows are more than 1048576 floats wide. It allocated a 1024-row read buffer with `sqlite3_malloc()`, which takes an `int`, so a buffer of 4 GiB or more was truncated, to 4096 bytes for rows of 1048577 floats, and `fread()` could write whole rows past it. Depending on the row width, files with rows of 524288 floats or more overflowed the buffer, failed with an out-of-memory error, or read correctly. The buffer is now allocated at its full size and holds no more rows than the file has, so a file with fewer than 1024 rows reads whenever its data fits in one SQLite allocation (just under 2 GiB by default). vlasky/sqlite-vec has the same code.
- `vec_npy_each` now rejects a numpy header whose `shape` describes more data than a `size_t` can count, with `numpy array error: shape is too large`. It computed the expected data size with wrapping arithmetic and truncated it to 32 bits, so shapes such as `(2, 1073741825)` with 8 bytes of data passed the size check, and reading the second row crashed. Size mismatches now report the full expected size, and `vec_npy_file()` reads files with more than 2 GiB of data, which failed with `numpy array file header length is invalid`. vlasky/sqlite-vec has the same code.
- Fixed three cases of undefined behavior that upstream's fuzzer found ([asg017@cdbc347](https://github.com/asg017/sqlite-vec/commit/cdbc347), [@2f4c2e4](https://github.com/asg017/sqlite-vec/commit/2f4c2e4), [@1b53b94](https://github.com/asg017/sqlite-vec/commit/1b53b94), as ported in [vlasky@899e98c](https://github.com/vlasky/sqlite-vec/commit/899e98c)). `float32` vectors passed as blobs were read in place as `float` arrays, which is a misaligned load when a caller binds a blob with `SQLITE_STATIC` at an unaligned address; they are now copied. Hamming distance now loads 64-bit words with `memcpy`, as upstream does, although `bit` vectors reach it only through copies that SQLite allocates aligned. `vec_quantize_int8()` converted values outside [-1, 1] to `int8` without clamping, so on x86-64 `2.0` became `-2` instead of `127`; values now clamp to [-128, 127]. The numpy header parser in `vec_npy_each` read one byte past the header when it ended inside a quoted string.
- Fixed `UPDATE` and `DELETE` with `WHERE rowid = ?` on a `vec0` table: bound to NULL, `'abc'`, or `x'00'`, they changed or deleted rowid 0, and bound to a real with a fraction, such as 5.5, they changed or deleted the row with its integer part. They now change no row. Fixed by the [vlasky#12](https://github.com/vlasky/sqlite-vec/pull/12) port above.
- Fixed a crash in KNN queries that compared a `text` metadata column with NULL using `<`, `<=`, `>`, or `>=`, such as `t > ?` bound to NULL, when a row's value was longer than 12 bytes. Fixed by the [vlasky#12](https://github.com/vlasky/sqlite-vec/pull/12) port above, which gives such a filter its result without reading the column.
- Fixed `vec_npy_file()` silently dropping or corrupting vectors on Windows when `float32` payloads contain `0x1A` or CRLF bytes. NumPy files are now opened in binary mode.
- Fixed `vec_npy_file()` rejecting numpy files larger than 2 GiB on Windows. File positions now use 64-bit APIs instead of Windows' 32-bit `long`.

### Infrastructure

- Added eight libFuzzer targets from [vlasky@3768246](https://github.com/vlasky/sqlite-vec/commit/3768246) (ported from asg017/sqlite-vec's fuzzing suite) alongside the existing four, and `fuzz.yaml`, which runs all twelve under ASan and UBSan for 60 seconds each on every push to `main` and nightly. Unlike vlasky's workflow, it runs only on Linux and installs clang from Ubuntu's packages. `vec0-delete-completeness` now creates its table with `chunk_size=8`: the `chunk_size=4` it used upstream is rejected, so that target never got past `CREATE`. It also runs `optimize` before checking that the shadow tables are empty, because `DELETE` here leaves emptied chunks for `optimize`.
- `make test-unit` gains upstream's C unit tests for the vec0 constructor tokenizer, scanner, and vector column parser ([asg017@0659d88](https://github.com/asg017/sqlite-vec/commit/0659d88), [@79d5818](https://github.com/asg017/sqlite-vec/commit/79d5818), via [vlasky@325282a](https://github.com/vlasky/sqlite-vec/commit/325282a)), and `test.yaml` now runs it on Linux x86_64 ([vlasky@10226cb](https://github.com/vlasky/sqlite-vec/commit/10226cb)).
- `sqlite-vec.c` initializes the 6-byte numpy magic header from a byte list instead of a 7-byte string literal, which GCC 15 reported with `-Wunterminated-string-initialization` and which is an error in C++. Ported from [vlasky@6342fb4](https://github.com/vlasky/sqlite-vec/commit/6342fb4) ([asg017#321](https://github.com/asg017/sqlite-vec/issues/321)).
- Added backwards-compatibility tests against a database created by upstream v0.1.6 (`tests/fixtures/legacy-v0.1.6.db`), ported from [asg017@6e2c4c6](https://github.com/asg017/sqlite-vec/commit/6e2c4c6).
- `release.yaml` now installs the release-candidate tarball on all eight targets and runs `tests/test-npm-package.mjs` against it before tagging. The test checks that the ESM and CommonJS entry points resolve that target's binary, that `vec_version()` matches the package version, and that a `vec0` KNN query returns the nearest rows. Previously `scripts/package-npm.sh` checked only the tarball's name, version, and file list, and the linux-arm64, linux-x64-musl, linux-arm64-musl, and win32-arm64 binaries shipped without running on those platforms. `publish.yaml` still rebuilds the published binaries from the signed tag; this check runs the release-candidate build of that same commit.

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
