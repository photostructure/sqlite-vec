import pytest
import random
import sqlite3
import struct
from collections import OrderedDict
from conftest import get_extension_path


def _f32(values):
    return struct.pack("%sf" % len(values), *values)


def exec(db, sql, parameters=[]):
    try:
        rows = db.execute(sql, parameters).fetchall()
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        return {
            "error": e.__class__.__name__,
            "message": str(e),
        }
    a = []
    for row in rows:
        o = OrderedDict()
        for k in row.keys():
            o[k] = row[k]
        a.append(o)
    result = OrderedDict()
    result["sql"] = sql
    result["rows"] = a
    return result


def ivf_total_vectors(db, table="t", col=0):
    """Count total vectors across all IVF cells."""
    return db.execute(
        f"SELECT COALESCE(SUM(n_vectors), 0) FROM {table}_ivf_cells{col:02d}"
    ).fetchone()[0]


def ivf_unassigned_count(db, table="t", col=0):
    """Count vectors in unassigned cells (centroid_id=-1)."""
    return db.execute(
        f"SELECT COALESCE(SUM(n_vectors), 0) FROM {table}_ivf_cells{col:02d} WHERE centroid_id = -1"
    ).fetchone()[0]


def ivf_assigned_count(db, table="t", col=0):
    """Count vectors in trained cells (centroid_id >= 0)."""
    return db.execute(
        f"SELECT COALESCE(SUM(n_vectors), 0) FROM {table}_ivf_cells{col:02d} WHERE centroid_id >= 0"
    ).fetchone()[0]


# ============================================================================
# Parser tests
# ============================================================================


def test_ivf_create_defaults(db):
    """ivf() with no args uses defaults."""
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf())")
    tables = [
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1"
        ).fetchall()
    ]
    assert "t_ivf_centroids00" in tables
    assert "t_ivf_cells00" in tables
    assert "t_ivf_rowid_map00" in tables


def test_ivf_create_custom_params(db):
    db.execute(
        "CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf(nlist=64, nprobe=8))"
    )
    tables = [
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1"
        ).fetchall()
    ]
    assert "t_ivf_centroids00" in tables
    assert "t_ivf_cells00" in tables


def test_ivf_create_with_distance_metric(db):
    db.execute(
        "CREATE VIRTUAL TABLE t USING vec0(v float[4] distance_metric=cosine indexed by ivf(nlist=16))"
    )
    tables = [
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1"
        ).fetchall()
    ]
    assert "t_ivf_centroids00" in tables


def test_ivf_create_error_unknown_key(db):
    result = exec(
        db,
        "CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf(bogus=1))",
    )
    assert "error" in result


def test_ivf_create_error_nprobe_gt_nlist(db):
    result = exec(
        db,
        "CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf(nlist=4, nprobe=10))",
    )
    assert "error" in result


# ============================================================================
# Shadow table tests
# ============================================================================


def test_ivf_shadow_tables_created(db):
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf(nlist=8))")
    trained = db.execute(
        "SELECT value FROM t_info WHERE key = 'ivf_trained_0'"
    ).fetchone()[0]
    assert str(trained) == "0"

    # No cells yet (created lazily on first insert)
    count = db.execute("SELECT count(*) FROM t_ivf_cells00").fetchone()[0]
    assert count == 0


def test_ivf_drop_cleans_up(db):
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf(nlist=4))")
    db.execute("DROP TABLE t")
    tables = [
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]
    assert not any("ivf" in t for t in tables)


# ============================================================================
# Insert tests (flat mode)
# ============================================================================


def test_ivf_insert_flat_mode(db):
    """Before training, vectors go to unassigned cell."""
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf(nlist=4))")
    db.execute("INSERT INTO t(rowid, v) VALUES (1, ?)", [_f32([1, 2, 3, 4])])
    db.execute("INSERT INTO t(rowid, v) VALUES (2, ?)", [_f32([5, 6, 7, 8])])

    assert ivf_unassigned_count(db) == 2
    assert ivf_assigned_count(db) == 0

    # rowid_map should have 2 entries
    assert db.execute("SELECT count(*) FROM t_ivf_rowid_map00").fetchone()[0] == 2


def test_ivf_delete_flat_mode(db):
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf(nlist=4))")
    db.execute("INSERT INTO t(rowid, v) VALUES (1, ?)", [_f32([1, 2, 3, 4])])
    db.execute("INSERT INTO t(rowid, v) VALUES (2, ?)", [_f32([5, 6, 7, 8])])
    db.execute("DELETE FROM t WHERE rowid = 1")

    assert ivf_unassigned_count(db) == 1
    assert db.execute("SELECT count(*) FROM t_ivf_rowid_map00").fetchone()[0] == 1


