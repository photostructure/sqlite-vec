import pytest
import sqlite3
from collections import OrderedDict
import json


def test_constructor_limit(db, snapshot):
    assert (
        exec(
            db,
            f"""
        create virtual table v using vec0(
          {",".join([f"metadata{x} integer" for x in range(17)])},
          v float[1]
        )
      """,
        )
        == snapshot(name="max 16 metadata columns")
    )


def test_normal(db, snapshot):
    db.execute(
        "create virtual table v using vec0(vector float[1], b boolean, n int, f float, t text, chunk_size=8)"
    )
    assert exec(
        db, "select * from sqlite_master where type = 'table' order by name"
    ) == snapshot(name="sqlite_master")

    assert vec0_shadow_table_contents(db, "v") == snapshot()

    INSERT = "insert into v(vector, b, n, f, t) values (?, ?, ?, ?, ?)"
    assert exec(db, INSERT, [b"\x11\x11\x11\x11", 1, 1, 1.1, "one"]) == snapshot()
    assert exec(db, INSERT, [b"\x22\x22\x22\x22", 1, 2, 2.2, "two"]) == snapshot()
    assert exec(db, INSERT, [b"\x33\x33\x33\x33", 1, 3, 3.3, "three"]) == snapshot()

    assert exec(db, "select * from v") == snapshot()
    assert vec0_shadow_table_contents(db, "v") == snapshot()

    assert exec(db, "drop table v") == snapshot()
    assert exec(db, "select * from sqlite_master") == snapshot()


#
# assert exec(db, "select * from v") == snapshot()
# assert vec0_shadow_table_contents(db, "v") == snapshot()
#
# db.execute("drop table v;")
# assert exec(db, "select * from sqlite_master order by name") == snapshot(
#    name="sqlite_master post drop"
# )


def test_text_knn(db, snapshot):
    db.execute(
        "create virtual table v using vec0(vector float[1], name text, chunk_size=8)"
    )
    assert vec0_shadow_table_contents(db, "v") == snapshot()
    INSERT = "insert into v(vector, name) values (?, ?)"
    db.execute("""
      INSERT INTO v(vector, name) VALUES
        ('[.11]', 'aaa'),
        ('[.22]', 'bbb'),
        ('[.33]', 'ccc'),
        ('[.44]', 'ddd'),
        ('[.55]', 'eee'),
        ('[.66]', 'fff'),
        ('[.77]', 'ggg'),
        ('[.88]', 'hhh'),
        ('[.99]', 'iii');
    """)
    assert exec(db, "select * from v") == snapshot()
    assert vec0_shadow_table_contents(db, "v") == snapshot()

    assert (
        exec(
            db,
            "select rowid, name, distance from v where vector match '[1]' and k = 5",
        )
        == snapshot()
    )

    assert (
        exec(
            db,
            "select rowid, name, distance from v where vector match '[1]' and k = 5 and name < 'ddd'",
        )
        == snapshot()
    )
    assert (
        exec(
            db,
            "select rowid, name, distance from v where vector match '[1]' and k = 5 and name <= 'ddd'",
        )
        == snapshot()
    )
    assert (
        exec(
            db,
            "select rowid, name, distance from v where vector match '[1]' and k = 5 and name > 'fff'",
        )
        == snapshot()
    )
    assert (
        exec(
            db,
            "select rowid, name, distance from v where vector match '[1]' and k = 5 and name >= 'fff'",
        )
        == snapshot()
    )
    assert (
        exec(
            db,
            "select rowid, name, distance from v where vector match '[1]' and k = 5 and name = 'aaa'",
        )
        == snapshot()
    )
    assert (
        exec(
            db,
            "select rowid, name, distance from v where vector match '[.01]' and k = 5 and name != 'aaa'",
        )
        == snapshot()
    )


def test_long_text_updates(db, snapshot):
    db.execute(
        "create virtual table v using vec0(vector float[1], name text, chunk_size=8)"
    )
    assert vec0_shadow_table_contents(db, "v") == snapshot()
    INSERT = "insert into v(vector, name) values (?, ?)"
    exec(db, INSERT, [b"\x11\x11\x11\x11", "123456789a12"])
    exec(db, INSERT, [b"\x11\x11\x11\x11", "123456789a123"])
    assert exec(db, "select * from v") == snapshot()
    assert vec0_shadow_table_contents(db, "v") == snapshot()


def test_long_text_knn(db, snapshot):
    db.execute(
        "create virtual table v using vec0(vector float[1], name text, chunk_size=8)"
    )
    INSERT = "insert into v(vector, name) values (?, ?)"
    exec(db, INSERT, ["[1]", "aaaa"])
    exec(db, INSERT, ["[2]", "aaaaaaaaaaaa_aaa"])
    exec(db, INSERT, ["[3]", "bbbb"])
    exec(db, INSERT, ["[4]", "bbbbbbbbbbbb_bbb"])
    exec(db, INSERT, ["[5]", "cccc"])
    exec(db, INSERT, ["[6]", "cccccccccccc_ccc"])

    tests = [
        "bbbb",
        "bb",
        "bbbbbb",
        "bbbbbbbbbbbb_bbb",
        "bbbbbbbbbbbb_aaa",
        "bbbbbbbbbbbb_ccc",
        "longlonglonglonglonglonglong",
    ]
    ops = ["=", "!=", "<", "<=", ">", ">="]
    op_names = ["eq", "ne", "lt", "le", "gt", "ge"]

    for test in tests:
        for op, op_name in zip(ops, op_names):
            assert exec(
                db,
                f"select rowid, name, distance from v where vector match '[100]' and k = 5 and name {op} ?",
                [test],
            ) == snapshot(name=f"{op_name}-{test}")


# Text values for comparing KNN text filters with an ordinary table, whose
# BINARY collation compares bytes with memcmp() and sorts a prefix first.
TEXT_FILTER_VALUES = [
    "",
    "a",
    "abc",
    "x" * 12,  # the longest value kept whole in the 12-byte prefix
    "x" * 13,  # the shortest value stored in the long-text table
    "a" * 11,
    "a" * 13,
    "a" * 12,
    "a" * 20,  # a long value that is a prefix of the next one
    "a" * 21,
    "ab\0c",
    "ab\0d",
    "a" * 14 + "\0b",
    "a" * 14 + "\0c",
    "\u00e9t\u00e9",
    "zzz",
    # NOCASE folds ASCII letters only, and RTRIM ignores trailing spaces only
    "ABC",
    "abc ",
    "ABC  ",
    "abc\t",
    " ",
    "a" * 11 + " ",
    "X" * 12,
    "x" * 12 + " ",  # stored in the long-text table, RTRIM equals "x" * 12
    "X" * 13,
    "x" * 13 + "   ",
    "A" * 20,
    "a" * 20 + " ",
    "a" * 12 + "B",
    "A" * 12 + "b",
    "AB\0D",  # NOCASE stops at a NUL, so this equals "ab\0c"
    "A" * 14 + "\0d",
    # long values with a NUL inside the 12-byte view: each pair is equal under
    # NOCASE, which stops at the NUL, but differs after it
    "ab\0" + "x" * 12,
    "AB\0" + "y" * 12,
    "abcdefghijk\0" + "xyz",  # the NUL is the view's last byte
    "ABCDEFGHIJK\0" + "XYW",
    "ab\0" + "x" * 13,
    "\u00c9t\u00c9",
    "\u00e9T\u00e9",
]


