# `vec0` Virtual Table

## Metadata in `vec0` Virtual Tables

There are three ways to store non-vector columns in `vec0` virtual tables:
metadata columns, partition keys, and auxiliary columns. Each option has its
own benefits and limitations.

```sql
create virtual table vec_chunks using vec0(
  chunk_id integer primary key,
  contents_embedding float[768],

  -- partition key column, denoted by 'partition key'
  user_id integer partition key,

  -- metadata column, appears as normal column definition
  label text,

  -- auxiliary column, denoted by '+'
  +contents text
);
```

A quick summary of each option:

| Column Type       | Description                                                             | Benefits                                             | Limitations                                                                                                               |
| ----------------- | ----------------------------------------------------------------------- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Metadata columns  | Stores boolean, integer, floating point, or text data alongside vectors | Can be included in the `WHERE` clause of a KNN query | Slower full scan, slightly inefficient with long strings (`> 12` characters)                                              |
| Auxiliary columns | Stores any kind of data in a separate internal table                    | Eliminates need for an external `JOIN`               | Cannot appear in the `WHERE` clause of a KNN query                                                                        |
| Partition Key     | Internally shards vector index on a given key                           | Makes selective queries much faster                  | Can cause oversharding and slow KNN if not used carefully. Should have hundreds of vectors per unique partition key value |

### Metadata Columns {#metadata}

Metadata columns are extra "regular" columns that you can include in a `vec0`
table definition. These columns will be indexed along with declared vector
columns, and allow you to include extra `WHERE` constraints during KNN queries.

```sql
create virtual table vec_movies using vec0(
  movie_id integer primary key,
  synopsis_embedding float[1024],
  genre text,
  num_reviews int,
  mean_rating float,
  contains_violence boolean
);
```

In the `vec0` constructor, the `genre`, `num_reviews`, `mean_rating`, and
`contains_violence` columns are metadata columns, with their specified types.

A sample KNN query on this table could look like:

```sql
select *
from vec_movies
where synopsis_embedding match '[...]'
  and k = 5
  and genre = 'scifi'
  and num_reviews between 100 and 500
  and mean_rating > 3.5
  and contains_violence = false;
```

The first two conditions in the `WHERE` clause (`synopsis_embedding match` and
`k = 5`) denote that the query is a KNN query. The other conditions are metadata
constraints that `sqlite-vec` will recognize and apply during the KNN
calculation. In other words, for the above query, a maximum of 5 rows would be
returned, all of which would match all the `WHERE` constraints for their
metadata column values.

#### Metadata Column Declaration

Metadata columns are declared in the `vec0` constructor just like regular
column definitions, with the column name first then the column type.

Only the following column types are supported in metadata columns. All these
columns are strictly typed.

- `TEXT` for text and strings
- `INTEGER` for 8-byte integers
- `FLOAT` for 8-byte floating-point numbers
- `BOOLEAN` for 1-bit `0` or `1`

Other column types may be supported in the future. Column type names are case
insensitive.

Additional column constraints like `UNIQUE` or `NOT NULL` are not supported.

A maximum of 16 metadata columns can be declared in a `vec0` virtual table.

#### Supported operations

In a KNN query, `vec0` applies the following conditions on metadata columns
while it searches, so the query returns up to `k` rows that satisfy all of
them:

| Operator                          | `text` | `integer` | `float` | `boolean` |
| --------------------------------- | ------ | --------- | ------- | --------- |
| `=`, `!=` or `<>`, `IS`, `IS NOT` | yes    | yes       | yes     | yes       |
| `IS NULL`, `IS NOT NULL`          | yes    | yes       | yes     | yes       |
| `<`, `<=`, `>`, `>=`, `BETWEEN`   | yes    | yes       | yes     | error     |
| `IN (...)`                        | yes    | yes       | error   | error     |
| `LIKE`, `GLOB`                    | yes    | error     | error   | error     |

An "error" cell means the query fails with an error, such as `LIKE operator is
only allowed on TEXT metadata columns.` An `IN` list with a single value works
on every column type, because SQLite passes it to `vec0` as `=`. `MATCH` on a
metadata column, and `REGEXP` when the application defines a `regexp()`
function, fail on every column type with `An illegal WHERE constraint was
provided on a vec0 metadata column in a KNN query.`

Metadata columns cannot store NULL, so `IS NULL` matches no row and
`IS NOT NULL` matches every row.

