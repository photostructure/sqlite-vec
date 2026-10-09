"""
Tests for vec0 table definition parser edge cases.

These tests verify that the parser correctly rejects malformed table definitions.
They specifically target the bug fixes where `&&` was incorrectly used instead of `||`
in parser condition checks (e.g., vec0_parse_table_option, vec0_parse_partition_key_definition,
vec0_parse_auxiliary_column_definition, vec0_parse_primary_key_definition, vec0_parse_vector_column).
"""

import re
import sqlite3
import pytest
from collections import OrderedDict
from conftest import get_extension_path


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
        result = exec(
            db, "create virtual table v using vec0(chunk_size=8 extra, a float[4])"
        )
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
        result = exec(
            db, "create virtual table v using vec0(p partition key, a float[4])"
        )
        assert result == snapshot(name="partition key missing type")

    def test_missing_partition_keyword(self, db, snapshot):
        """Column with just 'key' but not 'partition' should fail or parse differently."""
        result = exec(db, "create virtual table v using vec0(p int key, a float[4])")
        assert result == snapshot(name="missing partition keyword")

    def test_missing_key_keyword(self, db, snapshot):
        """Column with 'partition' but not 'key' should fail."""
        result = exec(
            db, "create virtual table v using vec0(p int partition, a float[4])"
        )
        assert result == snapshot(name="missing key keyword")

    def test_invalid_type(self, db, snapshot):
        """Partition key with invalid type should fail."""
        result = exec(
            db, "create virtual table v using vec0(p blob partition key, a float[4])"
        )
        assert result == snapshot(name="invalid partition key type")

    def test_valid_int_partition_key(self, db):
        """Sanity check: valid int partition key should succeed."""
        db.execute("create virtual table v using vec0(p int partition key, a float[4])")
        db.execute("drop table v")

    def test_valid_text_partition_key(self, db):
        """Sanity check: valid text partition key should succeed."""
        db.execute(
            "create virtual table v using vec0(p text partition key, a float[4])"
        )
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
        result = exec(
            db, "create virtual table v using vec0(id primary key, a float[4])"
        )
        assert result == snapshot(name="primary key missing type")

    def test_missing_primary_keyword(self, db, snapshot):
        """Column with 'key' but not 'primary' should fail or parse differently."""
        result = exec(db, "create virtual table v using vec0(id int key, a float[4])")
        assert result == snapshot(name="missing primary keyword")

    def test_missing_key_keyword(self, db, snapshot):
        """Column with 'primary' but not 'key' should fail."""
        result = exec(
            db, "create virtual table v using vec0(id int primary, a float[4])"
        )
        assert result == snapshot(name="missing key keyword after primary")

    def test_invalid_type(self, db, snapshot):
        """Primary key with invalid type should fail."""
        result = exec(
            db, "create virtual table v using vec0(id blob primary key, a float[4])"
        )
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
        result = exec(
            db, "create virtual table v using vec0(a float[4] distance_metric l2)"
        )
        assert result == snapshot(name="distance_metric missing equals")

    def test_distance_metric_missing_value(self, db, snapshot):
        """distance_metric= without value should fail."""
        result = exec(
            db, "create virtual table v using vec0(a float[4] distance_metric=)"
        )
        assert result == snapshot(name="distance_metric missing value")

    def test_distance_metric_invalid_value(self, db, snapshot):
        """distance_metric with invalid value should fail."""
        result = exec(
            db, "create virtual table v using vec0(a float[4] distance_metric=invalid)"
        )
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
        db.execute(
            "create virtual table v using vec0(a float[4] distance_metric=cosine)"
        )
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


# Keywords and trailing tokens in partition key, primary key, auxiliary, and
# metadata column definitions. CREATE requires whole keywords and nothing after
# the definition. vec0 re-parses the stored CREATE text on every connect, so
# connect still accepts the keyword prefixes and trailing tokens that earlier
# releases created tables with.

# kind: (a value of that kind, a value of another type, the error it gives)
COLUMN_KINDS = {
    "text partition key": (
        "a",
        b"\x00",
        "partition key column p has type TEXT, but BLOB",
    ),
    "integer partition key": (
        5,
        b"\x00",
        "partition key column p has type INTEGER, but BLOB",
    ),
    "text primary key": ("a", b"\x00", "declared with a TEXT primary key"),
    "integer primary key": (
        5,
        b"\x00",
        "Only integers are allowed for primary key values",
    ),
    "text auxiliary": ("a", b"\x00", "auxiliary column c has type TEXT, but BLOB"),
    "integer auxiliary": (
        5,
        b"\x00",
        "auxiliary column c has type INTEGER, but BLOB",
    ),
    "float auxiliary": (1.5, b"\x00", "auxiliary column c has type FLOAT, but BLOB"),
    "blob auxiliary": (b"\x01", "a", "auxiliary column c has type BLOB, but TEXT"),
    "boolean metadata": (1, b"\x00", "Expected 0 or 1 for BOOLEAN metadata column"),
    "integer metadata": (5, b"\x00", "Expected integer for INTEGER metadata column"),
    "float metadata": (1.5, b"\x00", "Expected float for FLOAT metadata column"),
    "text metadata": ("a", b"\x00", "Expected text for TEXT metadata column"),
}