def _create_text_filter_tables(db):
    db.execute("create virtual table v using vec0(e float[1], t text, chunk_size=8)")
    # untyped, like vec0's columns, so SQLite compares values with it as is
    db.execute("create table plain(t)")
    for rowid, value in enumerate(TEXT_FILTER_VALUES, 1):
        db.execute("insert into v(rowid, e, t) values (?, '[0]', ?)", [rowid, value])
        db.execute("insert into plain(rowid, t) values (?, ?)", [rowid, value])


def _assert_knn_filter_matches_plain(db, condition, parameters):
    expected = db.execute(
        f"select rowid from plain where {condition} order by rowid", parameters
    ).fetchall()
    actual = db.execute(
        f"select rowid from v where e match '[0]' and k = 100 and {condition}",
        parameters,
    ).fetchall()
    assert sorted(r[0] for r in actual) == [r[0] for r in expected], (
        condition,
        parameters,
    )


def test_text_range_matches_plain_table(db):
    _create_text_filter_tables(db)
    for op in ["<", "<=", ">", ">="]:
        for target in TEXT_FILTER_VALUES:
            _assert_knn_filter_matches_plain(db, f"t {op} ?", [target])


def test_text_equality_matches_plain_table(db):
    _create_text_filter_tables(db)
    for target in TEXT_FILTER_VALUES:
        for op in ["=", "!=", "is", "is not"]:
            _assert_knn_filter_matches_plain(db, f"t {op} ?", [target])
        _assert_knn_filter_matches_plain(db, "t in (?, 'nonsense')", [target])


def test_text_like_glob_matches_plain_table(db):
    # "x" * 12 is followed by a row whose stored length is 13, and "a" * 12 is
    # row 8, the last row of the first chunk. Matching used to run past both.
    _create_text_filter_tables(db)
    for pattern in ["%x", "%a", "x%", "a%", "%c", "_bc", "%\u00e9", "_" * 13]:
        _assert_knn_filter_matches_plain(db, "t like ?", [pattern])
    for pattern in ["*x", "*a", "x*", "a*", "*[cd]", "?bc", "?" * 13]:
        _assert_knn_filter_matches_plain(db, "t glob ?", [pattern])
    # "[" starts a character class, so these are not literal prefixes
    for pattern in ["[ab]*", "[a]*", "a[b]*"]:
        _assert_knn_filter_matches_plain(db, "t glob ?", [pattern])
    # SQLite reads a pattern only up to a NUL
    for condition, pattern in [
        ("t like ?", "a\0x%"),
        ("t glob ?", "a\0x*"),
        ("t glob ?", "[ab]*\0x"),
    ]:
        _assert_knn_filter_matches_plain(db, condition, [pattern])


def test_text_collate_matches_plain_table(db):
    _create_text_filter_tables(db)
    targets = TEXT_FILTER_VALUES + ["abc  ", "Abc", "X" * 12 + "  ", "A" * 13]
    for collation in ["nocase", "rtrim"]:
        for target in targets:
            for op in ["=", "<", "<=", ">", ">=", "is"]:
                _assert_knn_filter_matches_plain(
                    db, f"t {op} ? collate {collation}", [target]
                )
                _assert_knn_filter_matches_plain(
                    db, f"t collate {collation} {op} ?", [target]
                )
            # IN compares with the left operand's collation, so the second form
            # compares bytewise. SQLite rewrites the third, a one-value IN, as
            # `=`, which takes the collation from either side.
            for condition in [
                f"t collate {collation} in (?, 'nonsense')",
                f"t in (? collate {collation}, 'nonsense')",
                f"t in (? collate {collation})",
            ]:
                _assert_knn_filter_matches_plain(db, condition, [target])


def test_text_collate_not_equal_rechecked(db):
    # SQLite reports BINARY for a text `!=` or IS NOT constraint whatever
    # collation it names, so vec0 compares bytewise and SQLite re-checks each
    # row vec0 returns. A row equal under the collation but not bytewise takes
    # one of the k rows and is then dropped, so a query returns the nearest of
    # the plain table's rows in distance order, possibly fewer than k of them.
    # That is why this asserts a prefix of the plain table's rows, not equality.
    values = ["ABC", "abc ", "xyz", "abc", "Abc  ", "abd", "ABC\t", "aBc"]
    db.execute("create virtual table v using vec0(e float[1], t text, chunk_size=8)")
    db.execute("create table plain(t, d)")
    for rowid, value in enumerate(values, 1):
        db.execute(
            "insert into v(rowid, e, t) values (?, ?, ?)", [rowid, f"[{rowid}]", value]
        )
        db.execute(
            "insert into plain(rowid, t, d) values (?, ?, ?)", [rowid, value, rowid]
        )
    conditions = []
    for op in ["!=", "is not"]:
        conditions.append((f"t {op} ?", ["k", "limit"]))
        for collation in ["nocase", "rtrim"]:
            conditions.append((f"t {op} ? collate {collation}", ["k", "limit"]))
            # never offered to vec0, so SQLite passes it no LIMIT
            conditions.append((f"t collate {collation} {op} ?", ["k"]))
    for condition, forms in conditions:
        expected = [
            row[0]
            for row in db.execute(
                f"select rowid from plain where {condition} order by d", ["abc"]
            )
        ]
        for k in range(1, len(values) + 1):
            for form in forms:
                sql = f"select rowid from v where e match '[0]' and {condition}"
                sql += " and k = ?" if form == "k" else " limit ?"
                actual = [row[0] for row in db.execute(sql, ["abc", k])]
                assert actual == expected[: len(actual)], (sql, k)
                if "collate" not in condition:
                    # a bytewise re-check drops no row
                    assert len(actual) == min(k, len(expected)), (sql, k)


def test_text_collate_unsupported(db):
    # vec0 compares text with BINARY, NOCASE, and RTRIM only, so another
    # collation on a KNN text metadata constraint is an error.
    db.create_collation(
        "reverse", lambda a, b: (a[::-1] > b[::-1]) - (a[::-1] < b[::-1])
    )
    db.execute(
        "create virtual table v using vec0(e float[1], t text, n integer, f float, b boolean, chunk_size=8)"
    )
    db.execute("create table plain(t, n, f, b)")
    rows = [(1, "abc", 1, 1.5, 1), (2, "cba", 2, -2.0, 0), (3, "1", 3, 1.0, 1)]
    for row in rows:
        db.execute(
            "insert into v(rowid, e, t, n, f, b) values (?, '[0]', ?, ?, ?, ?)", row
        )
        db.execute("insert into plain(rowid, t, n, f, b) values (?, ?, ?, ?, ?)", row)
    for condition in [
        "t = ? collate reverse",
        "t collate reverse = ?",
        "t is ? collate reverse",
        "t > ? collate reverse",
        "t collate reverse <= ?",
        "t collate reverse in (?, 'nonsense')",
    ]:
        with pytest.raises(
            sqlite3.OperationalError, match="Only BINARY, NOCASE, and RTRIM"
        ):
            db.execute(
                f"select rowid from v where e match '[0]' and k = 10 and {condition}",
                ["abc"],
            )
    # SQLite offers vec0 each branch of an OR as if it stood alone, so the
    # error also fires inside an OR, which SQLite used to evaluate itself
    for condition in [
        "(t = ? collate reverse or n = 2)",
        "(n = 2 or t collate reverse > ?)",
    ]:
        with pytest.raises(
            sqlite3.OperationalError, match="Only BINARY, NOCASE, and RTRIM"
        ):
            db.execute(
                f"select rowid from v where e match '[0]' and k = 10 and {condition}",
                ["abc"],
            )

    # SQLite never compares an integer or real with a collation, and these
    # text constraints compare without one or are re-checked by SQLite
    def knn(condition, parameters):
        return sorted(
            row[0]
            for row in db.execute(
                f"select rowid from v where e match '[0]' and k = 10 and {condition}",
                parameters,
            )
        )

    def plain(condition, parameters):
        return sorted(
            row[0]
            for row in db.execute(
                f"select rowid from plain where {condition}", parameters
            )
        )

    for condition in [
        "n = ? collate reverse",
        "n collate reverse > ?",
        "n collate reverse in (?, 2)",
        "f <= ? collate reverse",
        "b = ? collate reverse",
        "b collate reverse is not ?",
        "t != ? collate reverse",
        "t is not ? collate reverse",
        "t like ? collate reverse",
        "t glob ? collate reverse",
    ]:
        for value in [1, 1.5, "1", "abc", "a%", "a*"]:
            assert knn(condition, [value]) == plain(condition, [value]), (
                condition,
                value,
            )
    condition = "t collate reverse is not null"
    assert knn(condition, []) == plain(condition, []) == [1, 2, 3]


