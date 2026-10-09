"""
Tests for error paths and edge cases that previously had memory leaks.

These tests specifically target error-handling code paths that were fixed
in PR #258 and related commits. The goal is to ensure these paths are
exercised by the test suite so that memory leaks would be caught by
sanitizers (ASan/LSan) if reintroduced.
"""

import sqlite3
import pytest
import struct
import re
import subprocess
import sys

from conftest import get_extension_path


def _raises(message, error=sqlite3.OperationalError):
    """Context manager for testing expected errors."""
    return pytest.raises(error, match=re.escape(message))


# Helper to create malformed vector blobs
def _malformed_blob(data):
    """Create a blob that looks like a vector but is malformed."""
    return data


class TestVecEachErrorPaths:
    """Test error paths in vec_each that previously leaked pzErrMsg."""

    def test_vec_each_with_null_input(self, db):
        """Test vec_each with NULL input - should error without leaking."""
        # The key is that it errors - exact message may vary
        with pytest.raises(sqlite3.OperationalError):
            db.execute("SELECT * FROM vec_each(NULL)").fetchall()

    def test_vec_each_with_integer_input(self, db):
        """Test vec_each with wrong type - should error without leaking."""
        with pytest.raises(sqlite3.OperationalError):
            db.execute("SELECT * FROM vec_each(42)").fetchall()

    def test_vec_each_with_malformed_json(self, db):
        """Test vec_each with malformed JSON - should error without leaking."""
        with pytest.raises(sqlite3.OperationalError):
            db.execute("SELECT * FROM vec_each('[1, 2, not valid json]')").fetchall()

    def test_vec_each_with_empty_json_array(self, db):
        """Test vec_each with empty array - should error without leaking."""
        with pytest.raises(sqlite3.OperationalError):
            db.execute("SELECT * FROM vec_each('[]')").fetchall()


class TestVecSliceErrorPaths:
    """
    Test error paths in vec_slice.

    Note: The malloc failure paths (INT8 and BIT cases) are very difficult to test
    without fault injection. Those paths are triggered when sqlite3_malloc() fails
    due to out-of-memory conditions. Without SQLITE_TESTCTRL_FAULT_INSTALL or
    similar fault injection, we cannot reliably trigger malloc failures.

    The fixes ensure that if malloc fails, the vector cleanup function is called
    via 'goto done' instead of 'return', preventing memory leaks.

    These tests cover other error paths to ensure the general error handling works.
    """

    def test_vec_slice_with_null_vector(self, db):
        """Test vec_slice with NULL vector - should error without leaking."""
        with pytest.raises(sqlite3.OperationalError):
            db.execute("SELECT vec_slice(NULL, 0, 1)").fetchone()

    def test_vec_slice_with_invalid_type(self, db):
        """Test vec_slice with non-vector type - should error without leaking."""
        with pytest.raises(sqlite3.OperationalError):
            db.execute("SELECT vec_slice(42, 0, 1)").fetchone()

    def test_vec_slice_with_negative_start(self, db):
        """Test vec_slice with negative start index."""
        with _raises("slice 'start' index must be a postive number."):
            db.execute("SELECT vec_slice(vec_f32('[1,2,3]'), -1, 2)").fetchone()

    def test_vec_slice_with_negative_end(self, db):
        """Test vec_slice with negative end index."""
        with _raises("slice 'end' index must be a postive number."):
            db.execute("SELECT vec_slice(vec_f32('[1,2,3]'), 0, -1)").fetchone()

    def test_vec_slice_with_start_greater_than_end(self, db):
        """Test vec_slice with start > end."""
        with _raises("slice 'start' index is greater than 'end' index"):
            db.execute("SELECT vec_slice(vec_f32('[1,2,3]'), 2, 1)").fetchone()

    def test_vec_slice_with_start_equal_to_end(self, db):
        """Test vec_slice with start == end (zero-length result)."""
        with _raises(
            "slice 'start' index is equal to the 'end' index, vectors must have non-zero length"
        ):
            db.execute("SELECT vec_slice(vec_f32('[1,2,3]'), 1, 1)").fetchone()

    def test_vec_slice_int8_with_out_of_bounds(self, db):
        """Test vec_slice on int8 vector with out of bounds indices."""
        with _raises("slice 'end' index is greater than the number of dimensions"):
            db.execute("SELECT vec_slice(vec_int8('[1,2,3]'), 0, 10)").fetchone()

    def test_vec_slice_bit_with_non_aligned_start(self, db):
        """Test vec_slice on bit vector with non-8-aligned start."""
        with _raises("start index must be divisible by 8."):
            db.execute("SELECT vec_slice(vec_bit(x'AABBCCDD'), 4, 16)").fetchone()

    def test_vec_slice_bit_with_non_aligned_end(self, db):
        """Test vec_slice on bit vector with non-8-aligned end."""
        with _raises("end index must be divisible by 8."):
            db.execute("SELECT vec_slice(vec_bit(x'AABBCCDD'), 0, 12)").fetchone()


