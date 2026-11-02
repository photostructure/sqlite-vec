import random
import sqlite3
import struct
import pytest
from collections import OrderedDict


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


def test_diskann_create_basic(db):
    """Basic DiskANN table creation with binary quantizer should succeed."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[128] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    # Table should exist
    tables = [
        row[0]
        for row in db.execute(
            "select name from sqlite_master where name like 't%' order by 1"
        ).fetchall()
    ]
    assert "t" in tables


def test_diskann_create_int8_quantizer(db):
    """DiskANN with int8 quantizer should succeed."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[64] INDEXED BY diskann(neighbor_quantizer=int8)
        )
    """)
    tables = [
        row[0]
        for row in db.execute(
            "select name from sqlite_master where name like 't%' order by 1"
        ).fetchall()
    ]
    assert "t" in tables


def test_diskann_create_with_options(db):
    """DiskANN with custom n_neighbors and search_list_size."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[128] INDEXED BY diskann(
                neighbor_quantizer=binary,
                n_neighbors=48,
                search_list_size=256
            )
        )
    """)
    tables = [
        row[0]
        for row in db.execute(
            "select name from sqlite_master where name like 't%' order by 1"
        ).fetchall()
    ]
    assert "t" in tables


def test_diskann_create_with_distance_metric(db):
    """DiskANN combined with distance_metric should work."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[128] distance_metric=cosine INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    tables = [
        row[0]
        for row in db.execute(
            "select name from sqlite_master where name like 't%' order by 1"
        ).fetchall()
    ]
    assert "t" in tables


def test_diskann_create_error_missing_quantizer(db):
    """Error when neighbor_quantizer is not specified."""
    result = exec(
        db,
        """
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[128] INDEXED BY diskann(n_neighbors=72)
        )
    """,
    )
    assert "error" in result


def test_diskann_create_error_empty_parens(db):
    """Error on empty parens."""
    result = exec(
        db,
        """
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[128] INDEXED BY diskann()
        )
    """,
    )
    assert "error" in result


def test_diskann_create_error_unknown_quantizer(db):
    """Error on unknown quantizer type."""
    result = exec(
        db,
        """
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[128] INDEXED BY diskann(neighbor_quantizer=unknown)
        )
    """,
    )
    assert "error" in result


def test_diskann_create_error_bit_column(db):
    """Error: DiskANN not supported on bit vector columns."""
    result = exec(
        db,
        """
        CREATE VIRTUAL TABLE t USING vec0(
            emb bit[128] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """,
    )
    assert "error" in result
    assert "bit" in result["message"].lower() or "DiskANN" in result["message"]


def test_diskann_create_error_binary_quantizer_odd_dims(db):
    """Error: binary quantizer requires dimensions divisible by 8."""
    result = exec(
        db,
        """
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[13] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """,
    )
    assert "error" in result
    assert "divisible" in result["message"].lower()


def test_diskann_create_error_bad_n_neighbors(db):
    """Error: n_neighbors must be divisible by 8."""
    result = exec(
        db,
        """
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[128] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=13)
        )
    """,
    )
    assert "error" in result


def test_diskann_shadow_tables_created(db):
    """DiskANN table should create _vectors00 and _diskann_nodes00 shadow tables."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[64] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    tables = sorted(
        [
            row[0]
            for row in db.execute(
                "select name from sqlite_master where type='table' and name like 't_%' order by 1"
            ).fetchall()
        ]
    )
    assert "t_vectors00" in tables
    assert "t_diskann_nodes00" in tables
    # DiskANN columns should NOT have _vector_chunks00
    assert "t_vector_chunks00" not in tables


def test_diskann_medoid_in_info(db):
    """_info table should contain diskann_medoid_00 key with NULL value."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[64] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    row = db.execute(
        "SELECT key, value FROM t_info WHERE key = 'diskann_medoid_00'"
    ).fetchone()
    assert row is not None
    assert row[0] == "diskann_medoid_00"
    assert row[1] is None


def test_non_diskann_no_extra_tables(db):
    """Non-DiskANN table must NOT create _vectors or _diskann_nodes tables."""
    db.execute("CREATE VIRTUAL TABLE t USING vec0(emb float[64])")
    tables = [
        row[0]
        for row in db.execute(
            "select name from sqlite_master where type='table' and name like 't_%' order by 1"
        ).fetchall()
    ]
    assert "t_vectors00" not in tables
    assert "t_diskann_nodes00" not in tables
    assert "t_vector_chunks00" in tables


def test_diskann_medoid_initial_null(db):
    """Medoid should be NULL initially (empty graph)."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[64] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    row = db.execute(
        "SELECT value FROM t_info WHERE key = 'diskann_medoid_00'"
    ).fetchone()
    assert row[0] is None


def test_diskann_medoid_set_via_info(db):
    """Setting medoid via _info table should be retrievable."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[64] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    # Manually set medoid to simulate first insert
    db.execute("UPDATE t_info SET value = 42 WHERE key = 'diskann_medoid_00'")
    row = db.execute(
        "SELECT value FROM t_info WHERE key = 'diskann_medoid_00'"
    ).fetchone()
    assert row[0] == 42

    # Reset to NULL (empty graph)
    db.execute("UPDATE t_info SET value = NULL WHERE key = 'diskann_medoid_00'")
    row = db.execute(
        "SELECT value FROM t_info WHERE key = 'diskann_medoid_00'"
    ).fetchone()
    assert row[0] is None


def test_diskann_single_insert(db):
    """Insert 1 vector. Verify _vectors00, _diskann_nodes00, and medoid."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    db.execute(
        "INSERT INTO t(rowid, emb) VALUES (1, ?)",
        [_f32([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])],
    )
    # Verify _vectors00 has 1 row
    count = db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0]
    assert count == 1

    # Verify _diskann_nodes00 has 1 row
    count = db.execute("SELECT count(*) FROM t_diskann_nodes00").fetchone()[0]
    assert count == 1

    # Verify medoid is set
    medoid = db.execute(
        "SELECT value FROM t_info WHERE key = 'diskann_medoid_00'"
    ).fetchone()[0]
    assert medoid == 1


def test_diskann_multiple_inserts(db):
    """Insert multiple vectors. Verify counts and that nodes have neighbors."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    import random

    random.seed(42)
    for i in range(1, 21):
        vec = [random.gauss(0, 1) for _ in range(8)]
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, _f32(vec)])

    # Verify counts
    assert db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0] == 20
    assert db.execute("SELECT count(*) FROM t_diskann_nodes00").fetchone()[0] == 20

    # Every node after the first should have at least 1 neighbor
    rows = db.execute(
        "SELECT rowid, neighbors_validity FROM t_diskann_nodes00"
    ).fetchall()
    nodes_with_neighbors = 0
    for row in rows:
        validity = row[1]
        has_neighbor = any(b != 0 for b in validity)
        if has_neighbor:
            nodes_with_neighbors += 1
    # At minimum, nodes 2-20 should have neighbors (node 1 gets neighbors via reverse edges)
    assert nodes_with_neighbors >= 19


def test_diskann_bidirectional_edges(db):
    """Insert A then B. B should be in A's neighbors and A in B's."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    db.execute(
        "INSERT INTO t(rowid, emb) VALUES (1, ?)",
        [_f32([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])],
    )
    db.execute(
        "INSERT INTO t(rowid, emb) VALUES (2, ?)",
        [_f32([0.9, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])],
    )

    # Check B(2) is in A(1)'s neighbor list
    row_a = db.execute(
        "SELECT neighbor_ids FROM t_diskann_nodes00 WHERE rowid = 1"
    ).fetchone()
    neighbor_ids_a = struct.unpack(f"{len(row_a[0])//8}q", row_a[0])
    assert 2 in neighbor_ids_a

    # Check A(1) is in B(2)'s neighbor list
    row_b = db.execute(
        "SELECT neighbor_ids FROM t_diskann_nodes00 WHERE rowid = 2"
    ).fetchone()
    neighbor_ids_b = struct.unpack(f"{len(row_b[0])//8}q", row_b[0])
    assert 1 in neighbor_ids_b


def test_diskann_delete_single(db):
    """Insert 3, delete 1. Verify counts."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    for i in range(1, 4):
        db.execute(
            "INSERT INTO t(rowid, emb) VALUES (?, ?)",
            [i, _f32([float(i)] * 8)],
        )
    db.execute("DELETE FROM t WHERE rowid = 2")

    assert db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0] == 2
    assert db.execute("SELECT count(*) FROM t_diskann_nodes00").fetchone()[0] == 2


def test_diskann_delete_no_stale_references(db):
    """After delete, no node should reference the deleted rowid."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    import random

    random.seed(123)
    for i in range(1, 11):
        vec = [random.gauss(0, 1) for _ in range(8)]
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, _f32(vec)])

    db.execute("DELETE FROM t WHERE rowid = 5")

    # Scan all remaining nodes and verify rowid 5 is not in any neighbor list
    rows = db.execute(
        "SELECT rowid, neighbors_validity, neighbor_ids FROM t_diskann_nodes00"
    ).fetchall()
    for row in rows:
        validity = row[1]
        neighbor_ids_blob = row[2]
        n_neighbors = len(validity) * 8
        ids = struct.unpack(f"{n_neighbors}q", neighbor_ids_blob)
        for i in range(n_neighbors):
            byte_idx = i // 8
            bit_idx = i % 8
            if validity[byte_idx] & (1 << bit_idx):
                assert ids[i] != 5, f"Node {row[0]} still references deleted rowid 5"


def test_diskann_delete_medoid(db):
    """Delete the medoid. Verify a new non-NULL medoid is selected."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    for i in range(1, 4):
        db.execute(
            "INSERT INTO t(rowid, emb) VALUES (?, ?)",
            [i, _f32([float(i)] * 8)],
        )

    medoid_before = db.execute(
        "SELECT value FROM t_info WHERE key = 'diskann_medoid_00'"
    ).fetchone()[0]
    assert medoid_before == 1

    db.execute("DELETE FROM t WHERE rowid = 1")

    medoid_after = db.execute(
        "SELECT value FROM t_info WHERE key = 'diskann_medoid_00'"
    ).fetchone()[0]
    assert medoid_after is not None
    assert medoid_after != 1