def test_text_like_prefix_with_limit(db):
    # For a LIKE pattern with a literal prefix, SQLite also offers vec0
    # `t collate nocase >= ?` and `t collate nocase < ?` range terms (unless
    # case_sensitive_like is on). vec0 must apply them, or SQLite does not pass
    # it the LIMIT.
    _create_text_filter_tables(db)
    patterns = ["abc%", "ABC%", "x%", "X" * 12 + "%", "x" * 13 + "%", "a" * 12 + "b%"]
    for pattern in patterns:
        expected = [
            row[0]
            for row in db.execute(
                "select rowid from plain where t like ? order by rowid", [pattern]
            )
        ]
        _assert_knn_filter_matches_plain(db, "t like ?", [pattern])
        for condition, parameters in [
            ("t like ?", [pattern]),
            (f"t like '{pattern}'", []),
        ]:
            for limit in [2, 100]:
                actual = [
                    row[0]
                    for row in db.execute(
                        f"select rowid from v where e match '[0]' and {condition} limit {limit}",
                        parameters,
                    )
                ]
                assert len(actual) == min(limit, len(expected)), (condition, limit)
                assert set(actual) <= set(expected), (condition, limit)


def test_types(db, snapshot):
    db.execute(
        "create virtual table v using vec0(vector float[1], b boolean, n int, f float, t text, chunk_size=8)"
    )
    INSERT = "insert into v(vector, b, n, f, t) values (?, ?, ?, ?, ?)"

    assert exec(db, INSERT, [b"\x11\x11\x11\x11", 1, 1, 1.1, "test"]) == snapshot(
        name="legal"
    )

    # fmt: off
    assert exec(db, INSERT, [b"\x11\x11\x11\x11", 'illegal', 1, 1.1, 'test']) == snapshot(name="illegal-type-boolean")
    assert exec(db, INSERT, [b"\x11\x11\x11\x11", 1, 'illegal', 1.1, 'test']) == snapshot(name="illegal-type-int")
    assert exec(db, INSERT, [b"\x11\x11\x11\x11", 1, 1, 'illegal', 'test']) == snapshot(name="illegal-type-float")
    assert exec(db, INSERT, [b"\x11\x11\x11\x11", 1, 1, 1.1, 420]) == snapshot(name="illegal-type-text")
    # fmt: on

    assert exec(db, INSERT, [b"\x11\x11\x11\x11", 44, 1, 1.1, "test"]) == snapshot(
        name="illegal-boolean"
    )


def test_boolean_rejects_integers_beyond_32_bits(db):
    # the low 32 bits of 2**32 and 2**32 + 1 are 0 and 1
    db.execute(
        "create virtual table v using vec0(vector float[1], b boolean, chunk_size=8)"
    )
    db.execute("insert into v(rowid, vector, b) values (1, '[1]', 1)")
    for value in [2**32, 2**32 + 1]:
        with pytest.raises(sqlite3.OperationalError, match="Expected 0 or 1"):
            db.execute("insert into v(rowid, vector, b) values (2, '[2]', ?)", [value])
        with pytest.raises(sqlite3.OperationalError, match="Expected 0 or 1"):
            db.execute("update v set b = ? where rowid = 1", [value])
    assert [tuple(row) for row in db.execute("select rowid, b from v")] == [(1, 1)]


def test_rejected_insert_leaves_no_row(db):
    # vec0 writes its shadow tables through separate statements that a failed
    # INSERT does not roll back, so value types are checked before any write
    db.execute(
        "create virtual table v using vec0(vector float[1], t text, +a integer, chunk_size=8)"
    )
    db.execute("insert into v(rowid, vector, t, a) values (1, '[1]', 'one', 1)")
    for values in [(2, "[2]", 2, 2), (2, "[2]", "two", "not int")]:
        with pytest.raises(sqlite3.DatabaseError):
            db.execute("insert into v(rowid, vector, t, a) values (?, ?, ?, ?)", values)
    assert [r[0] for r in db.execute("select rowid from v")] == [1]
    assert [r[0] for r in db.execute("select rowid from v_rowids")] == [1]


def test_updates(db, snapshot):
    db.execute(
        "create virtual table v using vec0(vector float[1], b boolean, n int, f float, t text, chunk_size=8)"
    )
    INSERT = "insert into v(rowid, vector, b, n, f, t) values (?, ?, ?, ?, ?, ?)"

    exec(db, INSERT, [1, b"\x11\x11\x11\x11", 1, 1, 1.1, "test1"])
    exec(db, INSERT, [2, b"\x22\x22\x22\x22", 1, 2, 2.2, "test2"])
    exec(db, INSERT, [3, b"\x33\x33\x33\x33", 1, 3, 3.3, "1234567890123"])
    assert exec(db, "select * from v") == snapshot(name="1-init-contents")
    assert vec0_shadow_table_contents(db, "v") == snapshot(name="1-init-shadow")

    assert exec(
        db, "UPDATE v SET b = 0, n = 11, f = 11.11, t = 'newtest1' where rowid = 1"
    )
    assert exec(db, "select * from v") == snapshot(name="general-update-contents")
    assert vec0_shadow_table_contents(db, "v") == snapshot(
        name="general-update-shaodnw"
    )

    # string update #1: long string updated to long string
    exec(db, "UPDATE v SET t = '1234567890123-updated' where rowid = 3")
    assert exec(db, "select * from v") == snapshot(name="string-update-1-contents")
    assert vec0_shadow_table_contents(db, "v") == snapshot(
        name="string-update-1-shadow"
    )

    # string update #2: short string updated to short string
    exec(db, "UPDATE v SET t = 'test2-short' where rowid = 2")
    assert exec(db, "select * from v") == snapshot(name="string-update-2-contents")
    assert vec0_shadow_table_contents(db, "v") == snapshot(
        name="string-update-2-shadow"
    )

    # string update #3: short string updated to long string
    exec(db, "UPDATE v SET t = 'test2-long-long-long' where rowid = 2")
    assert exec(db, "select * from v") == snapshot(name="string-update-3-contents")
    assert vec0_shadow_table_contents(db, "v") == snapshot(
        name="string-update-3-shadow"
    )

    # string update #4: long string updated to short string
    exec(db, "UPDATE v SET t = 'test2-shortx' where rowid = 2")
    assert exec(db, "select * from v") == snapshot(name="string-update-4-contents")
    assert vec0_shadow_table_contents(db, "v") == snapshot(
        name="string-update-4-shadow"
    )


