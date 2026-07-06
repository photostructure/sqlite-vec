"""Regression tests for the fork-only vec0 `optimize` command over tables that
carry metadata columns.

These exercise the metadata-copy compaction path that hard-crashed in the field
(native SIGTRAP / heap corruption) on tables shaped like the crash reporter's:
a ``bit[N]`` vector plus INTEGER and TEXT metadata columns, with TEXT values long
enough (> ``VEC0_METADATA_TEXT_VIEW_DATA_LENGTH`` == 12 bytes) to spill into the
``_metadatatextNN`` long-value shadow table.

The tests assert full post-optimize correctness (metadata, vectors, KNN, count)
and that optimize actually compacted the chunks. They must not be weakened to
pass -- a failure here is a real finding.
"""

import struct

# bit[16] -> 2-byte little-endian blobs, one distinct pattern per rowid.
DIM = 16
CHUNK_SIZE = 8


def _vec(rowid):
    """Deterministic, distinct 2-byte bit[16] pattern for a rowid."""
    return struct.pack("<H", rowid & 0xFFFF)


def _txt(rowid):
    """TEXT metadata value guaranteed > 12 bytes so it uses _metadatatextNN."""
    s = f"text-value-number-{rowid:05d}-long-enough-to-spill"
    assert len(s.encode("utf-8")) > 12
    return s


def _int(rowid):
    return rowid * 1000 + 7


def _create(db):
    db.execute(
        "create virtual table t using vec0("
        "  embedding bit[%d],"
        "  intmeta integer,"
        "  txtmeta text,"
        "  chunk_size=%d"
        ")" % (DIM, CHUNK_SIZE)
    )


def _insert(db, rowids):
    db.executemany(
        "insert into t(rowid, embedding, intmeta, txtmeta) "
        "values (?, vec_bit(?), ?, ?)",
        [(i, _vec(i), _int(i), _txt(i)) for i in rowids],
    )


def _chunk_stats(db):
    row = db.execute(
        "select count(*), coalesce(max(chunk_id), 0) from t_chunks"
    ).fetchone()
    return row[0], row[1]


def _assert_row_correct(db, rowid):
    row = db.execute(
        "select embedding, intmeta, txtmeta from t where rowid = ?", (rowid,)
    ).fetchone()
    assert row is not None, f"surviving rowid {rowid} vanished after optimize"
    assert row["embedding"] == _vec(rowid), f"vector corrupted for rowid {rowid}"
    assert row["intmeta"] == _int(rowid), f"intmeta corrupted for rowid {rowid}"
    assert row["txtmeta"] == _txt(rowid), f"txtmeta corrupted for rowid {rowid}"


def _assert_all_correct(db, survivors):
    # Every surviving rowid keeps its exact vector + metadata.
    for rowid in survivors:
        _assert_row_correct(db, rowid)

    # Deleted rowids are gone.
    assert db.execute("select count(*) from t").fetchone()[0] == len(survivors)

    # Long TEXT values really live in the long-value shadow table (i.e. we are
    # exercising the _metadatatextNN copy path, not just the inline view).
    assert (
        db.execute("select count(*) from t_metadatatext01").fetchone()[0] > 0
    ), "expected long TEXT metadata rows in _metadatatext01 shadow table"

    # KNN over the bit vector still returns the correct nearest rows. Query with
    # an exact survivor's vector: it must come back first at hamming distance 0,
    # and every returned rowid must be a survivor.
    target = min(survivors)
    knn = db.execute(
        "select rowid, distance from t " "where embedding match vec_bit(?) and k = ?",
        (_vec(target), min(5, len(survivors))),
    ).fetchall()
    assert knn[0]["rowid"] == target
    assert knn[0]["distance"] == 0.0
    returned = {r["rowid"] for r in knn}
    assert returned.issubset(
        survivors
    ), f"KNN returned deleted rowids: {returned - survivors}"


def test_optimize_metadata_compaction(db):
    """Single optimize pass over a fragmented bit+int+text table."""
    _create(db)

    # 40 rows at chunk_size=8 -> 5 full chunks.
    all_rowids = list(range(1, 41))
    _insert(db, all_rowids)

    n_chunks_insert, max_id_insert = _chunk_stats(db)
    assert n_chunks_insert == 5

    # Delete a scattered subset to fragment every chunk.
    deleted = {i for i in all_rowids if i % 3 == 0}
    db.executemany("delete from t where rowid = ?", [(i,) for i in sorted(deleted)])
    survivors = set(all_rowids) - deleted

    n_chunks_delete, max_id_delete = _chunk_stats(db)
    # Delete only flips validity bits; chunk rows are unchanged.
    assert n_chunks_delete == n_chunks_insert

    # The path under test.
    db.execute("insert into t(t) values ('optimize')")

    n_chunks_opt, max_id_opt = _chunk_stats(db)

    # Optimize actually compacted: survivors (27) repack into ceil(27/8) == 4
    # chunks, fewer than the 5 fragmented chunks, and it allocated fresh chunk
    # ids (max chunk_id advanced).
    assert (
        n_chunks_opt < n_chunks_delete
    ), f"optimize did not compact: {n_chunks_delete} -> {n_chunks_opt} chunks"
    assert max_id_opt > max_id_delete, "optimize did not allocate new chunk ids"

    _assert_all_correct(db, survivors)


def test_optimize_metadata_compaction_repeated_churn(db):
    """Multiple optimize passes interleaved with more delete+insert churn."""
    _create(db)

    survivors = set()
    next_rowid = 1

    # Seed: 48 rows -> 6 chunks.
    seed = list(range(next_rowid, next_rowid + 48))
    next_rowid += 48
    _insert(db, seed)
    survivors.update(seed)

    prev_max_id = 0

    for round_idx in range(4):
        # Fragment: delete a scattered subset of current survivors.
        to_delete = {
            r for idx, r in enumerate(sorted(survivors)) if (idx + round_idx) % 4 == 0
        }
        db.executemany(
            "delete from t where rowid = ?", [(i,) for i in sorted(to_delete)]
        )
        survivors -= to_delete

        # Add fresh rows (new long-TEXT + int + vector) to re-grow chunks.
        added = list(range(next_rowid, next_rowid + 10))
        next_rowid += 10
        _insert(db, added)
        survivors.update(added)

        # Compact.
        db.execute("insert into t(t) values ('optimize')")

        _, max_id_opt = _chunk_stats(db)
        # Each optimize pass copies survivors into freshly-allocated chunks, so
        # the max chunk id strictly advances every round.
        assert max_id_opt > prev_max_id, (
            f"round {round_idx}: chunk ids did not advance "
            f"({prev_max_id} -> {max_id_opt})"
        )
        prev_max_id = max_id_opt

        # Full correctness must hold after every pass.
        _assert_all_correct(db, survivors)

    # Final belt-and-suspenders check after all churn.
    assert db.execute("select count(*) from t").fetchone()[0] == len(survivors)
    for rowid in survivors:
        _assert_row_correct(db, rowid)