# ============================================================================
# KNN flat mode tests
# ============================================================================


def test_ivf_knn_flat_mode(db):
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf(nlist=4))")
    db.execute("INSERT INTO t(rowid, v) VALUES (1, ?)", [_f32([1, 0, 0, 0])])
    db.execute("INSERT INTO t(rowid, v) VALUES (2, ?)", [_f32([2, 0, 0, 0])])
    db.execute("INSERT INTO t(rowid, v) VALUES (3, ?)", [_f32([9, 0, 0, 0])])

    rows = db.execute(
        "SELECT rowid, distance FROM t WHERE v MATCH ? AND k = 2",
        [_f32([1.5, 0, 0, 0])],
    ).fetchall()
    assert len(rows) == 2
    rowids = {r[0] for r in rows}
    assert rowids == {1, 2}


def test_ivf_knn_flat_empty(db):
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf(nlist=4))")
    rows = db.execute(
        "SELECT rowid FROM t WHERE v MATCH ? AND k = 5",
        [_f32([1, 0, 0, 0])],
    ).fetchall()
    assert len(rows) == 0


# ============================================================================
# compute-centroids tests
# ============================================================================


def test_compute_centroids(db):
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf(nlist=4))")
    for i in range(40):
        db.execute(
            "INSERT INTO t(rowid, v) VALUES (?, ?)",
            [i, _f32([i % 10, i // 10, 0, 0])],
        )

    assert ivf_unassigned_count(db) == 40

    db.execute("INSERT INTO t(t) VALUES ('compute-centroids')")

    # After training: unassigned cell should be gone (or empty), vectors in trained cells
    assert ivf_unassigned_count(db) == 0
    assert ivf_assigned_count(db) == 40
    assert db.execute("SELECT count(*) FROM t_ivf_centroids00").fetchone()[0] == 4
    trained = db.execute(
        "SELECT value FROM t_info WHERE key='ivf_trained_0'"
    ).fetchone()[0]
    assert str(trained) == "1"


def test_compute_centroids_recompute(db):
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf(nlist=2))")
    for i in range(20):
        db.execute("INSERT INTO t(rowid, v) VALUES (?, ?)", [i, _f32([i, 0, 0, 0])])

    db.execute("INSERT INTO t(t) VALUES ('compute-centroids')")
    assert db.execute("SELECT count(*) FROM t_ivf_centroids00").fetchone()[0] == 2

    db.execute("INSERT INTO t(t) VALUES ('compute-centroids')")
    assert db.execute("SELECT count(*) FROM t_ivf_centroids00").fetchone()[0] == 2
    assert ivf_assigned_count(db) == 20


# ============================================================================
# Insert after training (assigned mode)
# ============================================================================


def test_ivf_insert_after_training(db):
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf(nlist=2))")
    for i in range(20):
        db.execute("INSERT INTO t(rowid, v) VALUES (?, ?)", [i, _f32([i, 0, 0, 0])])

    db.execute("INSERT INTO t(t) VALUES ('compute-centroids')")

    db.execute("INSERT INTO t(rowid, v) VALUES (100, ?)", [_f32([5, 0, 0, 0])])

    # Should be in a trained cell, not unassigned
    row = db.execute(
        "SELECT m.cell_id, c.centroid_id FROM t_ivf_rowid_map00 m "
        "JOIN t_ivf_cells00 c ON c.rowid = m.cell_id "
        "WHERE m.rowid = 100"
    ).fetchone()
    assert row is not None
    assert row[1] >= 0  # centroid_id >= 0 means trained cell


# ============================================================================
# KNN after training (IVF probe mode)
# ============================================================================


def test_ivf_knn_after_training(db):
    db.execute(
        "CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf(nlist=4, nprobe=4))"
    )
    for i in range(100):
        db.execute("INSERT INTO t(rowid, v) VALUES (?, ?)", [i, _f32([i, 0, 0, 0])])

    db.execute("INSERT INTO t(t) VALUES ('compute-centroids')")

    rows = db.execute(
        "SELECT rowid, distance FROM t WHERE v MATCH ? AND k = 5",
        [_f32([50.0, 0, 0, 0])],
    ).fetchall()
    assert len(rows) == 5
    assert rows[0][0] == 50
    assert rows[0][1] < 0.01


def test_ivf_knn_k_larger_than_n(db):
    db.execute(
        "CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf(nlist=2, nprobe=2))"
    )
    for i in range(5):
        db.execute("INSERT INTO t(rowid, v) VALUES (?, ?)", [i, _f32([i, 0, 0, 0])])

    db.execute("INSERT INTO t(t) VALUES ('compute-centroids')")

    rows = db.execute(
        "SELECT rowid FROM t WHERE v MATCH ? AND k = 100",
        [_f32([0, 0, 0, 0])],
    ).fetchall()
    assert len(rows) == 5


# ============================================================================
# Manual centroid import (set-centroid, assign-vectors)
# ============================================================================


def test_set_centroid_and_assign(db):
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf(nlist=0))")
    for i in range(20):
        db.execute("INSERT INTO t(rowid, v) VALUES (?, ?)", [i, _f32([i, 0, 0, 0])])

    db.execute(
        "INSERT INTO t(t, v) VALUES ('set-centroid:0', ?)",
        [_f32([5, 0, 0, 0])],
    )
    db.execute(
        "INSERT INTO t(t, v) VALUES ('set-centroid:1', ?)",
        [_f32([15, 0, 0, 0])],
    )

    assert db.execute("SELECT count(*) FROM t_ivf_centroids00").fetchone()[0] == 2

    db.execute("INSERT INTO t(t) VALUES ('assign-vectors')")

    assert ivf_unassigned_count(db) == 0
    assert ivf_assigned_count(db) == 20