def test_deletes(db, snapshot):
    db.execute(
        "create virtual table v using vec0(vector float[1], b boolean, n int, f float, t text, chunk_size=8)"
    )
    INSERT = "insert into v(rowid, vector, b, n, f, t) values (?, ?, ?, ?, ?, ?)"

    assert exec(db, INSERT, [1, b"\x11\x11\x11\x11", 1, 1, 1.1, "test1"]) == snapshot()
    assert exec(db, INSERT, [2, b"\x22\x22\x22\x22", 1, 2, 2.2, "test2"]) == snapshot()
    assert (
        exec(db, INSERT, [3, b"\x33\x33\x33\x33", 1, 3, 3.3, "1234567890123"])
        == snapshot()
    )

    assert exec(db, "select * from v") == snapshot()
    assert vec0_shadow_table_contents(db, "v") == snapshot()

    assert exec(db, "DELETE FROM v where rowid = 1") == snapshot()
    assert exec(db, "select * from v") == snapshot()
    assert vec0_shadow_table_contents(db, "v") == snapshot()

    assert exec(db, "DELETE FROM v where rowid = 3") == snapshot()
    assert exec(db, "select * from v") == snapshot()
    assert vec0_shadow_table_contents(db, "v") == snapshot()


def test_renames(db, snapshot):
    db.execute(
        "create virtual table v using vec0(vector float[1], b boolean, n int, f float, t text, chunk_size=8)"
    )
    INSERT = "insert into v(rowid, vector, b, n, f, t) values (?, ?, ?, ?, ?, ?)"

    assert exec(db, INSERT, [1, b"\x11\x11\x11\x11", 1, 1, 1.1, "test1"]) == snapshot()
    assert exec(db, INSERT, [2, b"\x22\x22\x22\x22", 1, 2, 2.2, "test2"]) == snapshot()
    assert (
        exec(db, INSERT, [3, b"\x33\x33\x33\x33", 1, 3, 3.3, "1234567890123"])
        == snapshot()
    )

    assert exec(db, "select * from v") == snapshot()
    assert vec0_shadow_table_contents(db, "v") == snapshot()

    result = exec(db, "select * from v")
    db.execute("alter table v rename to v1")
    assert exec(db, "select * from v1")["rows"] == result["rows"]


def test_knn(db, snapshot):
    db.execute(
        "create virtual table v using vec0(vector float[1], name text, chunk_size=8)"
    )
    assert exec(
        db, "select * from sqlite_master where type = 'table' order by name"
    ) == snapshot(name="sqlite_master")
    db.executemany(
        "insert into v(vector, name) values (?, ?)",
        [("[1]", "alex"), ("[2]", "brian"), ("[3]", "craig")],
    )

    # LIKE is now supported on text metadata columns
    assert (
        exec(
            db,
            "select *, distance from v where vector match '[5]' and k = 3 and name like 'a%'",
        )
        == snapshot()
    )


def test_like(db, snapshot):
    """Test LIKE operator on text metadata columns with various patterns"""
    db.execute(
        "create virtual table v using vec0(vector float[1], name text, chunk_size=8)"
    )

    # Insert test data with both short (≤12 bytes) and long (>12 bytes) strings
    db.execute("""
      INSERT INTO v(vector, name) VALUES
        ('[.11]', 'alice'),
        ('[.22]', 'alex'),
        ('[.33]', 'bob'),
        ('[.44]', 'bobby'),
        ('[.55]', 'carol'),
        ('[.66]', 'this_is_a_very_long_string_name'),
        ('[.77]', 'this_is_another_long_one'),
        ('[.88]', 'yet_another_string'),
        ('[.99]', 'zebra');
    """)

    # Test prefix-only patterns (fast path)
    assert exec(
        db,
        "select rowid, name, distance from v where vector match '[1]' and k = 5 and name like 'a%'",
    ) == snapshot(name="prefix a%")

    assert exec(
        db,
        "select rowid, name, distance from v where vector match '[1]' and k = 5 and name like 'bob%'",
    ) == snapshot(name="prefix bob%")

    assert exec(
        db,
        "select rowid, name, distance from v where vector match '[1]' and k = 5 and name like 'this_%'",
    ) == snapshot(name="prefix this_% with long strings")

    # Test complex patterns (slow path)
    assert exec(
        db,
        "select rowid, name, distance from v where vector match '[1]' and k = 9 and name like '%ice'",
    ) == snapshot(name="suffix %ice")

    assert exec(
        db,
        "select rowid, name, distance from v where vector match '[1]' and k = 9 and name like '%o%'",
    ) == snapshot(name="contains %o%")

    assert exec(
        db,
        "select rowid, name, distance from v where vector match '[1]' and k = 9 and name like 'a_e_'",
    ) == snapshot(name="wildcard pattern a_e_")

    # Test edge cases
    assert exec(
        db,
        "select rowid, name, distance from v where vector match '[1]' and k = 9 and name like '%'",
    ) == snapshot(name="match all %")

    assert exec(
        db,
        "select rowid, name, distance from v where vector match '[1]' and k = 9 and name like 'nomatch%'",
    ) == snapshot(name="no matches nomatch%")

    # Test LIKE on non-TEXT metadata should error
    db.execute("create virtual table v2 using vec0(vector float[1], age int)")
    db.execute("insert into v2(vector, age) values ('[1]', 25)")

    assert exec(
        db,
        "select * from v2 where vector match '[1]' and k = 1 and age like '2%'",
    ) == snapshot(name="error: LIKE on integer column")


def test_like_case_insensitive(db, snapshot):
    """Test LIKE operator is case-insensitive (SQLite default)"""
    db.execute(
        "create virtual table v using vec0(vector float[1], name text, chunk_size=8)"
    )

    # Insert test data with mixed case
    db.execute("""
      INSERT INTO v(vector, name) VALUES
        ('[.11]', 'Apple'),
        ('[.22]', 'BANANA'),
        ('[.33]', 'Cherry'),
        ('[.44]', 'DURIAN_IS_LONG'),
        ('[.55]', 'elderberry_is_very_long_string');
    """)

    # Test case insensitivity with prefix patterns (fast path)
    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name like 'apple%'",
    ) == snapshot(name="lowercase pattern matches uppercase data")

    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name like 'CHERRY%'",
    ) == snapshot(name="uppercase pattern matches mixed case data")

    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name like 'DuRiAn%'",
    ) == snapshot(name="mixed case pattern matches uppercase data")

    # Test case insensitivity with long strings
    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name like 'ELDERBERRY%'",
    ) == snapshot(name="uppercase pattern matches long lowercase data")

    # Test case insensitivity with complex patterns (slow path)
    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name like '%APPLE%'",
    ) == snapshot(name="complex pattern case insensitive")


def test_like_boundary_conditions(db, snapshot):
    """Test LIKE operator at 12-byte cache boundary"""
    db.execute(
        "create virtual table v using vec0(vector float[1], name text, chunk_size=8)"
    )

    # Insert test data with specific lengths
    # Exactly 12 bytes: fits in cache
    # Exactly 13 bytes: first 12 bytes in cache, last byte requires full fetch
    db.execute("""
      INSERT INTO v(vector, name) VALUES
        ('[.11]', 'exactly_12ch'),
        ('[.22]', 'exactly_13chr'),
        ('[.33]', 'short'),
        ('[.44]', 'this_is_14byte'),
        ('[.55]', 'this_is_much_longer_than_12_bytes');
    """)

    # Verify lengths
    lengths = db.execute("select name, length(name) from v order by rowid").fetchall()
    assert (
        lengths[0][1] == 12
    ), f"Expected 12 bytes, got {lengths[0][1]} for '{lengths[0][0]}'"
    assert (
        lengths[1][1] == 13
    ), f"Expected 13 bytes, got {lengths[1][1]} for '{lengths[1][0]}'"

    # Test prefix matching at exactly 12 bytes
    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name like 'exactly_12%'",
    ) == snapshot(name="12-byte boundary: exact match")

    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name like 'exactly%'",
    ) == snapshot(name="12-byte boundary: prefix matches both 12 and 13 byte strings")

    # Test pattern that is exactly 12 bytes (excluding %)
    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name like 'exactly_13ch%'",
    ) == snapshot(name="13-byte boundary: 12-byte pattern")

    # Test short pattern on long strings
    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name like 'this%'",
    ) == snapshot(name="boundary: short pattern on mixed length strings")

    # Test case insensitivity at boundary
    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name like 'EXACTLY_12%'",
    ) == snapshot(name="boundary: case insensitive at 12 bytes")