def test_diskann_delete_all(db):
    """Delete all vectors. Medoid should be NULL."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    for i in range(1, 4):
        db.execute(
            "INSERT INTO t(rowid, emb) VALUES (?, ?)",
            [i, _f32([float(i)] * 8)],
        )
    for i in range(1, 4):
        db.execute("DELETE FROM t WHERE rowid = ?", [i])

    assert db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM t_diskann_nodes00").fetchone()[0] == 0

    medoid = db.execute(
        "SELECT value FROM t_info WHERE key = 'diskann_medoid_00'"
    ).fetchone()[0]
    assert medoid is None


def test_diskann_insert_delete_insert_cycle(db):
    """Insert, delete, insert again. No crashes."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    db.execute("INSERT INTO t(rowid, emb) VALUES (1, ?)", [_f32([1.0] * 8)])
    db.execute("INSERT INTO t(rowid, emb) VALUES (2, ?)", [_f32([2.0] * 8)])
    db.execute("DELETE FROM t WHERE rowid = 1")
    db.execute("INSERT INTO t(rowid, emb) VALUES (3, ?)", [_f32([3.0] * 8)])

    assert db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0] == 2
    assert db.execute("SELECT count(*) FROM t_diskann_nodes00").fetchone()[0] == 2


def test_diskann_knn_basic(db):
    """Basic KNN query should return results."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    db.execute(
        "INSERT INTO t(rowid, emb) VALUES (1, ?)", [_f32([1, 0, 0, 0, 0, 0, 0, 0])]
    )
    db.execute(
        "INSERT INTO t(rowid, emb) VALUES (2, ?)", [_f32([0, 1, 0, 0, 0, 0, 0, 0])]
    )
    db.execute(
        "INSERT INTO t(rowid, emb) VALUES (3, ?)", [_f32([0.9, 0.1, 0, 0, 0, 0, 0, 0])]
    )

    rows = db.execute(
        "SELECT rowid, distance FROM t WHERE emb MATCH ? AND k=2",
        [_f32([1, 0, 0, 0, 0, 0, 0, 0])],
    ).fetchall()
    assert len(rows) == 2
    # Closest should be rowid 1 (exact match)
    assert rows[0][0] == 1
    assert rows[0][1] < 0.01  # ~0 distance


def test_diskann_knn_distances_sorted(db):
    """Returned distances should be in ascending order."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=16)
        )
    """)
    import random

    random.seed(42)
    for i in range(1, 51):
        vec = [random.gauss(0, 1) for _ in range(8)]
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, _f32(vec)])

    rows = db.execute(
        "SELECT rowid, distance FROM t WHERE emb MATCH ? AND k=10",
        [_f32([0.0] * 8)],
    ).fetchall()
    assert len(rows) == 10
    distances = [r[1] for r in rows]
    for i in range(len(distances) - 1):
        assert distances[i] <= distances[i + 1], f"Distances not sorted at index {i}"


def test_diskann_knn_empty_table(db):
    """KNN on empty table should return 0 results."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    rows = db.execute(
        "SELECT rowid, distance FROM t WHERE emb MATCH ? AND k=5",
        [_f32([1, 0, 0, 0, 0, 0, 0, 0])],
    ).fetchall()
    assert len(rows) == 0


def test_diskann_knn_after_delete(db):
    """KNN after delete should not return deleted rows."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    db.execute(
        "INSERT INTO t(rowid, emb) VALUES (1, ?)", [_f32([1, 0, 0, 0, 0, 0, 0, 0])]
    )
    db.execute(
        "INSERT INTO t(rowid, emb) VALUES (2, ?)", [_f32([0, 1, 0, 0, 0, 0, 0, 0])]
    )
    db.execute(
        "INSERT INTO t(rowid, emb) VALUES (3, ?)", [_f32([0.5, 0.5, 0, 0, 0, 0, 0, 0])]
    )
    db.execute("DELETE FROM t WHERE rowid = 1")

    rows = db.execute(
        "SELECT rowid, distance FROM t WHERE emb MATCH ? AND k=3",
        [_f32([1, 0, 0, 0, 0, 0, 0, 0])],
    ).fetchall()
    rowids = [r[0] for r in rows]
    assert 1 not in rowids
    assert len(rows) == 2


def test_diskann_no_index_still_works(db):
    """Tables without INDEXED BY should still work identically."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[4]
        )
    """)
    db.execute("INSERT INTO t(rowid, emb) VALUES (1, ?)", [_f32([1, 2, 3, 4])])
    rows = db.execute(
        "SELECT rowid, distance FROM t WHERE emb MATCH ? AND k=1",
        [_f32([1, 2, 3, 4])],
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 1


def test_diskann_drop_table(db):
    """DROP TABLE should clean up all shadow tables."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[128] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    db.execute("DROP TABLE t")
    tables = [
        row[0]
        for row in db.execute(
            "select name from sqlite_master where name like 't%'"
        ).fetchall()
    ]
    assert len(tables) == 0


def test_diskann_create_split_search_list_size(db):
    """DiskANN with separate search_list_size_search and search_list_size_insert."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[128] INDEXED BY diskann(
                neighbor_quantizer=binary,
                search_list_size_search=256,
                search_list_size_insert=64
            )
        )
    """)
    tables = [
        row[0]
        for row in db.execute(
            "select name from sqlite_master where name like 't%' order by 1"
        ).fetchall()
    ]
    assert "t" in tables


def test_diskann_create_error_mixed_search_list_size(db):
    """Error when mixing search_list_size with search_list_size_search."""
    result = exec(
        db,
        """
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[128] INDEXED BY diskann(
                neighbor_quantizer=binary,
                search_list_size=128,
                search_list_size_search=256
            )
        )
    """,
    )
    assert "error" in result


def test_diskann_command_search_list_size(db):
    """search_list_size=N changes a query's search on a table with no split size."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[16] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    for rowid, vec in _random_rows(42, 200, 16).items():
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [rowid, _f32(vec)])
    rng = random.Random(43)
    queries = [_f32([rng.uniform(-1, 1) for _ in range(16)]) for _ in range(10)]

    def knn():
        sql = "SELECT rowid FROM t WHERE emb MATCH ? AND k = 10"
        return [[r[0] for r in db.execute(sql, [q])] for q in queries]

    before = knn()
    db.execute("INSERT INTO t(t) VALUES ('search_list_size=1')")
    assert knn() != before


def test_diskann_command_search_list_size_insert(db):
    """
    After search_list_size_insert=N, inserts build the graph a table created
    with search_list_size_insert=N builds.
    """
    for name, option in [("t", ""), ("r", ", search_list_size_insert=2")]:
        db.execute(f"""
            CREATE VIRTUAL TABLE {name} USING vec0(
                emb float[16] INDEXED BY diskann(neighbor_quantizer=binary{option})
            )
        """)
    db.execute("INSERT INTO t(t) VALUES ('search_list_size_insert=2')")
    for rowid, vec in _random_rows(44, 200, 16).items():
        for name in ("t", "r"):
            db.execute(
                f"INSERT INTO {name}(rowid, emb) VALUES (?, ?)", [rowid, _f32(vec)]
            )
    nodes = "SELECT * FROM {}_diskann_nodes00 ORDER BY rowid"
    assert (
        db.execute(nodes.format("t")).fetchall()
        == db.execute(nodes.format("r")).fetchall()
    )


def test_diskann_command_search_list_size_error(db):
    """Error on invalid search_list_size command value."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[64] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    result = exec(db, "INSERT INTO t(t) VALUES ('search_list_size=0')")
    assert "error" in result
    result = exec(db, "INSERT INTO t(t) VALUES ('search_list_size=-1')")
    assert "error" in result


# ======================================================================
# Error cases: DiskANN + auxiliary/metadata/partition columns
# ======================================================================


def test_diskann_create_with_auxiliary_column(db):
    """DiskANN tables should support auxiliary columns."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[64] INDEXED BY diskann(neighbor_quantizer=binary),
            +extra text
        )
    """)
    # Auxiliary shadow table should exist
    tables = [
        r[0]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 't_%' ORDER BY 1"
        ).fetchall()
    ]
    assert "t_auxiliary" in tables


def test_diskann_create_error_with_metadata_column(db):
    """DiskANN tables should not support metadata columns."""
    with pytest.raises(
        sqlite3.OperationalError,
        match="^vec0 constructor error: Metadata columns are not supported "
        "with DiskANN-indexed vector columns$",
    ):
        db.execute("""
            CREATE VIRTUAL TABLE t USING vec0(
                emb float[64] INDEXED BY diskann(neighbor_quantizer=binary),
                metadata_col integer
            )
        """)


