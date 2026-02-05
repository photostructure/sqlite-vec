/**
 * Memory test harness for sqlite-vec
 *
 * Exercises common sqlite-vec operations to detect memory leaks,
 * use-after-free, and other memory issues when run under valgrind
 * or AddressSanitizer.
 *
 * Build: make dist/memory-test
 * Run with valgrind: make test-valgrind
 */

#include "../sqlite-vec.h"
#include "../vendor/sqlite3.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Forward declaration of the init function */
extern int sqlite3_vec_init(sqlite3 *db, char **pzErrMsg,
                            const sqlite3_api_routines *pApi);

#define CHECK_OK(rc, msg)                                                      \
  do {                                                                         \
    if ((rc) != SQLITE_OK) {                                                   \
      fprintf(stderr, "FAILED: %s (rc=%d: %s)\n", msg, rc,                     \
              sqlite3_errmsg(db));                                             \
      goto cleanup;                                                            \
    }                                                                          \
  } while (0)

#define CHECK_DONE(rc, msg)                                                    \
  do {                                                                         \
    if ((rc) != SQLITE_DONE) {                                                 \
      fprintf(stderr, "FAILED: %s (rc=%d: %s)\n", msg, rc,                     \
              sqlite3_errmsg(db));                                             \
      goto cleanup;                                                            \
    }                                                                          \
  } while (0)

#define CHECK_ROW(rc, msg)                                                     \
  do {                                                                         \
    if ((rc) != SQLITE_ROW) {                                                  \
      fprintf(stderr, "FAILED: %s (expected row, rc=%d: %s)\n", msg, rc,       \
              sqlite3_errmsg(db));                                             \
      goto cleanup;                                                            \
    }                                                                          \
  } while (0)

static int test_basic_vec0_operations(void) {
  printf("Testing basic vec0 operations...\n");
  sqlite3 *db = NULL;
  sqlite3_stmt *stmt = NULL;
  int rc;
  int result = 1; // assume failure

  rc = sqlite3_open(":memory:", &db);
  CHECK_OK(rc, "open database");

  // Create a vec0 table
  rc = sqlite3_exec(db,
                    "CREATE VIRTUAL TABLE test_vectors USING vec0("
                    "  embedding float[4]"
                    ")",
                    NULL, NULL, NULL);
  CHECK_OK(rc, "create vec0 table");

  // Insert vectors
  rc = sqlite3_prepare_v2(
      db, "INSERT INTO test_vectors(rowid, embedding) VALUES (?, ?)", -1, &stmt,
      NULL);
  CHECK_OK(rc, "prepare insert");

  for (int i = 1; i <= 100; i++) {
    float vec[4] = {(float)i, (float)(i * 2), (float)(i * 3), (float)(i * 4)};
    sqlite3_bind_int64(stmt, 1, i);
    sqlite3_bind_blob(stmt, 2, vec, sizeof(vec), SQLITE_STATIC);
    rc = sqlite3_step(stmt);
    CHECK_DONE(rc, "insert vector");
    sqlite3_reset(stmt);
  }
  sqlite3_finalize(stmt);
  stmt = NULL;

  // KNN query
  rc = sqlite3_prepare_v2(
      db,
      "SELECT rowid, distance FROM test_vectors "
      "WHERE embedding MATCH '[1,2,3,4]' AND k = 10",
      -1, &stmt, NULL);
  CHECK_OK(rc, "prepare KNN query");

  int count = 0;
  while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
    count++;
  }
  if (rc != SQLITE_DONE) {
    fprintf(stderr, "FAILED: KNN query iteration (rc=%d)\n", rc);
    goto cleanup;
  }
  if (count != 10) {
    fprintf(stderr, "FAILED: expected 10 results, got %d\n", count);
    goto cleanup;
  }
  sqlite3_finalize(stmt);
  stmt = NULL;

  // Update a vector
  rc = sqlite3_exec(
      db, "UPDATE test_vectors SET embedding = '[10,20,30,40]' WHERE rowid = 1",
      NULL, NULL, NULL);
  CHECK_OK(rc, "update vector");

  // Delete vectors
  rc = sqlite3_exec(db, "DELETE FROM test_vectors WHERE rowid > 50", NULL, NULL,
                    NULL);
  CHECK_OK(rc, "delete vectors");

  // Drop the table
  rc = sqlite3_exec(db, "DROP TABLE test_vectors", NULL, NULL, NULL);
  CHECK_OK(rc, "drop table");

  printf("  PASS: basic vec0 operations\n");
  result = 0;

