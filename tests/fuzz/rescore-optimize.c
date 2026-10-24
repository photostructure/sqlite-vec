#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sqlite-vec.h"
#include "sqlite3.h"
#include <assert.h>

static int64_t count_rows(sqlite3 *db, const char *zSql) {
  sqlite3_stmt *stmt = NULL;
  int64_t n = -1;
  if (sqlite3_prepare_v2(db, zSql, -1, &stmt, NULL) == SQLITE_OK &&
      sqlite3_step(stmt) == SQLITE_ROW) {
    n = sqlite3_column_int64(stmt, 0);
  }
  sqlite3_finalize(stmt);
  return n;
}

/**
 * Fuzz target: optimize on rescore tables, interleaved with inserts, updates,
 * deletes and KNN queries, with both quantizers and a chunk size of 8 so rows
 * move across chunks. optimize moves each row's quantized vectors to its new
 * slot and leaves its float32 vector where it is, so after every optimize the
 * table and its _rescore_vectors00 must hold the same rows.
 */
int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  if (size < 8) return 0;

  int rc;
  sqlite3 *db;
  sqlite3_stmt *stmtInsert = NULL;
  sqlite3_stmt *stmtUpdate = NULL;
  sqlite3_stmt *stmtDelete = NULL;
  sqlite3_stmt *stmtKnn = NULL;

  rc = sqlite3_open(":memory:", &db);
  assert(rc == SQLITE_OK);
  rc = sqlite3_vec_init(db, NULL, NULL);
  assert(rc == SQLITE_OK);

  int use_int8 = data[0] & 1;
  data++; size--;

  const char *create_sql = use_int8
    ? "CREATE VIRTUAL TABLE v USING vec0("
      "emb float[16] indexed by rescore(quantizer=int8), chunk_size=8)"
    : "CREATE VIRTUAL TABLE v USING vec0("
      "emb float[16] indexed by rescore(quantizer=bit), chunk_size=8)";

  rc = sqlite3_exec(db, create_sql, NULL, NULL, NULL);
  if (rc != SQLITE_OK) { sqlite3_close(db); return 0; }

  sqlite3_prepare_v2(db,
    "INSERT INTO v(rowid, emb) VALUES (?, ?)", -1, &stmtInsert, NULL);
  sqlite3_prepare_v2(db,
    "UPDATE v SET emb = ? WHERE rowid = ?", -1, &stmtUpdate, NULL);
  sqlite3_prepare_v2(db,
    "DELETE FROM v WHERE rowid = ?", -1, &stmtDelete, NULL);
  sqlite3_prepare_v2(db,
    "SELECT rowid, distance FROM v WHERE emb MATCH ? AND k = 5", -1,
    &stmtKnn, NULL);

  if (!stmtInsert || !stmtUpdate || !stmtDelete || !stmtKnn)
    goto cleanup;

  size_t i = 0;
  while (i + 2 <= size) {
    uint8_t op = data[i++] % 5;
    uint8_t rowid_byte = data[i++];
    int64_t rowid = (int64_t)(rowid_byte % 40) + 1;

    switch (op) {
      case 0: {
        float vec[16] = {0};
        for (int j = 0; j < 16 && i < size; j++, i++) {
          vec[j] = (float)((int8_t)data[i]) / 64.0f;
        }
        sqlite3_reset(stmtInsert);
        sqlite3_bind_int64(stmtInsert, 1, rowid);
        sqlite3_bind_blob(stmtInsert, 2, vec, sizeof(vec), SQLITE_TRANSIENT);
        sqlite3_step(stmtInsert);
        break;
      }
      case 1: {
        sqlite3_reset(stmtDelete);
        sqlite3_bind_int64(stmtDelete, 1, rowid);
        sqlite3_step(stmtDelete);
        break;
      }
      case 2: {
        float qvec[16] = {0};
        for (int j = 0; j < 16 && i < size; j++, i++) {
          qvec[j] = (float)((int8_t)data[i]) / 64.0f;
        }
        sqlite3_reset(stmtKnn);
        sqlite3_bind_blob(stmtKnn, 1, qvec, sizeof(qvec), SQLITE_STATIC);
        while (sqlite3_step(stmtKnn) == SQLITE_ROW) {
          (void)sqlite3_column_int64(stmtKnn, 0);
          (void)sqlite3_column_double(stmtKnn, 1);
        }
        break;
      }
      case 3: {
        float vec[16] = {0};
        for (int j = 0; j < 16 && i < size; j++, i++) {
          vec[j] = (float)((int8_t)data[i]) / 32.0f;
        }
        sqlite3_reset(stmtUpdate);
        sqlite3_bind_blob(stmtUpdate, 1, vec, sizeof(vec), SQLITE_TRANSIENT);
        sqlite3_bind_int64(stmtUpdate, 2, rowid);
        sqlite3_step(stmtUpdate);
        break;
      }
      case 4: {
        int64_t before = count_rows(db, "SELECT count(*) FROM v");
        rc = sqlite3_exec(db, "INSERT INTO v(v) VALUES ('optimize')", NULL,
                          NULL, NULL);
        assert(rc == SQLITE_OK);
        assert(count_rows(db, "SELECT count(*) FROM v") == before);
        assert(count_rows(db, "SELECT count(*) FROM v_rescore_vectors00") ==
               before);
        break;
      }
    }
  }

  sqlite3_exec(db, "SELECT * FROM v", NULL, NULL, NULL);

cleanup:
  sqlite3_finalize(stmtInsert);
  sqlite3_finalize(stmtUpdate);
  sqlite3_finalize(stmtDelete);
  sqlite3_finalize(stmtKnn);
  sqlite3_close(db);
  return 0;
}