def test_glob(db, snapshot):
    """Test GLOB operator on text metadata columns with various patterns"""
    db.execute(
        "create virtual table v using vec0(vector float[1], name text, chunk_size=8)"
    )

    # Insert test data with both short (≤12 bytes) and long (>12 bytes) strings
    db.execute("""
      INSERT INTO v(vector, name) VALUES
        ('[.11]', 'alice'),
        ('[.22]', 'alex'),
        ('[.33]', 'bob'),
        ('[.44]', 'bobby'),
        ('[.55]', 'carol'),
        ('[.66]', 'this_is_a_very_long_string_name'),
        ('[.77]', 'this_is_another_long_one'),
        ('[.88]', 'yet_another_string'),
        ('[.99]', 'zebra');
    """)

    # Test prefix-only patterns (fast path)
    assert exec(
        db,
        "select rowid, name, distance from v where vector match '[1]' and k = 5 and name glob 'a*'",
    ) == snapshot(name="prefix a*")

    assert exec(
        db,
        "select rowid, name, distance from v where vector match '[1]' and k = 5 and name glob 'bob*'",
    ) == snapshot(name="prefix bob*")

    assert exec(
        db,
        "select rowid, name, distance from v where vector match '[1]' and k = 5 and name glob 'this_*'",
    ) == snapshot(name="prefix this_* with long strings")

    # Test complex patterns (slow path)
    assert exec(
        db,
        "select rowid, name, distance from v where vector match '[1]' and k = 9 and name glob '*ice'",
    ) == snapshot(name="suffix *ice")

    assert exec(
        db,
        "select rowid, name, distance from v where vector match '[1]' and k = 9 and name glob '*o*'",
    ) == snapshot(name="contains *o*")

    assert exec(
        db,
        "select rowid, name, distance from v where vector match '[1]' and k = 9 and name glob 'a?e?'",
    ) == snapshot(name="wildcard pattern a?e?")

    # Test edge cases
    assert exec(
        db,
        "select rowid, name, distance from v where vector match '[1]' and k = 9 and name glob '*'",
    ) == snapshot(name="match all *")

    assert exec(
        db,
        "select rowid, name, distance from v where vector match '[1]' and k = 9 and name glob 'nomatch*'",
    ) == snapshot(name="no matches nomatch*")

    # Test GLOB on non-TEXT metadata should error
    db.execute("create virtual table v2 using vec0(vector float[1], age int)")
    db.execute("insert into v2(vector, age) values ('[1]', 25)")

    assert exec(
        db,
        "select * from v2 where vector match '[1]' and k = 1 and age glob '2*'",
    ) == snapshot(name="error: GLOB on integer column")


def test_glob_case_sensitive(db, snapshot):
    """Test GLOB operator is case-sensitive (unlike LIKE)"""
    db.execute(
        "create virtual table v using vec0(vector float[1], name text, chunk_size=8)"
    )

    # Insert test data with mixed case
    db.execute("""
      INSERT INTO v(vector, name) VALUES
        ('[.11]', 'Apple'),
        ('[.22]', 'BANANA'),
        ('[.33]', 'Cherry'),
        ('[.44]', 'DURIAN_IS_LONG'),
        ('[.55]', 'elderberry_is_very_long_string');
    """)

    # Test case sensitivity with prefix patterns (fast path)
    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name glob 'apple*'",
    ) == snapshot(name="lowercase pattern should not match uppercase data")

    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name glob 'Apple*'",
    ) == snapshot(name="exact case match Apple*")

    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name glob 'CHERRY*'",
    ) == snapshot(name="uppercase pattern should not match mixed case")

    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name glob 'Cherry*'",
    ) == snapshot(name="exact case match Cherry*")

    # Test case sensitivity with long strings
    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name glob 'ELDERBERRY*'",
    ) == snapshot(name="uppercase pattern should not match long lowercase data")

    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name glob 'elderberry*'",
    ) == snapshot(name="lowercase pattern matches long lowercase data")

    # Test case sensitivity with complex patterns (slow path)
    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name glob '*APPLE*'",
    ) == snapshot(name="complex pattern case sensitive")


def test_glob_boundary_conditions(db, snapshot):
    """Test GLOB operator at 12-byte cache boundary"""
    db.execute(
        "create virtual table v using vec0(vector float[1], name text, chunk_size=8)"
    )

    # Insert test data with specific lengths
    db.execute("""
      INSERT INTO v(vector, name) VALUES
        ('[.11]', 'exactly_12ch'),
        ('[.22]', 'exactly_13chr'),
        ('[.33]', 'short'),
        ('[.44]', 'this_is_14byte'),
        ('[.55]', 'this_is_much_longer_than_12_bytes');
    """)

    # Test prefix pattern that fits in cache (fast path)
    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name glob 'exactly_*'",
    ) == snapshot(name="boundary: prefix pattern at boundary")

    # Test that case sensitivity works at boundary
    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name glob 'EXACTLY_*'",
    ) == snapshot(name="boundary: case sensitive at 12 bytes")


def test_is_integer_metadata(db, snapshot):
    """Test IS operator on integer metadata columns"""
    db.execute(
        "create virtual table v using vec0(vector float[1], age int, chunk_size=8)"
    )

    # Insert test data
    db.execute("""
      INSERT INTO v(vector, age) VALUES
        ('[.11]', 10),
        ('[.22]', 20),
        ('[.33]', 30),
        ('[.44]', 20),
        ('[.55]', 40);
    """)

    # Test IS (should work like =)
    assert exec(
        db,
        "select rowid, age from v where vector match '[1]' and k = 5 and age is 20",
    ) == snapshot(name="IS 20")

    # Test IS NOT (should work like !=)
    assert exec(
        db,
        "select rowid, age from v where vector match '[1]' and k = 5 and age is not 20",
    ) == snapshot(name="IS NOT 20")

    # Test IS NULL (should return no rows - metadata doesn't support NULL)
    assert exec(
        db,
        "select rowid, age from v where vector match '[1]' and k = 5 and age is null",
    ) == snapshot(name="IS NULL")

    # Test IS NOT NULL (should return all rows - metadata doesn't support NULL)
    assert exec(
        db,
        "select rowid, age from v where vector match '[1]' and k = 5 and age is not null",
    ) == snapshot(name="IS NOT NULL")


def test_is_float_metadata(db, snapshot):
    """Test IS operator on float metadata columns"""
    db.execute(
        "create virtual table v using vec0(vector float[1], score float, chunk_size=8)"
    )

    # Insert test data
    db.execute("""
      INSERT INTO v(vector, score) VALUES
        ('[.11]', 1.5),
        ('[.22]', 2.5),
        ('[.33]', 3.5),
        ('[.44]', 2.5),
        ('[.55]', 4.5);
    """)

    # Test IS (should work like =)
    assert exec(
        db,
        "select rowid, score from v where vector match '[1]' and k = 5 and score is 2.5",
    ) == snapshot(name="IS 2.5")

    # Test IS NOT (should work like !=)
    assert exec(
        db,
        "select rowid, score from v where vector match '[1]' and k = 5 and score is not 2.5",
    ) == snapshot(name="IS NOT 2.5")

    # Test IS NULL (should return no rows)
    assert exec(
        db,
        "select rowid, score from v where vector match '[1]' and k = 5 and score is null",
    ) == snapshot(name="IS NULL float")

    # Test IS NOT NULL (should return all rows)
    assert exec(
        db,
        "select rowid, score from v where vector match '[1]' and k = 5 and score is not null",
    ) == snapshot(name="IS NOT NULL float")


