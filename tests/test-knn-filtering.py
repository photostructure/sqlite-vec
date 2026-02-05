"""
Tests demonstrating KNN filtering behavior: metadata columns vs JOINs.

Key insight: Filters on metadata columns are applied DURING the KNN search,
while filters on joined tables are applied AFTER. This affects result counts.
"""
import pytest


def test_metadata_filter_during_knn(db):
    """Metadata column filters are applied DURING KNN search.

    This guarantees you get up to k results matching your filter.
    """
    db.execute("""
        CREATE VIRTUAL TABLE products USING vec0(
            embedding float[4],
            category TEXT
        )
    """)

    # Insert 10 items: 5 electronics, 5 clothing
    for i in range(10):
        category = "electronics" if i < 5 else "clothing"
        db.execute(
            "INSERT INTO products(rowid, embedding, category) VALUES (?, ?, ?)",
            [i, f"[{i}, {i}, {i}, {i}]", category]
        )

    # Request k=5 with category filter - gets 5 electronics
    results = db.execute("""
        SELECT rowid, distance, category FROM products
        WHERE embedding MATCH '[0,0,0,0]'
          AND k = 5
          AND category = 'electronics'
        ORDER BY distance
    """).fetchall()

    assert len(results) == 5, "Should get exactly 5 results (all electronics)"
    assert all(r[2] == "electronics" for r in results)


def test_join_filter_after_knn(db):
    """JOIN filters are applied AFTER KNN search returns.

    This means you may get fewer than k results if the join eliminates rows.
    """
    # vec0 table with NO category metadata
    db.execute("""
        CREATE VIRTUAL TABLE products USING vec0(
            embedding float[4]
        )
    """)

    # Separate categories table
    db.execute("""
        CREATE TABLE categories (
            product_id INTEGER PRIMARY KEY,
            category TEXT
        )
    """)

    # Insert 10 items: 5 electronics, 5 clothing
    for i in range(10):
        category = "electronics" if i < 5 else "clothing"
        db.execute(
            "INSERT INTO products(rowid, embedding) VALUES (?, ?)",
            [i, f"[{i}, {i}, {i}, {i}]"]
        )
        db.execute(
            "INSERT INTO categories(product_id, category) VALUES (?, ?)",
            [i, category]
        )

    # Request k=5 with JOIN filter - KNN returns 5 nearest (rowids 0-4),
    # but they happen to all be electronics, so we get 5
    # This is a lucky case!
    results = db.execute("""
        SELECT p.rowid, p.distance, c.category
        FROM products p
        JOIN categories c ON p.rowid = c.product_id
        WHERE p.embedding MATCH '[0,0,0,0]'
          AND k = 5
          AND c.category = 'electronics'
        ORDER BY p.distance
    """).fetchall()

    # We get 5 here, but only because the 5 nearest happen to be electronics
    assert len(results) == 5


def test_join_filter_reduces_results(db):
    """Demonstrates the JOIN problem: asking for k results but getting fewer.

    This is the key gotcha developers need to understand.
    """
    db.execute("""
        CREATE VIRTUAL TABLE products USING vec0(
            embedding float[4]
        )
    """)

    db.execute("""
        CREATE TABLE categories (
            product_id INTEGER PRIMARY KEY,
            category TEXT
        )
    """)

    # Insert 10 items with interleaved categories
    # rowids 0,2,4,6,8 = electronics; 1,3,5,7,9 = clothing
    for i in range(10):
        category = "electronics" if i % 2 == 0 else "clothing"
        db.execute(
            "INSERT INTO products(rowid, embedding) VALUES (?, ?)",
            [i, f"[{i}, {i}, {i}, {i}]"]
        )
        db.execute(
            "INSERT INTO categories(product_id, category) VALUES (?, ?)",
            [i, category]
        )

    # Request k=5, but filter for electronics
    # KNN returns rowids 0,1,2,3,4 (nearest to origin)
    # After JOIN filter: only 0,2,4 remain (electronics)
    results = db.execute("""
        SELECT p.rowid, p.distance, c.category
        FROM products p
        JOIN categories c ON p.rowid = c.product_id
        WHERE p.embedding MATCH '[0,0,0,0]'
          AND k = 5
          AND c.category = 'electronics'
        ORDER BY p.distance
    """).fetchall()

    # Only 3 results even though we asked for k=5!
    assert len(results) == 3, (
        f"JOIN filter applied AFTER KNN - got {len(results)} instead of 5. "
        "This is expected behavior but often surprises developers."
    )
    assert [r[0] for r in results] == [0, 2, 4]