cleanup:
  if (stmt)
    sqlite3_finalize(stmt);
  if (db)
    sqlite3_close(db);
  return result;
}

static int test_vec0_with_metadata(void) {
  printf("Testing vec0 with metadata columns...\n");
  sqlite3 *db = NULL;
  sqlite3_stmt *stmt = NULL;
  int rc;
  int result = 1;

  rc = sqlite3_open(":memory:", &db);
  CHECK_OK(rc, "open database");

  // Create table with metadata columns (no + prefix = metadata, not auxiliary)
  rc = sqlite3_exec(db,
                    "CREATE VIRTUAL TABLE items USING vec0("
                    "  embedding float[8],"
                    "  category text,"
                    "  score integer"
                    ")",
                    NULL, NULL, NULL);
  CHECK_OK(rc, "create vec0 table with metadata");

  // Insert with metadata
  rc = sqlite3_prepare_v2(
      db,
      "INSERT INTO items(rowid, embedding, category, score) VALUES (?, ?, ?, "
      "?)",
      -1, &stmt, NULL);
  CHECK_OK(rc, "prepare insert with metadata");

  for (int i = 1; i <= 50; i++) {
    float vec[8];
    for (int j = 0; j < 8; j++)
      vec[j] = (float)(i + j);
    const char *cat = (i % 2 == 0) ? "even" : "odd";

    sqlite3_bind_int64(stmt, 1, i);
    sqlite3_bind_blob(stmt, 2, vec, sizeof(vec), SQLITE_STATIC);
    sqlite3_bind_text(stmt, 3, cat, -1, SQLITE_STATIC);
    sqlite3_bind_int(stmt, 4, i * 10);
    rc = sqlite3_step(stmt);
    CHECK_DONE(rc, "insert with metadata");
    sqlite3_reset(stmt);
  }
  sqlite3_finalize(stmt);
  stmt = NULL;

  // Query with metadata filter
  rc = sqlite3_prepare_v2(db,
                          "SELECT rowid, distance, category, score FROM items "
                          "WHERE embedding MATCH '[1,2,3,4,5,6,7,8]' "
                          "AND k = 5 AND category = 'even'",
                          -1, &stmt, NULL);
  CHECK_OK(rc, "prepare filtered query");

  int count = 0;
  while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
    const char *cat = (const char *)sqlite3_column_text(stmt, 2);
    if (strcmp(cat, "even") != 0) {
      fprintf(stderr, "FAILED: expected category 'even', got '%s'\n", cat);
      goto cleanup;
    }
    count++;
  }
  if (rc != SQLITE_DONE) {
    fprintf(stderr, "FAILED: filtered query iteration (rc=%d)\n", rc);
    goto cleanup;
  }
  sqlite3_finalize(stmt);
  stmt = NULL;

  // Drop table
  rc = sqlite3_exec(db, "DROP TABLE items", NULL, NULL, NULL);
  CHECK_OK(rc, "drop table");

  printf("  PASS: vec0 with metadata\n");
  result = 0;

cleanup:
  if (stmt)
    sqlite3_finalize(stmt);
  if (db)
    sqlite3_close(db);
  return result;
}