def test_is_text_metadata(db, snapshot):
    """Test IS operator on text metadata columns"""
    db.execute(
        "create virtual table v using vec0(vector float[1], name text, chunk_size=8)"
    )

    # Insert test data
    db.execute("""
      INSERT INTO v(vector, name) VALUES
        ('[.11]', 'alice'),
        ('[.22]', 'bob'),
        ('[.33]', 'carol'),
        ('[.44]', 'bob'),
        ('[.55]', 'david');
    """)

    # Test IS (should work like =)
    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name is 'bob'",
    ) == snapshot(name="IS bob")

    # Test IS NOT (should work like !=)
    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name is not 'bob'",
    ) == snapshot(name="IS NOT bob")

    # Test IS NULL (should return no rows)
    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name is null",
    ) == snapshot(name="IS NULL text")

    # Test IS NOT NULL (should return all rows)
    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name is not null",
    ) == snapshot(name="IS NOT NULL text")


def test_is_boolean_metadata(db, snapshot):
    """Test IS operator on boolean metadata columns (issue #190 use case)"""
    db.execute(
        "create virtual table v using vec0(vector float[1], is_hidden boolean, chunk_size=8)"
    )

    # Insert test data
    db.execute("""
      INSERT INTO v(vector, is_hidden) VALUES
        ('[.11]', 0),
        ('[.22]', 1),
        ('[.33]', 0),
        ('[.44]', 1),
        ('[.55]', 0);
    """)

    # Test IS FALSE (the original use case from issue #190)
    assert exec(
        db,
        "select rowid, is_hidden from v where vector match '[1]' and k = 5 and is_hidden is 0",
    ) == snapshot(name="is_hidden IS false")

    # Test IS TRUE
    assert exec(
        db,
        "select rowid, is_hidden from v where vector match '[1]' and k = 5 and is_hidden is 1",
    ) == snapshot(name="is_hidden IS true")

    # Test IS NOT FALSE
    assert exec(
        db,
        "select rowid, is_hidden from v where vector match '[1]' and k = 5 and is_hidden is not 0",
    ) == snapshot(name="is_hidden IS NOT false")

    # Test IS NULL (should return no rows)
    assert exec(
        db,
        "select rowid, is_hidden from v where vector match '[1]' and k = 5 and is_hidden is null",
    ) == snapshot(name="IS NULL boolean")

    # Test IS NOT NULL (should return all rows)
    assert exec(
        db,
        "select rowid, is_hidden from v where vector match '[1]' and k = 5 and is_hidden is not null",
    ) == snapshot(name="IS NOT NULL boolean")


def test_is_with_long_text(db, snapshot):
    """Test IS operator with long text strings (>12 bytes)"""
    db.execute(
        "create virtual table v using vec0(vector float[1], name text, chunk_size=8)"
    )

    # Insert test data with long strings
    db.execute("""
      INSERT INTO v(vector, name) VALUES
        ('[.11]', 'this_is_a_very_long_string_name'),
        ('[.22]', 'another_long_string'),
        ('[.33]', 'short'),
        ('[.44]', 'this_is_a_very_long_string_name'),
        ('[.55]', 'yet_another_long_one');
    """)

    # Test IS with long string
    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name is 'this_is_a_very_long_string_name'",
    ) == snapshot(name="IS long string")

    # Test IS NOT with long string
    assert exec(
        db,
        "select rowid, name from v where vector match '[1]' and k = 5 and name is not 'this_is_a_very_long_string_name'",
    ) == snapshot(name="IS NOT long string")


def test_is_equivalence_to_eq(db, snapshot):
    """Verify IS behaves identically to = for non-NULL values"""
    db.execute(
        "create virtual table v using vec0(vector float[1], age int, name text, chunk_size=8)"
    )

    db.execute("""
      INSERT INTO v(vector, age, name) VALUES
        ('[.11]', 10, 'alice'),
        ('[.22]', 20, 'bob'),
        ('[.33]', 30, 'carol');
    """)

    # IS should give same results as =
    result_is = exec(
        db,
        "select rowid from v where vector match '[1]' and k = 5 and age is 20",
    )
    result_eq = exec(
        db,
        "select rowid from v where vector match '[1]' and k = 5 and age = 20",
    )
    assert result_is["rows"] == result_eq["rows"], "IS should behave like ="

    # IS NOT should give same results as !=
    result_isnot = exec(
        db,
        "select rowid from v where vector match '[1]' and k = 5 and name is not 'bob'",
    )
    result_ne = exec(
        db,
        "select rowid from v where vector match '[1]' and k = 5 and name != 'bob'",
    )
    assert result_isnot["rows"] == result_ne["rows"], "IS NOT should behave like !="


def test_vacuum(db, snapshot):
    db.execute("create virtual table v using vec0(vector float[1], name text)")
    db.executemany(
        "insert into v(vector, name) values (?, ?)",
        [("[1]", "alex"), ("[2]", "brian"), ("[3]", "craig")],
    )

    exec(db, "delete from v where 1 = 1")
    prev_page_count = exec(db, "pragma page_count")["rows"][0]["page_count"]

    db.execute("insert into v(v) values ('optimize')")
    db.commit()
    db.execute("vacuum")

    cur_page_count = exec(db, "pragma page_count")["rows"][0]["page_count"]
    assert cur_page_count < prev_page_count


SUPPORTS_VTAB_IN = sqlite3.sqlite_version_info[1] >= 38


@pytest.mark.skipif(
    not SUPPORTS_VTAB_IN, reason="requires vtab `x in (...)` support in SQLite >=3.38"
)
def test_vtab_in(db, snapshot):
    db.execute(
        "create virtual table v using vec0(vector float[1], n int, t text, b boolean, f float, chunk_size=8)"
    )
    db.executemany(
        "insert into v(rowid, vector, n, t, b, f) values (?, ?, ?, ?, ?, ?)",
        [
            (1, "[1]", 999, "aaaa", 0, 1.1),
            (2, "[2]", 555, "aaaa", 0, 1.1),
            (3, "[3]", 999, "aaaa", 0, 1.1),
            (4, "[4]", 555, "aaaa", 0, 1.1),
            (5, "[5]", 999, "zzzz", 0, 1.1),
            (6, "[6]", 555, "zzzz", 0, 1.1),
            (7, "[7]", 999, "zzzz", 0, 1.1),
            (8, "[8]", 555, "zzzz", 0, 1.1),
        ],
    )

    # EVIDENCE-OF: V15248_32086
    assert exec(
        db, "select *  from v where vector match '[0]' and k = 8 and b in (1, 0)"
    ) == snapshot(name="block-bool")

    assert exec(
        db, "select *  from v where vector match '[0]' and k = 8 and f in (1.1, 0.0)"
    ) == snapshot(name="block-float")

    assert exec(
        db,
        "select rowid, n, distance  from v where vector match '[0]' and k = 8 and n in (555, 999)",
    ) == snapshot(name="allow-int-all")
    assert exec(
        db,
        "select rowid, n, distance from v where vector match '[0]' and k = 8 and n in (555, -1, -2)",
    ) == snapshot(name="allow-int-superfluous")

    assert exec(
        db,
        "select rowid, t, distance  from v where vector match '[0]' and k = 8 and t in ('aaaa', 'zzzz')",
    ) == snapshot(name="allow-text-all")
    assert exec(
        db,
        "select rowid, t, distance from v where vector match '[0]' and k = 8 and t in ('aaaa', 'foo', 'bar')",
    ) == snapshot(name="allow-text-superfluous")