def test_diskann_create_error_with_partition_key(db):
    """DiskANN tables should not support partition key columns."""
    result = exec(
        db,
        """
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[64] INDEXED BY diskann(neighbor_quantizer=binary),
            user_id text partition key
        )
    """,
    )
    assert "error" in result
    assert "partition" in result["message"].lower() or "Partition" in result["message"]


# ======================================================================
# Insert edge cases
# ======================================================================


def test_diskann_insert_no_rowid(db):
    """INSERT without explicit rowid (auto-generated) should work."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    db.execute("INSERT INTO t(emb) VALUES (?)", [_f32([1.0] * 8)])
    db.execute("INSERT INTO t(emb) VALUES (?)", [_f32([2.0] * 8)])
    assert db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0] == 2
    assert db.execute("SELECT count(*) FROM t_diskann_nodes00").fetchone()[0] == 2


def test_diskann_insert_large_batch(db):
    """INSERT 500 vectors, and each one's own vector finds it via KNN."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[16] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=16)
        )
    """)
    import random

    random.seed(99)
    N = 500
    for i in range(1, N + 1):
        vec = [random.gauss(0, 1) for _ in range(16)]
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, _f32(vec)])

    assert db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0] == N
    assert db.execute("SELECT count(*) FROM t_diskann_nodes00").fetchone()[0] == N

    # KNN should return results
    query = [random.gauss(0, 1) for _ in range(16)]
    rows = db.execute(
        "SELECT rowid, distance FROM t WHERE emb MATCH ? AND k=10",
        [_f32(query)],
    ).fetchall()
    assert len(rows) == 10
    # Distances should be sorted
    distances = [r[1] for r in rows]
    for i in range(len(distances) - 1):
        assert distances[i] <= distances[i + 1]

    for rowid, vector in db.execute("SELECT rowid, vector FROM t_vectors00"):
        found = db.execute(
            "SELECT rowid FROM t WHERE emb MATCH ? AND k = 1", [vector]
        ).fetchone()[0]
        assert found == rowid


def test_diskann_insert_zero_vector(db):
    """Insert an all-zero vector (edge case for binary quantizer)."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    db.execute("INSERT INTO t(rowid, emb) VALUES (1, ?)", [_f32([0.0] * 8)])
    db.execute("INSERT INTO t(rowid, emb) VALUES (2, ?)", [_f32([1.0] * 8)])
    count = db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0]
    assert count == 2

    # Query with zero vector should find rowid 1 as closest
    rows = db.execute(
        "SELECT rowid, distance FROM t WHERE emb MATCH ? AND k=2",
        [_f32([0.0] * 8)],
    ).fetchall()
    assert len(rows) == 2
    assert rows[0][0] == 1


def test_diskann_insert_large_values(db):
    """Insert vectors with very large float values."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    import sys

    large = sys.float_info.max / 1e300  # Large but not overflowing
    db.execute("INSERT INTO t(rowid, emb) VALUES (1, ?)", [_f32([large] * 8)])
    db.execute("INSERT INTO t(rowid, emb) VALUES (2, ?)", [_f32([-large] * 8)])
    db.execute("INSERT INTO t(rowid, emb) VALUES (3, ?)", [_f32([0.0] * 8)])
    assert db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0] == 3


def test_diskann_insert_int8_quantizer_knn(db):
    """Full insert + query cycle with int8 quantizer."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[16] INDEXED BY diskann(neighbor_quantizer=int8, n_neighbors=8)
        )
    """)
    import random

    random.seed(77)
    for i in range(1, 31):
        vec = [random.gauss(0, 1) for _ in range(16)]
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, _f32(vec)])

    assert db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0] == 30

    # KNN should work
    query = [random.gauss(0, 1) for _ in range(16)]
    rows = db.execute(
        "SELECT rowid, distance FROM t WHERE emb MATCH ? AND k=5",
        [_f32(query)],
    ).fetchall()
    assert len(rows) == 5
    distances = [r[1] for r in rows]
    for i in range(len(distances) - 1):
        assert distances[i] <= distances[i + 1]


# ======================================================================
# Delete edge cases
# ======================================================================


def test_diskann_delete_nonexistent(db):
    """DELETE of a rowid the table does not have deletes nothing."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    db.execute("INSERT INTO t(rowid, emb) VALUES (1, ?)", [_f32([1.0] * 8)])
    db.execute("DELETE FROM t WHERE rowid = 999")
    assert db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0] == 1


def test_diskann_delete_then_reinsert_same_rowid(db):
    """Delete rowid 5, then reinsert rowid 5 with a new vector."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    for i in range(1, 6):
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, _f32([float(i)] * 8)])

    db.execute("DELETE FROM t WHERE rowid = 5")
    assert db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0] == 4

    # Reinsert with new vector
    db.execute("INSERT INTO t(rowid, emb) VALUES (5, ?)", [_f32([99.0] * 8)])
    assert db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0] == 5
    assert db.execute("SELECT count(*) FROM t_diskann_nodes00").fetchone()[0] == 5


def test_diskann_delete_all_then_insert(db):
    """Delete everything, then insert new vectors. Graph should rebuild."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    for i in range(1, 6):
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, _f32([float(i)] * 8)])

    # Delete all
    for i in range(1, 6):
        db.execute("DELETE FROM t WHERE rowid = ?", [i])
    assert db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0] == 0

    medoid = db.execute(
        "SELECT value FROM t_info WHERE key = 'diskann_medoid_00'"
    ).fetchone()[0]
    assert medoid is None

    # Insert new vectors
    for i in range(10, 15):
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, _f32([float(i)] * 8)])

    assert db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0] == 5
    assert db.execute("SELECT count(*) FROM t_diskann_nodes00").fetchone()[0] == 5

    medoid = db.execute(
        "SELECT value FROM t_info WHERE key = 'diskann_medoid_00'"
    ).fetchone()[0]
    assert medoid is not None

    # KNN should work
    rows = db.execute(
        "SELECT rowid FROM t WHERE emb MATCH ? AND k=3",
        [_f32([12.0] * 8)],
    ).fetchall()
    assert len(rows) == 3


def test_diskann_delete_preserves_graph_connectivity(db):
    """After deleting a node, remaining nodes should still be reachable via KNN."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    import random

    random.seed(456)
    for i in range(1, 21):
        vec = [random.gauss(0, 1) for _ in range(8)]
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, _f32(vec)])

    # Delete 5 nodes
    for i in [3, 7, 11, 15, 19]:
        db.execute("DELETE FROM t WHERE rowid = ?", [i])

    remaining = db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0]
    assert remaining == 15

    # Every remaining node should be reachable via KNN (appears somewhere in top-k)
    all_rowids = [r[0] for r in db.execute("SELECT rowid FROM t_vectors00").fetchall()]
    reachable = set()
    for rid in all_rowids:
        vec_blob = db.execute(
            "SELECT vector FROM t_vectors00 WHERE rowid = ?", [rid]
        ).fetchone()[0]
        rows = db.execute(
            "SELECT rowid FROM t WHERE emb MATCH ? AND k=5",
            [vec_blob],
        ).fetchall()
        assert len(rows) >= 1  # At least some results
        for r in rows:
            reachable.add(r[0])
    # Most nodes should be reachable through the graph
    assert (
        len(reachable) >= len(all_rowids) * 0.8
    ), f"Only {len(reachable)}/{len(all_rowids)} nodes reachable"


# ======================================================================
# Update scenarios
# ======================================================================


def test_diskann_update_vector(db):
    """UPDATE a vector on DiskANN table should error (will be implemented soon)."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    db.execute(
        "INSERT INTO t(rowid, emb) VALUES (1, ?)", [_f32([1, 0, 0, 0, 0, 0, 0, 0])]
    )
    db.execute(
        "INSERT INTO t(rowid, emb) VALUES (2, ?)", [_f32([0, 1, 0, 0, 0, 0, 0, 0])]
    )
    db.execute(
        "INSERT INTO t(rowid, emb) VALUES (3, ?)", [_f32([0, 0, 1, 0, 0, 0, 0, 0])]
    )

    with pytest.raises(
        sqlite3.OperationalError,
        match="UPDATE on vector column.*not supported for DiskANN",
    ):
        db.execute(
            "UPDATE t SET emb = ? WHERE rowid = 1", [_f32([0, 0.9, 0.1, 0, 0, 0, 0, 0])]
        )


# ======================================================================
# KNN correctness after mutations
# ======================================================================


def test_diskann_knn_recall_after_inserts(db):
    """Insert N vectors, verify top-1 recall is 100% for exact matches."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=16)
        )
    """)
    import random

    random.seed(200)
    vectors = {}
    for i in range(1, 51):
        vec = [random.gauss(0, 1) for _ in range(8)]
        vectors[i] = vec
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, _f32(vec)])

    # Top-1 for each vector should return itself
    correct = 0
    for rid, vec in vectors.items():
        rows = db.execute(
            "SELECT rowid FROM t WHERE emb MATCH ? AND k=1",
            [_f32(vec)],
        ).fetchall()
        if rows and rows[0][0] == rid:
            correct += 1

    # The 50 rows fit in the search list, and results rank by exact distance
    assert correct == len(vectors), f"Top-1 recall: {correct}/{len(vectors)}"