static int test_vec0_with_auxiliary(void) {
  printf("Testing vec0 with auxiliary columns...\n");
  sqlite3 *db = NULL;
  sqlite3_stmt *stmt = NULL;
  int rc;
  int result = 1;

  rc = sqlite3_open(":memory:", &db);
  CHECK_OK(rc, "open database");

  // Create table with auxiliary columns (+ prefix = auxiliary, not metadata)
  rc = sqlite3_exec(db,
                    "CREATE VIRTUAL TABLE docs USING vec0("
                    "  embedding float[4],"
                    "  +title text,"
                    "  +content text"
                    ")",
                    NULL, NULL, NULL);
  CHECK_OK(rc, "create vec0 table with auxiliary");

  // Insert with auxiliary data
  rc = sqlite3_prepare_v2(
      db,
      "INSERT INTO docs(rowid, embedding, title, content) VALUES (?, ?, ?, ?)",
      -1, &stmt, NULL);
  CHECK_OK(rc, "prepare insert with auxiliary");

  for (int i = 1; i <= 25; i++) {
    float vec[4] = {(float)i, (float)i, (float)i, (float)i};
    char title[64], content[128];
    snprintf(title, sizeof(title), "Document %d", i);
    snprintf(content, sizeof(content), "This is the content of document %d", i);

    sqlite3_bind_int64(stmt, 1, i);
    sqlite3_bind_blob(stmt, 2, vec, sizeof(vec), SQLITE_STATIC);
    sqlite3_bind_text(stmt, 3, title, -1, SQLITE_STATIC);
    sqlite3_bind_text(stmt, 4, content, -1, SQLITE_STATIC);
    rc = sqlite3_step(stmt);
    CHECK_DONE(rc, "insert with auxiliary");
    sqlite3_reset(stmt);
  }
  sqlite3_finalize(stmt);
  stmt = NULL;

  // Query and verify auxiliary data
  rc = sqlite3_prepare_v2(db,
                          "SELECT rowid, title, content FROM docs "
                          "WHERE embedding MATCH '[5,5,5,5]' AND k = 3",
                          -1, &stmt, NULL);
  CHECK_OK(rc, "prepare auxiliary query");

  while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
    sqlite3_column_text(stmt, 1); // title
    sqlite3_column_text(stmt, 2); // content
  }
  if (rc != SQLITE_DONE) {
    fprintf(stderr, "FAILED: auxiliary query iteration (rc=%d)\n", rc);
    goto cleanup;
  }
  sqlite3_finalize(stmt);
  stmt = NULL;

  // Drop table
  rc = sqlite3_exec(db, "DROP TABLE docs", NULL, NULL, NULL);
  CHECK_OK(rc, "drop table");

  printf("  PASS: vec0 with auxiliary\n");
  result = 0;

cleanup:
  if (stmt)
    sqlite3_finalize(stmt);
  if (db)
    sqlite3_close(db);
  return result;
}

