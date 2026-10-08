import sqlite3
from collections import OrderedDict
import pytest


@pytest.mark.skipif(
    sqlite3.sqlite_version_info[1] < 37,
    reason="pragma_table_list was added in SQLite 3.37",
)
def test_shadow(db, snapshot):
    db.execute(
        "create virtual table v using vec0(a float[1], partition text partition key, metadata text, +name text, chunk_size=8)"
    )
    assert exec(db, "select * from sqlite_master order by name") == snapshot()
    assert (
        exec(db, "select * from pragma_table_list where type = 'shadow' order by name")
        == snapshot()
    )

    db.execute("drop table v;")
    assert (
        exec(db, "select * from pragma_table_list where type = 'shadow' order by name")
        == snapshot()
    )


@pytest.mark.skipif(
    sqlite3.sqlite_version_info[1] < 37,
    reason="pragma_table_list was added in SQLite 3.37",
)
def test_shadow_vector_chunks(db):
    # https://github.com/asg017/sqlite-vec/issues/320
    #
    # xShadowName reports "vector_chunksNN", but SQLite only consults it for
    # a table that already exists when the vec0 table's own schema entry is
    # parsed: a table created afterwards is matched to its virtual table by
    # splitting the name at the LAST underscore, which "v_vector_chunks00"
    # defeats. VACUUM rewrites sqlite_schema with virtual tables last, so
    # from then on every backing table is reported as a shadow table.
    #
    # Only the post-VACUUM state is asserted, since it holds on every SQLite
    # version. Before a VACUUM the chunk tables are ordinary tables up to
    # SQLite 3.53, while 3.54 is expected to also mark them after each
    # xConnect, so their type in a reopened database depends on the version.
    db.execute(
        "create virtual table v using vec0(a float[1], b int8[1], metadata text, +name text, chunk_size=8)"
    )
    db.execute(
        "insert into v(rowid, a, b, metadata, name) values (1, '[1]', vec_int8('[1]'), 'm', 'n')"
    )
    db.commit()
    db.execute("create table v_vector_chunks(x)")
    db.execute("create table v_vector_chunks0(x)")
    db.execute("create table v_vector_chunks000(x)")
    db.execute("create table v_vector_chunksxx(x)")
    db.execute("vacuum")

    types = {
        row["name"]: row["type"]
        for row in db.execute(
            "select name, type from pragma_table_list where schema = 'main'"
        )
        if row["name"].startswith("v")
    }
    assert types == {
        "v": "virtual",
        "v_auxiliary": "shadow",
        "v_chunks": "shadow",
        "v_info": "shadow",
        "v_metadatachunks00": "shadow",
        "v_metadatatext00": "shadow",
        "v_rowids": "shadow",
        "v_vector_chunks00": "shadow",
        "v_vector_chunks01": "shadow",
        # not vec0 backing tables
        "v_vector_chunks": "table",
        "v_vector_chunks0": "table",
        "v_vector_chunks000": "table",
        "v_vector_chunksxx": "table",
    }

    # the table keeps working once its vector chunks are shadow tables
    db.execute(
        "insert into v(rowid, a, b, metadata, name) values (2, '[2]', vec_int8('[2]'), 'm', 'n')"
    )
    db.execute("delete from v where rowid = 1")
    assert [
        row["rowid"]
        for row in db.execute("select rowid from v where a match '[2]' and k = 2")
    ] == [2]
    db.execute("alter table v rename to w")
    assert db.execute("select count(*) from w").fetchone()[0] == 1
    db.execute("drop table w")
    assert (
        db.execute(
            "select count(*) from sqlite_master where name like 'w_%'"
        ).fetchone()[0]
        == 0
    )


@pytest.mark.parametrize("name", ["order", "my vecs"])
def test_optimize_on_table_name_that_needs_quoting(db, name):
    db.execute(f'create virtual table "{name}" using vec0(a float[1], chunk_size=8)')
    db.execute(f"insert into \"{name}\"(rowid, a) values (1, '[1]')")
    db.execute(f'delete from "{name}" where rowid = 1')
    db.execute(f'insert into "{name}"("{name}") values (\'optimize\')')
    assert db.execute(f'select count(*) from "{name}_chunks"').fetchone()[0] == 0


@pytest.mark.parametrize(
    "name, columns",
    [
        ("emb", "emb float[1]"),
        ("Emb", "emb float[1]"),
        ("id", "id text primary key, a float[1]"),
        ("p", "a float[1], p text partition key"),
        ("aux", "a float[1], +aux text"),
        ("meta", "a float[1], meta text"),
        ("rowid", "a float[1]"),
        ("distance", "a float[1]"),
        ("k", "a float[1]"),
        ("mmr_lambda", "a float[1]"),
    ],
)
def test_create_rejects_column_named_like_table(db, name, columns):
    # The hidden command column has the table's name.
    with pytest.raises(
        sqlite3.OperationalError,
        match=rf"^vec0 constructor error: column name '{name}' conflicts with table name \(reserved for command column\)$",
    ):
        db.execute(f'create virtual table "{name}" using vec0({columns})')
    assert db.execute("select count(*) from sqlite_master").fetchone()[0] == 0


def test_create_accepts_rowid_table_name_with_primary_key(db):
    db.execute(
        'create virtual table "rowid" using vec0(id integer primary key, a float[1])'
    )
    db.execute("""insert into "rowid"(id, a) values (1, '[1]')""")
    db.execute("""insert into "rowid"("rowid") values ('optimize')""")
    assert [tuple(r) for r in db.execute('select id from "rowid"')] == [(1,)]


@pytest.mark.parametrize("name", ["emb", "rowid", "distance", "k", "mmr_lambda"])
def test_rename_to_column_name_drops_command_column(db, name):
    # ALTER TABLE RENAME reconnects the table without calling xCreate, as a
    # database from before v0.2.0-alpha does, so the table opens without a
    # command column. Renaming it again restores the command column.
    db.execute("create virtual table t using vec0(emb float[1], chunk_size=8)")
    db.execute("insert into t(rowid, emb) values (1, '[1]'), (2, '[2]'), (3, '[3]')")
    db.execute(f'alter table t rename to "{name}"')

    db.execute(f"""insert into "{name}"(rowid, emb) values (4, '[4]')""")
    db.execute(f'delete from "{name}" where rowid = 1')
    knn = f"""select rowid, distance from "{name}" where emb match '[2]' and k = 3"""
    expected = [(2, 0.0), (3, 1.0), (4, 2.0)]
    assert [tuple(r) for r in db.execute(knn)] == expected
    assert [tuple(r) for r in db.execute(knn + " and mmr_lambda = 1.0")] == expected
    assert db.execute(f'select emb from "{name}" where rowid = 4').fetchone()[0] == (
        b"\x00\x00\x80\x40"
    )

    db.execute(f'alter table "{name}" rename to t2')
    db.execute("delete from t2")
    db.execute("insert into t2(t2) values ('optimize')")
    assert db.execute("select count(*) from t2_chunks").fetchone()[0] == 0


def test_info(db, snapshot):
    db.execute("create virtual table v using vec0(a float[1])")
    assert exec(db, "select key, typeof(value) from v_info order by 1") == snapshot()


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
        o[shadow_table] = exec(db, f"select * from {shadow_table}")
    return o