def test_diskann_knn_k_larger_than_table(db):
    """k=100 on table with 5 rows should return 5."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    for i in range(1, 6):
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, _f32([float(i)] * 8)])

    rows = db.execute(
        "SELECT rowid, distance FROM t WHERE emb MATCH ? AND k=100",
        [_f32([3.0] * 8)],
    ).fetchall()
    assert len(rows) == 5


def test_diskann_knn_cosine_metric(db):
    """
    KNN ranks by cosine distance and returns it: rows whose norms differ rank
    otherwise under L2 (1, 5, 3, 2, 4).
    """
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] distance_metric=cosine INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    vectors = {
        1: [1, 0],
        2: [0, 1],
        3: [0.7, 0.7],
        4: [10, 5],
        5: [0.3, 0.1],
    }
    for rowid, vec in vectors.items():
        db.execute(
            "INSERT INTO t(rowid, emb) VALUES (?, ?)", [rowid, _f32(vec + [0] * 6)]
        )
    query = _f32([1] + [0] * 7)
    rows = db.execute(
        "SELECT rowid, distance, vec_distance_cosine(emb, ?) FROM t"
        " WHERE emb MATCH ? AND k = 5",
        [query, query],
    ).fetchall()
    assert [r[0] for r in rows] == [1, 5, 4, 3, 2]
    for _, distance, cosine in rows:
        assert distance == pytest.approx(cosine, abs=1e-6)


def test_diskann_knn_after_heavy_churn(db):
    """Interleave many inserts and deletes, then query."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=16)
        )
    """)
    import random

    random.seed(321)

    # Insert 50 vectors
    for i in range(1, 51):
        vec = [random.gauss(0, 1) for _ in range(8)]
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, _f32(vec)])

    # Delete even-numbered rows
    for i in range(2, 51, 2):
        db.execute("DELETE FROM t WHERE rowid = ?", [i])

    # Insert more vectors with higher rowids
    for i in range(51, 76):
        vec = [random.gauss(0, 1) for _ in range(8)]
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, _f32(vec)])

    remaining = db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0]
    assert remaining == 50  # 25 odd + 25 new

    # KNN should still work and return results
    query = [random.gauss(0, 1) for _ in range(8)]
    rows = db.execute(
        "SELECT rowid, distance FROM t WHERE emb MATCH ? AND k=10",
        [_f32(query)],
    ).fetchall()
    assert len(rows) == 10
    # Distances should be sorted
    distances = [r[1] for r in rows]
    for i in range(len(distances) - 1):
        assert distances[i] <= distances[i + 1]


def test_diskann_knn_batch_recall(db):
    """Insert 100+ vectors and verify reasonable recall."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[16] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=16)
        )
    """)
    import random

    random.seed(42)
    N = 150
    vectors = {}
    for i in range(1, N + 1):
        vec = [random.gauss(0, 1) for _ in range(16)]
        vectors[i] = vec
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, _f32(vec)])

    # Brute-force top-5 for a query and compare with DiskANN
    query = [random.gauss(0, 1) for _ in range(16)]

    # Compute true distances
    true_dists = []
    for rid, vec in vectors.items():
        d = sum((a - b) ** 2 for a, b in zip(query, vec))
        true_dists.append((d, rid))
    true_dists.sort()
    true_top5 = set(r for _, r in true_dists[:5])

    rows = db.execute(
        "SELECT rowid, distance FROM t WHERE emb MATCH ? AND k=5",
        [_f32(query)],
    ).fetchall()
    result_top5 = set(r[0] for r in rows)
    assert len(rows) == 5

    # At least 3 of top-5 should match (reasonable recall for approximate search)
    overlap = len(true_top5 & result_top5)
    assert overlap >= 3, f"Recall too low: only {overlap}/5 overlap"


# ======================================================================
# Additional edge cases
# ======================================================================


def test_diskann_insert_wrong_dimensions(db):
    """INSERT with wrong dimension vector should error."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    result = exec(db, "INSERT INTO t(rowid, emb) VALUES (1, ?)", [_f32([1.0] * 4)])
    assert "error" in result


def test_diskann_knn_wrong_query_dimensions(db):
    """KNN MATCH with wrong dimension query should error."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    db.execute("INSERT INTO t(rowid, emb) VALUES (1, ?)", [_f32([1.0] * 8)])

    result = exec(
        db, "SELECT rowid FROM t WHERE emb MATCH ? AND k=1", [_f32([1.0] * 4)]
    )
    assert "error" in result


def test_diskann_graph_connectivity_after_many_deletes(db):
    """After many deletes, the graph should still be connected enough for search."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=16)
        )
    """)
    import random

    random.seed(789)
    N = 40
    for i in range(1, N + 1):
        vec = [random.gauss(0, 1) for _ in range(8)]
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, _f32(vec)])

    # Delete 30 of 40 nodes
    to_delete = list(range(1, 31))
    for i in to_delete:
        db.execute("DELETE FROM t WHERE rowid = ?", [i])

    remaining = db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0]
    assert remaining == 10

    # Search should still work and return results
    query = [random.gauss(0, 1) for _ in range(8)]
    rows = db.execute(
        "SELECT rowid, distance FROM t WHERE emb MATCH ? AND k=10",
        [_f32(query)],
    ).fetchall()
    # Should return some results (graph may be fragmented after heavy deletion)
    assert len(rows) >= 1
    # Distances should be sorted
    distances = [r[1] for r in rows]
    for i in range(len(distances) - 1):
        assert distances[i] <= distances[i + 1]


def test_diskann_large_batch_insert_500(db):
    """Insert 500+ vectors and verify counts and KNN."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=16)
        )
    """)
    import random

    random.seed(555)
    N = 500
    for i in range(1, N + 1):
        vec = [random.gauss(0, 1) for _ in range(8)]
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, _f32(vec)])

    assert db.execute("SELECT count(*) FROM t_vectors00").fetchone()[0] == N

    query = [random.gauss(0, 1) for _ in range(8)]
    rows = db.execute(
        "SELECT rowid, distance FROM t WHERE emb MATCH ? AND k=20",
        [_f32(query)],
    ).fetchall()
    assert len(rows) == 20
    distances = [r[1] for r in rows]
    for i in range(len(distances) - 1):
        assert distances[i] <= distances[i + 1]


def test_corrupt_truncated_node_blob(db):
    """KNN should error (not crash) when DiskANN node blob is truncated."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    for i in range(5):
        vec = [0.0] * 8
        vec[i % 8] = 1.0
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i + 1, _f32(vec)])

    # Corrupt a DiskANN node: truncate neighbor_ids to 1 byte (wrong size)
    db.execute("UPDATE t_diskann_nodes00 SET neighbor_ids = x'00' WHERE rowid = 1")

    # Should not crash — may return wrong results or error
    try:
        db.execute(
            "SELECT rowid FROM t WHERE emb MATCH ? AND k=3",
            [_f32([1, 0, 0, 0, 0, 0, 0, 0])],
        ).fetchall()
    except sqlite3.OperationalError:
        pass  # Error is acceptable — crash is not


def test_diskann_delete_reinsert_cycle_knn(db):
    """Repeatedly delete and reinsert rows, verify KNN stays correct."""
    import random

    random.seed(101)
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    N = 30
    vecs = {}
    for i in range(1, N + 1):
        v = [random.gauss(0, 1) for _ in range(8)]
        vecs[i] = v
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, _f32(v)])

    # 3 cycles: delete half, reinsert with new vectors, verify KNN
    for cycle in range(3):
        to_delete = random.sample(sorted(vecs.keys()), len(vecs) // 2)
        for r in to_delete:
            db.execute("DELETE FROM t WHERE rowid = ?", [r])
            del vecs[r]

        # Reinsert with new rowids
        new_start = 100 + cycle * 50
        for i in range(len(to_delete)):
            rid = new_start + i
            v = [random.gauss(0, 1) for _ in range(8)]
            vecs[rid] = v
            db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [rid, _f32(v)])

        # KNN should return only alive rows
        query = [0.0] * 8
        rows = db.execute(
            "SELECT rowid FROM t WHERE emb MATCH ? AND k=10",
            [_f32(query)],
        ).fetchall()
        returned = {r["rowid"] for r in rows}
        assert returned.issubset(
            set(vecs.keys())
        ), f"Cycle {cycle}: deleted rowid in KNN results"
        assert len(rows) >= 1


def test_diskann_delete_interleaved_with_knn(db):
    """Delete one row at a time, querying KNN after each delete."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    N = 20
    for i in range(1, N + 1):
        vec = [0.0] * 8
        vec[i % 8] = float(i)
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, _f32(vec)])

    alive = set(range(1, N + 1))
    for to_del in [1, 5, 10, 15, 20]:
        db.execute("DELETE FROM t WHERE rowid = ?", [to_del])
        alive.discard(to_del)

        rows = db.execute(
            "SELECT rowid FROM t WHERE emb MATCH ? AND k=5",
            [_f32([1, 0, 0, 0, 0, 0, 0, 0])],
        ).fetchall()
        returned = {r["rowid"] for r in rows}
        assert returned.issubset(alive), f"Deleted rowid {to_del} found in KNN results"


# ======================================================================
# Text primary key + DiskANN
# ======================================================================


def test_diskann_text_pk_insert_knn_delete(db):
    """DiskANN with text primary key: insert, KNN, delete, KNN again."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            id text primary key,
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)

    vecs = {
        "alpha": [1, 0, 0, 0, 0, 0, 0, 0],
        "beta": [0, 1, 0, 0, 0, 0, 0, 0],
        "gamma": [0, 0, 1, 0, 0, 0, 0, 0],
        "delta": [0, 0, 0, 1, 0, 0, 0, 0],
        "epsilon": [0, 0, 0, 0, 1, 0, 0, 0],
    }
    for name, vec in vecs.items():
        db.execute("INSERT INTO t(id, emb) VALUES (?, ?)", [name, _f32(vec)])

    # KNN should return text IDs
    rows = db.execute(
        "SELECT id, distance FROM t WHERE emb MATCH ? AND k=3",
        [_f32([1, 0, 0, 0, 0, 0, 0, 0])],
    ).fetchall()
    assert len(rows) >= 1
    ids = [r["id"] for r in rows]
    assert "alpha" in ids  # closest to query

    # Delete and verify
    db.execute("DELETE FROM t WHERE id = 'alpha'")
    rows = db.execute(
        "SELECT id FROM t WHERE emb MATCH ? AND k=3",
        [_f32([1, 0, 0, 0, 0, 0, 0, 0])],
    ).fetchall()
    ids = [r["id"] for r in rows]
    assert "alpha" not in ids


