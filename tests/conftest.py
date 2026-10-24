import os
import pytest
import sqlite3


def get_extension_path():
    """Get the sqlite-vec extension path, allowing override via environment variable."""
    # Allow override for testing with ASan-instrumented builds
    ext_path = os.environ.get("SQLITE_VEC_EXT")
    if ext_path:
        # Strip .so/.dylib/.dll extension if present (SQLite adds it)
        for suffix in (".so", ".dylib", ".dll"):
            if ext_path.endswith(suffix):
                ext_path = ext_path[: -len(suffix)]
                break
        return ext_path
    return "dist/vec0"


def _has_build_flag(flag):
    db = sqlite3.connect(":memory:")
    db.enable_load_extension(True)
    db.load_extension(get_extension_path())
    debug = db.execute("SELECT vec_debug()").fetchone()[0]
    db.close()
    return flag in debug.split("Build flags:")[-1].split()


def pytest_collection_modifyitems(config, items):
    if _has_build_flag("ivf"):
        return
    skip_ivf = pytest.mark.skip(
        reason="IVF not enabled (compile with -DSQLITE_VEC_EXPERIMENTAL_IVF_ENABLE=1)"
    )
    for item in items:
        if item.fspath.basename.startswith("test-ivf"):
            item.add_marker(skip_ivf)


@pytest.fixture()
def db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.enable_load_extension(True)
    db.load_extension(get_extension_path())
    db.enable_load_extension(False)
    return db