class TestVectorFromValueErrorPaths:
    """
    Test various error paths in vector_from_value() which is called by many functions.

    This exercises the error handling that allocates pzErrMsg and ensures it's freed
    properly in all error cases.
    """

    def test_vec_length_with_null(self, db):
        """Test vec_length with NULL input."""
        with pytest.raises(sqlite3.OperationalError):
            db.execute("SELECT vec_length(NULL)").fetchone()

    def test_vec_length_with_wrong_type(self, db):
        """Test vec_length with wrong input type."""
        with pytest.raises(sqlite3.OperationalError):
            db.execute("SELECT vec_length(123)").fetchone()

    def test_vec_distance_l2_with_null(self, db):
        """Test vec_distance_l2 with NULL inputs."""
        with pytest.raises(sqlite3.OperationalError):
            db.execute("SELECT vec_distance_l2(NULL, vec_f32('[1,2,3]'))").fetchone()

    def test_vec_distance_l2_with_mismatched_types(self, db):
        """Test vec_distance_l2 with mismatched vector types."""
        with pytest.raises(sqlite3.OperationalError):
            db.execute(
                "SELECT vec_distance_l2(vec_f32('[1,2,3]'), vec_int8('[1,2,3]'))"
            ).fetchone()

    def test_vec_distance_l2_with_mismatched_dimensions(self, db):
        """Test vec_distance_l2 with mismatched dimensions."""
        with pytest.raises(sqlite3.OperationalError):
            db.execute(
                "SELECT vec_distance_l2(vec_f32('[1,2,3]'), vec_f32('[1,2,3,4]'))"
            ).fetchone()

    def test_vec_add_with_null(self, db):
        """Test vec_add with NULL input."""
        with pytest.raises(sqlite3.OperationalError):
            db.execute("SELECT vec_add(NULL, vec_f32('[1,2,3]'))").fetchone()

    def test_vec_add_with_mismatched_dimensions(self, db):
        """Test vec_add with mismatched dimensions."""
        with pytest.raises(sqlite3.OperationalError):
            db.execute(
                "SELECT vec_add(vec_f32('[1,2]'), vec_f32('[1,2,3]'))"
            ).fetchone()

    def test_vec_sub_with_mismatched_types(self, db):
        """Test vec_sub with mismatched types."""
        with pytest.raises(sqlite3.OperationalError):
            db.execute(
                "SELECT vec_sub(vec_f32('[1,2,3]'), vec_int8('[1,2,3]'))"
            ).fetchone()