# ============================================================================
# clear-centroids
# ============================================================================


def test_clear_centroids(db):
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf(nlist=2))")
    for i in range(20):
        db.execute("INSERT INTO t(rowid, v) VALUES (?, ?)", [i, _f32([i, 0, 0, 0])])

    db.execute("INSERT INTO t(t) VALUES ('compute-centroids')")
    assert db.execute("SELECT count(*) FROM t_ivf_centroids00").fetchone()[0] == 2

    db.execute("INSERT INTO t(t) VALUES ('clear-centroids')")
    assert db.execute("SELECT count(*) FROM t_ivf_centroids00").fetchone()[0] == 0
    assert ivf_unassigned_count(db) == 20
    trained = db.execute(
        "SELECT value FROM t_info WHERE key='ivf_trained_0'"
    ).fetchone()[0]
    assert str(trained) == "0"


# ============================================================================
# Delete after training
# ============================================================================


def test_ivf_delete_after_training(db):
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf(nlist=2))")
    for i in range(10):
        db.execute("INSERT INTO t(rowid, v) VALUES (?, ?)", [i, _f32([i, 0, 0, 0])])

    db.execute("INSERT INTO t(t) VALUES ('compute-centroids')")
    assert ivf_assigned_count(db) == 10

    db.execute("DELETE FROM t WHERE rowid = 5")
    assert ivf_assigned_count(db) == 9
    assert db.execute("SELECT count(*) FROM t_ivf_rowid_map00").fetchone()[0] == 9


# ============================================================================
# Recall test
# ============================================================================


def test_ivf_recall_nprobe_equals_nlist(db):
    db.execute(
        "CREATE VIRTUAL TABLE t USING vec0(v float[4] indexed by ivf(nlist=8, nprobe=8))"
    )
    for i in range(100):
        db.execute("INSERT INTO t(rowid, v) VALUES (?, ?)", [i, _f32([i, 0, 0, 0])])

    db.execute("INSERT INTO t(t) VALUES ('compute-centroids')")

    rows = db.execute(
        "SELECT rowid FROM t WHERE v MATCH ? AND k = 10",
        [_f32([50.0, 0, 0, 0])],
    ).fetchall()
    rowids = {r[0] for r in rows}

    # 45 and 55 are equidistant from 50, so either may appear in top 10
    assert 50 in rowids
    assert len(rowids) == 10
    assert all(45 <= r <= 55 for r in rowids)


# ============================================================================
# Behavior this port defines where upstream's IVF differs
# ============================================================================


def _random_rows(seed, n, dims):
    rng = random.Random(seed)
    return {i: [rng.uniform(-1, 1) for _ in range(dims)] for i in range(1, n + 1)}


def _connect(path):
    db = sqlite3.connect(path)
    db.enable_load_extension(True)
    db.load_extension(get_extension_path())
    db.enable_load_extension(False)
    return db


def _contents(db, table="t"):
    """Every row of every table of the vec0 table, by table name."""
    names = [
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
            " AND name LIKE ? ESCAPE '\\' ORDER BY name",
            [f"{table}\\_%"],
        )
    ]
    return {
        name: db.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall()
        for name in names
    }