def test_vtab_in_long_text(db, snapshot):
    db.execute(
        "create virtual table v using vec0(vector float[1], t text, chunk_size=8)"
    )
    data = [
        (1, "aaaa"),
        (2, "aaaaaaaaaaaa_aaa"),
        (3, "bbbb"),
        (4, "bbbbbbbbbbbb_bbb"),
        (5, "cccc"),
        (6, "cccccccccccc_ccc"),
    ]
    db.executemany(
        "insert into v(rowid, vector, t) values (:rowid, printf('[%d]', :rowid), :vector)",
        [{"rowid": row[0], "vector": row[1]} for row in data],
    )

    for _, lookup in data:
        assert exec(
            db,
            "select rowid, t from v where vector match '[0]' and k = 10 and t in (?, 'nonsense')",
            [lookup],
        ) == snapshot(name=f"individual-{lookup}")

    assert exec(
        db,
        "select rowid, t from v where vector match '[0]' and k = 10 and t in (select value from json_each(?))",
        [json.dumps([row[1] for row in data])],
    ) == snapshot(name="all")


@pytest.mark.skipif(
    not SUPPORTS_VTAB_IN, reason="requires vtab `x in (...)` support in SQLite >=3.38"
)
def test_vtab_in_integer_list(db):
    db.execute(
        "create virtual table v using vec0(vector float[1], n int, chunk_size=8)"
    )
    # values 2**32 apart, which a comparator narrowing their difference to an
    # int would read as equal
    values = [i * 2**32 + 1 for i in range(40)]
    db.executemany(
        "insert into v(rowid, vector, n) values (?, ?, ?)",
        [(i + 1, f"[{i}]", n) for i, n in enumerate(values)],
    )
    wanted = values[::3] + [-5, 7, 2**62]
    rows = db.execute(
        "select rowid from v where vector match '[0]' and k = 100 and n in (select value from json_each(?))",
        [json.dumps(wanted)],
    ).fetchall()
    assert sorted(row[0] for row in rows) == list(range(1, 41, 3))

    # a list that holds no integer matches no row, not even n = 0
    db.execute("insert into v(rowid, vector, n) values (41, '[40]', 0)")
    rows = db.execute(
        "select rowid from v where vector match '[0]' and k = 100 and n in ('a', x'00')"
    ).fetchall()
    assert rows == []


def test_idxstr(db, snapshot):
    db.execute("""
          create virtual table vec_movies using vec0(
            movie_id integer primary key,
            synopsis_embedding float[1],
            +title text,
            is_favorited boolean,
            genre text,
            num_reviews int,
            mean_rating float,
            chunk_size=8
          );
        """)

    assert (
        eqp(
            db,
            "select * from vec_movies where synopsis_embedding match '' and k = 0 and is_favorited = true",
        )
        == snapshot()
    )

    ops = ["<", ">", "<=", ">=", "!="]

    for op in ops:
        assert eqp(
            db,
            f"select * from vec_movies where synopsis_embedding match '' and k = 0 and genre {op} NULL",
        ) == snapshot(name=f"knn-constraint-text {op}")

    for op in ops:
        assert eqp(
            db,
            f"select * from vec_movies where synopsis_embedding match '' and k = 0 and num_reviews {op} NULL",
        ) == snapshot(name=f"knn-constraint-int {op}")

    for op in ops:
        assert eqp(
            db,
            f"select * from vec_movies where synopsis_embedding match '' and k = 0 and mean_rating {op} NULL",
        ) == snapshot(name=f"knn-constraint-float {op}")

    # for op in ops:
    #    assert eqp(
    #        db,
    #        f"select * from vec_movies where synopsis_embedding match '' and k = 0 and is_favorited {op} NULL",
    #    ) == snapshot(name=f"knn-constraint-boolean {op}")


def eqp(db, sql):
    o = OrderedDict()
    o["sql"] = sql
    o["plan"] = [
        dict(row) for row in db.execute(f"explain query plan {sql}").fetchall()
    ]
    for p in o["plan"]:
        # value is different on macos-aarch64 in github actions, not sure why
        del p["notused"]
    return o


def test_stress(db, snapshot):
    db.execute("""
          create virtual table vec_movies using vec0(
            movie_id integer primary key,
            synopsis_embedding float[1],
            +title text,
            is_favorited boolean,
            genre text,
            num_reviews int,
            mean_rating float,
            chunk_size=8
          );
        """)

    db.execute("""
          INSERT INTO vec_movies(movie_id, synopsis_embedding, is_favorited, genre, title, num_reviews, mean_rating)
          VALUES
            (1, '[1]', 0, 'horror', 'The Conjuring', 153, 4.6),
            (2, '[2]', 0, 'comedy', 'Dumb and Dumber', 382, 2.6),
            (3, '[3]', 0, 'scifi', 'Interstellar', 53, 5.0),
            (4, '[4]', 0, 'fantasy', 'The Lord of the Rings: The Fellowship of the Ring', 210, 4.2),
            (5, '[5]', 1, 'documentary', 'An Inconvenient Truth', 93, 3.4),
            (6, '[6]', 1, 'horror', 'Hereditary', 167, 4.7),
            (7, '[7]', 1, 'comedy', 'Anchorman: The Legend of Ron Burgundy', 482, 2.9),
            (8, '[8]', 0, 'scifi', 'Blade Runner 2049', 301, 5.0),
            (9, '[9]', 1, 'fantasy', 'Harry Potter and the Sorcerer''s Stone', 134, 4.1),
            (10, '[10]', 0, 'documentary', 'Free Solo', 66, 3.2),
            (11, '[11]', 1, 'horror', 'Get Out', 88, 4.9),
            (12, '[12]', 0, 'comedy', 'The Hangover', 59, 2.8),
            (13, '[13]', 1, 'scifi', 'The Matrix', 423, 4.5),
            (14, '[14]', 0, 'fantasy', 'Pan''s Labyrinth', 275, 3.6),
            (15, '[15]', 1, 'documentary', '13th', 191, 4.4),
            (16, '[16]', 0, 'horror', 'It Follows', 314, 4.3),
            (17, '[17]', 1, 'comedy', 'Step Brothers', 74, 3.0),
            (18, '[18]', 1, 'scifi', 'Inception', 201, 5.0),
            (19, '[19]', 1, 'fantasy', 'The Shape of Water', 399, 2.7),
            (20, '[20]', 1, 'documentary', 'Won''t You Be My Neighbor?', 186, 4.8),
            (21, '[21]', 1, 'scifi', 'Gravity', 342, 4.0),
            (22, '[22]', 1, 'scifi', 'Dune', 451, 4.4),
            (23, '[23]', 1, 'scifi', 'The Martian', 522, 4.6),
            (24, '[24]', 1, 'horror', 'A Quiet Place', 271, 4.3),
            (25, '[25]', 1, 'fantasy', 'The Chronicles of Narnia: The Lion, the Witch and the Wardrobe', 310, 3.9);

        """)

    assert vec0_shadow_table_contents(db, "vec_movies") == snapshot()
    assert (
        exec(
            db,
            """
          select
            movie_id,
            title,
            genre,
            num_reviews,
            mean_rating,
            is_favorited,
            distance
          from vec_movies
          where synopsis_embedding match '[15.5]'
            and genre = 'scifi'
            and num_reviews between 100 and 500
            and mean_rating > 3.5
            and k = 5;
        """,
        )
        == snapshot()
    )

    assert (
        exec(
            db,
            "select movie_id, genre, distance from vec_movies where synopsis_embedding match '[100]' and k = 5 and genre = 'horror'",
        )
        == snapshot()
    )
    assert (
        exec(
            db,
            "select movie_id, genre, distance from vec_movies where synopsis_embedding match '[100]' and k = 5 and genre = 'comedy'",
        )
        == snapshot()
    )
    assert (
        exec(
            db,
            "select movie_id, num_reviews, distance from vec_movies where synopsis_embedding match '[100]' and k = 5 and num_reviews between 100 and 500",
        )
        == snapshot()
    )
    assert (
        exec(
            db,
            "select movie_id, num_reviews, distance from vec_movies where synopsis_embedding match '[100]' and k = 5 and num_reviews >= 500",
        )
        == snapshot()
    )
    assert (
        exec(
            db,
            "select movie_id, mean_rating, distance from vec_movies where synopsis_embedding match '[100]' and k = 5 and mean_rating < 3.0",
        )
        == snapshot()
    )
    assert (
        exec(
            db,
            "select movie_id, mean_rating, distance from vec_movies where synopsis_embedding match '[100]' and k = 5 and mean_rating between 4.0 and 5.0",
        )
        == snapshot()
    )

    assert exec(
        db,
        "select movie_id, is_favorited, distance from vec_movies where synopsis_embedding match '[100]' and k = 5 and is_favorited = TRUE",
    ) == snapshot(name="bool-eq-true")
    assert exec(
        db,
        "select movie_id, is_favorited, distance from vec_movies where synopsis_embedding match '[100]' and k = 5 and is_favorited != TRUE",
    ) == snapshot(name="bool-ne-true")
    assert exec(
        db,
        "select movie_id, is_favorited, distance from vec_movies where synopsis_embedding match '[100]' and k = 5 and is_favorited = FALSE",
    ) == snapshot(name="bool-eq-false")
    assert exec(
        db,
        "select movie_id, is_favorited, distance from vec_movies where synopsis_embedding match '[100]' and k = 5 and is_favorited != FALSE",
    ) == snapshot(name="bool-ne-false")

    # EVIDENCE-OF: V10145_26984
    assert exec(
        db,
        "select movie_id, is_favorited, distance from vec_movies where synopsis_embedding match '[100]' and k = 5 and is_favorited >= 999",
    ) == snapshot(name="bool-other-op")


