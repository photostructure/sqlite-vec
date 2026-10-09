# `sqlite-vec` Architecture

Internal documentation for how `sqlite-vec` works under-the-hood. Not meant for
users of the `sqlite-vec` project, consult
[the official `sqlite-vec` documentation](https://alexgarcia.xyz/sqlite-vec) for
how-to-guides. Rather, this is for people interested in how `sqlite-vec` works
and some guidelines to any future contributors.

Very much a WIP.

## `vec0`

### Shadow Tables

#### `xyz_chunks`

- `chunk_id INTEGER`
- `size INTEGER`
- `validity BLOB`
- `rowids BLOB`

#### `xyz_rowids`

- `rowid INTEGER`
- `id`
- `chunk_id INTEGER`
- `chunk_offset INTEGER`

#### `xyz_vector_chunksNN`

- `rowid INTEGER`
- `vector BLOB`

#### `xyz_auxiliary`

- `rowid INTEGER`
- `valueNN [type]`

#### `xyz_metadatachunksNN`

- `rowid INTEGER`
- `data BLOB`

#### `xyz_metadatatextNN`

- `rowid INTEGER`
- `data TEXT`

#### Identifying shadow tables

The supported way to tell which tables belong to a `vec0` table is by name. A
`vec0` table `xyz` owns these tables and no others (`NN` is two digits):

- `xyz_info`, `xyz_chunks`, `xyz_rowids`: always
- `xyz_vector_chunksNN`: one per vector column
- `xyz_auxiliary`: only if there are auxiliary columns
- `xyz_metadatachunksNN`: one per metadata column
- `xyz_metadatatextNN`: one per text metadata column

This query lists them for every `vec0` table in a database. It reads only
`sqlite_master`, so it works on every SQLite version and on a connection that
has not loaded `sqlite-vec`:

```sql
select v.name as vec0_table, s.name as backing_table
from sqlite_master as v
join sqlite_master as s
  on s.type = 'table'
 and substr(s.name, 1, length(v.name) + 1) = v.name || '_'
 and (substr(s.name, length(v.name) + 2) in ('rowids', 'chunks', 'info', 'auxiliary')
   or substr(s.name, length(v.name) + 2) glob 'vector_chunks[0-9][0-9]'
   or substr(s.name, length(v.name) + 2) glob 'metadatachunks[0-9][0-9]'
   or substr(s.name, length(v.name) + 2) glob 'metadatatext[0-9][0-9]')
where v.type = 'table' and v.rootpage = 0
  and v.sql like 'create virtual table%using vec0%'
order by 1, 2;
```

`type = 'shadow'` in `PRAGMA table_list` is best-effort and should not be
relied on:

- A connection that has not loaded `sqlite-vec` reports every backing table as
  `table`.
- Up to SQLite 3.53, so does a connection that parsed the schema before loading
  the extension.
- Before SQLite 3.37 there is no `PRAGMA table_list` and no prefix marking (see
  below), so the vector chunk tables are never shadow tables.
- SQLite finds the virtual table that owns a newly created or newly parsed
  table by splitting its name at the **last** underscore
  ([documented](https://www.sqlite.org/vtab.html#the_xshadowname_method)). For
  `xyz_vector_chunks00` it looks for a virtual table called `xyz_vector`, so
  `xShadowName` is never asked about it on that path.
- `xShadowName` does report `vector_chunksNN`, and SQLite also marks shadow
  tables by name prefix when it parses the virtual table's own schema entry.
  That only sees tables parsed earlier, which in practice means after a
  `VACUUM` (it rewrites `sqlite_master` with virtual tables last). A `vec0`
  table created after that `VACUUM` is not covered until the next one.
- SQLite 3.54 additionally marks by prefix after every `xConnect`. There the
  vector chunk tables become `shadow` once the `vec0` table has been used in
  the connection, except in the connection that created it. `PRAGMA
  table_list` connects every virtual table first, so it always reports them as
  `shadow`, but under `SQLITE_DBCONFIG_DEFENSIVE` a direct write to a chunk
  table is still accepted until the `vec0` table is first touched. This prefix
  matching is not part of the documented contract.

Rules that follow from this:

- A new backing table that has no upstream counterpart should use a suffix
  without underscores (`metadatachunksNN`, not `metadata_chunksNN`), so that it
  follows the documented rule. A table ported from upstream keeps upstream's
  name, to stay file-compatible, and is added to `vec0ShadowName`.
- `xyz_vector_chunksNN` is not renamed, because that would make databases
  unreadable by upstream `sqlite-vec` and by earlier releases of this fork.
- Do not rename a backing table from inside `xConnect`. In
  [vlasky/sqlite-vec](https://github.com/vlasky/sqlite-vec/commit/44bded9)'s
  test of a minimal module under AddressSanitizer on SQLite 3.45.3, an
  `ALTER TABLE ... RENAME` issued there was a heap-use-after-free in the
  statement that triggered the connect.

### idxStr

The `vec0` idxStr is a string composed of a single "header" character and 0 or
more "blocks" of 4 characters each.

The "header" character denotes the type of query plan, as determined by the
`enum vec0_query_plan` values. The current possible values are:

| Name                       | Value | Description                                                            |
| -------------------------- | ----- | ---------------------------------------------------------------------- |
| `VEC0_QUERY_PLAN_FULLSCAN` | `'1'` | Perform a full-scan on all rows                                        |
| `VEC0_QUERY_PLAN_POINT`    | `'2'` | Perform a single-lookup point query for the provided rowid             |
| `VEC0_QUERY_PLAN_KNN`      | `'3'` | Perform a KNN-style query on the provided query vector and parameters. |

Each 4-character "block" is associated with a corresponding value in `argv[]`.
For example, the 1st block at byte offset `1-4` (inclusive) is the 1st block and
is associated with `argv[0]`. The 2nd block at byte offset `5-8` (inclusive) is
associated with `argv[1]` and so on. Each block describes what kind of value or
filter the given `argv[i]` value is.

#### `VEC0_IDXSTR_KIND_KNN_MATCH` (`'{'`)

`argv[i]` is the query vector of the KNN query.

The remaining 3 characters of the block are `_` fillers.

#### `VEC0_IDXSTR_KIND_KNN_K` (`'}'`)

`argv[i]` is the limit/k value of the KNN query.

The remaining 3 characters of the block are `_` fillers.

#### `VEC0_IDXSTR_KIND_KNN_ROWID_IN` (`'['`)

`argv[i]` is the optional `rowid in (...)` value, and must be handled with
[`sqlite3_vtab_in_first()` / `sqlite3_vtab_in_next()`](https://www.sqlite.org/c3ref/vtab_in_first.html).

The remaining 3 characters of the block are `_` fillers.

#### `VEC0_IDXSTR_KIND_KNN_ROWID_EQ` (`'='`)

`argv[i]` is the optional `rowid = ?` value, or `id = ?` for a table with a
primary key column. SQLite also passes a one-value `rowid in (?)` this way.
`vec0` restricts the KNN search to the row it names, as it does for each value
of a `'['` list, so a query has at most one of the two blocks: with both
constraints, `vec0` takes the `=` value and leaves the list to SQLite. It
leaves a text primary key constraint whose collation is not `BINARY` to SQLite.
For a text primary key, a value that is not text names no row, in this block
or in a `'['` list.

The remaining 3 characters of the block are `_` fillers.

#### `VEC0_IDXSTR_KIND_KNN_PARTITON_CONSTRAINT` (`']'`)

`argv[i]` is a "constraint" on a specific partition key.

The second character of the block denotes which partition key to filter on,
using `A` to denote the first partition key column, `B` for the second, etc. It
is encoded with `'A' + partition_idx` and can be decoded with `c - 'A'`.

The third character of the block denotes which operator is used in the
constraint. It will be one of the values of `enum vec0_partition_operator`.
`vec0_chunks_iter()` turns each block into a condition on the `_chunks`
table's `partitionNN` column:

| Operator    | Value | Condition                 |
| ----------- | ----- | ------------------------- |
| `EQ`        | `'a'` | `partitionNN = ?`         |
| `GT`        | `'b'` | `partitionNN > ?`         |
| `LE`        | `'c'` | `partitionNN <= ?`        |
| `LT`        | `'d'` | `partitionNN < ?`         |
| `GE`        | `'e'` | `partitionNN >= ?`        |
| `NE`        | `'f'` | `partitionNN != ?`        |
| `IN`        | `'g'` | `partitionNN IN (?, ...)` |
| `LIKE`      | `'h'` | `partitionNN LIKE ?`      |
| `GLOB`      | `'i'` | `partitionNN GLOB ?`      |
| `IS`        | `'j'` | `partitionNN IS ?`        |
| `ISNOT`     | `'k'` | `partitionNN IS NOT ?`    |
| `ISNULL`    | `'l'` | `partitionNN IS NULL`     |
| `ISNOTNULL` | `'m'` | `partitionNN IS NOT NULL` |

`argv[i]` of an `IN` block is read with `sqlite3_vtab_in_first()` /
`sqlite3_vtab_in_next()`, and each of its values is bound to its own parameter
of the `_chunks` query, so the query fails to prepare when the distinct values
of its `IN` blocks and its other partition key values together number more
than `SQLITE_LIMIT_VARIABLE_NUMBER`. `ISNULL` and `ISNOTNULL` blocks bind nothing.

These conditions compare text with `BINARY` (`LIKE` and `GLOB` keep their own
case rules, and `LIKE` follows `PRAGMA case_sensitive_like`), and they see only
`argv[i]`'s value, not the affinity of the expression that produced it, so
`p IS CAST(5 AS INTEGER)` does not match a text `'5'`. `EQ`, `NE`, and the
range operators are encoded whatever collation the query names. An `IN` or
`IS` constraint is encoded as such only when `sqlite3_vtab_collation()`
reports `BINARY`: an `IN` with another collation is encoded as `EQ`, which
SQLite runs once per value that is distinct under that collation, as before
`vec0` encoded `IN`, and an `IS` with
another collation is left to SQLite. SQLite reports `BINARY` for `IS NOT`
whatever collation the query names, so `xBestIndex` leaves `omit` unset for it
and SQLite re-checks each row.

The fourth character of the block is a `_` filler.

#### `VEC0_IDXSTR_KIND_POINT_ID` (`'!'`)

`argv[i]` is the value of the rowid or id to match against for the point query.
For a text primary key, `xBestIndex` leaves `omit` unset and SQLite re-checks
the row: `vec0` looks the id up in `_rowids.id`, which is declared `TEXT`, so
the integer 5 finds `'5'`, and SQLite drops that row unless the other side of
the `=` has numeric affinity.

The remaining 3 characters of the block are `_` fillers.

#### `VEC0_IDXSTR_KIND_METADATA_CONSTRAINT` (`'&'`)

`argv[i]` is the value of the `WHERE` constraint for a metadata column in a KNN
query.

The second character of the block denotes which metadata column the constraint
belongs to, using `A` to denote the first metadata column, `B` for the
second, etc. It is encoded with `'A' + metadata_idx` and can be decoded with
`c - 'A'`.

The third character of the block is the constraint operator. It will be one of
`enum vec0_metadata_operator`, as only a subset of operators are supported on
metadata column KNN filters.

The fourth character of the block is the collation a text constraint compares
with, one of `enum vec0_metadata_collation`:

| Collation | Value |
| --------- | ----- |
| `BINARY`  | `'_'` |
| `NOCASE`  | `'n'` |
| `RTRIM`   | `'r'` |

Only `=`, `IS`, `<`, `<=`, `>`, `>=`, and `IN` constraints on a text column
carry the collation that `sqlite3_vtab_collation()` reports for them; `xBestIndex`
rejects any other collation on them. SQLite also calls `xBestIndex` with each
branch of an `OR` offered as a constraint, which `vec0` cannot tell from a
top-level one, so the error fires for such a constraint inside an `OR` too,
although SQLite may evaluate that `OR` itself.

Every other constraint carries `'_'`: SQLite compares an INTEGER or REAL without
a collation, `LIKE` and `GLOB` have their own case rules, and SQLite reports
`BINARY` for a text `!=` or `IS NOT` whatever collation the query names. `vec0`
compares those two bytewise and leaves `omit` unset, so SQLite re-checks each
row with the query's collation.

#### `VEC0_IDXSTR_KIND_KNN_DISTANCE_CONSTRAINT` (`'*'`)

`argv[i]` is a constraint on the `distance` column in a KNN query.

This enables filtering KNN results by distance thresholds, useful for:
- Cursor-based pagination: `WHERE embedding MATCH ? AND k = 10 AND distance > 0.21`
- Range queries: `WHERE embedding MATCH ? AND k = 100 AND distance BETWEEN 0.5 AND 1.0`

The second character of the block denotes the constraint operator. It will be one of
the values of `enum vec0_distance_constraint_operator`:

| Operator | Value | Description              | SQL Example          |
| -------- | ----- | ------------------------ | -------------------- |
| `GT`     | `'a'` | Greater than             | `distance > 0.5`     |
| `GE`     | `'b'` | Greater than or equal to | `distance >= 0.5`    |
| `LT`     | `'c'` | Less than                | `distance < 1.0`     |
| `LE`     | `'d'` | Less than or equal to    | `distance <= 1.0`    |

The third and fourth characters of the block are `_` fillers.

**Note on precision:** Distance values are cast from f64 to f32 for comparison, which may
result in precision loss for very small distance differences.

**Note on pagination:** When multiple vectors have identical distances, pagination using
`distance > X` may skip some results. For stable pagination, combine distance with rowid:
`WHERE (distance > 0.5) OR (distance = 0.5 AND rowid > 123)`

#### `VEC0_IDXSTR_KIND_KNN_MMR_LAMBDA` (`'#'`)

`argv[i]` is the value of the optional `mmr_lambda = ?` constraint of a KNN
query. Unless `k` is 0, `vec0Filter_knn` applies numeric affinity to it with
`sqlite3_value_numeric_type()`, as SQLite does to a `LIMIT` value, and fails
the query unless it is then an INTEGER or REAL: `'0.5'` reads as 0.5, and NULL,
a blob, or text such as `'abc'` fails. It converts the number to `f32` and
fails the query if it is below 0.0 or above 1.0. For a value below 1.0, it
fetches the `k * 5` nearest rows (at most 4096) and, if it finds more than
`k`, selects `k` of them by MMR.

The remaining 3 characters of the block are `_` fillers.
