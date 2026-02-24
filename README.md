# `sqlite-vec`

[![npm version](https://img.shields.io/npm/v/@photostructure/sqlite-vec.svg)](https://www.npmjs.com/package/@photostructure/sqlite-vec)
[![Build & Test](https://github.com/photostructure/sqlite-vec/actions/workflows/test.yaml/badge.svg)](https://github.com/photostructure/sqlite-vec/actions/workflows/test.yaml)
[![Memory Tests](https://github.com/photostructure/sqlite-vec/actions/workflows/memory-tests.yaml/badge.svg)](https://github.com/photostructure/sqlite-vec/actions/workflows/memory-tests.yaml)

> [!NOTE]
> **PhotoStructure's Production Fork:** This is [PhotoStructure](https://photostructure.com)'s actively maintained fork of [`asg017/sqlite-vec`](https://github.com/asg017/sqlite-vec), optimized for production use with additional features, comprehensive testing, and ongoing maintenance funded by PhotoStructure Inc.
>
> **Credits:** [Alex Garcia](https://github.com/asg017) (original implementation), [Vlad Lasky](https://github.com/vlasky) (community fork with 15+ merged upstream PRs), PhotoStructure Inc. (ongoing maintenance and improvements).
>
> **Why this fork exists:**
>
> - PhotoStructure depends on sqlite-vec for production vector search in our photo management platform
> - We've added production-critical features, security hardening, and comprehensive testing
> - We're committed to maintaining this for as long as PhotoStructure exists
> - All improvements remain open source (MIT/Apache-2.0) for the community
>
> **Fork improvements:**
>
> - **Testing:** AddressSanitizer/Valgrind/UBSan integration, 30+ error path tests, memory leak fixes
> - **Security:** Safe integer parsing, vendor checksum validation, pinned CI actions, OIDC releases
> - **Node.js:** Alpine/musl + Windows ARM64 prebuilds, bundled binaries (no post-install scripts)
> - **Features:** Distance constraints, OPTIMIZE command, ALTER TABLE RENAME, GLOB/LIKE operators
> - **Documentation:** Comprehensive error path coverage, KNN filtering behavior, production deployment guides
>
> Maintained by PhotoStructure Inc. Contributions welcome. See [CHANGELOG.md](CHANGELOG.md) for detailed changes.

An extremely small, "fast enough" vector search SQLite extension that runs
anywhere! A successor to [`sqlite-vss`](https://github.com/asg017/sqlite-vss)

- Store and query float, int8, and binary vectors in `vec0` virtual tables
- Written in pure C, no dependencies, runs anywhere SQLite runs
  (Linux/MacOS/Windows, in the browser with WASM, Raspberry Pis, etc.)
- Store non-vector data in metadata, auxiliary, or partition key columns

<p align="center">
  <a href="https://hacks.mozilla.org/2024/06/sponsoring-sqlite-vec-to-enable-more-powerful-local-ai-applications/">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./.github/logos/mozilla.dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="./.github/logos/mozilla.svg">
    <img alt="Mozilla Builders logo" width=400>
  </picture>
  </a>
</p>

<p align="center">
<i>
<code>sqlite-vec</code> is a
<a href="https://hacks.mozilla.org/2024/06/sponsoring-sqlite-vec-to-enable-more-powerful-local-ai-applications/">Mozilla Builders project</a>,
with additional sponsorship from
<a href="https://fly.io/"><img width=14px src="./.github/logos/flyio.small.ico"/> Fly.io </a>,
<a href="https://tur.so/sqlite-vec"><img width=14px src="./.github/logos/turso.small.ico"/> Turso</a>,
<a href="https://sqlitecloud.io/"><img width=14px src="./.github/logos/sqlitecloud.small.svg"/> SQLite Cloud</a>, and
<a href="https://shinkai.com/"><img width=14px src="./.github/logos/shinkai.small.svg"/> Shinkai</a>.
See <a href="#sponsors">the Sponsors section</a> for more details.
</i>
</p>

## Installing

### Node.js

Prebuilt binaries for all major platforms are published to npm:

```bash
npm install @photostructure/sqlite-vec
```

**Supported platforms:** Linux (x64, ARM64, musl), macOS (x64, ARM64), Windows (x64, ARM64)

### Other Languages

For Python, Ruby, Rust, Go, and other language bindings, see the original [`asg017/sqlite-vec`](https://github.com/asg017/sqlite-vec) or [Vlad Lasky's fork](https://github.com/vlasky/sqlite-vec). This fork only publishes the Node.js package.

## Electron

The native extension is automatically resolved from `app.asar.unpacked` when running inside a packaged Electron app. You need to configure your build tool to unpack the extension binaries:

**electron-builder:**

```json
{
  "asarUnpack": ["node_modules/@mceachen/sqlite-vec/**/*.{so,dylib,dll}"]
}
```

**electron-forge:**

```js
packagerConfig: {
  asar: {
    unpack: "*.{so,dylib,dll}";
  }
}
```

## What's New

See [CHANGELOG.md](CHANGELOG.md) for a complete list of improvements, bug fixes, and merged upstream PRs.

## Basic Usage

**Vector types:** `sqlite-vec` supports three vector types with different trade-offs:

```sql
-- Float vectors (32-bit floating point, most common)
CREATE VIRTUAL TABLE vec_floats USING vec0(embedding float[384]);

-- Int8 vectors (8-bit integers, smaller memory footprint)
CREATE VIRTUAL TABLE vec_int8 USING vec0(embedding int8[384]);

-- Binary vectors (1 bit per dimension, maximum compression)
CREATE VIRTUAL TABLE vec_binary USING vec0(embedding bit[384]);
```

**Usage example:**

```sql
.load ./vec0

create virtual table vec_examples using vec0(
  sample_embedding float[8]
);

-- vectors can be provided as JSON or in a compact binary format
insert into vec_examples(rowid, sample_embedding)
  values
    (1, '[0.279, -0.95, -0.45, -0.554, 0.473, 0.353, 0.784, -0.826]'),
    (2, '[-0.156, -0.94, -0.563, 0.011, -0.947, -0.602, 0.3, 0.09]'),
    (3, '[-0.559, 0.179, 0.619, -0.987, 0.612, 0.396, -0.319, -0.689]'),
    (4, '[0.914, -0.327, -0.815, -0.807, 0.695, 0.207, 0.614, 0.459]'),
    (5, '[0.072, 0.946, -0.243, 0.104, 0.659, 0.237, 0.723, 0.155]'),
    (6, '[0.409, -0.908, -0.544, -0.421, -0.84, -0.534, -0.798, -0.444]'),
    (7, '[0.271, -0.27, -0.26, -0.581, -0.466, 0.873, 0.296, 0.218]'),
    (8, '[-0.658, 0.458, -0.673, -0.241, 0.979, 0.28, 0.114, 0.369]'),
    (9, '[0.686, 0.552, -0.542, -0.936, -0.369, -0.465, -0.578, 0.886]'),
    (10, '[0.753, -0.371, 0.311, -0.209, 0.829, -0.082, -0.47, -0.507]'),
    (11, '[0.123, -0.475, 0.169, 0.796, -0.201, -0.561, 0.995, 0.019]'),
    (12, '[-0.818, -0.906, -0.781, 0.255, 0.584, -0.156, -0.873, -0.237]'),
    (13, '[0.992, 0.058, 0.942, 0.722, -0.977, 0.441, 0.363, 0.074]'),
    (14, '[-0.466, 0.282, -0.777, -0.13, -0.093, 0.908, 0.752, -0.473]'),
    (15, '[0.001, -0.643, 0.825, 0.741, -0.403, 0.278, 0.218, -0.694]'),
    (16, '[0.525, 0.079, 0.557, 0.061, -0.999, -0.352, -0.961, 0.858]'),
    (17, '[0.757, 0.663, -0.385, -0.884, 0.756, 0.894, -0.829, -0.028]'),
    (18, '[-0.862, 0.521, 0.532, -0.743, -0.049, 0.1, -0.47, 0.745]'),
    (19, '[-0.154, -0.576, 0.079, 0.46, -0.598, -0.377, 0.99, 0.3]'),
    (20, '[-0.124, 0.035, -0.758, -0.551, -0.324, 0.177, -0.54, -0.56]');


-- Find 3 nearest neighbors using LIMIT
select
  rowid,
  distance
from vec_examples
where sample_embedding match '[0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]'
order by distance
limit 3;
/*
┌───────┬──────────────────┐
│ rowid │     distance     │
├───────┼──────────────────┤
│ 5     │ 1.16368770599365 │
│ 13    │ 1.75137972831726 │
│ 11    │ 1.83941268920898 │
└───────┴──────────────────┘
*/
```

**How vector search works:** The `MATCH` operator finds vectors similar to your query vector. In the example above, `sample_embedding MATCH '[0.5, ...]'` searches for vectors closest to `[0.5, ...]` and returns them ordered by distance (smallest = most similar).

Under the hood, sqlite-vec stores vectors in fixed-size chunks and scans each chunk to find the top-K nearest results, using SIMD instructions (AVX on x86_64, NEON on ARM) to accelerate distance calculations. Results from each chunk are merged using a two-pointer technique to produce the final sorted output. This brute-force approach trades theoretical optimality for simplicity and reliability — no complex index structures to maintain or tune.

**Note:** All vector similarity queries require `LIMIT` or `k = ?` (where k is the number of nearest neighbors to return). This prevents accidentally returning too many results on large datasets, since finding all vectors within a distance threshold requires calculating distance to every vector in the table.

## Advanced Usage

This fork adds several powerful features for production use:

### Distance Constraints for KNN Queries

Filter results by distance thresholds using `>`, `>=`, `<`, `<=` operators on the `distance` column:

```sql
-- KNN query with distance constraint
-- Requests k=10 neighbors, but only returns those with distance < 1.5
select rowid, distance
from vec_examples
where sample_embedding match '[0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]'
  and k = 10
  and distance < 1.5
order by distance;
/*
┌───────┬──────────────────┐
│ rowid │     distance     │
├───────┼──────────────────┤
│ 5     │ 1.16368770599365 │
└───────┴──────────────────┘
*/

-- KNN query with range constraint: find vectors in a specific distance range
select rowid, distance
from vec_examples
where sample_embedding match '[0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]'
  and k = 20
  and distance between 1.5 and 2.0
order by distance;
/*
┌───────┬──────────────────┐
│ rowid │     distance     │
├───────┼──────────────────┤
│ 13    │ 1.75137972831726 │
│ 11    │ 1.83941268920898 │
│ 7     │ 1.89339029788971 │
│ 8     │ 1.92658650875092 │
│ 10    │ 1.93983662128448 │
└───────┴──────────────────┘
*/
```

### Cursor-based Pagination

Instead of using `OFFSET` (which is slow for large datasets), you can use the last result's distance value as a 'cursor' to fetch the next page. This is more efficient because you're filtering directly rather than skipping rows.

```sql
-- First page: get initial results
select rowid, distance
from vec_examples
where sample_embedding match '[0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]'
  and k = 3
order by distance;
/*
┌───────┬──────────────────┐
│ rowid │     distance     │
├───────┼──────────────────┤
│ 5     │ 1.16368770599365 │
│ 13    │ 1.75137972831726 │
│ 11    │ 1.83941268920898 │
└───────┴──────────────────┘
*/

-- Next page: use last distance as cursor (distance > 1.83941268920898)
select rowid, distance
from vec_examples
where sample_embedding match '[0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]'
  and k = 3
  and distance > 1.83941268920898
order by distance;
/*
┌───────┬──────────────────┐
│ rowid │     distance     │
├───────┼──────────────────┤
│ 7     │ 1.89339029788971 │
│ 8     │ 1.92658650875092 │
│ 10    │ 1.93983662128448 │
└───────┴──────────────────┘
*/
```

### Space Reclamation with Optimize

`optimize` compacts vec shadow tables. To shrink the database file:

```sql
-- Before creating vec tables: enable autovacuum and apply it (recommended)
PRAGMA auto_vacuum = FULL;  -- or INCREMENTAL
VACUUM;                     -- activates the setting

-- Use WAL for better concurrency
PRAGMA journal_mode = WAL;
```

After deletes, reclaim space:

```sql
-- Compact shadow tables
INSERT INTO vec_examples(vec_examples) VALUES('optimize');

- Flush WAL
PRAGMA wal_checkpoint(TRUNCATE);

-- Reclaim freed pages (if using auto_vacuum=INCREMENTAL)
PRAGMA incremental_vacuum;

-- If you did NOT enable autovacuum, run VACUUM (after checkpoint) to shrink the file.
-- With autovacuum on, VACUUM is optional.
VACUUM;
```

`VACUUM` should not corrupt vec tables; a checkpoint first is recommended when
using WAL so the rewrite starts from a clean state.

## Sponsors

> [!NOTE]
> The sponsors listed below support the original [`asg017/sqlite-vec`](https://github.com/asg017/sqlite-vec) project by Alex Garcia, not this community fork.

Development of the original `sqlite-vec` is supported by multiple generous sponsors! Mozilla
is the main sponsor through the new Builders project.

<p align="center">
  <a href="https://hacks.mozilla.org/2024/06/sponsoring-sqlite-vec-to-enable-more-powerful-local-ai-applications/">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./.github/logos/mozilla.dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="./.github/logos/mozilla.svg">
    <img alt="Mozilla Builders logo" width=400>
  </picture>
  </a>
</p>

`sqlite-vec` is also sponsored by the following companies:

<a href="https://fly.io/">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./.github/logos/flyio.dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./.github/logos/flyio.svg">
  <img alt="Fly.io logo" src="./.github/logos/flyio.svg" width="48%">
</picture>
</a>

<a href="https://tur.so/sqlite-vec">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./.github/logos/turso.svg">
  <source media="(prefers-color-scheme: light)" srcset="./.github/logos/turso.svg">
  <img alt="Turso logo" src="./.github/logos/turso.svg" width="48%">
</picture>
</a>

<a href="https://sqlitecloud.io/">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./.github/logos/sqlitecloud.dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./.github/logos/sqlitecloud.svg">
  <img alt="SQLite Cloud logo" src="./.github/logos/flyio.svg" width="48%">
</picture>
</a>

<a href="https://shinkai.com">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./.github/logos/shinkai.dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./.github/logos/shinkai.svg">

  <img alt="Shinkai logo" src="./.github/logos/shinkai.svg" width="48%">
</picture>
</a>

As well as multiple individual supporters on
[Github sponsors](https://github.com/sponsors/asg017/)!

If your company interested in sponsoring `sqlite-vec` development, send me an
email to get more info: https://alexgarcia.xyz

## Documentation

For full API reference and guides, see the [upstream sqlite-vec documentation](https://alexgarcia.xyz/sqlite-vec/).

## See Also

- [**`sqlite-ecosystem`**](https://github.com/asg017/sqlite-ecosystem), Maybe
  more 3rd party SQLite extensions I've developed
- [**`sqlite-rembed`**](https://github.com/asg017/sqlite-rembed), Generate text
  embeddings from remote APIs like OpenAI/Nomic/Ollama, meant for testing and
  SQL scripts
- [**`sqlite-lembed`**](https://github.com/asg017/sqlite-lembed), Generate text
  embeddings locally from embedding models in the `.gguf` format