def test_diskann_delete_scrubs_all_references(db):
    """After DELETE, no shadow table should contain the deleted rowid or its data."""
    import struct

    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    for i in range(20):
        vec = struct.pack("8f", *[float(i + d) for d in range(8)])
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, vec])

    target = 5
    db.execute("DELETE FROM t WHERE rowid = ?", [target])

    # Node row itself should be gone
    assert (
        db.execute(
            "SELECT count(*) FROM t_diskann_nodes00 WHERE rowid=?", [target]
        ).fetchone()[0]
        == 0
    )

    # Vector should be gone
    assert (
        db.execute(
            "SELECT count(*) FROM t_vectors00 WHERE rowid=?", [target]
        ).fetchone()[0]
        == 0
    )

    # No other node should reference the deleted rowid in neighbor_ids
    for row in db.execute("SELECT rowid, neighbor_ids FROM t_diskann_nodes00"):
        node_rowid = row[0]
        ids_blob = row[1]
        for j in range(0, len(ids_blob), 8):
            nid = struct.unpack("<q", ids_blob[j : j + 8])[0]
            assert nid != target, (
                f"Node {node_rowid} slot {j // 8} still references "
                f"deleted rowid {target}"
            )


# ======================================================================
# KNN constraints, int8 columns and exact distances
# ======================================================================


def _random_rows(seed, n, dims):
    rng = random.Random(seed)
    return {i: [rng.uniform(-1, 1) for _ in range(dims)] for i in range(1, n + 1)}


# A search list as long as the table holds every row, so the KNN of a DiskANN
# column must answer as a flat column does, constraint for constraint.
@pytest.mark.parametrize(
    "where, params",
    [
        ("k = 10", []),
        ("k = 10 AND distance > 0.4", []),
        ("k = 10 AND distance <= 0.8", []),
        ("k = 10 AND distance >= 0.2 AND distance < 0.9", []),
        ("k = 5 AND rowid IN (3, 7, 11, 19, 23, 31, 999)", []),
        ("k = 3 AND rowid = 17", []),
        ("k = 6 AND mmr_lambda = 0.5", []),
        ("k = 6 AND mmr_lambda = 0.2 AND distance > 0.3", []),
    ],
)
# with buffer_threshold=25, 10 of the 60 rows are still in the buffer
@pytest.mark.parametrize("buffered", [0, 10])
def test_diskann_knn_answers_as_flat_when_the_search_covers_the_table(
    db, where, params, buffered
):
    threshold = ", buffer_threshold=25" if buffered else ""
    db.execute(f"""
        CREATE VIRTUAL TABLE d USING vec0(
            emb float[16] distance_metric=cosine
                INDEXED BY diskann(neighbor_quantizer=int8, n_neighbors=8,
                                   search_list_size=128{threshold})
        )
    """)
    db.execute(
        "CREATE VIRTUAL TABLE f USING vec0(emb float[16] distance_metric=cosine)"
    )
    rows = _random_rows(11, 60, 16)
    for rowid, vec in rows.items():
        for table in ("d", "f"):
            db.execute(
                f"INSERT INTO {table}(rowid, emb) VALUES (?, ?)", [rowid, _f32(vec)]
            )
    assert (
        db.execute("SELECT count(*) FROM d_diskann_buffer00").fetchone()[0] == buffered
    )
    rng = random.Random(12)
    for _ in range(10):
        query = _f32([rng.uniform(-1, 1) for _ in range(16)])
        sql = "SELECT rowid, distance FROM {} WHERE emb MATCH ? AND " + where
        got = db.execute(sql.format("d"), [query, *params]).fetchall()
        want = db.execute(sql.format("f"), [query, *params]).fetchall()
        assert [tuple(r) for r in got] == [tuple(r) for r in want]


@pytest.mark.parametrize("quantizer", ["int8", "binary"])
def test_diskann_int8_column(db, quantizer):
    """
    With a search list covering the table, an int8 column's KNN, query and
    distances included, answers as brute force does.
    """
    db.execute(f"""
        CREATE VIRTUAL TABLE t USING vec0(
            emb int8[64] INDEXED BY diskann(neighbor_quantizer={quantizer},
                                            n_neighbors=16)
        )
    """)
    rng = random.Random(3)
    for i in range(1, 101):
        vec = struct.pack("64b", *[rng.randint(-100, 100) for _ in range(64)])
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, vec_int8(?))", [i, vec])
    for _ in range(20):
        query = struct.pack("64b", *[rng.randint(-100, 100) for _ in range(64)])
        got = db.execute(
            "SELECT rowid, distance FROM t WHERE emb MATCH vec_int8(?) AND k = 10",
            [query],
        ).fetchall()
        want = db.execute(
            "SELECT rowid, vec_distance_l2(emb, vec_int8(?)) AS d FROM t "
            "ORDER BY d LIMIT 10",
            [query],
        ).fetchall()
        assert [tuple(r) for r in got] == [tuple(r) for r in want]


def test_diskann_knn_distances_are_exact(db):
    """A result's distance is its exact one, never its quantized one."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[32] distance_metric=cosine
                INDEXED BY diskann(neighbor_quantizer=int8, n_neighbors=16)
        )
    """)
    for rowid, vec in _random_rows(5, 300, 32).items():
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [rowid, _f32(vec)])
    rng = random.Random(6)
    for _ in range(30):
        query = _f32([rng.uniform(-1, 1) for _ in range(32)])
        got = db.execute(
            "SELECT rowid, distance FROM t WHERE emb MATCH ? AND k = 10", [query]
        ).fetchall()
        exact = dict(
            db.execute(
                "SELECT rowid, vec_distance_cosine(emb, ?) FROM t", [query]
            ).fetchall()
        )
        assert [d for _, d in got] == [exact[r] for r, _ in got]
        assert [d for _, d in got] == sorted(d for _, d in got)


def test_diskann_deleted_medoid_is_replaced_from_the_graph(db):
    """A medoid deleted while vectors wait in the buffer is replaced by a node."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[16] INDEXED BY diskann(neighbor_quantizer=int8,
                                             n_neighbors=8, buffer_threshold=10)
        )
    """)
    rng = random.Random(9)
    vecs = {}
    # ten rows flush into the graph, then three wait in the buffer with rowids
    # below every node's
    for rowid in [*range(100, 110), 1, 2, 3]:
        vecs[rowid] = [rng.uniform(-1, 1) for _ in range(16)]
        db.execute(
            "INSERT INTO t(rowid, emb) VALUES (?, ?)", [rowid, _f32(vecs[rowid])]
        )
    medoid_sql = "SELECT value FROM t_info WHERE key = 'diskann_medoid_00'"
    db.execute("DELETE FROM t WHERE rowid = ?", [db.execute(medoid_sql).fetchone()[0]])

    def nodes():
        return {r for (r,) in db.execute("SELECT rowid FROM t_diskann_nodes00")}

    def finds_itself(rowid):
        return (
            db.execute(
                "SELECT rowid FROM t WHERE emb MATCH ? AND k = 1", [_f32(vecs[rowid])]
            ).fetchone()[0]
            == rowid
        )

    assert db.execute(medoid_sql).fetchone()[0] in nodes()
    assert all(finds_itself(r) for r in nodes())
    for rowid in range(4, 11):
        vecs[rowid] = [rng.uniform(-1, 1) for _ in range(16)]
        db.execute(
            "INSERT INTO t(rowid, emb) VALUES (?, ?)", [rowid, _f32(vecs[rowid])]
        )
    assert len(nodes()) == 19
    assert all(finds_itself(r) for r in nodes())