class TestVec0ErrorPaths:
    """
    Test error paths in vec0 virtual table operations.

    These test paths that allocate memory (zSql, knn_data, etc.) and ensure
    proper cleanup on errors.
    """

    def test_vec0_insert_with_null_vector(self, db):
        """Test INSERT with NULL vector - should error without leaking."""
        db.execute("CREATE VIRTUAL TABLE test USING vec0(v float[3])")
        with pytest.raises(sqlite3.OperationalError):
            db.execute("INSERT INTO test(rowid, v) VALUES (1, NULL)")
        db.execute("DROP TABLE test")

    def test_vec0_insert_with_wrong_dimensions(self, db):
        """Test INSERT with wrong number of dimensions."""
        db.execute("CREATE VIRTUAL TABLE test USING vec0(v float[3])")
        with pytest.raises(sqlite3.OperationalError):
            db.execute("INSERT INTO test(rowid, v) VALUES (1, vec_f32('[1,2,3,4]'))")
        db.execute("DROP TABLE test")

    def test_vec0_insert_with_wrong_type(self, db):
        """Test INSERT with wrong vector type."""
        db.execute("CREATE VIRTUAL TABLE test USING vec0(v float[3])")
        with pytest.raises(sqlite3.OperationalError):
            db.execute("INSERT INTO test(rowid, v) VALUES (1, vec_int8('[1,2,3]'))")
        db.execute("DROP TABLE test")

    def test_vec0_knn_with_null_query(self, db):
        """Test KNN query with NULL query vector - should error without leaking knn_data."""
        db.execute("CREATE VIRTUAL TABLE test USING vec0(v float[3])")
        db.execute("INSERT INTO test(rowid, v) VALUES (1, vec_f32('[1,2,3]'))")
        with pytest.raises(sqlite3.OperationalError):
            db.execute("SELECT * FROM test WHERE v MATCH NULL AND k = 5").fetchall()
        db.execute("DROP TABLE test")

    def test_vec0_knn_with_mismatched_dimensions(self, db):
        """Test KNN query with wrong dimensions - should error without leaking."""
        db.execute("CREATE VIRTUAL TABLE test USING vec0(v float[3])")
        db.execute("INSERT INTO test(rowid, v) VALUES (1, vec_f32('[1,2,3]'))")
        with pytest.raises(sqlite3.OperationalError):
            db.execute(
                "SELECT * FROM test WHERE v MATCH vec_f32('[1,2,3,4]') AND k = 5"
            ).fetchall()
        db.execute("DROP TABLE test")

    def test_vec0_knn_with_mismatched_type(self, db):
        """Test KNN query with wrong type - should error without leaking."""
        db.execute("CREATE VIRTUAL TABLE test USING vec0(v float[3])")
        db.execute("INSERT INTO test(rowid, v) VALUES (1, vec_f32('[1,2,3]'))")
        with pytest.raises(sqlite3.OperationalError):
            db.execute(
                "SELECT * FROM test WHERE v MATCH vec_int8('[1,2,3]') AND k = 5"
            ).fetchall()
        db.execute("DROP TABLE test")

    def test_vec0_metadata_insert_with_null_metadata(self, db):
        """Test INSERT with NULL metadata value - should error."""
        db.execute("CREATE VIRTUAL TABLE test USING vec0(v float[3], category text)")
        # NULL metadata is not supported - should error
        with pytest.raises(sqlite3.OperationalError):
            db.execute(
                "INSERT INTO test(rowid, v, category) VALUES (1, vec_f32('[1,2,3]'), NULL)"
            )
        db.execute("DROP TABLE test")

    def test_vec0_with_invalid_metadata_filter(self, db):
        """Test query with invalid metadata IN clause."""
        db.execute("CREATE VIRTUAL TABLE test USING vec0(v float[3], score integer)")
        db.execute(
            "INSERT INTO test(rowid, v, score) VALUES (1, vec_f32('[1,2,3]'), 100)"
        )

        # This exercises the metadata IN clause path
        result = db.execute(
            "SELECT * FROM test WHERE v MATCH vec_f32('[1,2,3]') AND k = 5 AND score IN (100, 200)"
        ).fetchall()
        assert len(result) == 1

        db.execute("DROP TABLE test")