`LIKE` ignores the case of ASCII letters and `GLOB` does not, as in SQLite by
default.

On a `text` column, `=`, `IS`, `<`, `<=`, `>`, `>=`, and `IN` compare with the
`BINARY`, `NOCASE`, or `RTRIM` collation that the query names, as in
`genre = 'SciFi' collate nocase` or
`genre collate nocase in ('scifi', 'drama')`. Any other collation fails the
query with `Collation "x" is not supported on the "genre" metadata column in a
vec0 KNN query. Only BINARY, NOCASE, and RTRIM are supported.` A `!=` or
`IS NOT` condition with `COLLATE` on the value, as in
`genre != 'scifi' collate nocase`, can return fewer than `k` rows, because
`vec0` compares it bytewise and SQLite drops each returned row that equals the
value under that collation.

SQLite does not pass some conditions on metadata columns to `vec0`, and
instead applies them to the `k` rows that `vec0` returns. A KNN query with such
a condition can return fewer than `k` rows, and if it uses `LIMIT` instead of
`k = ?`, it fails with `A LIMIT or 'k = ?' constraint is required on vec0 knn
queries.` These conditions include:

- `NOT IN`, `NOT LIKE`, and `NOT GLOB`
- `LIKE ... ESCAPE`. For some patterns that begin with literal text, such as
  `'sci!_fi%' escape '!'`, SQLite instead passes `vec0` range conditions that
  select the same rows, so the query returns up to `k` matching rows and works
  with `LIMIT`.
- `!=` and `IS NOT` with `COLLATE` on the column, as in
  `genre collate nocase != 'scifi'`
- `IS TRUE`, `IS FALSE`, and a boolean column on its own, as in
  `and contains_violence` or `and not contains_violence`
- conditions joined with `OR`, except `=` conditions on one column, which
  SQLite turns into `IN`
- conditions on an expression, such as `lower(genre) = 'scifi'`

Outside a KNN query, SQLite applies every `WHERE` condition on a metadata
column itself, as for an ordinary table.

### Partition Key Columns {#partition-keys}

Partition key columns allow one to internally shard a vector index based on a
given key. In a KNN query, an `=`, `!=`, `<`, `<=`, `>`, `>=`, `BETWEEN`,
`IN (...)`, `IS`, `IS NOT`, `IS NULL`, `IS NOT NULL`, `LIKE`, or `GLOB`
condition on a partition key column restricts the search to the partitions
whose key satisfies it, except in the forms listed below. `LIKE` and `GLOB`
match as in SQLite, and `LIKE` follows `PRAGMA case_sensitive_like`.

When `vec0` uses an `=`, `!=`, `<`, `<=`, `>`, `>=`, or `BETWEEN` condition on
a `text` key, it compares bytewise and ignores any `COLLATE` clause, so
`name = 'alice' collate nocase` does not search a partition keyed `'Alice'`.
`vec0` uses an `IN` condition that names a collation other than `BINARY`, such
as `name collate nocase in ('alice', 'bob')`, only as one bytewise `=` per
value: it searches the `'alice'` and `'bob'` partitions one at a time and
returns up to `k` rows from each, and the query fails if it uses `LIMIT`
instead of `k = ?`. SQLite first keeps only one of the values that the
collation treats as equal, so `name collate nocase in ('alice', 'Alice')`
searches only one of those two partitions. An `IS NOT` condition with `COLLATE` on the value, as in
`name is not 'alice' collate nocase`, can return fewer than `k` rows, because
`vec0` compares it bytewise and SQLite drops each returned row that equals the
value under that collation.

`vec0` binds each distinct value of an `IN` list or `IN (select ...)` as its
own SQL parameter, so the query fails with
`Error preparing stmtChunk: too many SQL variables` when those distinct values
and the query's other partition key values number more than SQLite's host
parameter limit (32766 by default). An `IN` that names a collation other than
`BINARY` runs once per distinct value and has no such limit.

SQLite does not pass some conditions on partition key columns to `vec0`, or
`vec0` does not use them, and SQLite instead applies them to the `k` rows that
`vec0` returns. A KNN query with such a condition can return fewer than `k`
rows, and if it uses `LIMIT` instead of `k = ?`, it fails with
`A LIMIT or 'k = ?' constraint is required on vec0 knn queries.` These
conditions include:

- `IS` with a collation other than `BINARY`, as in
  `name is 'alice' collate nocase`
- `!=` and `IS NOT` with `COLLATE` on the column, as in
  `name collate nocase != 'alice'`
- `NOT IN`, `NOT LIKE`, and `NOT GLOB`
- `LIKE ... ESCAPE`. For some patterns that begin with literal text, such as
  `'a!_%' escape '!'`, SQLite also passes `vec0` range conditions, which `vec0`
  compares bytewise, so the query can return fewer than `k` rows even with
  `LIMIT`, without an error.
- `IS TRUE`, `IS FALSE`, `IS NOT TRUE`, and `IS NOT FALSE`
- conditions joined with `OR`, except `=` conditions on one column, which
  SQLite turns into `IN`
- conditions on an expression, such as `lower(name) = 'alice'`

For example, say you're performing vector search on a large dataset of
documents. However, each document belongs to a user, and users can only search
their own documents. It would be wasteful to perform a brute-force search over all
documents if you only care about 1 user at a time. So, you can partition the
vector index based on user ID like so:

```sql
create virtual table vec_documents using vec0(
  document_id integer primary key,
  user_id integer partition key,
  contents_embedding float[1024]
)
```

Then, during a KNN query, you can constrain results to a specific user in the
`WHERE` clause like so:

```sql
select
  document_id,
  user_id,
  distance
from vec_documents
where contents_embedding match :query
  and k = 20
  and user_id = 123;
```

`sqlite-vec` will recognize the `user_id = 123` constraint and pre-filter
vectors during a KNN search. Vectors with the same partition key values are
collocated together, so this is a fast operation.

Another example: say you're performing vector search on a large dataset of news
headlines of the past 100 years. However, in your application, most users only
want to search a subset of articles based on when they were written, like "in
the past ten years" or "during the obama administration." You can partition
based on published date like so:

```sql
create virtual table vec_articles using vec0(
  article_id integer primary key,
  published_date text partition key,
  headline_embedding float[1024]
);
```

And a KNN query:

```sql
select
  article_id,
  published_date,
  distance
from vec_articles
where headline_embedding match :query
  and k = 20
  and published_date between '2009-01-20' and '2017-01-20'; -- Obama administration
```

But be careful! over-using partition key columns can lead to over-sharding and
slower KNN queries. As a rule of thumb, make sure that every unique partition
key value has ~100s of vectors associated with it. In the above examples, make
sure that every user has on the magnitude of dozens or hundreds of documents
each, or that there are dozens or, preferably, hundreds of articles per day. If they
don't and you're noticing slow queries, try a more broad partition key value,
like `organization_id` or `published_month`.

A maximum of 4 partition key columns can be declared in a `vec0` virtual table,
but use caution if you find yourself using more than 1 partition key column. Vectors are sharded
along each unique combination, so over-sharding is more common with more
partition key columns.

### Auxiliary Columns {#aux}

Auxiliary columns store additional unindexed data separate from the internal
vector index. They are meant for larger metadata that will never appear in a
`WHERE` clause of a KNN query, but can be retrieved in the result set without needing a separate `JOIN`.

Auxiliary columns are denoted by a `+` prefix in their column definition, like
so:

```sql
create virtual table vec_text_chunks using vec0(
  contents_embedding float[1024],
  +contents text
);

select
  rowid,
  contents,
  distance
from vec_text_chunks
where contents_embedding match :query
  and k = 10;
```

Here we store the text contents of each chunk in the `contents` auxiliary
column. When we perform a KNN query, we can reference the `contents` column in
the `SELECT` clause, to get the raw text contents of the most relevant chunks.

A similar approach can be used for image embeddings:

```sql
create virtual table vec_image_chunks using vec0(
  image_embedding float[1024],
  +image blob
);

select
  rowid,
  image,
  distance
from vec_image_chunks
where image_embedding match :query
  and k = 10;
```

Here the `image` auxiliary column can store the raw image file in a large `BLOB`
column. It can appear in the `SELECT` clause of the KNN query, to get the most
relevant raw images.

In general, auxiliary columns are good for large text, blobs, URLs, or other
datatypes that won't be a part of a `WHERE` clause of a KNN query. Auxiliary columns are a good fit for columns
that will appear often in a `SELECT` clause but not in the `WHERE` clause.

A maximum of 16 auxiliary columns can be declared in a `vec0` virtual table.
