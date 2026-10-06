// Tests an installed copy of the @photostructure/sqlite-vec npm package: both
// entry points must resolve the binary for this platform, and that binary must
// load into node:sqlite and answer a KNN query.
//
// Run it through tests/test-npm-package.sh, which installs a packed tarball
// into an empty project first. SQLITE_VEC_EXPECTED_BINARY names the binary this
// platform must resolve to, relative to the package root, e.g.
// dist/linux-x64-musl/vec0.so.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { test } from "node:test";
import * as esm from "@photostructure/sqlite-vec";

const require = createRequire(import.meta.url);
const cjs = require("@photostructure/sqlite-vec");
const packageDir = dirname(require.resolve("@photostructure/sqlite-vec"));
const { version } = JSON.parse(
  readFileSync(join(packageDir, "package.json"), "utf8")
);

const expectedBinary = process.env.SQLITE_VEC_EXPECTED_BINARY;
assert.ok(
  expectedBinary,
  "Set SQLITE_VEC_EXPECTED_BINARY, e.g. dist/linux-x64/vec0.so"
);

function openDb(entry) {
  const db = new DatabaseSync(":memory:", { allowExtension: true });
  entry.load(db);
  return db;
}

test("ESM and CommonJS entry points resolve this platform's binary", () => {
  const expected = join(packageDir, ...expectedBinary.split("/"));
  assert.equal(esm.getLoadablePath(), expected);
  assert.equal(cjs.getLoadablePath(), expected);
});

for (const [name, entry] of [
  ["ESM", esm],
  ["CommonJS", cjs],
]) {
  test(`${name} load() adds sqlite-vec v${version} to node:sqlite`, () => {
    const db = openDb(entry);
    assert.equal(db.prepare("SELECT vec_version() AS v").get().v, `v${version}`);
    db.close();
  });
}

test("vec0 KNN query returns the nearest rows", () => {
  const db = openDb(esm);
  db.exec(`
    CREATE VIRTUAL TABLE items USING vec0(embedding float[4]);
    INSERT INTO items(rowid, embedding) VALUES
      (1, '[1, 0, 0, 0]'),
      (2, '[0, 2, 0, 0]'),
      (3, '[0, 0, 3, 0]');
  `);
  const rows = db
    .prepare(
      "SELECT rowid, distance FROM items WHERE embedding MATCH ? AND k = 2 ORDER BY distance"
    )
    .all("[0, 0, 0, 0]");
  assert.deepEqual(
    rows.map((row) => ({ ...row })),
    [
      { rowid: 1, distance: 1 },
      { rowid: 2, distance: 2 },
    ]
  );
  db.close();
});