def column_name(declaration):
    return declaration.lstrip("+").split()[0]


def insert_value(db, declaration, kind):
    db.execute(
        f"insert into v(a, {column_name(declaration)}) values ('[1]', ?)",
        [COLUMN_KINDS[kind][0]],
    )


def assert_column_kind(db, declaration, kind):
    # The row insert_value() wrote is found, and a value of another type fails
    # with the error of the column's kind.
    column = column_name(declaration)
    value, wrong_value, error = COLUMN_KINDS[kind]
    rows = db.execute(f"select {column} from v where a match '[1]' and k = 1")
    assert [tuple(r) for r in rows] == [(value,)]
    with pytest.raises(sqlite3.DatabaseError, match=error):
        db.execute(
            f"insert into v(a, {column}) values ('[2]', ?)",
            [wrong_value],
        )


def assert_create_fails(db, declaration):
    with pytest.raises(
        sqlite3.OperationalError,
        match=rf"^vec0 constructor error: Could not parse '{re.escape(declaration)}'$",
    ):
        db.execute(f"create virtual table v using vec0(a float[1], {declaration})")
    assert db.execute("select count(*) from sqlite_master").fetchone()[0] == 0


@pytest.mark.parametrize(
    "declaration",
    [
        # partition key: text, int, integer, partition, key
        "p te partition key",
        "p i partition key",
        "p integ partition key",
        "p text part key",
        "p text partition ke",
        # primary key: text, int, integer, primary, key
        "id te primary key",
        "id i primary key",
        "id integ primary key",
        "id integer prim key",
        "id integer primary ke",
        "id te primary ke",
        # auxiliary: text, int, integer, float, double, blob
        "+c te",
        "+c i",
        "+c integ",
        "+c f",
        "+c d",
        "+c b",
        # metadata: boolean, bool, int64, integer64, integer, int, float,
        # double, float64, f64, text
        "x boolea",
        "x boo",
        "x int6",
        "x integer6",
        "x integ",
        "x i",
        "x floa",
        "x d",
        "x float6",
        "x f6",
        "x f",
        "x te",
    ],
)
def test_create_rejects_keyword_prefix(db, declaration):
    assert_create_fails(db, declaration)


@pytest.mark.parametrize(
    "declaration",
    [
        "p text partition key junk",
        "p integer partition key collate nocase",
        "id integer primary key junk",
        "id text primary key not null",
        # Without this rule, a primary key or partition key definition that
        # ends early is read as a metadata column and the rest is ignored.
        "id integer prim",
        "id integer primary",
        "p text partition",
        "+c text junk",
        "+c text collate nocase",
        "x text junk",
        "x text collate nocase",
        "x integer not null",
        "x boolean default 0",
        "x text default 'a'",
    ],
)
def test_create_rejects_tokens_after_definition(db, declaration):
    assert_create_fails(db, declaration)


@pytest.mark.parametrize(
    "declaration, kind",
    [
        ("p TEXT Partition KEY", "text partition key"),
        ("p Int PARTITION key", "integer partition key"),
        ("p INTEGER partition Key", "integer partition key"),
        ("id Text PRIMARY Key", "text primary key"),
        ("id INT primary KEY", "integer primary key"),
        ("id Integer Primary Key", "integer primary key"),
        ("+c TEXT", "text auxiliary"),
        ("+c Int", "integer auxiliary"),
        ("+c INTEGER", "integer auxiliary"),
        ("+c Float", "float auxiliary"),
        ("+c DOUBLE", "float auxiliary"),
        ("+c Blob", "blob auxiliary"),
        ("x BOOLEAN", "boolean metadata"),
        ("x Bool", "boolean metadata"),
        ("x INT64", "integer metadata"),
        ("x Integer64", "integer metadata"),
        ("x INTEGER", "integer metadata"),
        ("x Int", "integer metadata"),
        ("x FLOAT", "float metadata"),
        ("x Double", "float metadata"),
        ("x FLOAT64", "float metadata"),
        ("x F64", "float metadata"),
        ("x Text", "text metadata"),
    ],
)
def test_create_accepts_whole_keywords_in_any_case(db, declaration, kind):
    db.execute(f"create virtual table v using vec0(a float[1], {declaration})")
    insert_value(db, declaration, kind)
    assert_column_kind(db, declaration, kind)