static int test_sql_functions(void) {
  printf("Testing SQL scalar functions...\n");
  sqlite3 *db = NULL;
  sqlite3_stmt *stmt = NULL;
  int rc;
  int result = 1;

  rc = sqlite3_open(":memory:", &db);
  CHECK_OK(rc, "open database");

  // Test vec_f32
  rc = sqlite3_prepare_v2(db, "SELECT vec_f32('[1.0, 2.0, 3.0]')", -1, &stmt,
                          NULL);
  CHECK_OK(rc, "prepare vec_f32");
  rc = sqlite3_step(stmt);
  CHECK_ROW(rc, "vec_f32 result");
  sqlite3_finalize(stmt);
  stmt = NULL;

  // Test vec_length
  rc = sqlite3_prepare_v2(db, "SELECT vec_length(vec_f32('[1,2,3,4,5]'))", -1,
                          &stmt, NULL);
  CHECK_OK(rc, "prepare vec_length");
  rc = sqlite3_step(stmt);
  CHECK_ROW(rc, "vec_length result");
  if (sqlite3_column_int(stmt, 0) != 5) {
    fprintf(stderr, "FAILED: vec_length expected 5\n");
    goto cleanup;
  }
  sqlite3_finalize(stmt);
  stmt = NULL;

  // Test vec_distance_l2
  rc = sqlite3_prepare_v2(
      db, "SELECT vec_distance_l2('[1,0,0]', '[0,1,0]')", -1, &stmt, NULL);
  CHECK_OK(rc, "prepare vec_distance_l2");
  rc = sqlite3_step(stmt);
  CHECK_ROW(rc, "vec_distance_l2 result");
  sqlite3_finalize(stmt);
  stmt = NULL;

  // Test vec_distance_cosine
  rc = sqlite3_prepare_v2(
      db, "SELECT vec_distance_cosine('[1,0,0]', '[1,0,0]')", -1, &stmt, NULL);
  CHECK_OK(rc, "prepare vec_distance_cosine");
  rc = sqlite3_step(stmt);
  CHECK_ROW(rc, "vec_distance_cosine result");
  sqlite3_finalize(stmt);
  stmt = NULL;

  // Test vec_normalize
  rc = sqlite3_prepare_v2(db, "SELECT vec_normalize('[3,4]')", -1, &stmt, NULL);
  CHECK_OK(rc, "prepare vec_normalize");
  rc = sqlite3_step(stmt);
  CHECK_ROW(rc, "vec_normalize result");
  sqlite3_finalize(stmt);
  stmt = NULL;

  // Test vec_slice
  rc = sqlite3_prepare_v2(db, "SELECT vec_slice('[1,2,3,4,5]', 1, 3)", -1,
                          &stmt, NULL);
  CHECK_OK(rc, "prepare vec_slice");
  rc = sqlite3_step(stmt);
  CHECK_ROW(rc, "vec_slice result");
  sqlite3_finalize(stmt);
  stmt = NULL;

  // Test vec_add and vec_sub
  rc = sqlite3_prepare_v2(db, "SELECT vec_add('[1,2,3]', '[4,5,6]')", -1, &stmt,
                          NULL);
  CHECK_OK(rc, "prepare vec_add");
  rc = sqlite3_step(stmt);
  CHECK_ROW(rc, "vec_add result");
  sqlite3_finalize(stmt);
  stmt = NULL;

  rc = sqlite3_prepare_v2(db, "SELECT vec_sub('[4,5,6]', '[1,2,3]')", -1, &stmt,
                          NULL);
  CHECK_OK(rc, "prepare vec_sub");
  rc = sqlite3_step(stmt);
  CHECK_ROW(rc, "vec_sub result");
  sqlite3_finalize(stmt);
  stmt = NULL;

  // Test vec_quantize_int8
  rc = sqlite3_prepare_v2(
      db, "SELECT vec_quantize_int8('[0.1, 0.5, -0.3]', 'unit')", -1, &stmt,
      NULL);
  CHECK_OK(rc, "prepare vec_quantize_int8");
  rc = sqlite3_step(stmt);
  CHECK_ROW(rc, "vec_quantize_int8 result");
  sqlite3_finalize(stmt);
  stmt = NULL;

  printf("  PASS: SQL scalar functions\n");
  result = 0;

cleanup:
  if (stmt)
    sqlite3_finalize(stmt);
  if (db)
    sqlite3_close(db);
  return result;
}

