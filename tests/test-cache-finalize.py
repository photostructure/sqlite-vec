"""vec0 must leave no cached prepared statement in progress, or VACUUM fails
with "SQL statements in progress": `vec0Sync` finalizes every cached statement
when a transaction commits, and a statement is reset as soon as it has run.

https://github.com/asg017/sqlite-vec/issues/295
"""

import struct


def _f32(values):
    return struct.pack("%sf" % len(values), *values)


def test_vacuum_after_diskann_inserts(db):
    db.execute(
        "create virtual table v using vec0("
        "a float[8] indexed by diskann(neighbor_quantizer=binary))"
    )
    for i in range(1, 11):
        db.execute("insert into v(rowid, a) values (?, ?)", (i, _f32([0.1 * i] * 8)))
    db.commit()
    db.execute("VACUUM")


def test_vacuum_after_diskann_knn(db):
    # A KNN query commits nothing, so the statements it ran must not stay in
    # progress until the next write.
    db.execute(
        "create virtual table v using vec0("
        "a float[8] indexed by diskann(neighbor_quantizer=binary))"
    )
    for i in range(1, 11):
        db.execute("insert into v(rowid, a) values (?, ?)", (i, _f32([0.1 * i] * 8)))
    db.commit()
    rows = db.execute(
        "select rowid from v where a match ? and k = 3", (_f32([0.5] * 8),)
    ).fetchall()
    assert len(rows) == 3
    db.execute("VACUUM")


def test_vacuum_after_flat_inserts(db):
    db.execute("create virtual table v using vec0(a float[2])")
    db.execute("insert into v(rowid, a) values (1, ?)", (_f32([0.1, 0.2]),))
    db.commit()
    db.execute("VACUUM")
