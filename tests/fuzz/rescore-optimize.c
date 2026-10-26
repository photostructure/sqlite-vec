#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sqlite-vec.h"
#include "sqlite3.h"
#include "../sqlite-vec-internal.h"
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
 * Asserts that every row of v has its float32 vector in _rescore_vectors00
 * and, in its slot of _rescore_chunks00, the quantized form of that vector,
 * and returns the number of rows.
 */
static int64_t check_quantized_slots(sqlite3 *db, int use_int8) {
  size_t qsize = use_int8 ? 16 : 16 / 8;
  sqlite3_stmt *stmt = NULL;
  int rc = sqlite3_prepare_v2(db,
    "SELECT r.chunk_offset, c.vectors, f.vector FROM v_rowids r "
    "JOIN v_rescore_chunks00 c ON c.rowid = r.chunk_id "
    "JOIN v_rescore_vectors00 f ON f.rowid = r.rowid", -1, &stmt, NULL);
  assert(rc == SQLITE_OK);
  int64_t n = 0;
  while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
    int64_t offset = sqlite3_column_int64(stmt, 0);
    const uint8_t *slots = sqlite3_column_blob(stmt, 1);
    assert(slots && sqlite3_column_bytes(stmt, 1) >= (offset + 1) * qsize);
    assert(sqlite3_column_bytes(stmt, 2) == 16 * sizeof(float));
    float vec[16];
    memcpy(vec, sqlite3_column_blob(stmt, 2), sizeof(vec));
    uint8_t q[16];
    if (use_int8) {
      rescore_quantize_float_to_int8(vec, (int8_t *)q, 16);
    } else {
      rescore_quantize_float_to_bit(vec, q, 16);
    }
    assert(memcmp(slots + offset * qsize, q, qsize) == 0);
    n++;
  }
  assert(rc == SQLITE_DONE);
  sqlite3_finalize(stmt);
  return n;
}

/**
 * Fuzz target: optimize on rescore tables, interleaved with inserts, updates,
 * deletes and KNN queries, with both quantizers and a chunk size of 8 so rows
 * move across chunks. optimize moves each row's quantized vectors to its new
 * slot and leaves its float32 vector where it is, so after every optimize the
 * table and its _rescore_vectors00 must hold the same rows, and each row's slot
 * the quantized form of its vector. An input that inserts a row and then
 * optimizes is at least 21 bytes, and libFuzzer's inputs grew only to 17 bytes
 * in a 90-second run from an empty corpus, so corpus/rescore-optimize/ holds
 * seeds that fill two chunks, delete from the first and optimize.
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
        assert(check_quantized_slots(db, use_int8) == before);
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