# With nprobe = nlist every cell is read, and an oversample as large as the
# table ranks every row by its exact distance, so the KNN of an IVF column must
# answer as a flat column does, constraint for constraint, before and after
# compute-centroids.
@pytest.mark.parametrize(
    "options",
    [
        "nlist=4, nprobe=4",
        "nlist=4, nprobe=4, quantizer=int8, oversample=100",
        "nlist=4, nprobe=4, quantizer=binary, oversample=100",
    ],
)
@pytest.mark.parametrize(
    "where",
    [
        "k = 10",
        "k = 10 AND distance > 0.4",
        "k = 10 AND distance <= 0.8",
        "k = 10 AND distance >= 0.2 AND distance < 0.9",
        "k = 5 AND rowid IN (3, 7, 11, 19, 23, 31, 999)",
        "k = 3 AND rowid = 17",
        "k = 6 AND mmr_lambda = 0.5",
        "k = 6 AND mmr_lambda = 0.2 AND distance > 0.3",
    ],
)
def test_ivf_knn_answers_as_flat_when_every_cell_is_read(db, options, where):
    db.execute(
        "CREATE VIRTUAL TABLE i USING vec0("
        f"emb float[16] distance_metric=cosine INDEXED BY ivf({options}))"
    )
    db.execute(
        "CREATE VIRTUAL TABLE f USING vec0(emb float[16] distance_metric=cosine)"
    )
    rows = _random_rows(11, 60, 16)
    for rowid, vec in rows.items():
        for table in ("i", "f"):
            db.execute(
                f"INSERT INTO {table}(rowid, emb) VALUES (?, ?)", [rowid, _f32(vec)]
            )

    def compare():
        rng = random.Random(12)
        for _ in range(10):
            query = _f32([rng.uniform(-1, 1) for _ in range(16)])
            sql = "SELECT rowid, distance FROM {} WHERE emb MATCH ? AND " + where
            got = db.execute(sql.format("i"), [query]).fetchall()
            want = db.execute(sql.format("f"), [query]).fetchall()
            assert [tuple(r) for r in got] == [tuple(r) for r in want]

    compare()
    db.execute("INSERT INTO i(i) VALUES ('compute-centroids')")
    compare()


@pytest.mark.parametrize("quantizer", ["int8", "binary"])
def test_ivf_quantized_column_returns_its_float_vectors(db, quantizer):
    """The cells hold the vectors quantized; the column reads as float32."""
    db.execute(
        "CREATE VIRTUAL TABLE t USING vec0("
        f"v float[8] INDEXED BY ivf(nlist=2, quantizer={quantizer}, oversample=2))"
    )
    rows = _random_rows(5, 20, 8)
    for rowid, vec in rows.items():
        db.execute("INSERT INTO t(rowid, v) VALUES (?, ?)", [rowid, _f32(vec)])
    for command in (None, "compute-centroids", "clear-centroids"):
        if command:
            db.execute("INSERT INTO t(t) VALUES (?)", [command])
        assert db.execute("SELECT v FROM t WHERE rowid = 7").fetchone()[0] == _f32(
            rows[7]
        )
        assert {r: v for r, v in db.execute("SELECT rowid, v FROM t")} == {
            r: _f32(v) for r, v in rows.items()
        }


def test_ivf_point_query_for_a_missing_rowid(db):
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[8] INDEXED BY ivf())")
    db.execute("INSERT INTO t(rowid, v) VALUES (1, ?)", [_f32([1] * 8)])
    assert db.execute("SELECT rowid, v FROM t WHERE rowid = 2").fetchall() == []
    assert [tuple(r) for r in db.execute("SELECT rowid FROM t WHERE rowid = 1")] == [
        (1,)
    ]


def test_ivf_another_connection_reads_the_centroids(tmp_path):
    """Whether a column has centroids is read from the database, not kept by
    the connection, so a connection sees the centroids another one makes."""
    path = str(tmp_path / "ivf.db")
    a = _connect(path)
    b = _connect(path)
    a.execute(
        "CREATE VIRTUAL TABLE t USING vec0(v float[8] INDEXED BY ivf(nlist=4, nprobe=1))"
    )
    rows = _random_rows(9, 40, 8)
    for rowid, vec in rows.items():
        a.execute("INSERT INTO t(rowid, v) VALUES (?, ?)", [rowid, _f32(vec)])
    a.commit()
    sql = "SELECT rowid, distance FROM t WHERE v MATCH ? AND k = 5"
    query = [_f32(rows[3])]
    assert b.execute(sql, query).fetchall() == a.execute(sql, query).fetchall()
    for command in ("compute-centroids", "clear-centroids", "compute-centroids"):
        a.execute("INSERT INTO t(t) VALUES (?)", [command])
        a.commit()
        got = b.execute(sql, query).fetchall()
        assert got == a.execute(sql, query).fetchall()
        assert got[0] == (3, 0.0)


