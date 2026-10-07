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