@pytest.mark.parametrize(
    "declaration, stored, kind",
    [
        ("p text partition key", "p te partition ke", "text partition key"),
        ("p integer partition key", "p i partition key junk", "integer partition key"),
        ("id integer primary key", "id i primary ke", "integer primary key"),
        ("id text primary key", "id text primary key not null", "text primary key"),
        ("+c double", "+c d", "float auxiliary"),
        ("+c text", "+c text collate nocase", "text auxiliary"),
        ("x text", "x te", "text metadata"),
        ("x text", "x text collate nocase", "text metadata"),
        ("id integer", "id integer prim", "integer metadata"),
    ],
)
def test_connect_accepts_keyword_prefix_and_tokens_after_definition(
    tmp_path, declaration, stored, kind
):
    # Creates the table with whole keywords, then rewrites its stored
    # declaration to the form an earlier release accepted at CREATE.
    path = str(tmp_path / "test.db")

    def connect():
        db = sqlite3.connect(path)
        db.enable_load_extension(True)
        db.load_extension(get_extension_path())
        return db

    db = connect()
    db.execute(f"create virtual table v using vec0(a float[1], {declaration})")
    insert_value(db, declaration, kind)
    stored_sql = f"create virtual table v using vec0(a float[1], {stored})"
    db.execute("pragma writable_schema = on")
    db.execute("update sqlite_master set sql = ? where name = 'v'", [stored_sql])
    db.commit()
    db.close()

    db = connect()
    assert db.execute("select sql from sqlite_master where name = 'v'").fetchone() == (
        stored_sql,
    )
    assert_column_kind(db, stored, kind)
    db.execute("drop table v")
    assert (
        db.execute("select name from sqlite_master where name like 'v%'").fetchall()
        == []
    )
    db.close()


def connect_file(path):
    db = sqlite3.connect(path)
    db.enable_load_extension(True)
    db.load_extension(get_extension_path())
    return db


# vec0 2.0.2 and earlier accepted any token where a vector column definition
# has its name, `[`, `]`, and option keys and values, so tables declared like
# these exist. CREATE rejects these definitions; connect still opens such a
# table, with the distance metric 2.0.2 read.
L2 = [(1, 1.0), (2, 1.4142)]


@pytest.mark.parametrize(
    "stored, column, distances",
    [
        ("5 float[2]", '"5"', L2),
        ("= float[2]", '""', L2),
        ("b float+2+", "b", L2),
        # `+` and `=` have empty token text, which matches any option key or
        # value: `distance_metric` as a key, and `l2`, the first value tried
        ("b float[2] +=cosine", "b", [(1, 0.0), (2, 0.2929)]),
        ("b float[2] distance_metric=+", "b", L2),
        ("b float[2] ==l1", "b", [(1, 1.0), (2, 2.0)]),
    ],
)
def test_connect_accepts_vector_definition_earlier_releases_created(
    db, tmp_path, stored, column, distances
):
    with pytest.raises(
        sqlite3.OperationalError, match="(?i)^vec0 constructor error: could not parse"
    ):
        db.execute(f"create virtual table v using vec0({stored})")

    path = str(tmp_path / "test.db")
    con = connect_file(path)
    con.execute("create virtual table v using vec0(x float[2])")
    con.execute("insert into v(rowid, x) values (1, '[1, 0]')")
    con.execute("pragma writable_schema = on")
    con.execute(
        "update sqlite_master set sql = ? where name = 'v'",
        [f"create virtual table v using vec0({stored})"],
    )
    con.commit()
    con.close()

    con = connect_file(path)
    con.execute(f"insert into v(rowid, {column}) values (2, '[1, 1]')")
    rows = con.execute(
        f"select rowid, round(distance, 4) from v where {column} match '[2, 0]' and k = 2"
    )
    assert rows.fetchall() == distances
    con.close()


# 2.0.2 read `+bits text` as a vector column named `+` of type `bits` and
# failed CREATE; 2.1.0 creates it as an auxiliary column, and connect must keep
# that reading rather than fall back to 2.0.2's.
def test_connect_keeps_auxiliary_column_named_like_vector_type(tmp_path):
    path = str(tmp_path / "test.db")
    con = connect_file(path)
    con.execute("create virtual table v using vec0(a float[1], +bits text)")
    con.execute("insert into v(rowid, a, bits) values (1, '[1]', 'x')")
    con.commit()
    con.close()

    con = connect_file(path)
    assert con.execute("select bits from v where rowid = 1").fetchall() == [("x",)]
    con.close()
