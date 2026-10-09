import sqlite3
from collections import OrderedDict


def test_constructor_limit(db, snapshot):
    assert (
        exec(
            db,
            """
        create virtual table v using vec0(
          p1 int partition key,
          p2 int partition key,
          p3 int partition key,
          p4 int partition key,
          p5 int partition key,
          v float[1]
        )
      """,
        )
        == snapshot(name="max 4 partition keys")
    )


def test_normal(db, snapshot):
    db.execute(
        "create virtual table v using vec0(p1 int partition key, a float[1], chunk_size=8)"
    )

    db.execute("insert into v(rowid, p1, a) values (1, 100, X'11223344')")
    assert vec0_shadow_table_contents(db, "v") == snapshot(name="1 row")
    db.execute("insert into v(rowid, p1, a) values (2, 100, X'44556677')")
    assert vec0_shadow_table_contents(db, "v") == snapshot(name="2 rows, same parition")
    db.execute("insert into v(rowid, p1, a) values (3, 200, X'8899aabb')")
    assert vec0_shadow_table_contents(db, "v") == snapshot(name="3 rows, 2 partitions")


def test_types(db, snapshot):
    db.execute(
        "create virtual table v using vec0(p1 int partition key, a float[1], chunk_size=8)"
    )

    # EVIDENCE-OF: V11454_28292
    assert exec(
        db, "insert into v(p1, a) values(?, ?)", ["not int", b"\x11\x22\x33\x44"]
    ) == snapshot(name="1. raises type error")

    assert vec0_shadow_table_contents(db, "v") == snapshot(name="2. empty DB")

    # but allow NULLs
    assert exec(
        db, "insert into v(p1, a) values(?, ?)", [None, b"\x11\x22\x33\x44"]
    ) == snapshot(name="3. allow nulls")

    assert vec0_shadow_table_contents(db, "v") == snapshot(
        name="4. show NULL partition key"
    )


def test_updates(db, snapshot):
    db.execute(
        "create virtual table v using vec0(p text partition key, a float[1], chunk_size=8)"
    )

    db.execute(
        "insert into v(rowid, p, a) values (?, ?, ?)", [1, "a", b"\x11\x11\x11\x11"]
    )
    db.execute(
        "insert into v(rowid, p, a) values (?, ?, ?)", [2, "a", b"\x22\x22\x22\x22"]
    )
    db.execute(
        "insert into v(rowid, p, a) values (?, ?, ?)", [3, "a", b"\x33\x33\x33\x33"]
    )

    assert exec(db, "select * from v") == snapshot(name="1. Initial dataset")
    assert exec(db, "update v set p = ? where rowid = ?", ["new", 1]) == snapshot(
        name="2. update #1"
    )


def test_vacuum(db, snapshot):
    db.execute("create virtual table v using vec0(p text partition key, a float[1])")

    db.execute(
        "insert into v(rowid, p, a) values (?, ?, ?)", [1, "a", b"\x11\x11\x11\x11"]
    )
    db.execute(
        "insert into v(rowid, p, a) values (?, ?, ?)", [2, "a", b"\x22\x22\x22\x22"]
    )
    db.execute(
        "insert into v(rowid, p, a) values (?, ?, ?)", [3, "a", b"\x33\x33\x33\x33"]
    )

    exec(db, "delete from v where 1 = 1")
    prev_page_count = exec(db, "pragma page_count")["rows"][0]["page_count"]

    db.execute("insert into v(v) values ('optimize')")
    db.commit()
    db.execute("vacuum")

    cur_page_count = exec(db, "pragma page_count")["rows"][0]["page_count"]
    assert cur_page_count < prev_page_count


# (p, q) values for comparing KNN partition key filters with an ordinary table.
# Row i's vector is [i], so a query for [0] ranks rows by rowid.
PARTITION_FILTER_ROWS = [
    ("a", 1),
    ("b", 2),
    ("x", 3),
    ("ax", -1),
    (None, None),
    ("A", 1),
    ("aX", 2),
    ("abc", 3),
    ("ABC", None),
    ("a", 4),
    ("%x", 1 << 40),
    ("_x", 0),
    ("ab\0c", 2),
    ("ab\0d", 1),
    ("b", 3),
    ("abc ", 1),
    ("é", 2),
    ("É", 3),
]


def _create_partition_filter_tables(db):
    db.execute(
        "create virtual table v using vec0(p text partition key, q integer partition key, e float[1], chunk_size=8)"
    )
    # untyped, like _chunks.partitionNN, so SQLite compares values with it as is
    db.execute("create table plain(p, q)")
    for rowid, (p, q) in enumerate(PARTITION_FILTER_ROWS, 1):
        db.execute(
            "insert into v(rowid, p, q, e) values (?, ?, ?, ?)",
            [rowid, p, q, f"[{rowid}]"],
        )
        db.execute("insert into plain(rowid, p, q) values (?, ?, ?)", [rowid, p, q])


def _knn_partition_filter(db, condition, parameters, form, k):
    sql = f"select rowid from v where e match '[0]' and {condition}"
    sql += " and k = ?" if form == "k" else " limit ?"
    return [row[0] for row in db.execute(sql, parameters + [k])]


def _plain_partition_filter(db, condition, parameters):
    return [
        row[0]
        for row in db.execute(
            f"select rowid from plain where {condition} order by rowid", parameters
        )
    ]


def _assert_knn_partition_filter_matches_plain(db, condition, parameters):
    expected = _plain_partition_filter(db, condition, parameters)
    for k in range(1, len(PARTITION_FILTER_ROWS) + 1):
        for form in ["k", "limit"]:
            actual = _knn_partition_filter(db, condition, parameters, form, k)
            assert actual == expected[:k], (condition, parameters, form, k)