def test_repeated_error_operations(db):
    """
    Test repeated error conditions to stress-test cleanup paths.

    If memory leaks exist in error paths, this will accumulate them
    and make them more visible to memory leak detectors.
    """
    db.execute("CREATE VIRTUAL TABLE test USING vec0(v float[3])")
    db.execute("INSERT INTO test(rowid, v) VALUES (1, vec_f32('[1,2,3]'))")

    # Repeat error conditions many times
    for i in range(50):
        # Invalid dimension
        with pytest.raises(sqlite3.OperationalError):
            db.execute(
                "INSERT INTO test(rowid, v) VALUES (?, vec_f32('[1,2,3,4]'))", [i + 2]
            )

        # Invalid type
        with pytest.raises(sqlite3.OperationalError):
            db.execute(
                "INSERT INTO test(rowid, v) VALUES (?, vec_int8('[1,2,3]'))", [i + 2]
            )

        # Invalid KNN query
        with pytest.raises(sqlite3.OperationalError):
            db.execute(
                "SELECT * FROM test WHERE v MATCH vec_f32('[1,2,3,4]') AND k = 5"
            ).fetchall()

    db.execute("DROP TABLE test")


def test_rowids_shadow_insert_reports_real_error(db):
    """
    Regression test: a non-primary-key failure during an explicit-rowid
    insert used sqlite3_errmsg(sqlite3_db_handle(stmtRowidsInsertId)), but
    that statement is never prepared on the explicit-rowid path, so the
    error surfaced as "out of memory" instead of the real message.
    """
    db.execute("CREATE VIRTUAL TABLE test USING vec0(v float[1])")
    db.execute("INSERT INTO test(rowid, v) VALUES (1, '[1]')")
    # Break the rowids shadow table so the next explicit-rowid insert fails
    # with something other than a primary-key conflict.
    db.execute("DROP TABLE test_rowids")
    with pytest.raises(sqlite3.OperationalError) as excinfo:
        db.execute("INSERT INTO test(rowid, v) VALUES (2, '[2]')")
    assert "out of memory" not in str(excinfo.value)
    assert "no such table" in str(excinfo.value)


def test_point_query_reports_unpreparable_rowid_lookup(db):
    # vec0 prepares its rowid-to-chunk lookup on first use, and called
    # sqlite3_clear_bindings() on the NULL statement when that prepare failed.
    db.execute("CREATE VIRTUAL TABLE test USING vec0(v float[1])")
    db.execute("INSERT INTO test(rowid, v) VALUES (1, '[1]')")
    db.execute("DROP TABLE test_rowids")
    with _raises("could not initialize 'rowids get chunk position' statement"):
        db.execute("SELECT * FROM test WHERE rowid = 1").fetchall()


_FAILED_DROP_SCRIPT = """
import sqlite3, sys
ext, shadow, then = sys.argv[1:]
db = sqlite3.connect(":memory:", isolation_level=None)
db.enable_load_extension(True)
db.load_extension(ext)
db.execute("CREATE VIRTUAL TABLE v USING vec0(x float[1], m integer, +a text)")
db.execute("INSERT INTO v(rowid, x, m, a) VALUES (1, '[1]', 2, 'a')")
db.execute(f"DROP TABLE v_{shadow}")
try:
    db.execute("DROP TABLE v")
except sqlite3.OperationalError as e:
    print("drop failed:", e)
if then == "drop-again":
    print(db.execute("SELECT rowid, x, m, a FROM v").fetchall())
    db.execute(f"CREATE TABLE v_{shadow}(x)")
    db.execute("DROP TABLE v")
    print(db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'v%'").fetchall())
db.close()
print("closed")
"""