static int test_int8_vectors(void) {
  printf("Testing int8 vectors...\n");
  sqlite3 *db = NULL;
  sqlite3_stmt *stmt = NULL;
  int rc;
  int result = 1;

  rc = sqlite3_open(":memory:", &db);
  CHECK_OK(rc, "open database");

  // Create int8 vec0 table
  rc = sqlite3_exec(db,
                    "CREATE VIRTUAL TABLE int8_test USING vec0("
                    "  embedding int8[16]"
                    ")",
                    NULL, NULL, NULL);
  CHECK_OK(rc, "create int8 vec0 table");

  // Insert int8 vectors using vec_int8() wrapper
  rc = sqlite3_prepare_v2(
      db, "INSERT INTO int8_test(rowid, embedding) VALUES (?, vec_int8(?))", -1,
      &stmt, NULL);
  CHECK_OK(rc, "prepare int8 insert");

  for (int i = 1; i <= 30; i++) {
    int8_t vec[16];
    for (int j = 0; j < 16; j++)
      vec[j] = (int8_t)((i + j) % 128);
    sqlite3_bind_int64(stmt, 1, i);
    sqlite3_bind_blob(stmt, 2, vec, sizeof(vec), SQLITE_STATIC);
    rc = sqlite3_step(stmt);
    CHECK_DONE(rc, "insert int8 vector");
    sqlite3_reset(stmt);
  }
  sqlite3_finalize(stmt);
  stmt = NULL;

  // KNN query on int8
  rc = sqlite3_prepare_v2(
      db,
      "SELECT rowid FROM int8_test "
      "WHERE embedding MATCH vec_int8('[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,"
      "16]') AND k = 5",
      -1, &stmt, NULL);
  CHECK_OK(rc, "prepare int8 KNN query");

  int count = 0;
  while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
    count++;
  }
  if (rc != SQLITE_DONE || count != 5) {
    fprintf(stderr, "FAILED: int8 KNN query (rc=%d, count=%d)\n", rc, count);
    goto cleanup;
  }
  sqlite3_finalize(stmt);
  stmt = NULL;

  rc = sqlite3_exec(db, "DROP TABLE int8_test", NULL, NULL, NULL);
  CHECK_OK(rc, "drop int8 table");

  printf("  PASS: int8 vectors\n");
  result = 0;

cleanup:
  if (stmt)
    sqlite3_finalize(stmt);
  if (db)
    sqlite3_close(db);
  return result;
}

static int test_binary_vectors(void) {
  printf("Testing binary (bit) vectors...\n");
  sqlite3 *db = NULL;
  sqlite3_stmt *stmt = NULL;
  int rc;
  int result = 1;

  rc = sqlite3_open(":memory:", &db);
  CHECK_OK(rc, "open database");

  // Create bit vec0 table (64 bits = 8 bytes)
  rc = sqlite3_exec(db,
                    "CREATE VIRTUAL TABLE bit_test USING vec0("
                    "  embedding bit[64]"
                    ")",
                    NULL, NULL, NULL);
  CHECK_OK(rc, "create bit vec0 table");

  // Insert binary vectors using vec_bit() wrapper
  rc = sqlite3_prepare_v2(
      db, "INSERT INTO bit_test(rowid, embedding) VALUES (?, vec_bit(?))", -1,
      &stmt, NULL);
  CHECK_OK(rc, "prepare bit insert");

  for (int i = 1; i <= 20; i++) {
    unsigned char vec[8];
    for (int j = 0; j < 8; j++)
      vec[j] = (unsigned char)(i + j);
    sqlite3_bind_int64(stmt, 1, i);
    sqlite3_bind_blob(stmt, 2, vec, sizeof(vec), SQLITE_STATIC);
    rc = sqlite3_step(stmt);
    CHECK_DONE(rc, "insert bit vector");
    sqlite3_reset(stmt);
  }
  sqlite3_finalize(stmt);
  stmt = NULL;

  // Hamming distance query - use vec_bit() for the query vector
  rc = sqlite3_prepare_v2(db,
                          "SELECT rowid FROM bit_test "
                          "WHERE embedding MATCH vec_bit(?) AND k = 3",
                          -1, &stmt, NULL);
  CHECK_OK(rc, "prepare hamming query");
  unsigned char query_vec[8] = {1, 2, 3, 4, 5, 6, 7, 8};
  sqlite3_bind_blob(stmt, 1, query_vec, sizeof(query_vec), SQLITE_STATIC);

  int count = 0;
  while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
    count++;
  }
  if (rc != SQLITE_DONE || count != 3) {
    fprintf(stderr, "FAILED: hamming query (rc=%d, count=%d)\n", rc, count);
    goto cleanup;
  }
  sqlite3_finalize(stmt);
  stmt = NULL;

  rc = sqlite3_exec(db, "DROP TABLE bit_test", NULL, NULL, NULL);
  CHECK_OK(rc, "drop bit table");

  printf("  PASS: binary vectors\n");
  result = 0;