def test_knn_partition_filters_match_plain_table(db):
    _create_partition_filter_tables(db)
    text_values = [p for p, _ in PARTITION_FILTER_ROWS] + [1, "nonsense"]
    for value in text_values:
        for op in ["is", "is not"]:
            _assert_knn_partition_filter_matches_plain(db, f"p {op} ?", [value])
    integer_values = [1, 2, -1, 0, 1 << 40, None, 1.0, 1.5, "1", "nonsense"]
    for value in integer_values:
        for op in ["is", "is not"]:
            _assert_knn_partition_filter_matches_plain(db, f"q {op} ?", [value])
    for column in ["p", "q"]:
        _assert_knn_partition_filter_matches_plain(db, f"{column} is null", [])
        _assert_knn_partition_filter_matches_plain(db, f"{column} is not null", [])

    for parameters in [
        ["a", "b", None],
        ["a", 1, "nonsense"],
        ["A", "ab\0c", "é"],
    ]:
        _assert_knn_partition_filter_matches_plain(db, "p in (?, ?, ?)", parameters)
    for parameters in [[1, 2.0, "3"], [None, -1, 1 << 40], [1.5, "x", 0]]:
        _assert_knn_partition_filter_matches_plain(db, "q in (?, ?, ?)", parameters)
    for condition in [
        # IN compares with the left operand's collation, so this is BINARY
        "p in (? collate nocase, 'b')",
        "p in (select p from plain where rowid > 10)",
        "p in (select p from plain where 0)",
        "q in (select q from plain where rowid < 4)",
        "p in ('a', 'b') and q in (1, 2, 4)",
    ]:
        parameters = ["a"] if "?" in condition else []
        _assert_knn_partition_filter_matches_plain(db, condition, parameters)

    like_patterns = ["%x", "a%", "A%", "_x", "%", "a\0x%", "%b%", "é%", "ab%"]
    for case_sensitive_like in [0, 1]:
        db.execute(f"pragma case_sensitive_like = {case_sensitive_like}")
        for pattern in like_patterns:
            _assert_knn_partition_filter_matches_plain(db, "p like ?", [pattern])
        for pattern in ["1%", "%2", "-%", "1_%"]:
            _assert_knn_partition_filter_matches_plain(db, "q like ?", [pattern])
    for pattern in ["*x", "a*", "A*", "[ab]*", "?x", "*", "ab*", "a\0x*"]:
        _assert_knn_partition_filter_matches_plain(db, "p glob ?", [pattern])
    for pattern in ["1*", "*2", "[0-2]", "-*"]:
        _assert_knn_partition_filter_matches_plain(db, "q glob ?", [pattern])

    for condition, parameters in [
        ("p like ? and q in (?, ?)", ["a%", 1, 2]),
        ("p is not null and q is not ?", [1]),
        ("p glob ? and q is null", ["A*"]),
    ]:
        _assert_knn_partition_filter_matches_plain(db, condition, parameters)


def test_knn_partition_filters_with_collation(db):
    # vec0 compares partition keys bytewise. SQLite reports a text IS
    # constraint's collation, so vec0 leaves one that names another collation
    # to SQLite, which applies it to the k rows vec0 returns. It reports BINARY
    # for IS NOT whatever collation the query names, so vec0 filters bytewise
    # and SQLite re-checks each row. Either way a query returns the nearest of
    # the plain table's rows, possibly fewer than k, so this asserts a prefix.
    _create_partition_filter_tables(db)
    conditions = []
    for collation in ["nocase", "rtrim"]:
        conditions.append((f"p is ? collate {collation}", ["k"]))
        conditions.append((f"p collate {collation} is ?", ["k"]))
        conditions.append((f"p is not ? collate {collation}", ["k", "limit"]))
    for condition, forms in conditions:
        for value in ["a", "A", "abc", "ABC", "abc ", "é"]:
            expected = _plain_partition_filter(db, condition, [value])
            for k in range(1, len(PARTITION_FILTER_ROWS) + 1):
                for form in forms:
                    actual = _knn_partition_filter(db, condition, [value], form, k)
                    assert actual == expected[: len(actual)], (condition, value, k)
                    assert len(actual) <= k


def test_knn_partition_in_with_collation_keeps_bytewise_matches(db):
    # vec0 runs an IN that names a collation other than BINARY as one bytewise
    # `=` per value, as it did before it consumed IN. When only one value has
    # matches and they have no case or trailing-space variants, that returns
    # the plain table's rows; leaving the IN to SQLite would apply it to the k
    # nearest "other" rows and return none.
    db.execute("create virtual table v using vec0(p text partition key, e float[1])")
    db.execute("create table plain(p)")
    values = ["other"] * 6 + ["acme"] * 3 + ["beta"] * 3
    for rowid, value in enumerate(values, 1):
        db.execute(
            "insert into v(rowid, p, e) values (?, ?, ?)", [rowid, value, f"[{rowid}]"]
        )
        db.execute("insert into plain(rowid, p) values (?, ?)", [rowid, value])
    for collation in ["nocase", "rtrim"]:
        condition = f"p collate {collation} in ('acme', 'zzz')"
        expected = [
            row[0]
            for row in db.execute(
                f"select rowid from plain where {condition} order by rowid"
            )
        ]
        for k in range(1, len(values) + 1):
            actual = [
                row[0]
                for row in db.execute(
                    f"select rowid from v where e match '[0]' and {condition} and k = ?",
                    [k],
                )
            ]
            assert actual == expected[:k], (condition, k)


class Row:
    def __init__(self):
        pass

    def __repr__(self) -> str:
        return repr()


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