def test_ivf_int8_quantizer_ranks_by_the_column_metric(db):
    """By cosine, the first two rows are both at distance 0 from the query."""
    db.execute(
        "CREATE VIRTUAL TABLE t USING vec0("
        "v float[8] distance_metric=cosine INDEXED BY ivf(nlist=2, quantizer=int8))"
    )
    for rowid, vec in (
        (1, [0.9, 0.9, 0, 0, 0, 0, 0, 0]),
        (2, [0.1, 0.1, 0, 0, 0, 0, 0, 0]),
        (3, [0.5, -0.5, 0, 0, 0, 0, 0, 0]),
    ):
        db.execute("INSERT INTO t(rowid, v) VALUES (?, ?)", [rowid, _f32(vec)])
    rows = db.execute(
        "SELECT rowid, distance FROM t WHERE v MATCH ? AND k = 2",
        [_f32([0.2, 0.2, 0, 0, 0, 0, 0, 0])],
    ).fetchall()
    assert {r[0] for r in rows} == {1, 2}
    assert all(r[1] == pytest.approx(0.0, abs=1e-6) for r in rows)


def test_ivf_rename_then_create_under_the_old_name(db):
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[8] INDEXED BY ivf(nlist=2))")
    rows = _random_rows(4, 20, 8)
    for rowid, vec in rows.items():
        db.execute("INSERT INTO t(rowid, v) VALUES (?, ?)", [rowid, _f32(vec)])
    db.execute("INSERT INTO t(t) VALUES ('compute-centroids')")
    db.execute("ALTER TABLE t RENAME TO u")
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[8] INDEXED BY ivf(nlist=2))")
    db.execute("INSERT INTO t(rowid, v) VALUES (1, ?)", [_f32(rows[2])])
    knn = "SELECT rowid FROM {} WHERE v MATCH ? AND k = 1"
    assert db.execute(knn.format("u"), [_f32(rows[5])]).fetchone()[0] == 5
    assert db.execute(knn.format("t"), [_f32(rows[2])]).fetchone()[0] == 1
    indexed = sorted(
        r[0]
        for r in db.execute("SELECT tbl_name FROM sqlite_master WHERE type = 'index'")
        if "ivf" in r[0]
    )
    assert indexed == ["t_ivf_cells00", "u_ivf_cells00"]


@pytest.mark.parametrize(
    "columns, message",
    [
        ("v int8[8] INDEXED BY ivf()", "could not parse vector column"),
        ("v bit[8] INDEXED BY ivf()", "could not parse vector column"),
        (
            "v float[8] INDEXED BY ivf(), m integer",
            "metadata columns are not supported with IVF indexes",
        ),
        (
            "p integer partition key, v float[8] INDEXED BY ivf()",
            "partition key columns are not supported with IVF indexes",
        ),
    ],
)
def test_ivf_create_refuses(db, columns, message):
    with pytest.raises(sqlite3.OperationalError, match=message):
        db.execute(f"CREATE VIRTUAL TABLE t USING vec0({columns})")


@pytest.mark.parametrize(
    "option",
    [
        "quantizer=bin",
        "nli=8",
        "nlist=8x",
        "nlist=99999999999",
        "nlist=65537",
        "nprobe=0",
        "quantizer=int8, oversample=0",
        "nlist=8,",
    ],
)
def test_ivf_create_option_must_be_whole(db, option):
    result = exec(
        db, f"CREATE VIRTUAL TABLE t USING vec0(v float[8] INDEXED BY ivf({option}))"
    )
    assert "error" in result


def test_ivf_with_auxiliary_and_text_primary_key(db):
    db.execute(
        "CREATE VIRTUAL TABLE t USING vec0("
        "id text primary key, v float[8] INDEXED BY ivf(nlist=2), +label text)"
    )
    rows = _random_rows(6, 20, 8)
    for rowid, vec in rows.items():
        db.execute(
            "INSERT INTO t(id, v, label) VALUES (?, ?, ?)",
            [f"id{rowid}", _f32(vec), f"label{rowid}"],
        )
    db.execute("INSERT INTO t(t) VALUES ('compute-centroids')")
    db.execute("DELETE FROM t WHERE id = 'id4'")
    for rowid, vec in rows.items():
        got = db.execute(
            "SELECT id, label, distance FROM t WHERE v MATCH ? AND k = 1",
            [_f32(vec)],
        ).fetchone()
        if rowid == 4:
            assert got[0] != "id4"
        else:
            assert tuple(got) == (f"id{rowid}", f"label{rowid}", 0.0)