cleanup:
  if (stmt)
    sqlite3_finalize(stmt);
  if (db)
    sqlite3_close(db);
  return result;
}

static int test_repeated_operations(void) {
  printf("Testing repeated create/drop cycles...\n");
  sqlite3 *db = NULL;
  int rc;
  int result = 1;

  rc = sqlite3_open(":memory:", &db);
  CHECK_OK(rc, "open database");

  // Repeated create/insert/drop cycles to catch leaks
  for (int cycle = 0; cycle < 10; cycle++) {
    rc = sqlite3_exec(db,
                      "CREATE VIRTUAL TABLE cycle_test USING vec0("
                      "  embedding float[8]"
                      ")",
                      NULL, NULL, NULL);
    CHECK_OK(rc, "create table in cycle");

    // Insert some data
    for (int i = 0; i < 10; i++) {
      char sql[256];
      snprintf(sql, sizeof(sql),
               "INSERT INTO cycle_test(rowid, embedding) "
               "VALUES (%d, '[%d,%d,%d,%d,%d,%d,%d,%d]')",
               i + 1, i, i, i, i, i, i, i, i);
      rc = sqlite3_exec(db, sql, NULL, NULL, NULL);
      CHECK_OK(rc, "insert in cycle");
    }

    // Query
    rc = sqlite3_exec(db,
                      "SELECT rowid FROM cycle_test "
                      "WHERE embedding MATCH '[1,1,1,1,1,1,1,1]' AND k = 5",
                      NULL, NULL, NULL);
    CHECK_OK(rc, "query in cycle");

    // Drop
    rc = sqlite3_exec(db, "DROP TABLE cycle_test", NULL, NULL, NULL);
    CHECK_OK(rc, "drop table in cycle");
  }

  printf("  PASS: repeated operations\n");
  result = 0;

cleanup:
  if (db)
    sqlite3_close(db);
  return result;
}

static int test_repeated_knn_queries(void) {
  printf("Testing repeated KNN queries with cursor cleanup...\n");
  sqlite3 *db = NULL;
  sqlite3_stmt *stmt = NULL;
  int rc;
  int result = 1;

  rc = sqlite3_open(":memory:", &db);
  CHECK_OK(rc, "open database");

  // Create a vec0 table
  rc = sqlite3_exec(db,
                    "CREATE VIRTUAL TABLE test_vecs USING vec0("
                    "  embedding float[4]"
                    ")",
                    NULL, NULL, NULL);
  CHECK_OK(rc, "create vec0 table");

  // Insert vectors
  for (int i = 1; i <= 50; i++) {
    char sql[256];
    snprintf(sql, sizeof(sql),
             "INSERT INTO test_vecs(rowid, embedding) VALUES (%d, '[%d,%d,%d,%d]')",
             i, i, i*2, i*3, i*4);
    rc = sqlite3_exec(db, sql, NULL, NULL, NULL);
    CHECK_OK(rc, "insert vector");
  }

  // Query with KNN multiple times
  // This exercises the cursor cleanup paths including knn_data
  for (int iter = 0; iter < 30; iter++) {
    rc = sqlite3_prepare_v2(
        db,
        "SELECT rowid, distance FROM test_vecs "
        "WHERE embedding MATCH '[1,2,3,4]' AND k = 10",
        -1, &stmt, NULL);
    CHECK_OK(rc, "prepare KNN query");

    int count = 0;
    while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
      count++;
    }
    if (rc != SQLITE_DONE) {
      fprintf(stderr, "FAILED: KNN iteration (rc=%d)\n", rc);
      goto cleanup;
    }
    if (count != 10) {
      fprintf(stderr, "FAILED: expected 10 results, got %d\n", count);
      goto cleanup;
    }

    sqlite3_finalize(stmt);
    stmt = NULL;
  }

  // Cleanup
  rc = sqlite3_exec(db, "DROP TABLE test_vecs", NULL, NULL, NULL);
  CHECK_OK(rc, "drop table");

  printf("  PASS: repeated KNN queries\n");
  result = 0;

