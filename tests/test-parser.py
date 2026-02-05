"""
Tests for vec0 table definition parser edge cases.

These tests verify that the parser correctly rejects malformed table definitions.
They specifically target the bug fixes where `&&` was incorrectly used instead of `||`
in parser condition checks (e.g., vec0_parse_table_option, vec0_parse_partition_key_definition,
vec0_parse_auxiliary_column_definition, vec0_parse_primary_key_definition, vec0_parse_vector_column).
"""

import sqlite3
import pytest
from collections import OrderedDict


def exec(db, sql, parameters=[]):
    """Execute SQL and return result dict, capturing errors."""
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


class TestTableOptionParser:
    """Tests for vec0_parse_table_option edge cases."""

    def test_missing_equals_sign(self, db, snapshot):
        """Table option without '=' should fail."""
        result = exec(db, "create virtual table v using vec0(chunk_size 8, a float[4])")
        assert result == snapshot(name="missing equals sign")

    def test_missing_value(self, db, snapshot):
        """Table option with '=' but no value should fail."""
        result = exec(db, "create virtual table v using vec0(chunk_size=, a float[4])")
        assert result == snapshot(name="missing value after equals")

    def test_missing_key(self, db, snapshot):
        """Table option with '=' but no key should fail."""
        result = exec(db, "create virtual table v using vec0(=8, a float[4])")
        assert result == snapshot(name="missing key before equals")

    def test_extra_tokens_after_value(self, db, snapshot):
        """Table option with extra tokens after value should fail."""
        result = exec(db, "create virtual table v using vec0(chunk_size=8 extra, a float[4])")
        assert result == snapshot(name="extra tokens after value")

    def test_valid_table_option(self, db):
        """Sanity check: valid table option should succeed."""
        db.execute("create virtual table v using vec0(chunk_size=8, a float[4])")
        # If we get here without exception, it worked
        db.execute("drop table v")


class TestPartitionKeyParser:
    """Tests for vec0_parse_partition_key_definition edge cases."""

    def test_missing_type(self, db, snapshot):
        """Partition key without type should fail."""
        result = exec(db, "create virtual table v using vec0(p partition key, a float[4])")
        assert result == snapshot(name="partition key missing type")

    def test_missing_partition_keyword(self, db, snapshot):
        """Column with just 'key' but not 'partition' should fail or parse differently."""
        result = exec(db, "create virtual table v using vec0(p int key, a float[4])")
        assert result == snapshot(name="missing partition keyword")

    def test_missing_key_keyword(self, db, snapshot):
        """Column with 'partition' but not 'key' should fail."""
        result = exec(db, "create virtual table v using vec0(p int partition, a float[4])")
        assert result == snapshot(name="missing key keyword")

    def test_invalid_type(self, db, snapshot):
        """Partition key with invalid type should fail."""
        result = exec(db, "create virtual table v using vec0(p blob partition key, a float[4])")
        assert result == snapshot(name="invalid partition key type")

    def test_valid_int_partition_key(self, db):
        """Sanity check: valid int partition key should succeed."""
        db.execute("create virtual table v using vec0(p int partition key, a float[4])")
        db.execute("drop table v")

    def test_valid_text_partition_key(self, db):
        """Sanity check: valid text partition key should succeed."""
        db.execute("create virtual table v using vec0(p text partition key, a float[4])")
        db.execute("drop table v")


class TestAuxiliaryColumnParser:
    """Tests for vec0_parse_auxiliary_column_definition edge cases."""

    def test_plus_without_name(self, db, snapshot):
        """Auxiliary column '+' without column name should fail."""
        result = exec(db, "create virtual table v using vec0(+ text, a float[4])")
        assert result == snapshot(name="plus without column name")

    def test_plus_without_type(self, db, snapshot):
        """Auxiliary column with name but no type should fail."""
        result = exec(db, "create virtual table v using vec0(+aux, a float[4])")
        assert result == snapshot(name="auxiliary without type")

    def test_invalid_auxiliary_type(self, db, snapshot):
        """Auxiliary column with invalid type should fail."""
        result = exec(db, "create virtual table v using vec0(+aux varchar, a float[4])")
        assert result == snapshot(name="invalid auxiliary type")

    def test_valid_text_auxiliary(self, db):
        """Sanity check: valid text auxiliary column should succeed."""
        db.execute("create virtual table v using vec0(+aux text, a float[4])")
        db.execute("drop table v")

    def test_valid_integer_auxiliary(self, db):
        """Sanity check: valid integer auxiliary column should succeed."""
        db.execute("create virtual table v using vec0(+aux integer, a float[4])")
        db.execute("drop table v")

    def test_valid_float_auxiliary(self, db):
        """Sanity check: valid float auxiliary column should succeed."""
        db.execute("create virtual table v using vec0(+aux float, a float[4])")
        db.execute("drop table v")

    def test_valid_blob_auxiliary(self, db):
        """Sanity check: valid blob auxiliary column should succeed."""
        db.execute("create virtual table v using vec0(+aux blob, a float[4])")
        db.execute("drop table v")