@pytest.mark.parametrize(
    "command",
    ["compute-centroids", "clear-centroids", "assign-vectors"],
)
def test_ivf_interrupted_command_changes_nothing(db, command):
    """A command stopped part way leaves every table as it was, and the
    connection goes on answering queries."""
    db.execute(
        "CREATE VIRTUAL TABLE t USING vec0("
        "v float[8] INDEXED BY ivf(nlist=4, quantizer=int8, oversample=4))"
    )
    rows = _random_rows(8, 100, 8)
    for rowid, vec in rows.items():
        db.execute("INSERT INTO t(rowid, v) VALUES (?, ?)", [rowid, _f32(vec)])
    if command == "clear-centroids":
        db.execute("INSERT INTO t(t) VALUES ('compute-centroids')")
    if command == "assign-vectors":
        db.execute("INSERT INTO t(t, v) VALUES ('set-centroid:3', ?)", [_f32(rows[1])])
        db.execute("INSERT INTO t(t, v) VALUES ('set-centroid:8', ?)", [_f32(rows[2])])
    db.commit()
    image = db.serialize()

    def fresh():
        c = sqlite3.connect(":memory:")
        c.deserialize(image)
        c.enable_load_extension(True)
        c.load_extension(get_extension_path())
        c.enable_load_extension(False)
        return c

    counted = fresh()
    steps = 0

    def count():
        nonlocal steps
        steps += 1
        return 0

    counted.set_progress_handler(count, 1)
    counted.execute("INSERT INTO t(t) VALUES (?)", [command])
    counted.set_progress_handler(None, 1)
    after = _contents(counted)

    before = _contents(fresh())
    assert after != before
    # A progress handler also runs once the statement has halted, when SQLite
    # reports the interrupt but has nothing left to roll back, so the points
    # stop short of the last steps.
    for n in [1 + steps * tenth // 10 for tenth in range(10)]:
        c = fresh()
        seen = 0

        def stop():
            nonlocal seen
            seen += 1
            return seen >= n

        c.set_progress_handler(stop, 1)
        with pytest.raises(sqlite3.OperationalError, match="interrupted"):
            c.execute("INSERT INTO t(t) VALUES (?)", [command])
        c.set_progress_handler(None, 1)
        assert _contents(c) == before
        got = c.execute(
            "SELECT rowid, distance FROM t WHERE v MATCH ? AND k = 3",
            [_f32(rows[50])],
        ).fetchall()
        assert got[0] == (50, 0.0)


def test_ivf_commands_apply_to_every_ivf_column(db):
    db.execute(
        "CREATE VIRTUAL TABLE t USING vec0("
        "a float[8] INDEXED BY ivf(nlist=2), "
        "f float[8], "
        "b float[8] INDEXED BY ivf(nlist=3, quantizer=int8))"
    )
    rows = _random_rows(7, 30, 8)
    for rowid, vec in rows.items():
        db.execute(
            "INSERT INTO t(rowid, a, f, b) VALUES (?, ?, ?, ?)",
            [rowid, _f32(vec), _f32(vec), _f32([-x for x in vec])],
        )

    def trained():
        return [
            (key, str(value))
            for key, value in db.execute(
                "SELECT key, value FROM t_info WHERE key LIKE 'ivf_trained_%' "
                "ORDER BY key"
            )
        ]

    def centroids(col):
        return db.execute(f"SELECT count(*) FROM t_ivf_centroids{col:02d}").fetchone()[
            0
        ]

    def unassigned(col):
        return ivf_unassigned_count(db, col=col)

    db.execute("INSERT INTO t(t) VALUES ('compute-centroids')")
    assert trained() == [("ivf_trained_0", "1"), ("ivf_trained_2", "1")]
    assert (centroids(0), centroids(2)) == (2, 3)
    assert (unassigned(0), unassigned(2)) == (0, 0)

    db.execute("INSERT INTO t(t) VALUES ('clear-centroids')")
    assert trained() == [("ivf_trained_0", "0"), ("ivf_trained_2", "0")]
    assert (centroids(0), centroids(2)) == (0, 0)
    assert (unassigned(0), unassigned(2)) == (30, 30)

    db.execute(
        "INSERT INTO t(t, a, b) VALUES ('set-centroid:4', ?, ?)",
        [_f32([0.5] * 8), _f32([-0.5] * 8)],
    )
    assert trained() == [("ivf_trained_0", "1"), ("ivf_trained_2", "1")]
    db.execute("INSERT INTO t(t) VALUES ('assign-vectors')")
    assert (unassigned(0), unassigned(2)) == (0, 0)
    for rowid, vec in rows.items():
        for column, value in (("a", vec), ("b", [-x for x in vec])):
            got = db.execute(
                f"SELECT rowid, distance FROM t WHERE {column} MATCH ? AND k = 1",
                [_f32(value)],
            ).fetchone()
            assert tuple(got) == (rowid, 0.0)


@pytest.mark.parametrize(
    "command, message",
    [
        ("nprobe=0", "nprobe must be >= 1"),
        ("nprobe=5x", "nprobe must be >= 1"),
        ("nprobe= 5", "nprobe must be >= 1"),
        ("nprobe=", "nprobe must be >= 1"),
        (
            'compute-centroids:{"nlist": 0}',
            "option nlist must be an integer from 1 to 65536",
        ),
        (
            'compute-centroids:{"nlist": 2.5}',
            "option nlist must be an integer from 1 to 65536",
        ),
        (
            'compute-centroids:{"nlist": "2"}',
            "option nlist must be an integer from 1 to 65536",
        ),
        (
            'compute-centroids:{"seed": -1}',
            "option seed must be an integer from 0 to 4294967295",
        ),
        ('compute-centroids:{"nlists": 2}', "unknown compute-centroids option: nlists"),
        ("compute-centroids:[2]", "options must be a JSON object"),
        ("compute-centroids:[]", "options must be a JSON object"),
        ("compute-centroids:2", "options must be a JSON object"),
        ("compute-centroids:{nlist: 2", "compute-centroids options: malformed JSON"),
        ("compute-centroids:", "compute-centroids options: malformed JSON"),
        ("set-centroid:-1", "set-centroid needs a centroid id from 0 to 2147483647"),
        ("set-centroid:x", "set-centroid needs a centroid id from 0 to 2147483647"),
        ("set-centroid:1", "set-centroid needs a vector for an IVF-indexed column"),
        ("assign-vectors", "vector column 0 has no IVF centroids"),
        ("compute-centroid", "unknown vec0 command"),
        ("compute-centroids2", "unknown vec0 command"),
    ],
)
def test_ivf_command_errors(db, command, message):
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[8] INDEXED BY ivf(nlist=2))")
    db.execute("INSERT INTO t(rowid, v) VALUES (1, ?)", [_f32([0.5] * 8)])
    with pytest.raises(sqlite3.OperationalError, match=message):
        db.execute("INSERT INTO t(t) VALUES (?)", [command])