cleanup:
  if (stmt)
    sqlite3_finalize(stmt);
  if (db)
    sqlite3_close(db);
  return result;
}

static int test_long_text_metadata_updates(void) {
  printf("Testing long text metadata updates...\n");
  sqlite3 *db = NULL;
  sqlite3_stmt *stmt = NULL;
  int rc;
  int result = 1;

  rc = sqlite3_open(":memory:", &db);
  CHECK_OK(rc, "open database");

  // Create table with text metadata column
  rc = sqlite3_exec(db,
                    "CREATE VIRTUAL TABLE docs USING vec0("
                    "  embedding float[4],"
                    "  description text"
                    ")",
                    NULL, NULL, NULL);
  CHECK_OK(rc, "create vec0 table with text metadata");

  // Create long text that exceeds VEC0_METADATA_TEXT_VIEW_DATA_LENGTH
  // to trigger the prepare_v2 path that had the leak
  char long_text[500];
  memset(long_text, 'A', sizeof(long_text) - 1);
  long_text[sizeof(long_text) - 1] = '\0';

  // Insert with long text
  rc = sqlite3_prepare_v2(
      db,
      "INSERT INTO docs(rowid, embedding, description) VALUES (?, ?, ?)",
      -1, &stmt, NULL);
  CHECK_OK(rc, "prepare insert with long text");

  for (int i = 1; i <= 30; i++) {
    float vec[4] = {(float)i, (float)i, (float)i, (float)i};
    sqlite3_bind_int64(stmt, 1, i);
    sqlite3_bind_blob(stmt, 2, vec, sizeof(vec), SQLITE_STATIC);
    sqlite3_bind_text(stmt, 3, long_text, -1, SQLITE_STATIC);
    rc = sqlite3_step(stmt);
    CHECK_DONE(rc, "insert with long text");
    sqlite3_reset(stmt);
  }
  sqlite3_finalize(stmt);
  stmt = NULL;

  // Update with different long text (exercises UPDATE path)
  memset(long_text, 'B', sizeof(long_text) - 1);
  rc = sqlite3_prepare_v2(
      db,
      "UPDATE docs SET description = ? WHERE rowid = ?",
      -1, &stmt, NULL);
  CHECK_OK(rc, "prepare update with long text");

  for (int i = 1; i <= 30; i++) {
    sqlite3_bind_text(stmt, 1, long_text, -1, SQLITE_STATIC);
    sqlite3_bind_int64(stmt, 2, i);
    rc = sqlite3_step(stmt);
    CHECK_DONE(rc, "update with long text");
    sqlite3_reset(stmt);
  }
  sqlite3_finalize(stmt);
  stmt = NULL;

  // Update to short text to trigger DELETE of long text data
  // (when text becomes short enough, the long text data should be deleted)
  rc = sqlite3_prepare_v2(
      db,
      "UPDATE docs SET description = 'short' WHERE rowid = ?",
      -1, &stmt, NULL);
  CHECK_OK(rc, "prepare update to short text");

  for (int i = 1; i <= 30; i++) {
    sqlite3_bind_int64(stmt, 1, i);
    rc = sqlite3_step(stmt);
    CHECK_DONE(rc, "update to short text");
    sqlite3_reset(stmt);
  }
  sqlite3_finalize(stmt);
  stmt = NULL;

  // Cleanup
  rc = sqlite3_exec(db, "DROP TABLE docs", NULL, NULL, NULL);
  CHECK_OK(rc, "drop table");

  printf("  PASS: long text metadata updates\n");
  result = 0;

cleanup:
  if (stmt)
    sqlite3_finalize(stmt);
  if (db)
    sqlite3_close(db);
  return result;
}