def test_subquery_also_filters_after(db):
    """Subqueries with external filters also apply AFTER KNN."""
    db.execute("""
        CREATE VIRTUAL TABLE products USING vec0(
            embedding float[4]
        )
    """)

    db.execute("""
        CREATE TABLE categories (
            product_id INTEGER PRIMARY KEY,
            category TEXT
        )
    """)

    for i in range(10):
        category = "electronics" if i % 2 == 0 else "clothing"
        db.execute(
            "INSERT INTO products(rowid, embedding) VALUES (?, ?)",
            [i, f"[{i}, {i}, {i}, {i}]"]
        )
        db.execute(
            "INSERT INTO categories(product_id, category) VALUES (?, ?)",
            [i, category]
        )

    # CTE approach - same problem
    results = db.execute("""
        WITH knn AS (
            SELECT rowid, distance
            FROM products
            WHERE embedding MATCH '[0,0,0,0]' AND k = 5
        )
        SELECT knn.rowid, knn.distance, c.category
        FROM knn
        JOIN categories c ON knn.rowid = c.product_id
        WHERE c.category = 'electronics'
    """).fetchall()

    assert len(results) == 3, "CTE+JOIN also filters after KNN"


def test_workaround_increase_k(db):
    """Workaround: request more results than needed, filter, then limit.

    This works but wastes computation and may still miss results.
    """
    db.execute("""
        CREATE VIRTUAL TABLE products USING vec0(
            embedding float[4]
        )
    """)

    db.execute("""
        CREATE TABLE categories (
            product_id INTEGER PRIMARY KEY,
            category TEXT
        )
    """)

    for i in range(10):
        category = "electronics" if i % 2 == 0 else "clothing"
        db.execute(
            "INSERT INTO products(rowid, embedding) VALUES (?, ?)",
            [i, f"[{i}, {i}, {i}, {i}]"]
        )
        db.execute(
            "INSERT INTO categories(product_id, category) VALUES (?, ?)",
            [i, category]
        )

    # Request k=10 (2x what we need), then filter and limit
    results = db.execute("""
        SELECT p.rowid, p.distance, c.category
        FROM products p
        JOIN categories c ON p.rowid = c.product_id
        WHERE p.embedding MATCH '[0,0,0,0]'
          AND k = 10
          AND c.category = 'electronics'
        ORDER BY p.distance
        LIMIT 5
    """).fetchall()

    assert len(results) == 5, "Got 5 results by over-fetching"


def test_solution_use_metadata_columns(db):
    """The correct solution: use metadata columns for filterable attributes."""
    db.execute("""
        CREATE VIRTUAL TABLE products USING vec0(
            embedding float[4],
            category TEXT
        )
    """)

    # All category data in the vec0 table itself
    for i in range(10):
        category = "electronics" if i % 2 == 0 else "clothing"
        db.execute(
            "INSERT INTO products(rowid, embedding, category) VALUES (?, ?, ?)",
            [i, f"[{i}, {i}, {i}, {i}]", category]
        )

    # Filter applied DURING KNN search
    results = db.execute("""
        SELECT rowid, distance, category FROM products
        WHERE embedding MATCH '[0,0,0,0]'
          AND k = 5
          AND category = 'electronics'
        ORDER BY distance
    """).fetchall()

    assert len(results) == 5, "Metadata filter guarantees k results"
    assert [r[0] for r in results] == [0, 2, 4, 6, 8]