@pytest.mark.parametrize("then", ["close", "drop-again"])
@pytest.mark.parametrize("shadow", ["chunks", "info"])
def test_failed_drop_keeps_table_usable(shadow, then):
    # vec0Destroy freed the table even when a DROP TABLE of a shadow table
    # failed, but SQLite keeps a virtual table whose xDestroy fails, so the
    # failed DROP TABLE itself, or the next query, DROP, or close, used freed
    # memory. vec0Destroy drops _chunks first: when that fails, SQLite goes on
    # using the same table; when dropping _info fails, the rollback of the
    # _chunks drop makes SQLite connect a new one and only disconnect the old.
    # The script runs in a child process because the bug crashed it.
    result = subprocess.run(
        [sys.executable, "-c", _FAILED_DROP_SCRIPT, get_extension_path(), shadow, then],
        capture_output=True,
        text=True,
    )
    output = ["drop failed: SQL logic error"]
    if then == "drop-again":
        output += ["[(1, b'\\x00\\x00\\x80?', 2, 'a')]", "[]"]
    output += ["closed"]
    assert (result.returncode, result.stdout.splitlines()) == (0, output), result.stderr


def test_optimize_reports_missing_partition_chunk(db):
    # optimize returned SQLITE_ROW when it could not look up a chunk's
    # partition key, so sqlite3_step() returned SQLITE_ROW: the caller saw
    # success and SQLite rolled the optimize back.
    db.execute(
        "CREATE VIRTUAL TABLE test USING vec0(p integer partition key, "
        "v float[1], chunk_size=8)"
    )
    db.executemany(
        "INSERT INTO test(rowid, p, v) VALUES (?, ?, ?)",
        [(i, i % 2, f"[{i}]") for i in range(1, 5)],
    )
    db.execute("DELETE FROM test_chunks WHERE chunk_id = 1")
    with _raises("SQL logic error"):
        db.execute("INSERT INTO test(test) VALUES ('optimize')")


@pytest.fixture(scope="module")
def interrupt_template():
    db = sqlite3.connect(":memory:")
    db.enable_load_extension(True)
    db.load_extension(get_extension_path())
    # Text values are longer than the 12 bytes a metadata chunk holds, so
    # filters and reads go to the _metadatatext table. v's one chunk is full,
    # so an INSERT adds a chunk; vp has a deleted row for optimize to skip.
    db.execute(
        "CREATE VIRTUAL TABLE v USING vec0(vector float[2], m integer, t text, "
        "+a text, chunk_size=8)"
    )
    db.executemany(
        "INSERT INTO v(rowid, vector, m, t, a) VALUES (?, ?, ?, ?, ?)",
        [
            (i, f"[{i}, {i % 3}]", i % 4, f"text value number {i:05d}", f"aux {i}")
            for i in range(1, 9)
        ],
    )
    db.execute(
        "CREATE VIRTUAL TABLE vp USING vec0(p integer partition key, "
        "vector float[2], m integer, chunk_size=8)"
    )
    db.executemany(
        "INSERT INTO vp(rowid, p, vector, m) VALUES (?, ?, ?, ?)",
        [(i, i % 2, f"[{i}, {i % 3}]", i % 4) for i in range(1, 5)],
    )
    db.execute("DELETE FROM vp WHERE rowid = 2")
    db.execute(
        "CREATE VIRTUAL TABLE vt USING vec0(id text primary key, vector float[2], "
        "chunk_size=8)"
    )
    db.executemany(
        "INSERT INTO vt(id, vector) VALUES (?, ?)",
        [(f"id{i}", f"[{i}, {i % 3}]") for i in range(1, 9)],
    )
    db.commit()
    return db.serialize()