static int test_insert_with_multiple_vectors(void) {
  printf("Testing INSERT with multiple vector columns...\n");
  sqlite3 *db = NULL;
  sqlite3_stmt *stmt = NULL;
  int rc;
  int result = 1;

  rc = sqlite3_open(":memory:", &db);
  CHECK_OK(rc, "open database");

  // Create table with multiple vector columns
  // This exercises the cleanup array that needed initialization
  rc = sqlite3_exec(db,
                    "CREATE VIRTUAL TABLE multi USING vec0("
                    "  vec1 float[4],"
                    "  vec2 float[4],"
                    "  vec3 float[4]"
                    ")",
                    NULL, NULL, NULL);
  CHECK_OK(rc, "create vec0 table with multiple vectors");

  // Insert rows with all vectors
  rc = sqlite3_prepare_v2(
      db,
      "INSERT INTO multi(rowid, vec1, vec2, vec3) VALUES (?, ?, ?, ?)",
      -1, &stmt, NULL);
  CHECK_OK(rc, "prepare multi-vector insert");

  for (int i = 1; i <= 30; i++) {
    float v1[4] = {(float)i, (float)i, (float)i, (float)i};
    float v2[4] = {(float)(i*2), (float)(i*2), (float)(i*2), (float)(i*2)};
    float v3[4] = {(float)(i*3), (float)(i*3), (float)(i*3), (float)(i*3)};

    sqlite3_bind_int64(stmt, 1, i);
    sqlite3_bind_blob(stmt, 2, v1, sizeof(v1), SQLITE_STATIC);
    sqlite3_bind_blob(stmt, 3, v2, sizeof(v2), SQLITE_STATIC);
    sqlite3_bind_blob(stmt, 4, v3, sizeof(v3), SQLITE_STATIC);
    rc = sqlite3_step(stmt);
    CHECK_DONE(rc, "insert multi-vector row");
    sqlite3_reset(stmt);
  }
  sqlite3_finalize(stmt);
  stmt = NULL;

  // Query each vector column
  for (int col = 1; col <= 3; col++) {
    char sql[256];
    snprintf(sql, sizeof(sql),
             "SELECT rowid FROM multi WHERE vec%d MATCH '[1,1,1,1]' AND k = 5",
             col);
    rc = sqlite3_prepare_v2(db, sql, -1, &stmt, NULL);
    CHECK_OK(rc, "prepare query");

    int count = 0;
    while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
      count++;
    }
    if (rc != SQLITE_DONE) {
      fprintf(stderr, "FAILED: vec%d query iteration (rc=%d)\n", col, rc);
      goto cleanup;
    }

    sqlite3_finalize(stmt);
    stmt = NULL;
  }

  // Cleanup
  rc = sqlite3_exec(db, "DROP TABLE multi", NULL, NULL, NULL);
  CHECK_OK(rc, "drop table");

  printf("  PASS: INSERT with multiple vectors\n");
  result = 0;

cleanup:
  if (stmt)
    sqlite3_finalize(stmt);
  if (db)
    sqlite3_close(db);
  return result;
}

int main(void) {
  printf("sqlite-vec memory test harness\n");
  printf("==============================\n\n");

  /* Register sqlite-vec as an auto extension so it's available in all
   * connections */
  int rc = sqlite3_auto_extension((void (*)(void))sqlite3_vec_init);
  if (rc != SQLITE_OK) {
    fprintf(stderr, "FATAL: Failed to register sqlite-vec extension\n");
    return 1;
  }

  int failures = 0;

  failures += test_basic_vec0_operations();
  failures += test_vec0_with_metadata();
  failures += test_vec0_with_auxiliary();
  failures += test_sql_functions();
  failures += test_int8_vectors();
  failures += test_binary_vectors();
  failures += test_repeated_operations();
  failures += test_repeated_knn_queries();
  failures += test_long_text_metadata_updates();
  failures += test_insert_with_multiple_vectors();

  printf("\n==============================\n");
  if (failures == 0) {
    printf("All tests PASSED\n");
    return 0;
  } else {
    printf("%d test(s) FAILED\n", failures);
    return 1;
  }
}