def test_diskann_finds_neighbors_when_exact_distances_exceed_quantized_ones(db):
    """
    Exact L2 distances of vectors scaled by 100 run past the hamming counts a
    binary search ranks unvisited rows by. A search that moved each visited
    row by its exact distance put it behind the unvisited ones, walked most of
    the graph, and kept the rows it reached last: 0 of the 200 nearest. Upstream's
    build at 04d28bd finds 72 of them here; this one finds 161.
    """
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[16] INDEXED BY diskann(
                neighbor_quantizer=binary, n_neighbors=16, search_list_size=32
            )
        )
    """)
    db.execute("CREATE VIRTUAL TABLE f USING vec0(emb float[16])")
    rng = random.Random(7)
    centers = [[rng.uniform(-1, 1) for _ in range(16)] for _ in range(20)]

    def near(center):
        return _f32([100 * (x + rng.gauss(0, 0.3)) for x in center])

    for i in range(1, 801):
        vector = near(centers[i % 20])
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i, vector])
        db.execute("INSERT INTO f(rowid, emb) VALUES (?, ?)", [i, vector])
    found = 0
    for q in range(20):
        query = near(centers[q])
        knn = "SELECT rowid FROM {} WHERE emb MATCH ? AND k = 10"
        got = {r[0] for r in db.execute(knn.format("t"), [query])}
        want = {r[0] for r in db.execute(knn.format("f"), [query])}
        found += len(got & want)
    assert found >= 120


def _diskann_insert(db, *rowids):
    for rowid in rowids:
        db.execute(
            "INSERT INTO t(rowid, emb) VALUES (?, ?)", [rowid, _f32([rowid] * 8)]
        )


def _diskann_with_medoid(db, rows, medoid):
    """
    Writes a state upstream's build (asg017 04d28bd) can leave, which this
    build's delete does not: buffer_threshold=3, rows inserted in order, and
    _info naming medoid, a row with no node. A medoid among rows is one
    upstream's delete chose from _vectors00 while it waited in the buffer; a
    medoid not among them is one upstream's delete removed since. Returns a
    function that runs a KNN query near row 11 and returns its rowids, nearest
    first.
    """
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(
                neighbor_quantizer=binary, n_neighbors=8, buffer_threshold=3
            )
        )
    """)
    _diskann_insert(db, *rows)
    db.execute("UPDATE t_info SET value = ? WHERE key = 'diskann_medoid_00'", [medoid])

    def knn():
        sql = "SELECT rowid FROM t WHERE emb MATCH ? AND k = 10"
        return [r for (r,) in db.execute(sql, [_f32([11.25] * 8)])]

    return knn


def _diskann_medoid_is_a_node(db):
    return db.execute("""
            SELECT count(*) FROM t_diskann_nodes00 WHERE rowid =
              (SELECT value FROM t_info WHERE key = 'diskann_medoid_00')
        """).fetchone()[0] == 1


def test_diskann_knn_walks_the_graph_from_a_buffered_medoid(db):
    """
    A search starting at a buffered medoid found no node and returned only the
    medoid, which the buffer scan added again: [5, 5], as upstream's build
    returns. The search now starts at a node of the graph.
    """
    knn = _diskann_with_medoid(db, (10, 11, 12, 5), 5)
    assert knn() == [11, 12, 10, 5]


def test_diskann_flush_links_rows_into_the_graph_past_a_buffered_medoid(db):
    """
    A flush that kept the buffered medoid linked rows 1 and 2 only to it, and
    it to none, so a KNN query found [5], as upstream's build does. The flush
    now makes a node of the graph the medoid first.
    """
    knn = _diskann_with_medoid(db, (10, 11, 12, 5), 5)
    _diskann_insert(db, 1, 2)
    nodes = db.execute("SELECT rowid FROM t_diskann_nodes00 ORDER BY rowid")
    assert [r for (r,) in nodes] == [1, 2, 5, 10, 11, 12]
    assert db.execute("SELECT count(*) FROM t_diskann_buffer00").fetchone()[0] == 0
    assert _diskann_medoid_is_a_node(db)
    assert knn() == [11, 12, 10, 5, 2, 1]


def test_diskann_delete_of_a_buffered_medoid_replaces_it(db):
    """
    Deleting a buffered medoid left _info naming a row with no vector, and a
    KNN query or a flushing insert then failed with "the DiskANN medoid 5 of
    vector column 0 has no vector". The delete now replaces the medoid with a
    node of the graph, as the delete of a node does.
    """
    knn = _diskann_with_medoid(db, (10, 11, 12, 5), 5)
    db.execute("DELETE FROM t WHERE rowid = 5")
    assert _diskann_medoid_is_a_node(db)
    assert knn() == [11, 12, 10]
    _diskann_insert(db, 1, 2, 3)
    assert knn() == [11, 12, 10, 3, 2, 1]


@pytest.mark.parametrize(
    "rows, deleted, after",
    [
        ((10, 11, 12, 5), 11, [12, 10, 5]),
        ((10, 11, 12), 11, [12, 10]),
        ((10, 11, 12, 5, 7), 7, [11, 12, 10, 5]),
    ],
)
def test_diskann_delete_replaces_a_medoid_with_no_node(db, rows, deleted, after):
    """
    A delete replaced the medoid only when it deleted the medoid, so deleting
    node 11, or buffered row 7, left _info naming row 5, buffered or deleted,
    as upstream's build does. A delete now replaces any medoid with no node.
    """
    knn = _diskann_with_medoid(db, rows, 5)
    db.execute("DELETE FROM t WHERE rowid = ?", [deleted])
    assert _diskann_medoid_is_a_node(db)
    assert knn() == after


@pytest.mark.parametrize(
    "graph, before, after",
    [
        ((10, 11, 12), [11, 12, 10], [11, 12, 10, 3, 2, 1]),
        ((), [], [3, 2, 1]),
    ],
)
def test_diskann_medoid_with_no_vector_is_replaced(db, graph, before, after):
    """
    Upstream's build deletes a buffered medoid without replacing it, and its
    KNN queries and flushing inserts then fail, as this build's did with "the
    DiskANN medoid 5 of vector column 0 has no vector". A search now starts at
    a node of the graph, if it has one, and the flush replaces the medoid.
    """
    knn = _diskann_with_medoid(db, graph, 5)
    assert knn() == before
    _diskann_insert(db, 1, 2, 3)
    assert _diskann_medoid_is_a_node(db)
    assert knn() == after


def test_diskann_buffered_medoid_of_an_empty_graph(db):
    """
    With no node in the graph, a search from a buffered medoid returned the
    medoid, which the buffer scan added again: [5, 5]. The graph is now
    searched as empty, and the flush gives it a node as medoid.
    """
    knn = _diskann_with_medoid(db, (5,), 5)
    assert knn() == [5]
    _diskann_insert(db, 1, 2)
    assert _diskann_medoid_is_a_node(db)
    assert knn() == [5, 2, 1]


@pytest.mark.parametrize("blob", [b"", b"\x00" * 4])
def test_diskann_corrupt_buffer_row_errors(db, blob):
    """A buffered vector of the wrong size fails the flush and a KNN query."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(
                neighbor_quantizer=binary, buffer_threshold=3
            )
        )
    """)
    for rowid in (1, 2):
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [rowid, _f32([1.0] * 8)])
    db.execute("UPDATE t_diskann_buffer00 SET vector = ? WHERE rowid = 1", [blob])
    for sql, parameters in [
        ("SELECT rowid FROM t WHERE emb MATCH ? AND k = 2", [_f32([1.0] * 8)]),
        ("INSERT INTO t(rowid, emb) VALUES (3, ?)", [_f32([1.0] * 8)]),
    ]:
        with pytest.raises(
            sqlite3.OperationalError,
            match="^the DiskANN buffer of vector column 0 is corrupt$",
        ):
            db.execute(sql, parameters).fetchall()


@pytest.mark.parametrize(
    "event, rows, message",
    [
        ("INSERT", 1, "could not add a row to"),
        ("DELETE", 2, "could not empty"),
    ],
)
def test_diskann_unwritable_buffer_errors(db, event, rows, message):
    """A failed statement on the buffer says what it did and SQLite's reason."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(
                neighbor_quantizer=binary, buffer_threshold=2
            )
        )
    """)
    db.execute(f"""
        CREATE TRIGGER refuse BEFORE {event} ON t_diskann_buffer00
        BEGIN SELECT RAISE(ABORT, 'refused'); END
    """)
    for rowid in range(1, rows):
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [rowid, _f32([1.0] * 8)])
    with pytest.raises(
        sqlite3.OperationalError,
        match=f"^{message} the DiskANN buffer of vector column 0: refused$",
    ):
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [rows, _f32([1.0] * 8)])