def test_errors(db, snapshot):
    db.execute("create virtual table v using vec0(vector float[1], t text)")
    db.execute("insert into v(vector, t) values ('[1]', 'aaaaaaaaaaaax')")

    assert exec(db, "select * from v") == snapshot()

    # EVIDENCE-OF: V15466_32305
    db.set_authorizer(
        authorizer_deny_on(sqlite3.SQLITE_READ, "v_metadatatext00", "data")
    )
    assert exec(db, "select * from v") == snapshot()


def test_knn_filters_compare_as_sqlite(db):
    # vec0 declares its columns without a type, so SQLite compares a
    # constraint's value with them as is, the way it compares with the untyped
    # columns of `plain`: NULL compares with nothing, a number never equals
    # text, and an integer compares with a real exactly. A KNN query's filters
    # must keep the rows SQLite keeps.
    db.execute(
        "create virtual table v using vec0(vector float[1], b boolean, n integer, f float, t text, chunk_size=8)"
    )
    db.execute("create table plain(id integer primary key, b, n, f, t)")
    rows = [
        (1, 0, 0, 0.0, ""),
        (2, 1, 5, 5.0, "5"),
        (3, 1, 6, 6.5, "abc"),
        (4, 0, -3, -3.25, "x"),
        (5, 1, 2**53 + 1, 2.0**53, "5.5"),
    ]
    for row in rows:
        db.execute(
            "insert into v(rowid, vector, b, n, f, t) values (?, '[1]', ?, ?, ?, ?)",
            row,
        )
        db.execute("insert into plain values (?, ?, ?, ?, ?)", row)

    def knn(where, parameters=[]):
        return sorted(
            row[0]
            for row in db.execute(
                f"select rowid from v where vector match '[1]' and k = 10 and {where}",
                parameters,
            )
        )

    def sql(where, parameters=[]):
        return sorted(
            row[0]
            for row in db.execute(f"select id from plain where {where}", parameters)
        )

    # 2.0**53 equals 2**53 + 1 when both are doubles, but not exactly
    values = [
        None,
        0,
        1,
        1.0,
        5,
        5.0,
        5.5,
        -3,
        2**53 + 1,
        2.0**53,
        "5",
        "abc",
        "",
        b"\x05",
    ]
    comparisons = ["=", "!=", "<", "<=", ">", ">=", "is", "is not"]
    operators = {
        "b": ["=", "!=", "is", "is not"],
        "n": comparisons,
        "f": comparisons,
        "t": comparisons + ["like", "glob"],
    }
    mismatches = []
    for column, ops in operators.items():
        for op in ops:
            for value in values:
                where = f"{column} {op} ?"
                if knn(where, [value]) != sql(where, [value]):
                    mismatches.append(
                        (where, value, knn(where, [value]), sql(where, [value]))
                    )
    for where in [
        "n in (null, 5)",
        "n in ('5', 6)",
        "n in (5.0, 'abc', x'05', 5.5, -3)",
        "t in (null, 'abc')",
        "t in (5, 'x')",
        "t in (x'78', '')",
    ]:
        if knn(where) != sql(where):
            mismatches.append((where, None, knn(where), sql(where)))
    assert mismatches == []


def test_knn_text_filter_null_long_value(db):
    # A text value longer than the 12-byte prefix kept in the chunk is compared
    # in full, which once read through the NULL pointer of a NULL constraint
    # value and crashed. In SQLite, `select 'x' < null` is NULL, so no row
    # matches.
    db.execute(
        "create virtual table v using vec0(vector float[1], t text, chunk_size=8)"
    )
    db.execute("insert into v(rowid, vector, t) values (1, '[1]', ?)", ["x" * 20])
    for op in ["<", "<=", ">", ">="]:
        assert (
            db.execute(
                f"select rowid from v where vector match '[1]' and k = 10 and t {op} ?",
                [None],
            ).fetchall()
            == []
        )


def test_knn_metadata_filter_error_message(db):
    # A KNN query with a metadata filter once set "Could not open metadata
    # blob" on success, and SQLite reported it for a later error that sets no
    # message of its own, such as an interrupt.
    db.execute(
        "create virtual table v using vec0(vector float[1], m integer, chunk_size=8)"
    )
    db.executemany(
        "insert into v(rowid, vector, m) values (?, ?, 1)",
        [(i, f"[{i}]") for i in range(1, 6)],
    )
    cursor = db.execute(
        "select rowid from v where vector match '[1]' and k = 5 and m = 1"
    )
    cursor.fetchone()
    db.set_progress_handler(lambda: 1, 1)
    with pytest.raises(sqlite3.OperationalError, match="^interrupted$"):
        cursor.fetchall()
    db.set_progress_handler(None, 1)


def authorizer_deny_on(operation, x1, x2=None):
    def _auth(op, p1, p2, p3, p4):
        if op == operation and p1 == x1 and p2 == x2:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    return _auth


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


def vec0_shadow_table_contents(db, v):
    shadow_tables = [
        row[0]
        for row in db.execute(
            "select name from sqlite_master where name like ? order by 1", [f"{v}_%"]
        ).fetchall()
    ]
    o = {}
    for shadow_table in shadow_tables:
        if shadow_table.endswith("_info"):
            continue
        o[shadow_table] = exec(db, f"select * from {shadow_table}")
    return o