def test_ivf_compute_centroids_options(db):
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[8] INDEXED BY ivf(nlist=0))")
    with pytest.raises(
        sqlite3.OperationalError,
        match="compute-centroids needs at least one row in vector column 0",
    ):
        db.execute("""INSERT INTO t(t) VALUES ('compute-centroids:{"nlist": 2}')""")
    rows = _random_rows(10, 30, 8)
    for rowid, vec in rows.items():
        db.execute("INSERT INTO t(rowid, v) VALUES (?, ?)", [rowid, _f32(vec)])
    with pytest.raises(
        sqlite3.OperationalError,
        match="compute-centroids needs nlist for vector column 0, which was "
        "created with nlist=0",
    ):
        db.execute("INSERT INTO t(t) VALUES ('compute-centroids')")

    def centroids(table="t"):
        return [
            tuple(r)
            for r in db.execute(
                f"SELECT centroid_id, centroid FROM {table}_ivf_centroids00 ORDER BY 1"
            )
        ]

    # the same rows, read in the same order, and the same seed
    db.execute("CREATE VIRTUAL TABLE u USING vec0(v float[8] INDEXED BY ivf(nlist=0))")
    for rowid, vec in rows.items():
        db.execute("INSERT INTO u(rowid, v) VALUES (?, ?)", [rowid, _f32(vec)])
    for table in ("t", "u"):
        db.execute(
            f"INSERT INTO {table}({table}) VALUES "
            """('compute-centroids:{"nlist": 3, "seed": 5}')"""
        )
    assert len(centroids("t")) == 3
    assert centroids("t") == centroids("u")

    # without iterations, the centroids are the rows k-means++ picks
    db.execute(
        "INSERT INTO t(t) VALUES "
        """('compute-centroids:{"nlist": 4, "max_iterations": 0, "seed": 9}')"""
    )
    vectors = {_f32(vec) for vec in rows.values()}
    assert len(centroids()) == 4
    assert all(c in vectors for _, c in centroids())

    # at most one centroid per row
    db.execute("""INSERT INTO t(t) VALUES ('compute-centroids:{"nlist": 64}')""")
    assert len(centroids()) == 30
    assert ivf_assigned_count(db) == 30