def _diskann_graph(db, n_neighbors, qsize):
    """Each node's slots of t's graph, as (valid, rowid, quantized bytes)."""
    nodes = {}
    for rowid, validity, ids, qvecs in db.execute(
        "SELECT rowid, neighbors_validity, neighbor_ids, neighbor_quantized_vectors"
        " FROM t_diskann_nodes00"
    ):
        nodes[rowid] = [
            (validity[s // 8] >> (s % 8) & 1, nid, qvecs[s * qsize : (s + 1) * qsize])
            for s, nid in enumerate(struct.unpack(f"{n_neighbors}q", ids))
        ]
    return nodes


@pytest.mark.parametrize(
    "kind, quantizer",
    [("float", "binary"), ("float", "int8"), ("int8", "binary"), ("int8", "int8")],
)
def test_diskann_delete_keeps_every_slot_true(db, kind, quantizer):
    """
    Deleting 80 of 200 random rows leaves no slot naming a deleted row, also
    in nodes that named it without being among its neighbors (the scrub's
    work), clears each freed slot, gives each neighbor that named the deleted
    row, and lacked one of the row's other neighbors, one of them (the
    repair's), and leaves every valid slot the quantized form of its row's
    vector.
    """
    dims = 16
    db.execute(f"""
        CREATE VIRTUAL TABLE t USING vec0(
            emb {kind}[{dims}] INDEXED BY diskann(
                neighbor_quantizer={quantizer}, n_neighbors=8
            )
        )
    """)
    rng = random.Random(3)
    vectors = {}
    for rowid in range(1, 201):
        if kind == "float":
            values = [rng.gauss(0, 1) for _ in range(dims)]
            vectors[rowid] = _f32(values)
            sql = "INSERT INTO t(rowid, emb) VALUES (?, ?)"
        else:
            values = [rng.randint(-128, 127) for _ in range(dims)]
            vectors[rowid] = struct.pack(f"{dims}b", *values)
            sql = "INSERT INTO t(rowid, emb) VALUES (?, vec_int8(?))"
        db.execute(sql, [rowid, vectors[rowid]])

    def quantized(rowid):
        fmt = f"{dims}f" if kind == "float" else f"{dims}b"
        values = struct.unpack(fmt, vectors[rowid])
        if quantizer == "int8" and kind == "int8":
            return vectors[rowid]
        if quantizer == "int8":
            # the C quantizer's float32 arithmetic, truncated toward zero
            f32 = lambda x: struct.unpack("f", struct.pack("f", x))[0]
            step = f32(2.0 / 255.0)
            out = []
            for value in values:
                v = f32(f32(f32(f32(value) + 1.0) / step) - 128.0)
                out.append(int(min(max(v, -128.0), 127.0)))
            return struct.pack(f"{dims}b", *out)
        bits = bytearray(dims // 8)
        for d, value in enumerate(values):
            if value > 0:
                bits[d // 8] |= 1 << (d % 8)
        return bytes(bits)

    qsize = dims // 8 if quantizer == "binary" else dims
    one_way = 0
    for target in rng.sample(sorted(vectors), 80):
        before = _diskann_graph(db, 8, qsize)
        out = [nid for valid, nid, _ in before[target] if valid]
        one_way += sum(
            1
            for node, slots in before.items()
            if node != target
            and node not in out
            and any(valid and nid == target for valid, nid, _ in slots)
        )
        lacking = {}
        for node in out:
            ids = {nid for valid, nid, _ in before[node] if valid}
            if target in ids:
                lacking[node] = {o for o in out if o != node and o not in ids}
        db.execute("DELETE FROM t WHERE rowid = ?", [target])
        del vectors[target]
        after = _diskann_graph(db, 8, qsize)
        for node, missing in lacking.items():
            if missing:
                ids = {nid for valid, nid, _ in after[node] if valid}
                assert ids & missing, (target, node)

    assert one_way > 0
    for node, slots in _diskann_graph(db, 8, qsize).items():
        for valid, nid, qbytes in slots:
            if valid:
                assert nid in vectors, (node, nid)
                assert qbytes == quantized(nid), (node, nid)
            else:
                assert (nid, qbytes) == (0, bytes(qsize)), node


@pytest.mark.parametrize(
    "table, event, buffered, message",
    [
        ("t_vectors00", "DELETE", False, "could not change row 2 of t_vectors00"),
        (
            "t_diskann_nodes00",
            "DELETE",
            False,
            "could not change row 2 of t_diskann_nodes00",
        ),
        (
            "t_diskann_buffer00",
            "DELETE",
            True,
            "could not change row 2 of t_diskann_buffer00",
        ),
        (
            "t_info",
            "UPDATE",
            False,
            "could not set the DiskANN medoid of vector column 0",
        ),
    ],
)
def test_diskann_failed_delete_errors(db, table, event, buffered, message):
    """A delete's failed statement says what it changed and SQLite's reason."""
    threshold = ", buffer_threshold=8" if buffered else ""
    db.execute(f"""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary{threshold})
        )
    """)
    for rowid in (1, 2, 3):
        db.execute(
            "INSERT INTO t(rowid, emb) VALUES (?, ?)", [rowid, _f32([rowid] * 8)]
        )
    db.execute("UPDATE t_info SET value = 2 WHERE key = 'diskann_medoid_00'")
    db.execute(f"""
        CREATE TRIGGER refuse BEFORE {event} ON {table}
        BEGIN SELECT RAISE(ABORT, 'refused'); END
    """)
    with pytest.raises(sqlite3.OperationalError, match=f"^{message}: refused$"):
        db.execute("DELETE FROM t WHERE rowid = 2")


def test_diskann_unreadable_buffer_errors(db):
    """A KNN query whose read of the buffer fails names it and SQLite's reason."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(
                neighbor_quantizer=binary, buffer_threshold=2
            )
        )
    """)
    for rowid in (1, 2, 3):
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [rowid, _f32([1.0] * 8)])
    db.execute("DROP TABLE t_diskann_buffer00")
    with pytest.raises(
        sqlite3.OperationalError,
        match="^could not read the DiskANN buffer of vector column 0: "
        "no such table: main.t_diskann_buffer00$",
    ):
        db.execute(
            "SELECT rowid FROM t WHERE emb MATCH ? AND k = 2", [_f32([1.0] * 8)]
        ).fetchall()


def test_shadow_diskann_tables(db):
    # As in test_shadow_rescore_tables (test-rescore.py): after VACUUM, SQLite
    # asks xShadowName about every backing table, and a name that only looks
    # like a DiskANN table's stays an ordinary table. Upstream's xShadowName
    # names none of the three.
    db.execute("""
        CREATE VIRTUAL TABLE v USING vec0(
            a float[8] INDEXED BY diskann(neighbor_quantizer=binary), b float[1]
        )
    """)
    db.execute("INSERT INTO v(rowid, a, b) VALUES (1, ?, '[1]')", [_f32([1.0] * 8)])
    db.commit()
    for name in ["v_vectors", "v_vectors0", "v_diskann_nodes000", "v_diskann_buffer"]:
        db.execute(f"CREATE TABLE {name}(x)")
    db.execute("VACUUM")
    types = {
        row[0]: row[1]
        for row in db.execute(
            "SELECT name, type FROM pragma_table_list WHERE schema = 'main'"
        )
        if row[0].startswith(("v_vectors", "v_diskann"))
    }
    assert types == {
        "v_vectors00": "shadow",
        "v_diskann_nodes00": "shadow",
        "v_diskann_buffer00": "shadow",
        "v_vectors": "table",
        "v_vectors0": "table",
        "v_diskann_nodes000": "table",
        "v_diskann_buffer": "table",
    }


# This build finds 166 (int8) and 104 (binary) of the 200. A build that reads
# the query as floats, as upstream's at 04d28bd does, reads past the query and
# finds 8 to 18 (int8) and 2 to 12 (binary), depending on the memory there.
@pytest.mark.parametrize("quantizer, floor", [("int8", 120), ("binary", 60)])
def test_diskann_int8_column_query_quantized_as_int8(db, quantizer, floor):
    """
    With a search list shorter than the table, an int8 query quantized as
    int8 finds its neighbors; read as floats, as upstream reads it, it does not.
    """
    db.execute(f"""
        CREATE VIRTUAL TABLE t USING vec0(
            emb int8[64] INDEXED BY diskann(neighbor_quantizer={quantizer},
                                            n_neighbors=16, search_list_size=32)
        )
    """)
    db.execute("CREATE VIRTUAL TABLE f USING vec0(emb int8[64])")
    rng = random.Random(21)
    for rowid in range(1, 1001):
        vec = struct.pack("64b", *[rng.randint(-128, 127) for _ in range(64)])
        for table in ("t", "f"):
            db.execute(
                f"INSERT INTO {table}(rowid, emb) VALUES (?, vec_int8(?))", [rowid, vec]
            )
    found = 0
    for _ in range(20):
        query = struct.pack("64b", *[rng.randint(-128, 127) for _ in range(64)])
        sql = "SELECT rowid FROM {} WHERE emb MATCH vec_int8(?) AND k = 10"
        got = {r[0] for r in db.execute(sql.format("t"), [query])}
        want = {r[0] for r in db.execute(sql.format("f"), [query])}
        found += len(got & want)
    assert found >= floor


def test_diskann_point_query_for_a_missing_rowid(db):
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    db.execute("INSERT INTO t(rowid, emb) VALUES (1, ?)", [_f32([1] * 8)])
    assert db.execute("SELECT rowid, emb FROM t WHERE rowid = 2").fetchall() == []
    assert [tuple(r) for r in db.execute("SELECT rowid FROM t WHERE rowid = 1")] == [
        (1,)
    ]


def test_diskann_corrupt_node_blob_errors(db):
    """A node whose blobs have the wrong size fails the query that reads it."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    for i in range(5):
        vec = [0.0] * 8
        vec[i % 8] = 1.0
        db.execute("INSERT INTO t(rowid, emb) VALUES (?, ?)", [i + 1, _f32(vec)])
    medoid = db.execute(
        "SELECT value FROM t_info WHERE key = 'diskann_medoid_00'"
    ).fetchone()[0]
    db.execute(
        "UPDATE t_diskann_nodes00 SET neighbor_ids = x'00' WHERE rowid = ?", [medoid]
    )
    with pytest.raises(
        sqlite3.OperationalError,
        match=f"^node {medoid} of the DiskANN graph of vector column 0 is corrupt$",
    ):
        db.execute(
            "SELECT rowid FROM t WHERE emb MATCH ? AND k = 3", [_f32([1] + [0] * 7)]
        ).fetchall()


def test_diskann_delete_scrub_errors_on_a_corrupt_node(db):
    """
    The scrub of a DELETE reads every node, and fails on one whose blob has
    the wrong size, naming it, rather than skip it.
    """
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary, n_neighbors=8)
        )
    """)
    for rowid in range(1, 6):
        db.execute(
            "INSERT INTO t(rowid, emb) VALUES (?, ?)", [rowid, _f32([rowid] * 8)]
        )
    db.execute("UPDATE t_diskann_nodes00 SET neighbor_ids = x'00' WHERE rowid = 5")
    with pytest.raises(
        sqlite3.OperationalError,
        match="^node 5 of the DiskANN graph of vector column 0 is corrupt$",
    ):
        db.execute("DELETE FROM t WHERE rowid = 1")


def test_diskann_corrupt_vector_blob_errors(db):
    """A vector of the wrong size fails each query that reads it, naming it."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    for i in range(3):
        db.execute(
            "INSERT INTO t(rowid, emb) VALUES (?, ?)", [i + 1, _f32([i + 1.0] * 8)]
        )
    db.execute("UPDATE t_vectors00 SET vector = x'00' WHERE rowid = 2")
    for sql, parameters in [
        ("SELECT emb FROM t WHERE rowid = 2", []),
        ("SELECT rowid, emb FROM t", []),
        ("SELECT rowid FROM t WHERE emb MATCH ? AND k = 3", [_f32([2.0] * 8)]),
    ]:
        with pytest.raises(
            sqlite3.OperationalError,
            match="^the DiskANN vector of row 2 in vector column 0 is corrupt$",
        ):
            db.execute(sql, parameters).fetchall()


def test_diskann_unreadable_vector_errors(db):
    """A failed read of a vector names the vector and SQLite's reason."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    for i in range(3):
        db.execute(
            "INSERT INTO t(rowid, emb) VALUES (?, ?)", [i + 1, _f32([i + 1.0] * 8)]
        )
    db.execute("DROP TABLE t_vectors00")
    for sql, parameters in [
        ("SELECT emb FROM t WHERE rowid = 2", []),
        ("SELECT rowid, emb FROM t", []),
        ("SELECT rowid FROM t WHERE emb MATCH ? AND k = 3", [_f32([2.0] * 8)]),
    ]:
        with pytest.raises(
            sqlite3.OperationalError,
            match="^could not read the DiskANN vector of row [123] in vector "
            "column 0: no such table: main.t_vectors00$",
        ):
            db.execute(sql, parameters).fetchall()


def test_diskann_unreadable_node_errors(db):
    """A failed read of a node names the node and SQLite's reason."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    for i in range(3):
        db.execute(
            "INSERT INTO t(rowid, emb) VALUES (?, ?)", [i + 1, _f32([i + 1.0] * 8)]
        )
    db.execute("DROP TABLE t_diskann_nodes00")
    for sql, parameters in [
        ("SELECT rowid FROM t WHERE emb MATCH ? AND k = 3", [_f32([2.0] * 8)]),
        ("INSERT INTO t(rowid, emb) VALUES (9, ?)", [_f32([9.0] * 8)]),
        ("DELETE FROM t WHERE rowid = 2", []),
    ]:
        with pytest.raises(
            sqlite3.OperationalError,
            match="^could not read node [123] of the DiskANN graph of vector "
            "column 0: no such table: main.t_diskann_nodes00$",
        ):
            db.execute(sql, parameters).fetchall()


@pytest.mark.parametrize(
    "table, message",
    [
        (
            "t_vectors00",
            "could not write the DiskANN vector of row 1 in vector column 0",
        ),
        (
            "t_diskann_nodes00",
            "could not write node 1 of the DiskANN graph of vector column 0",
        ),
    ],
)
def test_diskann_unwritable_row_errors(db, table, message):
    """A failed write of a vector or a node names it and SQLite's reason."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    db.execute(f"""
        CREATE TRIGGER refuse BEFORE INSERT ON {table}
        BEGIN SELECT RAISE(ABORT, 'refused'); END
    """)
    with pytest.raises(sqlite3.OperationalError, match=f"^{message}: refused$"):
        db.execute("INSERT INTO t(rowid, emb) VALUES (1, ?)", [_f32([1.0] * 8)])


@pytest.mark.parametrize(
    "option",
    [
        "neighbor_quantizer=bin",
        "neighbor_quantizer=binary, n_neigh=16",
        "neighbor_quantizer=binary, search_list_size=99999999999",
        "neighbor_quantizer=binary, n_neighbors=0",
        "neighbor_quantizer=binary, n_neighbors=264",
        "neighbor_quantizer=binary, search_list_size=0",
        "neighbor_quantizer=binary,",
    ],
)
def test_diskann_create_option_must_be_whole(db, option):
    result = exec(
        db,
        f"CREATE VIRTUAL TABLE t USING vec0(emb float[8] INDEXED BY diskann({option}))",
    )
    assert "error" in result


@pytest.mark.parametrize(
    "command, message",
    [
        ("search_list_size=12abc", "search_list_size must be a whole number"),
        ("search_list_size=", "search_list_size must be a whole number"),
        ("search_list_size_search= 64", "search_list_size_search must be a whole"),
        ("search_list_size_insert=0", "search_list_size_insert must be a whole"),
        (
            "search_list_size=3000000000",
            "^search_list_size must be a whole number from 1 to 2147483647$",
        ),
        ("search_list_sizes=64", "unknown vec0 command"),
    ],
)
def test_diskann_command_value_must_be_digits(db, command, message):
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            emb float[8] INDEXED BY diskann(neighbor_quantizer=binary)
        )
    """)
    with pytest.raises(sqlite3.OperationalError, match=message):
        db.execute("INSERT INTO t(t) VALUES (?)", [command])


