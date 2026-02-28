# Changelog

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
