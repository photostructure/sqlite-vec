# Changelog (@mceachen/sqlite-vec fork)

All notable changes specific to this community fork's releases will be documented here.
For upstream changes, see [CHANGELOG.md](CHANGELOG.md).

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