class TestPrimaryKeyParser:
    """Tests for vec0_parse_primary_key_definition edge cases."""

    def test_missing_type(self, db, snapshot):
        """Primary key without type should fail."""
        result = exec(db, "create virtual table v using vec0(id primary key, a float[4])")
        assert result == snapshot(name="primary key missing type")

    def test_missing_primary_keyword(self, db, snapshot):
        """Column with 'key' but not 'primary' should fail or parse differently."""
        result = exec(db, "create virtual table v using vec0(id int key, a float[4])")
        assert result == snapshot(name="missing primary keyword")

    def test_missing_key_keyword(self, db, snapshot):
        """Column with 'primary' but not 'key' should fail."""
        result = exec(db, "create virtual table v using vec0(id int primary, a float[4])")
        assert result == snapshot(name="missing key keyword after primary")

    def test_invalid_type(self, db, snapshot):
        """Primary key with invalid type should fail."""
        result = exec(db, "create virtual table v using vec0(id blob primary key, a float[4])")
        assert result == snapshot(name="invalid primary key type")

    def test_valid_int_primary_key(self, db):
        """Sanity check: valid int primary key should succeed."""
        db.execute("create virtual table v using vec0(id int primary key, a float[4])")
        db.execute("drop table v")

    def test_valid_text_primary_key(self, db):
        """Sanity check: valid text primary key should succeed."""
        db.execute("create virtual table v using vec0(id text primary key, a float[4])")
        db.execute("drop table v")


class TestVectorColumnParser:
    """Tests for vec0_parse_vector_column edge cases."""

    def test_missing_dimensions(self, db, snapshot):
        """Vector column without dimensions should fail."""
        result = exec(db, "create virtual table v using vec0(a float)")
        assert result == snapshot(name="vector missing dimensions")

    def test_missing_type(self, db, snapshot):
        """Vector column without type should fail."""
        result = exec(db, "create virtual table v using vec0(a [4])")
        assert result == snapshot(name="vector missing type")

    def test_zero_dimensions(self, db, snapshot):
        """Vector column with zero dimensions should fail."""
        result = exec(db, "create virtual table v using vec0(a float[0])")
        assert result == snapshot(name="zero dimensions")

    def test_negative_dimensions(self, db, snapshot):
        """Vector column with negative dimensions should fail."""
        result = exec(db, "create virtual table v using vec0(a float[-1])")
        assert result == snapshot(name="negative dimensions")

    def test_distance_metric_missing_equals(self, db, snapshot):
        """distance_metric without '=' should fail."""
        result = exec(db, "create virtual table v using vec0(a float[4] distance_metric l2)")
        assert result == snapshot(name="distance_metric missing equals")

    def test_distance_metric_missing_value(self, db, snapshot):
        """distance_metric= without value should fail."""
        result = exec(db, "create virtual table v using vec0(a float[4] distance_metric=)")
        assert result == snapshot(name="distance_metric missing value")

    def test_distance_metric_invalid_value(self, db, snapshot):
        """distance_metric with invalid value should fail."""
        result = exec(db, "create virtual table v using vec0(a float[4] distance_metric=invalid)")
        assert result == snapshot(name="distance_metric invalid value")

    def test_valid_float_vector(self, db):
        """Sanity check: valid float vector should succeed."""
        db.execute("create virtual table v using vec0(a float[4])")
        db.execute("drop table v")

    def test_valid_int8_vector(self, db):
        """Sanity check: valid int8 vector should succeed."""
        db.execute("create virtual table v using vec0(a int8[4])")
        db.execute("drop table v")

    def test_valid_bit_vector(self, db):
        """Sanity check: valid bit vector should succeed."""
        db.execute("create virtual table v using vec0(a bit[64])")
        db.execute("drop table v")

    def test_valid_distance_metric_l2(self, db):
        """Sanity check: valid L2 distance metric should succeed."""
        db.execute("create virtual table v using vec0(a float[4] distance_metric=l2)")
        db.execute("drop table v")

    def test_valid_distance_metric_cosine(self, db):
        """Sanity check: valid cosine distance metric should succeed."""
        db.execute("create virtual table v using vec0(a float[4] distance_metric=cosine)")
        db.execute("drop table v")

    def test_valid_distance_metric_l1(self, db):
        """Sanity check: valid L1 distance metric should succeed."""
        db.execute("create virtual table v using vec0(a float[4] distance_metric=L1)")
        db.execute("drop table v")


class TestMalformedDefinitions:
    """Tests for completely malformed table definitions."""

    def test_empty_definition(self, db, snapshot):
        """Empty vec0 definition should fail."""
        result = exec(db, "create virtual table v using vec0()")
        assert result == snapshot(name="empty definition")

    def test_only_whitespace(self, db, snapshot):
        """Definition with only whitespace should fail."""
        result = exec(db, "create virtual table v using vec0(   )")
        assert result == snapshot(name="only whitespace")

    def test_just_comma(self, db, snapshot):
        """Definition with just comma should fail."""
        result = exec(db, "create virtual table v using vec0(,)")
        assert result == snapshot(name="just comma")

    def test_trailing_comma(self, db, snapshot):
        """Definition with trailing comma should fail."""
        result = exec(db, "create virtual table v using vec0(a float[4],)")
        assert result == snapshot(name="trailing comma")

    def test_leading_comma(self, db, snapshot):
        """Definition with leading comma should fail."""
        result = exec(db, "create virtual table v using vec0(, a float[4])")
        assert result == snapshot(name="leading comma")

    def test_double_comma(self, db, snapshot):
        """Definition with double comma should fail."""
        result = exec(db, "create virtual table v using vec0(a float[4],, b float[4])")
        assert result == snapshot(name="double comma")

    def test_number_only(self, db, snapshot):
        """Definition with just a number should fail."""
        result = exec(db, "create virtual table v using vec0(123)")
        assert result == snapshot(name="number only")

    def test_special_characters(self, db, snapshot):
        """Definition with special characters should fail."""
        result = exec(db, "create virtual table v using vec0(@#$)")
        assert result == snapshot(name="special characters")