def test_ivf_corrupt_cell_errors(db):
    db.execute("CREATE VIRTUAL TABLE t USING vec0(v float[8] INDEXED BY ivf(nlist=2))")
    rows = _random_rows(2, 10, 8)
    for rowid, vec in rows.items():
        db.execute("INSERT INTO t(rowid, v) VALUES (?, ?)", [rowid, _f32(vec)])
    db.execute("UPDATE t_ivf_rowid_map00 SET slot = 99 WHERE rowid = 3")
    with pytest.raises(
        sqlite3.OperationalError,
        match="Could not fetch vector data for 3 from the IVF index",
    ):
        db.execute("SELECT v FROM t WHERE rowid = 3").fetchall()
    db.execute("UPDATE t_ivf_cells00 SET vectors = x'00'")
    with pytest.raises(sqlite3.OperationalError, match="cell 1 .* is corrupt"):
        db.execute(
            "SELECT rowid FROM t WHERE v MATCH ? AND k = 3", [_f32(rows[1])]
        ).fetchall()
    with pytest.raises(sqlite3.OperationalError, match="cell 1 .* is corrupt"):
        db.execute("INSERT INTO t(t) VALUES ('compute-centroids')")


@pytest.mark.parametrize("options", ["nlist=2", "nlist=2, quantizer=int8"])
def test_ivf_insert_or_replace(db, options):
    db.execute(
        f"CREATE VIRTUAL TABLE t USING vec0(v float[4] INDEXED BY ivf({options}), "
        "+a text)"
    )
    db.execute("INSERT INTO t(rowid, v, a) VALUES (1, ?, 'x')", [_f32([1, 0, 0, 0])])
    db.execute("INSERT INTO t(rowid, v, a) VALUES (2, ?, 'y')", [_f32([0, 1, 0, 0])])
    db.execute("INSERT INTO t(t) VALUES ('compute-centroids')")
    db.execute(
        "INSERT OR REPLACE INTO t(rowid, v, a) VALUES (1, ?, 'z')",
        [_f32([0, 0, 1, 0])],
    )
    rows = db.execute("SELECT rowid, v, a FROM t ORDER BY rowid")
    assert [tuple(r) for r in rows] == [
        (1, _f32([0, 0, 1, 0]), "z"),
        (2, _f32([0, 1, 0, 0]), "y"),
    ]
    got = db.execute(
        "SELECT rowid, distance FROM t WHERE v MATCH ? AND k = 2", [_f32([0, 0, 1, 0])]
    ).fetchall()
    assert [tuple(r) for r in got] == [(1, 0.0), (2, pytest.approx(2**0.5))]
    assert ivf_total_vectors(db) == 2


def test_ivf_vacuum_after_knn(db):
    """A KNN query leaves no statement in progress, so VACUUM works after it.
    https://github.com/asg017/sqlite-vec/issues/295"""
    db.execute(
        "CREATE VIRTUAL TABLE t USING vec0("
        "v float[8] INDEXED BY ivf(nlist=2, quantizer=binary, oversample=2))"
    )
    for i in range(1, 11):
        db.execute("INSERT INTO t(rowid, v) VALUES (?, ?)", [i, _f32([0.1 * i] * 8)])
    db.execute("INSERT INTO t(t) VALUES ('compute-centroids')")
    db.commit()
    rows = db.execute(
        "SELECT rowid FROM t WHERE v MATCH ? AND k = 3", [_f32([0.5] * 8)]
    ).fetchall()
    assert len(rows) == 3
    db.execute("VACUUM")


def test_ivf_optimize_beside_a_flat_column(db):
    """optimize moves a flat column's vectors and leaves an IVF column's."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            f float[8],
            i float[8] INDEXED BY ivf(nlist=3, quantizer=int8, oversample=8),
            chunk_size=8
        )
    """)
    rows = _random_rows(13, 40, 8)
    for rowid, vec in rows.items():
        db.execute(
            "INSERT INTO t(rowid, f, i) VALUES (?, ?, ?)",
            [rowid, _f32(vec), _f32([-x for x in vec])],
        )
    db.execute("INSERT INTO t(t) VALUES ('compute-centroids')")
    for rowid in range(1, 41, 3):
        db.execute("DELETE FROM t WHERE rowid = ?", [rowid])
        del rows[rowid]
    db.execute("INSERT INTO t(t) VALUES ('optimize')")
    for rowid, f, i in db.execute("SELECT rowid, f, i FROM t").fetchall():
        assert f == _f32(rows[rowid])
        assert i == _f32([-x for x in rows[rowid]])
    for rowid, vec in rows.items():
        for column, value in (("f", vec), ("i", [-x for x in vec])):
            got = db.execute(
                f"SELECT rowid FROM t WHERE {column} MATCH ? AND k = 1", [_f32(value)]
            ).fetchone()[0]
            assert got == rowid