@pytest.mark.parametrize(
    "column", ["v float[8]", "v float[8] INDEXED BY rescore(quantizer=bit)"]
)
@pytest.mark.parametrize(
    "command",
    [
        "search_list_size=64",
        "search_list_size_search=64",
        "search_list_size_insert=64",
        "search_list_size=abc",
    ],
)
def test_diskann_commands_are_unknown_without_a_diskann_column(db, column, command):
    """As on main and upstream, a table with no DiskANN column has no such command."""
    db.execute(f"CREATE VIRTUAL TABLE t USING vec0({column})")
    with pytest.raises(
        sqlite3.OperationalError, match=f"^unknown vec0 command: '{command}'$"
    ):
        db.execute("INSERT INTO t(t) VALUES (?)", [command])


def test_diskann_command_sets_every_diskann_column(db):
    """
    search_list_size_search=N changes the searches of both DiskANN columns
    as a CREATE with it does; upstream's command sets only the first.
    """
    options = "neighbor_quantizer=binary, n_neighbors=8"
    db.execute(f"""
        CREATE VIRTUAL TABLE t USING vec0(
            a float[16] INDEXED BY diskann({options}, search_list_size=4),
            b float[16] INDEXED BY diskann({options}, search_list_size=4)
        )
    """)
    db.execute(f"""
        CREATE VIRTUAL TABLE r USING vec0(
            a float[16] INDEXED BY diskann({options}, search_list_size_insert=4,
                                           search_list_size_search=800)
        )
    """)
    for rowid, vec in _random_rows(5, 800, 16).items():
        db.execute(
            "INSERT INTO t(rowid, a, b) VALUES (?, ?, ?)", [rowid, _f32(vec), _f32(vec)]
        )
        db.execute("INSERT INTO r(rowid, a) VALUES (?, ?)", [rowid, _f32(vec)])
    rng = random.Random(6)
    queries = [_f32([rng.uniform(-1, 1) for _ in range(16)]) for _ in range(10)]

    def knn(table, column):
        sql = f"SELECT rowid FROM {table} WHERE {column} MATCH ? AND k = 10"
        return [[r[0] for r in db.execute(sql, [q])] for q in queries]

    before = knn("t", "b")
    db.execute("INSERT INTO t(t) VALUES ('search_list_size_search=800')")
    want = knn("r", "a")
    assert knn("t", "a") == want
    assert knn("t", "b") == want
    assert before != want


def test_diskann_optimize_beside_a_flat_column(db):
    """optimize moves a flat column's vectors and leaves a DiskANN column's."""
    db.execute("""
        CREATE VIRTUAL TABLE t USING vec0(
            f float[8],
            d float[8] INDEXED BY diskann(neighbor_quantizer=binary),
            chunk_size=8
        )
    """)
    rows = _random_rows(13, 40, 8)
    for rowid, vec in rows.items():
        db.execute(
            "INSERT INTO t(rowid, f, d) VALUES (?, ?, ?)",
            [rowid, _f32(vec), _f32([-x for x in vec])],
        )
    for rowid in range(1, 41, 3):
        db.execute("DELETE FROM t WHERE rowid = ?", [rowid])
        del rows[rowid]
    chunks = "SELECT count(*) FROM t_chunks"
    positions = "SELECT rowid, chunk_id, chunk_offset FROM t_rowids ORDER BY rowid"
    chunks_before = db.execute(chunks).fetchone()[0]
    positions_before = db.execute(positions).fetchall()
    db.execute("INSERT INTO t(t) VALUES ('optimize')")
    assert db.execute(chunks).fetchone()[0] < chunks_before
    assert db.execute(positions).fetchall() != positions_before
    for rowid, f, d in db.execute("SELECT rowid, f, d FROM t").fetchall():
        assert f == _f32(rows[rowid])
        assert d == _f32([-x for x in rows[rowid]])
    for rowid, vec in rows.items():
        assert (
            db.execute(
                "SELECT rowid FROM t WHERE d MATCH ? AND k = 1",
                [_f32([-x for x in vec])],
            ).fetchone()[0]
            == rowid
        )