def _run_interrupted(template, sql, n, mode):
    """Runs sql on a new connection to a copy of template and interrupts it at
    the n-th progress handler call: the handler returns 1 from then on in
    "progress" mode and calls sqlite3_interrupt() in "interrupt" mode. Returns
    the number of calls, the error or None, the rows, and the database image.
    """
    db = sqlite3.connect(":memory:", isolation_level=None)
    db.deserialize(template)
    db.enable_load_extension(True)
    db.load_extension(get_extension_path())
    # load the schema before counting calls
    db.execute("SELECT count(*) FROM sqlite_master").fetchall()
    calls = 0

    def handler():
        nonlocal calls
        calls += 1
        if mode == "interrupt" and calls == n:
            db.interrupt()
        return mode == "progress" and n is not None and calls >= n

    db.set_progress_handler(handler, 1)
    error = rows = None
    try:
        rows = db.execute(sql).fetchall()
    except sqlite3.Error as e:
        error = e
    db.set_progress_handler(None, 1)
    image = db.serialize()
    db.close()
    return calls, error, rows, image


@pytest.mark.parametrize("mode", ["progress", "interrupt"])
@pytest.mark.parametrize(
    "sql",
    [
        pytest.param(
            "SELECT rowid, distance, vector, m, t, a FROM v "
            "WHERE vector MATCH '[3, 4]' AND k = 3 "
            "AND t >= 'text value number 00002' AND mmr_lambda = 0.5",
            id="knn",
        ),
        pytest.param(
            "SELECT rowid, p, vector FROM vp WHERE vector MATCH '[3, 4]' AND k = 3 "
            "AND p = 1",
            id="knn-partition",
        ),
        pytest.param(
            "SELECT id, distance FROM vt WHERE vector MATCH '[3, 4]' AND k = 3",
            id="knn-text-pk",
        ),
        pytest.param("SELECT rowid, vector, m, t, a FROM v", id="fullscan"),
        pytest.param("SELECT rowid, p, vector, m FROM vp", id="fullscan-partition"),
        pytest.param(
            "SELECT rowid, vector, m, t, a FROM v WHERE rowid = 4", id="point"
        ),
        pytest.param(
            "SELECT rowid, vector, m, t, a FROM v WHERE rowid = 99", id="point-missing"
        ),
        pytest.param("SELECT id, vector FROM vt WHERE id = 'id4'", id="point-text-pk"),
        pytest.param(
            "INSERT INTO v(rowid, vector, m, t, a) "
            "VALUES (100, '[1, 1]', 1, 'a long text value here', 'x')",
            id="insert",
        ),
        pytest.param(
            "INSERT INTO vt(id, vector) VALUES ('new', '[1, 1]')", id="insert-text-pk"
        ),
        pytest.param(
            "INSERT OR REPLACE INTO v(rowid, vector, m, t, a) "
            "VALUES (4, '[1, 1]', 1, 'a long text value here', 'x')",
            id="insert-or-replace",
        ),
        pytest.param(
            "UPDATE v SET vector = '[9, 9]', m = 5, t = 'another long text value', "
            "a = 'zzz' WHERE rowid = 4",
            id="update",
        ),
        pytest.param("DELETE FROM v WHERE rowid = 4", id="delete"),
        pytest.param("DELETE FROM vt WHERE id = 'id4'", id="delete-text-pk"),
        pytest.param("INSERT INTO vp(vp) VALUES ('optimize')", id="optimize"),
    ],
)
def test_interrupt_is_reported_as_interrupt(interrupt_template, sql, mode):
    # vec0 used to replace SQLITE_INTERRUPT from its internal statements with
    # SQLITE_ERROR and a message of its own. Interrupt sql at every progress
    # handler call and expect what an ordinary table reports.
    total, error, rows, image = _run_interrupted(interrupt_template, sql, None, mode)
    assert error is None
    for n in range(1, total + 1):
        _, error, n_rows, n_image = _run_interrupted(interrupt_template, sql, n, mode)
        if error is None:
            # sqlite3_interrupt() has no effect once no statement is running
            assert mode == "interrupt", n
            assert (n_rows, n_image) == (rows, image), n
        else:
            assert (error.sqlite_errorname, str(error)) == (
                "SQLITE_INTERRUPT",
                "interrupted",
            ), n


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
