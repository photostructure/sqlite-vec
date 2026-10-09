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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_point_query_reports_unpreparable_rowid_lookup(db):
    # vec0 prepares its rowid-to-chunk lookup on first use, and called
    # sqlite3_clear_bindings() on the NULL statement when that prepare failed.
    db.execute("CREATE VIRTUAL TABLE test USING vec0(v float[1])")
    db.execute("INSERT INTO test(rowid, v) VALUES (1, '[1]')")
    db.execute("DROP TABLE test_rowids")
    with _raises("could not initialize 'rowids get chunk position' statement"):
        db.execute("SELECT * FROM test WHERE rowid = 1").fetchall()
