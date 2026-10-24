#include "../sqlite-vec.h"
#include "sqlite-vec-internal.h"
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <math.h>

#define countof(x) (sizeof(x) / sizeof((x)[0]))

// Tests vec0_token_next(), the low-level tokenizer that extracts the next
// token from a raw char range. Covers every token type (identifier, digit,
// brackets, plus, equals), whitespace skipping, EOF on empty/whitespace-only
// input, error on unrecognised characters, and boundary behaviour where
// identifiers and digits stop at the next non-matching character.
void test_vec0_token_next() {
  printf("Starting %s...\n", __func__);
  struct Vec0Token token;
  int rc;
  char *input;

  // Single-character tokens
  input = "+";
  rc = vec0_token_next(input, input + 1, &token);
  assert(rc == VEC0_TOKEN_RESULT_SOME);
  assert(token.token_type == TOKEN_TYPE_PLUS);

  input = "[";
  rc = vec0_token_next(input, input + 1, &token);
  assert(rc == VEC0_TOKEN_RESULT_SOME);
  assert(token.token_type == TOKEN_TYPE_LBRACKET);

  input = "]";
  rc = vec0_token_next(input, input + 1, &token);
  assert(rc == VEC0_TOKEN_RESULT_SOME);
  assert(token.token_type == TOKEN_TYPE_RBRACKET);

  input = "=";
  rc = vec0_token_next(input, input + 1, &token);
  assert(rc == VEC0_TOKEN_RESULT_SOME);
  assert(token.token_type == TOKEN_TYPE_EQ);

  // Identifier
  input = "hello";
  rc = vec0_token_next(input, input + 5, &token);
  assert(rc == VEC0_TOKEN_RESULT_SOME);
  assert(token.token_type == TOKEN_TYPE_IDENTIFIER);
  assert(token.start == input);
  assert(token.end == input + 5);

  // Identifier with underscores and digits
  input = "col_1a";
  rc = vec0_token_next(input, input + 6, &token);
  assert(rc == VEC0_TOKEN_RESULT_SOME);
  assert(token.token_type == TOKEN_TYPE_IDENTIFIER);
  assert(token.end - token.start == 6);

  // Digit sequence
  input = "1234";
  rc = vec0_token_next(input, input + 4, &token);
  assert(rc == VEC0_TOKEN_RESULT_SOME);
  assert(token.token_type == TOKEN_TYPE_DIGIT);
  assert(token.start == input);
  assert(token.end == input + 4);

  // Leading whitespace is skipped
  input = "  abc";
  rc = vec0_token_next(input, input + 5, &token);
  assert(rc == VEC0_TOKEN_RESULT_SOME);
  assert(token.token_type == TOKEN_TYPE_IDENTIFIER);
  assert(token.end - token.start == 3);

  // Tab/newline whitespace
  input = "\t\n\r X";
  rc = vec0_token_next(input, input + 5, &token);
  assert(rc == VEC0_TOKEN_RESULT_SOME);
  assert(token.token_type == TOKEN_TYPE_IDENTIFIER);

  // Empty input
  input = "";
  rc = vec0_token_next(input, input, &token);
  assert(rc == VEC0_TOKEN_RESULT_EOF);

  // Only whitespace
  input = "   ";
  rc = vec0_token_next(input, input + 3, &token);
  assert(rc == VEC0_TOKEN_RESULT_EOF);

  // Unrecognized character
  input = "@";
  rc = vec0_token_next(input, input + 1, &token);
  assert(rc == VEC0_TOKEN_RESULT_ERROR);

  input = "!";
  rc = vec0_token_next(input, input + 1, &token);
  assert(rc == VEC0_TOKEN_RESULT_ERROR);

  // Identifier stops at bracket
  input = "foo[";
  rc = vec0_token_next(input, input + 4, &token);
  assert(rc == VEC0_TOKEN_RESULT_SOME);
  assert(token.token_type == TOKEN_TYPE_IDENTIFIER);
  assert(token.end - token.start == 3);

  // Digit stops at non-digit
  input = "42abc";
  rc = vec0_token_next(input, input + 5, &token);
  assert(rc == VEC0_TOKEN_RESULT_SOME);
  assert(token.token_type == TOKEN_TYPE_DIGIT);
  assert(token.end - token.start == 2);

  // Left paren
  input = "(";
  rc = vec0_token_next(input, input + 1, &token);
  assert(rc == VEC0_TOKEN_RESULT_SOME);
  assert(token.token_type == TOKEN_TYPE_LPAREN);

  // Right paren
  input = ")";
  rc = vec0_token_next(input, input + 1, &token);
  assert(rc == VEC0_TOKEN_RESULT_SOME);
  assert(token.token_type == TOKEN_TYPE_RPAREN);

  // Comma
  input = ",";
  rc = vec0_token_next(input, input + 1, &token);
  assert(rc == VEC0_TOKEN_RESULT_SOME);
  assert(token.token_type == TOKEN_TYPE_COMMA);

  printf("  All vec0_token_next tests passed.\n");
}

// Tests Vec0Scanner, the stateful wrapper around vec0_token_next() that
// tracks position and yields successive tokens. Verifies correct tokenisation
// of full sequences like "abc float[128]" and "key=value", empty input,
// whitespace-heavy input, and expressions with operators ("a+b").
void test_vec0_scanner() {
  printf("Starting %s...\n", __func__);
  struct Vec0Scanner scanner;
  struct Vec0Token token;
  int rc;

  // Scan "abc float[128]"
  {
    const char *input = "abc float[128]";
    vec0_scanner_init(&scanner, input, (int)strlen(input));

    rc = vec0_scanner_next(&scanner, &token);
    assert(rc == VEC0_TOKEN_RESULT_SOME);
    assert(token.token_type == TOKEN_TYPE_IDENTIFIER);
    assert(token.end - token.start == 3);
    assert(strncmp(token.start, "abc", 3) == 0);

    rc = vec0_scanner_next(&scanner, &token);
    assert(rc == VEC0_TOKEN_RESULT_SOME);
    assert(token.token_type == TOKEN_TYPE_IDENTIFIER);
    assert(token.end - token.start == 5);
    assert(strncmp(token.start, "float", 5) == 0);

    rc = vec0_scanner_next(&scanner, &token);
    assert(rc == VEC0_TOKEN_RESULT_SOME);
    assert(token.token_type == TOKEN_TYPE_LBRACKET);

    rc = vec0_scanner_next(&scanner, &token);
    assert(rc == VEC0_TOKEN_RESULT_SOME);
    assert(token.token_type == TOKEN_TYPE_DIGIT);
    assert(strncmp(token.start, "128", 3) == 0);

    rc = vec0_scanner_next(&scanner, &token);
    assert(rc == VEC0_TOKEN_RESULT_SOME);
    assert(token.token_type == TOKEN_TYPE_RBRACKET);

    rc = vec0_scanner_next(&scanner, &token);
    assert(rc == VEC0_TOKEN_RESULT_EOF);
  }

  // Scan "key=value"
  {
    const char *input = "key=value";
    vec0_scanner_init(&scanner, input, (int)strlen(input));

    rc = vec0_scanner_next(&scanner, &token);
    assert(rc == VEC0_TOKEN_RESULT_SOME);
    assert(token.token_type == TOKEN_TYPE_IDENTIFIER);
    assert(strncmp(token.start, "key", 3) == 0);

    rc = vec0_scanner_next(&scanner, &token);
    assert(rc == VEC0_TOKEN_RESULT_SOME);
    assert(token.token_type == TOKEN_TYPE_EQ);

    rc = vec0_scanner_next(&scanner, &token);
    assert(rc == VEC0_TOKEN_RESULT_SOME);
    assert(token.token_type == TOKEN_TYPE_IDENTIFIER);
    assert(strncmp(token.start, "value", 5) == 0);

    rc = vec0_scanner_next(&scanner, &token);
    assert(rc == VEC0_TOKEN_RESULT_EOF);
  }

  // Scan empty string
  {
    const char *input = "";
    vec0_scanner_init(&scanner, input, 0);

    rc = vec0_scanner_next(&scanner, &token);
    assert(rc == VEC0_TOKEN_RESULT_EOF);
  }

  // Scan with lots of whitespace
  {
    const char *input = "  a   b  ";
    vec0_scanner_init(&scanner, input, (int)strlen(input));

    rc = vec0_scanner_next(&scanner, &token);
    assert(rc == VEC0_TOKEN_RESULT_SOME);
    assert(token.token_type == TOKEN_TYPE_IDENTIFIER);
    assert(token.end - token.start == 1);
    assert(*token.start == 'a');

    rc = vec0_scanner_next(&scanner, &token);
    assert(rc == VEC0_TOKEN_RESULT_SOME);
    assert(token.token_type == TOKEN_TYPE_IDENTIFIER);
    assert(token.end - token.start == 1);
    assert(*token.start == 'b');

    rc = vec0_scanner_next(&scanner, &token);
    assert(rc == VEC0_TOKEN_RESULT_EOF);
  }

  // Scan "a+b"
  {
    const char *input = "a+b";
    vec0_scanner_init(&scanner, input, (int)strlen(input));

    rc = vec0_scanner_next(&scanner, &token);
    assert(rc == VEC0_TOKEN_RESULT_SOME);
    assert(token.token_type == TOKEN_TYPE_IDENTIFIER);

    rc = vec0_scanner_next(&scanner, &token);
    assert(rc == VEC0_TOKEN_RESULT_SOME);
    assert(token.token_type == TOKEN_TYPE_PLUS);

    rc = vec0_scanner_next(&scanner, &token);
    assert(rc == VEC0_TOKEN_RESULT_SOME);
    assert(token.token_type == TOKEN_TYPE_IDENTIFIER);

    rc = vec0_scanner_next(&scanner, &token);
    assert(rc == VEC0_TOKEN_RESULT_EOF);
  }

  printf("  All vec0_scanner tests passed.\n");
}

// Tests vec0_parse_vector_column(), which parses a vec0 column definition
// string like "embedding float[768] distance_metric=cosine" into a
// VectorColumnDefinition struct. Covers all element types (float/f32, int8/i8,
// bit), column names with underscores/digits, all distance metrics (L2, L1,
// cosine), the default metric, and error cases: empty input, missing type,
// unknown type, missing dimensions, unknown metric, unknown option key, and
// distance_metric on bit columns.
void test_vec0_parse_vector_column() {
  printf("Starting %s...\n", __func__);
  struct VectorColumnDefinition col;
  int rc;

  // Basic float column
  {
    const char *input = "embedding float[768]";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.name_length == 9);
    assert(strncmp(col.name, "embedding", 9) == 0);
    assert(col.element_type == SQLITE_VEC_ELEMENT_TYPE_FLOAT32);
    assert(col.dimensions == 768);
    assert(col.distance_metric == VEC0_DISTANCE_METRIC_L2);
    sqlite3_free(col.name);
  }

  // f32 alias
  {
    const char *input = "v f32[3]";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.element_type == SQLITE_VEC_ELEMENT_TYPE_FLOAT32);
    assert(col.dimensions == 3);
    sqlite3_free(col.name);
  }

  // int8 column
  {
    const char *input = "quantized int8[256]";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.element_type == SQLITE_VEC_ELEMENT_TYPE_INT8);
    assert(col.dimensions == 256);
    assert(col.name_length == 9);
    assert(strncmp(col.name, "quantized", 9) == 0);
    sqlite3_free(col.name);
  }

  // i8 alias
  {
    const char *input = "q i8[64]";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.element_type == SQLITE_VEC_ELEMENT_TYPE_INT8);
    assert(col.dimensions == 64);
    sqlite3_free(col.name);
  }

  // bit column
  {
    const char *input = "bvec bit[1024]";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.element_type == SQLITE_VEC_ELEMENT_TYPE_BIT);
    assert(col.dimensions == 1024);
    sqlite3_free(col.name);
  }

  // Column name with underscores and digits
  {
    const char *input = "col_name_2 float[10]";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.name_length == 10);
    assert(strncmp(col.name, "col_name_2", 10) == 0);
    sqlite3_free(col.name);
  }

  // distance_metric=cosine
  {
    const char *input = "emb float[128] distance_metric=cosine";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.distance_metric == VEC0_DISTANCE_METRIC_COSINE);
    assert(col.dimensions == 128);
    sqlite3_free(col.name);
  }

  // distance_metric=L2 (explicit)
  {
    const char *input = "emb float[128] distance_metric=L2";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.distance_metric == VEC0_DISTANCE_METRIC_L2);
    sqlite3_free(col.name);
  }

  // distance_metric=L1
  {
    const char *input = "emb float[128] distance_metric=l1";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.distance_metric == VEC0_DISTANCE_METRIC_L1);
    sqlite3_free(col.name);
  }

  // Error: empty string
  {
    const char *input = "";
    rc = vec0_parse_vector_column(input, 0, &col, true);
    assert(rc != SQLITE_OK);
  }

  // Error: no type
  {
    const char *input = "emb";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc != SQLITE_OK);
  }

  // Error: unknown type
  {
    const char *input = "emb double[128]";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc != SQLITE_OK);
  }

  // Error: missing dimensions
  {
    const char *input = "emb float";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc != SQLITE_OK);
  }

  // Error: unknown distance metric
  {
    const char *input = "emb float[128] distance_metric=hamming";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc != SQLITE_OK);
  }

  // Error: unknown option key
  {
    const char *input = "emb float[128] foobar=baz";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc != SQLITE_OK);
  }

  // Error: distance_metric on bit type
  {
    const char *input = "emb bit[64] distance_metric=cosine";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc != SQLITE_OK);
  }

  // indexed by flat()
  {
    const char *input = "emb float[768] indexed by flat()";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.index_type == VEC0_INDEX_TYPE_FLAT);
    assert(col.dimensions == 768);
    sqlite3_free(col.name);
  }

  // indexed by flat() with distance_metric
  {
    const char *input =
        "emb float[768] distance_metric=cosine indexed by flat()";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.index_type == VEC0_INDEX_TYPE_FLAT);
    assert(col.distance_metric == VEC0_DISTANCE_METRIC_COSINE);
    sqlite3_free(col.name);
  }

  // indexed by flat() on int8
  {
    const char *input = "emb int8[256] indexed by flat()";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.index_type == VEC0_INDEX_TYPE_FLAT);
    assert(col.element_type == SQLITE_VEC_ELEMENT_TYPE_INT8);
    sqlite3_free(col.name);
  }

  // indexed by flat() on bit
  {
    const char *input = "emb bit[64] indexed by flat()";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.index_type == VEC0_INDEX_TYPE_FLAT);
    assert(col.element_type == SQLITE_VEC_ELEMENT_TYPE_BIT);
    sqlite3_free(col.name);
  }

  // default index_type is FLAT
  {
    const char *input = "emb float[768]";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.index_type == VEC0_INDEX_TYPE_FLAT);
    sqlite3_free(col.name);
  }

  // Error: indexed by (missing type name)
  {
    const char *input = "emb float[768] indexed by";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_ERROR);
  }

  // Error: indexed by unknown()
  {
    const char *input = "emb float[768] indexed by unknown()";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_ERROR);
  }

  // Error: indexed by flat (missing parens)
  {
    const char *input = "emb float[768] indexed by flat";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_ERROR);
  }

  // Error: indexed flat() (missing "by")
  {
    const char *input = "emb float[768] indexed flat()";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_ERROR);
  }

  // Error: a prefix of a keyword, even when not strict
  {
    const char *input = "emb float[768] index by flat()";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, false);
    assert(rc == SQLITE_ERROR);
  }

  printf("  All vec0_parse_vector_column tests passed.\n");
}

// Tests vec0_parse_partition_key_definition(), which parses a vec0 partition
// key column definition like "user_id integer partition key". Verifies correct
// parsing of integer and text partition keys, column name extraction, and
// rejection of invalid inputs: empty strings, non-partition-key definitions
// ("primary key"), and misspelled keywords. Keyword prefixes and tokens after
// the definition are rejected only when creating the table (isCreate).
void test_vec0_parse_partition_key_definition() {
  printf("Starting %s...\n", __func__);
  typedef struct {
    char * test;
    bool isCreate;
    int expected_rc;
    const char *expected_column_name;
    int expected_column_type;
  } TestCase;

  TestCase suite[] = {
    {"user_id integer partition key", true, SQLITE_OK, "user_id", SQLITE_INTEGER},
    {"USER_id int partition key", true, SQLITE_OK, "USER_id", SQLITE_INTEGER},
    {"category text partition key", true, SQLITE_OK, "category", SQLITE_TEXT},
    {"category te partition ke", false, SQLITE_OK, "category", SQLITE_TEXT},
    {"category text partition key junk", false, SQLITE_OK, "category", SQLITE_TEXT},

    {"", true, SQLITE_EMPTY, "", 0},
    {"document_id text primary key", true, SQLITE_EMPTY, "", 0},
    {"document_id text partition keyy", true, SQLITE_EMPTY, "", 0},
    {"category te partition key", true, SQLITE_EMPTY, "", 0},
    {"category text partition ke", true, SQLITE_EMPTY, "", 0},
    {"category text partition key junk", true, SQLITE_EMPTY, "", 0},
  };
  for(int i = 0; i < countof(suite); i++) {
    char * out_column_name;
    int out_column_name_length;
    int out_column_type;
    int rc;
    rc = vec0_parse_partition_key_definition(
      suite[i].test,
      strlen(suite[i].test),
      &out_column_name,
      &out_column_name_length,
      &out_column_type,
      suite[i].isCreate
    );
    assert(rc == suite[i].expected_rc);

    if(rc == SQLITE_OK) {
      assert(out_column_name_length == strlen(suite[i].expected_column_name));
      assert(strncmp(out_column_name, suite[i].expected_column_name, out_column_name_length) == 0);
      assert(out_column_type == suite[i].expected_column_type);
    }

    printf("  Passed: \"%s\"\n", suite[i].test);
  }
}

// Runs a full scan of a 16-row, two-chunk vec0 table and, after `stopAt` rows,
// rolls back a transaction that changed the schema on the same connection. That
// rollback invalidates the scan's blob handle, which then answers
// SQLITE_ABORT_ROLLBACK when the connection has extended result codes on; the
// scan must replace the handle and return every row, as with them off.
static void fullscan_across_schema_rollback(int extendedCodes, int stopAt) {
  sqlite3 *db;
  sqlite3_stmt *stmt;
  int rc = sqlite3_open(":memory:", &db);
  assert(rc == SQLITE_OK);
  rc = sqlite3_vec_init(db, NULL, NULL);
  assert(rc == SQLITE_OK);
  sqlite3_extended_result_codes(db, extendedCodes);
  rc = sqlite3_exec(
      db, "create virtual table v using vec0(a float[2], chunk_size=8)", 0, 0,
      0);
  assert(rc == SQLITE_OK);
  for (int i = 1; i <= 16; i++) {
    char sql[64];
    snprintf(sql, sizeof sql, "insert into v(rowid, a) values (%d, '[%d, 0]')",
             i, i);
    rc = sqlite3_exec(db, sql, 0, 0, 0);
    assert(rc == SQLITE_OK);
  }
  rc = sqlite3_prepare_v2(db, "select rowid, a from v", -1, &stmt, 0);
  assert(rc == SQLITE_OK);
  int rows = 0;
  while ((rc = sqlite3_step(stmt)) == SQLITE_ROW) {
    rows++;
    assert(sqlite3_column_int64(stmt, 0) == rows);
    assert(((const float *)sqlite3_column_blob(stmt, 1))[0] == rows);
    if (rows == stopAt) {
      int rrc =
          sqlite3_exec(db, "begin; create table u(y); rollback;", 0, 0, 0);
      assert(rrc == SQLITE_OK);
    }
  }
  assert(rc == SQLITE_DONE);
  assert(rows == 16);
  sqlite3_finalize(stmt);
  sqlite3_close(db);
}

void test_vec0_fullscan_schema_rollback() {
  printf("Starting %s...\n", __func__);
  for (int extendedCodes = 0; extendedCodes <= 1; extendedCodes++) {
    // Mid-chunk the read fails; at a chunk's last row the next reopen does.
    fullscan_across_schema_rollback(extendedCodes, 3);
    fullscan_across_schema_rollback(extendedCodes, 8);
  }
}

#if SQLITE_VEC_ENABLE_RESCORE

void test_rescore_quantize_float_to_bit() {
  printf("Starting %s...\n", __func__);
  uint8_t dst[16];

  // All positive -> all bits 1
  {
    float src[8] = {1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f, 7.0f, 8.0f};
    memset(dst, 0, sizeof(dst));
    rescore_quantize_float_to_bit(src, dst, 8);
    assert(dst[0] == 0xFF);
  }

  // All negative -> all bits 0
  {
    float src[8] = {-1.0f, -2.0f, -3.0f, -4.0f, -5.0f, -6.0f, -7.0f, -8.0f};
    memset(dst, 0xFF, sizeof(dst));
    rescore_quantize_float_to_bit(src, dst, 8);
    assert(dst[0] == 0x00);
  }

  // Alternating positive/negative
  {
    float src[8] = {1.0f, -1.0f, 1.0f, -1.0f, 1.0f, -1.0f, 1.0f, -1.0f};
    rescore_quantize_float_to_bit(src, dst, 8);
    // bits 0,2,4,6 set => 0b01010101 = 0x55
    assert(dst[0] == 0x55);
  }

  // Zero values -> bit is set (>= 0.0f)
  {
    float src[8] = {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f};
    rescore_quantize_float_to_bit(src, dst, 8);
    assert(dst[0] == 0xFF);
  }

  // 128 dimensions -> 16 bytes output
  {
    float src[128];
    for (int i = 0; i < 128; i++)
      src[i] = (i % 2 == 0) ? 1.0f : -1.0f;
    memset(dst, 0, 16);
    rescore_quantize_float_to_bit(src, dst, 128);
    // Even indices set: bits 0,2,4,6 in each byte => 0x55
    for (int i = 0; i < 16; i++) {
      assert(dst[i] == 0x55);
    }
  }

  printf("  All rescore_quantize_float_to_bit tests passed.\n");
}

void test_rescore_quantize_float_to_int8() {
  printf("Starting %s...\n", __func__);
  int8_t dst[16];

  // [-1, 1] maps onto [-128, 127] in steps of 2/255, truncating toward zero.
  // 1.0 lands just below 127 in float arithmetic, so it truncates to 126.
  {
    float src[6] = {-1.0f, -0.5f, 0.0f, 0.5f, 1.0f, 1.004f};
    rescore_quantize_float_to_int8(src, dst, 6);
    assert(dst[0] == -128);
    assert(dst[1] == -64);
    assert(dst[2] == 0);
    assert(dst[3] == 63);
    assert(dst[4] == 126);
    assert(dst[5] == 127);
  }

  // Values outside [-1, 1] clamp, and NaN clamps to 127
  {
    float src[5] = {2.0f, -2.0f, INFINITY, -INFINITY, NAN};
    rescore_quantize_float_to_int8(src, dst, 5);
    assert(dst[0] == 127);
    assert(dst[1] == -128);
    assert(dst[2] == 127);
    assert(dst[3] == -128);
    assert(dst[4] == 127);
  }

  // The mapping never decreases
  {
    int8_t prev = -128;
    for (int i = 0; i <= 2200; i++) {
      float src = -1.1f + (float)i * 0.001f;
      int8_t out;
      rescore_quantize_float_to_int8(&src, &out, 1);
      assert(out >= prev);
      prev = out;
    }
  }

  printf("  All rescore_quantize_float_to_int8 tests passed.\n");
}

void test_rescore_quantized_byte_size() {
  printf("Starting %s...\n", __func__);
  struct VectorColumnDefinition col;
  memset(&col, 0, sizeof(col));

  // Bit quantizer: dims/8
  col.rescore.quantizer_type = VEC0_RESCORE_QUANTIZER_BIT;
  col.dimensions = 128;
  assert(rescore_quantized_byte_size(&col) == 16);
  col.dimensions = 8;
  assert(rescore_quantized_byte_size(&col) == 1);
  col.dimensions = 1024;
  assert(rescore_quantized_byte_size(&col) == 128);

  // Int8 quantizer: dims
  col.rescore.quantizer_type = VEC0_RESCORE_QUANTIZER_INT8;
  col.dimensions = 128;
  assert(rescore_quantized_byte_size(&col) == 128);
  col.dimensions = 8;
  assert(rescore_quantized_byte_size(&col) == 8);
  col.dimensions = 1024;
  assert(rescore_quantized_byte_size(&col) == 1024);

  printf("  All rescore_quantized_byte_size tests passed.\n");
}

void test_vec0_parse_vector_column_rescore() {
  printf("Starting %s...\n", __func__);
  struct VectorColumnDefinition col;
  int rc;

  // Basic bit quantizer
  {
    const char *input = "emb float[128] indexed by rescore(quantizer=bit)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.index_type == VEC0_INDEX_TYPE_RESCORE);
    assert(col.rescore.quantizer_type == VEC0_RESCORE_QUANTIZER_BIT);
    assert(col.rescore.oversample == 8); // default
    assert(col.rescore.oversample_search == 0);
    sqlite3_free(col.name);
  }

  // Int8 quantizer
  {
    const char *input = "emb float[128] indexed by rescore(quantizer=int8)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.index_type == VEC0_INDEX_TYPE_RESCORE);
    assert(col.rescore.quantizer_type == VEC0_RESCORE_QUANTIZER_INT8);
    sqlite3_free(col.name);
  }

  // Bit quantizer with oversample, in either order
  {
    const char *input =
        "emb float[128] indexed by rescore(quantizer=bit, oversample=16)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.index_type == VEC0_INDEX_TYPE_RESCORE);
    assert(col.rescore.quantizer_type == VEC0_RESCORE_QUANTIZER_BIT);
    assert(col.rescore.oversample == 16);
    sqlite3_free(col.name);
  }
  {
    const char *input =
        "emb float[128] indexed by rescore(oversample=128, quantizer=int8)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.rescore.quantizer_type == VEC0_RESCORE_QUANTIZER_INT8);
    assert(col.rescore.oversample == 128);
    sqlite3_free(col.name);
  }

  // With distance_metric=cosine
  {
    const char *input = "emb float[128] distance_metric=cosine indexed by "
                        "rescore(quantizer=int8)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.index_type == VEC0_INDEX_TYPE_RESCORE);
    assert(col.distance_metric == VEC0_DISTANCE_METRIC_COSINE);
    assert(col.rescore.quantizer_type == VEC0_RESCORE_QUANTIZER_INT8);
    sqlite3_free(col.name);
  }

  const char *errors[] = {
      // a non-float element type
      "emb int8[128] indexed by rescore(quantizer=bit)",
      "emb bit[128] indexed by rescore(quantizer=bit)",
      // dimensions not divisible by 8 for the bit quantizer
      "emb float[100] indexed by rescore(quantizer=bit)",
      // no quantizer
      "emb float[128] indexed by rescore(oversample=8)",
      "emb float[128] indexed by rescore()",
      "emb float[128] indexed by rescore",
      // an unknown quantizer or option
      "emb float[128] indexed by rescore(quantizer=float)",
      "emb float[128] indexed by rescore(quantizer=bit, k=8)",
      // oversample outside 1 to 128, or not an integer
      "emb float[128] indexed by rescore(quantizer=bit, oversample=0)",
      "emb float[128] indexed by rescore(quantizer=bit, oversample=129)",
      "emb float[128] indexed by rescore(quantizer=bit, oversample=bit)",
      // malformed options
      "emb float[128] indexed by rescore(quantizer=bit",
      "emb float[128] indexed by rescore(quantizer=bit,)",
      "emb float[128] indexed by rescore(quantizer bit)",
      "emb float[128] indexed by rescore(quantizer=bit oversample=8)",
  };
  for (size_t i = 0; i < countof(errors); i++) {
    rc = vec0_parse_vector_column(errors[i], (int)strlen(errors[i]), &col,
                                  true);
    assert(rc == SQLITE_ERROR);
  }

  // Error: a prefix of a keyword, even when not strict
  {
    const char *input = "emb float[128] indexed by rescor(quantizer=bit)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, false);
    assert(rc == SQLITE_ERROR);
  }
  {
    const char *input = "emb float[128] indexed by rescore(quant=bit)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, false);
    assert(rc == SQLITE_ERROR);
  }

  printf("  All vec0_parse_vector_column_rescore tests passed.\n");
}

#endif /* SQLITE_VEC_ENABLE_RESCORE */

#if SQLITE_VEC_ENABLE_DISKANN

void test_vec0_parse_vector_column_diskann() {
  printf("Starting %s...\n", __func__);
  struct VectorColumnDefinition col;
  int rc;

  // No INDEXED BY: not DiskANN
  {
    const char *input = "emb float[128]";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.index_type != VEC0_INDEX_TYPE_DISKANN);
    sqlite3_free(col.name);
  }

  // With distance_metric but no INDEXED BY
  {
    const char *input = "emb float[128] distance_metric=cosine";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.index_type != VEC0_INDEX_TYPE_DISKANN);
    assert(col.distance_metric == VEC0_DISTANCE_METRIC_COSINE);
    sqlite3_free(col.name);
  }

  // Binary quantizer, with every default
  {
    const char *input =
        "emb float[128] INDEXED BY diskann(neighbor_quantizer=binary)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.index_type == VEC0_INDEX_TYPE_DISKANN);
    assert(col.diskann.quantizer_type == VEC0_DISKANN_QUANTIZER_BINARY);
    assert(col.diskann.n_neighbors == 72);
    assert(col.diskann.search_list_size == 128);
    assert(col.diskann.search_list_size_search == 0);
    assert(col.diskann.search_list_size_insert == 0);
    assert(col.diskann.buffer_threshold == 0);
    assert(col.dimensions == 128);
    sqlite3_free(col.name);
  }

  // Int8 quantizer
  {
    const char *input =
        "v float[64] INDEXED BY diskann(neighbor_quantizer=int8)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.index_type == VEC0_INDEX_TYPE_DISKANN);
    assert(col.diskann.quantizer_type == VEC0_DISKANN_QUANTIZER_INT8);
    sqlite3_free(col.name);
  }

  // Custom n_neighbors, search_list_size and buffer_threshold
  {
    const char *input = "emb float[128] INDEXED BY "
                        "diskann(neighbor_quantizer=binary, n_neighbors=48, "
                        "search_list_size=256, buffer_threshold=100)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.diskann.n_neighbors == 48);
    assert(col.diskann.search_list_size == 256);
    assert(col.diskann.buffer_threshold == 100);
    sqlite3_free(col.name);
  }

  // Combined with distance_metric (distance_metric first)
  {
    const char *input = "emb float[128] distance_metric=cosine INDEXED BY "
                        "diskann(neighbor_quantizer=int8)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.distance_metric == VEC0_DISTANCE_METRIC_COSINE);
    assert(col.index_type == VEC0_INDEX_TYPE_DISKANN);
    assert(col.diskann.quantizer_type == VEC0_DISKANN_QUANTIZER_INT8);
    sqlite3_free(col.name);
  }

  // Keywords in any case
  {
    const char *input =
        "emb float[128] indexed by DISKANN(NEIGHBOR_QUANTIZER=BINARY)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.index_type == VEC0_INDEX_TYPE_DISKANN);
    assert(col.diskann.quantizer_type == VEC0_DISKANN_QUANTIZER_BINARY);
    sqlite3_free(col.name);
  }

  // Split search_list_size: search and insert
  {
    const char *input =
        "emb float[128] INDEXED BY diskann(neighbor_quantizer=binary, "
        "search_list_size_search=256, search_list_size_insert=64)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.diskann.search_list_size == 128);
    assert(col.diskann.search_list_size_search == 256);
    assert(col.diskann.search_list_size_insert == 64);
    sqlite3_free(col.name);
  }

  // Split search_list_size: only search
  {
    const char *input = "emb float[128] INDEXED BY "
                        "diskann(neighbor_quantizer=binary, "
                        "search_list_size_search=200)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.diskann.search_list_size_search == 200);
    assert(col.diskann.search_list_size_insert == 0);
    sqlite3_free(col.name);
  }

  const char *errors[] = {
      // neighbor_quantizer is required
      "emb float[128] INDEXED BY diskann(n_neighbors=72)",
      "emb float[128] INDEXED BY diskann()",
      "emb float[128] INDEXED BY diskann(neighbor_quantizer=unknown)",
      // n_neighbors: a multiple of 8 from 8 to 256
      "emb float[128] INDEXED BY diskann(neighbor_quantizer=binary, "
      "n_neighbors=13)",
      "emb float[128] INDEXED BY diskann(neighbor_quantizer=binary, "
      "n_neighbors=512)",
      "emb float[128] INDEXED BY diskann(neighbor_quantizer=binary, "
      "n_neighbors=0)",
      "emb float[128] INDEXED diskann(neighbor_quantizer=binary)",
      "emb float[128] INDEXED BY hnsw(neighbor_quantizer=binary)",
      "emb float[128] INDEXED BY diskann(neighbor_quantizer=binary, "
      "foobar=baz)",
      // search_list_size beside either of the split sizes
      "emb float[128] INDEXED BY diskann(neighbor_quantizer=binary, "
      "search_list_size=128, search_list_size_search=256)",
      "emb float[128] INDEXED BY diskann(neighbor_quantizer=binary, "
      "search_list_size=128, search_list_size_insert=64)",
      // whole keywords and values, all digits, no trailing comma
      "emb float[128] INDEXED BY diskann(neighbor_quantizer=bin)",
      "emb float[128] INDEXED BY diskann(neighbor_quant=binary)",
      "emb float[128] INDEXED BY diskann(neighbor_quantizer=binary, n=16)",
      "emb float[128] INDEXED BY diskann(neighbor_quantizer=binary, "
      "search_list_size=12x)",
      "emb float[128] INDEXED BY diskann(neighbor_quantizer=binary,)",
      "emb float[128] INDEXED BY diskann(neighbor_quantizer=binary, "
      "buffer_threshold=99999999999)",
  };
  for (size_t i = 0; i < countof(errors); i++) {
    rc = vec0_parse_vector_column(errors[i], (int)strlen(errors[i]), &col,
                                  true);
    assert(rc == SQLITE_ERROR);
  }

  printf("  All vec0_parse_vector_column_diskann tests passed.\n");
}

void test_diskann_validity_bitmap() {
  printf("Starting %s...\n", __func__);

  unsigned char validity[3]; // 24 bits
  memset(validity, 0, sizeof(validity));

  for (int i = 0; i < 24; i++) {
    assert(diskann_validity_get(validity, i) == 0);
  }
  assert(diskann_validity_count(validity, 24) == 0);

  diskann_validity_set(validity, 0, 1);
  assert(diskann_validity_get(validity, 0) == 1);
  assert(diskann_validity_count(validity, 24) == 1);

  // the last bit of the first byte and the first of the second
  diskann_validity_set(validity, 7, 1);
  diskann_validity_set(validity, 8, 1);
  assert(diskann_validity_get(validity, 7) == 1);
  assert(diskann_validity_get(validity, 8) == 1);
  assert(diskann_validity_count(validity, 24) == 3);

  diskann_validity_set(validity, 23, 1);
  assert(diskann_validity_get(validity, 23) == 1);
  assert(diskann_validity_count(validity, 24) == 4);

  diskann_validity_set(validity, 0, 0);
  assert(diskann_validity_get(validity, 0) == 0);
  assert(diskann_validity_count(validity, 24) == 3);
  assert(diskann_validity_get(validity, 7) == 1);
  assert(diskann_validity_get(validity, 8) == 1);

  printf("  All diskann_validity_bitmap tests passed.\n");
}

void test_diskann_neighbor_ids() {
  printf("Starting %s...\n", __func__);

  unsigned char ids[8 * 8]; // 8 slots of 8 bytes
  memset(ids, 0, sizeof(ids));

  diskann_neighbor_id_set(ids, 0, 42);
  diskann_neighbor_id_set(ids, 3, 12345);
  diskann_neighbor_id_set(ids, 7, 99999);
  diskann_neighbor_id_set(ids, 1, INT64_MAX);
  diskann_neighbor_id_set(ids, 2, -7);
  assert(diskann_neighbor_id_get(ids, 0) == 42);
  assert(diskann_neighbor_id_get(ids, 3) == 12345);
  assert(diskann_neighbor_id_get(ids, 7) == 99999);
  assert(diskann_neighbor_id_get(ids, 1) == INT64_MAX);
  assert(diskann_neighbor_id_get(ids, 2) == -7);

  printf("  All diskann_neighbor_ids tests passed.\n");
}

void test_diskann_quantize_binary() {
  printf("Starting %s...\n", __func__);

  // a bit per dimension, LSB first, set when the value is > 0
  {
    float src[8] = {1.0f, -1.0f, 0.5f, 0.0f, -0.5f, 0.1f, -0.1f, 100.0f};
    unsigned char out[1];
    assert(diskann_quantize_vector(src, 8, VEC0_DISKANN_QUANTIZER_BINARY,
                                   out) == SQLITE_OK);
    assert(out[0] == 0xA5);
  }
  {
    float src[16] = {1.0f,  -1.0f, 0.5f, -0.5f, 0.1f,  -0.1f, 0.0f, 100.0f,
                     -1.0f, 1.0f,  1.0f, 1.0f,  -1.0f, -1.0f, 1.0f, -1.0f};
    unsigned char out[2];
    assert(diskann_quantize_vector(src, 16, VEC0_DISKANN_QUANTIZER_BINARY,
                                   out) == SQLITE_OK);
    assert(out[0] == 0x95);
    assert(out[1] == 0x4E);
  }
  {
    float src[8] = {1.0f, 2.0f, 0.1f, 0.001f, 100.0f, 42.0f, 0.5f, 3.14f};
    unsigned char out[1];
    diskann_quantize_vector(src, 8, VEC0_DISKANN_QUANTIZER_BINARY, out);
    assert(out[0] == 0xFF);
  }
  {
    float src[8] = {-1.0f, -2.0f, -0.1f, -0.001f, -100.0f, -42.0f, -0.5f, 0.0f};
    unsigned char out[1];
    diskann_quantize_vector(src, 8, VEC0_DISKANN_QUANTIZER_BINARY, out);
    assert(out[0] == 0x00);
  }

  printf("  All diskann_quantize_binary tests passed.\n");
}

void test_diskann_quantize_int8() {
  printf("Starting %s...\n", __func__);

  // [-1, 1] maps onto [-128, 127] in steps of 2/255, truncating toward zero.
  // 1.0 lands just below 127 in float arithmetic, so it truncates to 126.
  {
    float src[6] = {-1.0f, -0.5f, 0.0f, 0.5f, 1.0f, 1.004f};
    unsigned char out[6];
    assert(diskann_quantize_vector(src, 6, VEC0_DISKANN_QUANTIZER_INT8, out) ==
           SQLITE_OK);
    int8_t *q = (int8_t *)out;
    assert(q[0] == -128);
    assert(q[1] == -64);
    assert(q[2] == 0);
    assert(q[3] == 63);
    assert(q[4] == 126);
    assert(q[5] == 127);
  }
  // values outside [-1, 1] clamp, and NaN clamps to 127
  {
    float src[5] = {2.0f, -2.0f, INFINITY, -INFINITY, NAN};
    unsigned char out[5];
    diskann_quantize_vector(src, 5, VEC0_DISKANN_QUANTIZER_INT8, out);
    int8_t *q = (int8_t *)out;
    assert(q[0] == 127);
    assert(q[1] == -128);
    assert(q[2] == 127);
    assert(q[3] == -128);
    assert(q[4] == 127);
  }
  // the mapping never decreases
  {
    int8_t prev = -128;
    for (int i = 0; i <= 2200; i++) {
      float src = -1.1f + (float)i * 0.001f;
      unsigned char out;
      diskann_quantize_vector(&src, 1, VEC0_DISKANN_QUANTIZER_INT8, &out);
      assert((int8_t)out >= prev);
      prev = (int8_t)out;
    }
  }

  printf("  All diskann_quantize_int8 tests passed.\n");
}

void test_diskann_node_init_sizes() {
  printf("Starting %s...\n", __func__);

  unsigned char *validity, *ids, *qvecs;
  int validitySize, idsSize, qvecsSize;

  int rc = diskann_node_init(72, VEC0_DISKANN_QUANTIZER_BINARY, 1024,
                             &validity, &validitySize, &ids, &idsSize, &qvecs,
                             &qvecsSize);
  assert(rc == SQLITE_OK);
  assert(validitySize == 9);  // 72 / 8
  assert(idsSize == 576);     // 72 * 8
  assert(qvecsSize == 9216);  // 72 * 1024 / 8
  assert(diskann_validity_count(validity, 72) == 0);
  sqlite3_free(validity);
  sqlite3_free(ids);
  sqlite3_free(qvecs);

  rc = diskann_node_init(8, VEC0_DISKANN_QUANTIZER_INT8, 32, &validity,
                         &validitySize, &ids, &idsSize, &qvecs, &qvecsSize);
  assert(rc == SQLITE_OK);
  assert(validitySize == 1);
  assert(idsSize == 64);
  assert(qvecsSize == 256);
  sqlite3_free(validity);
  sqlite3_free(ids);
  sqlite3_free(qvecs);

  assert(diskann_quantized_vector_byte_size(VEC0_DISKANN_QUANTIZER_BINARY,
                                            128) == 16);
  assert(diskann_quantized_vector_byte_size(VEC0_DISKANN_QUANTIZER_BINARY,
                                            8) == 1);
  assert(diskann_quantized_vector_byte_size(VEC0_DISKANN_QUANTIZER_INT8,
                                            768) == 768);
  assert(diskann_neighbor_ids_byte_size(72) == 576);
  assert(diskann_neighbor_qvecs_byte_size(8, VEC0_DISKANN_QUANTIZER_INT8,
                                          32) == 256);

  printf("  All diskann_node_init_sizes tests passed.\n");
}

void test_diskann_node_set_clear_neighbor() {
  printf("Starting %s...\n", __func__);

  unsigned char *validity, *ids, *qvecs;
  int validitySize, idsSize, qvecsSize;
  int rc = diskann_node_init(8, VEC0_DISKANN_QUANTIZER_BINARY, 16, &validity,
                             &validitySize, &ids, &idsSize, &qvecs,
                             &qvecsSize);
  assert(rc == SQLITE_OK);

  unsigned char test_qvec[2] = {0xAB, 0xCD};
  diskann_node_set_neighbor(validity, ids, qvecs, 3, 42, test_qvec,
                            VEC0_DISKANN_QUANTIZER_BINARY, 16);
  assert(diskann_validity_get(validity, 3) == 1);
  assert(diskann_validity_count(validity, 8) == 1);
  assert(diskann_neighbor_id_get(ids, 3) == 42);
  const unsigned char *read_qvec =
      diskann_neighbor_qvec_get(qvecs, 3, VEC0_DISKANN_QUANTIZER_BINARY, 16);
  assert(read_qvec[0] == 0xAB);
  assert(read_qvec[1] == 0xCD);

  diskann_node_clear_neighbor(validity, ids, qvecs, 3,
                              VEC0_DISKANN_QUANTIZER_BINARY, 16);
  assert(diskann_validity_get(validity, 3) == 0);
  assert(diskann_neighbor_id_get(ids, 3) == 0);
  assert(read_qvec[0] == 0 && read_qvec[1] == 0);
  assert(diskann_validity_count(validity, 8) == 0);

  sqlite3_free(validity);
  sqlite3_free(ids);
  sqlite3_free(qvecs);

  printf("  All diskann_node_set_clear_neighbor tests passed.\n");
}

static float test_prune_matrix_distance(void *ctx, int a, int b) {
  return ((const float *)ctx)[a * 5 + b];
}

void test_diskann_prune_select() {
  printf("Starting %s...\n", __func__);

  // Five candidates in order of their distances to the node, A=1 to E=5, and
  // the distances between them:
  //       A     B     C     D     E
  // A   0.0   1.5   3.0   4.0   5.0
  // B   1.5   0.0   1.5   3.0   4.0
  // C   3.0   1.5   0.0   1.5   3.0
  // D   4.0   3.0   1.5   0.0   1.5
  // E   5.0   4.0   3.0   1.5   0.0
  float p_distances[5] = {1.0f, 2.0f, 3.0f, 4.0f, 5.0f};
  float inter[25] = {
      0.0f, 1.5f, 3.0f, 4.0f, 5.0f, 1.5f, 0.0f, 1.5f, 3.0f,
      4.0f, 3.0f, 1.5f, 0.0f, 1.5f, 3.0f, 4.0f, 3.0f, 1.5f,
      0.0f, 1.5f, 5.0f, 4.0f, 3.0f, 1.5f, 0.0f,
  };
  int selected[5];
  int count;

  // alpha=1: A covers every other candidate
  {
    int rc = diskann_prune_select(p_distances, 5, 1.0f, 3,
                                  test_prune_matrix_distance, inter, selected,
                                  &count);
    assert(rc == SQLITE_OK);
    assert(count == 1);
    assert(selected[0] == 1);
  }

  // alpha=1.5: A covers none; B covers C; D is the third
  {
    int rc = diskann_prune_select(p_distances, 5, 1.5f, 3,
                                  test_prune_matrix_distance, inter, selected,
                                  &count);
    assert(rc == SQLITE_OK);
    assert(count == 3);
    assert(selected[0] == 1);
    assert(selected[1] == 1);
    assert(selected[2] == 0);
    assert(selected[3] == 1);
    assert(selected[4] == 0);
  }

  // a large alpha covers nothing, and every candidate fits
  {
    int rc = diskann_prune_select(p_distances, 5, 100.0f, 10,
                                  test_prune_matrix_distance, inter, selected,
                                  &count);
    assert(rc == SQLITE_OK);
    assert(count == 5);
  }

  // no candidate
  {
    int rc = diskann_prune_select(NULL, 0, 1.2f, 3, test_prune_matrix_distance,
                                  inter, selected, &count);
    assert(rc == SQLITE_OK);
    assert(count == 0);
  }

  printf("  All diskann_prune_select tests passed.\n");
}

void test_diskann_config_defaults() {
  printf("Starting %s...\n", __func__);

  struct VectorColumnDefinition col;
  memset(&col, 0, sizeof(col));
  assert(col.index_type != VEC0_INDEX_TYPE_DISKANN);
  assert(col.diskann.n_neighbors == 0);
  assert(col.diskann.search_list_size == 0);

  const char *input = "embedding float[768]";
  int rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
  assert(rc == SQLITE_OK);
  assert(col.index_type != VEC0_INDEX_TYPE_DISKANN);
  sqlite3_free(col.name);

  printf("  All diskann_config_defaults tests passed.\n");
}

void test_diskann_candidate_list_operations() {
  printf("Starting %s...\n", __func__);

  struct DiskannCandidateList list;
  int rc = diskann_candidate_list_init(&list, 5);
  assert(rc == SQLITE_OK);

  diskann_candidate_list_insert(&list, 10, 3.0f);
  diskann_candidate_list_insert(&list, 20, 1.0f);
  diskann_candidate_list_insert(&list, 30, 2.0f);
  assert(list.count == 3);
  assert(list.items[0].rowid == 20 && list.items[0].distance == 1.0f);
  assert(list.items[1].rowid == 30 && list.items[1].distance == 2.0f);
  assert(list.items[2].rowid == 10 && list.items[2].distance == 3.0f);

  // a rowid already held moves up to a nearer distance
  diskann_candidate_list_insert(&list, 10, 0.5f);
  assert(list.count == 3);
  assert(list.items[0].rowid == 10 && list.items[0].distance == 0.5f);
  // and keeps its place for a farther one
  diskann_candidate_list_insert(&list, 10, 9.0f);
  assert(list.items[0].rowid == 10 && list.items[0].distance == 0.5f);

  assert(diskann_candidate_list_next_unvisited(&list) == 0);
  list.items[0].visited = 1;
  assert(diskann_candidate_list_next_unvisited(&list) == 1);

  // at capacity a farther candidate is ignored, a nearer one drops the
  // farthest
  diskann_candidate_list_insert(&list, 40, 4.0f);
  diskann_candidate_list_insert(&list, 50, 5.0f);
  assert(list.count == 5);
  assert(diskann_candidate_list_insert(&list, 60, 10.0f) == 0);
  assert(list.count == 5);
  assert(diskann_candidate_list_insert(&list, 60, 3.5f) == 1);
  assert(list.count == 5);
  assert(list.items[4].rowid == 40);

  // re-ranking by an exact distance moves a candidate either way
  // (list: 10 0.5, 20 1.0, 30 2.0, 60 3.5, 40 4.0)
  int at = diskann_candidate_list_rerank(&list, 0, 3.0f);
  assert(at == 2);
  assert(list.items[2].rowid == 10 && list.items[2].visited == 1);
  assert(list.items[0].rowid == 20 && list.items[1].rowid == 30);
  at = diskann_candidate_list_rerank(&list, 4, 0.1f);
  assert(at == 0);
  assert(list.items[0].rowid == 40);
  for (int i = 1; i < list.count; i++) {
    assert(list.items[i - 1].distance <= list.items[i].distance);
  }

  diskann_candidate_list_free(&list);

  printf("  All diskann_candidate_list_operations tests passed.\n");
}

void test_diskann_visited_set_operations() {
  printf("Starting %s...\n", __func__);

  struct DiskannVisitedSet set;
  int rc = diskann_visited_set_init(&set, 32);
  assert(rc == SQLITE_OK);
  int added;

  assert(diskann_visited_set_contains(&set, 1) == 0);
  assert(diskann_visited_set_insert(&set, 42, &added) == SQLITE_OK);
  assert(added == 1);
  assert(diskann_visited_set_contains(&set, 42) == 1);
  assert(diskann_visited_set_contains(&set, 43) == 0);
  diskann_visited_set_insert(&set, 42, &added);
  assert(added == 0);

  // rowid 0 is a rowid like any other
  assert(diskann_visited_set_contains(&set, 0) == 0);
  diskann_visited_set_insert(&set, 0, &added);
  assert(added == 1);
  assert(diskann_visited_set_contains(&set, 0) == 1);
  diskann_visited_set_insert(&set, 0, &added);
  assert(added == 0);

  // far past its starting capacity it holds every rowid, negative ones too
  for (long long r = -500; r <= 500; r++) {
    assert(diskann_visited_set_insert(&set, r * 7919, &added) == SQLITE_OK);
  }
  assert(set.capacity > 1001 * 2);
  for (long long r = -500; r <= 500; r++) {
    assert(diskann_visited_set_contains(&set, r * 7919) == 1);
    assert(diskann_visited_set_contains(&set, r * 7919 + 1) == (r * 7919 + 1 == 42));
  }

  diskann_visited_set_free(&set);

  printf("  All diskann_visited_set_operations tests passed.\n");
}

#endif /* SQLITE_VEC_ENABLE_DISKANN */

#if SQLITE_VEC_EXPERIMENTAL_IVF_ENABLE

void test_vec0_parse_vector_column_ivf() {
  printf("Starting %s...\n", __func__);
  struct VectorColumnDefinition col;
  int rc;

  // Every default
  {
    const char *input = "v float[4] indexed by ivf()";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.index_type == VEC0_INDEX_TYPE_IVF);
    assert(col.dimensions == 4);
    assert(col.ivf.nlist == 128);
    assert(col.ivf.nprobe == 10);
    assert(col.ivf.quantizer == VEC0_IVF_QUANTIZER_NONE);
    assert(col.ivf.oversample == 1);
    sqlite3_free(col.name);
  }

  // nprobe defaults to at most nlist
  {
    const char *input = "v float[4] indexed by ivf(nlist=8)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.ivf.nlist == 8);
    assert(col.ivf.nprobe == 8);
    sqlite3_free(col.name);
  }

  {
    const char *input = "v float[4] indexed by ivf(nlist=64, nprobe=8)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.ivf.nlist == 64);
    assert(col.ivf.nprobe == 8);
    sqlite3_free(col.name);
  }

  // distance_metric before indexed by
  {
    const char *input =
        "v float[4] distance_metric=cosine indexed by ivf(nlist=16)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.index_type == VEC0_INDEX_TYPE_IVF);
    assert(col.distance_metric == VEC0_DISTANCE_METRIC_COSINE);
    assert(col.ivf.nlist == 16);
    sqlite3_free(col.name);
  }

  // nlist=0 leaves the centroids to set-centroid
  {
    const char *input = "v float[4] indexed by ivf(nlist=0)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.ivf.nlist == 0);
    sqlite3_free(col.name);
  }

  // nlist at its maximum
  {
    const char *input = "v float[4] indexed by ivf(nlist=65536)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.ivf.nlist == 65536);
    sqlite3_free(col.name);
  }

  // Quantizers
  {
    const char *input =
        "v float[768] indexed by ivf(nlist=128, quantizer=binary)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.ivf.nlist == 128);
    assert(col.ivf.quantizer == VEC0_IVF_QUANTIZER_BINARY);
    assert(col.ivf.oversample == 1);
    sqlite3_free(col.name);
  }

  {
    const char *input = "v float[768] indexed by ivf(nlist=64, quantizer=int8)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.ivf.quantizer == VEC0_IVF_QUANTIZER_INT8);
    sqlite3_free(col.name);
  }

  {
    const char *input = "v float[768] indexed by ivf(quantizer=none)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.ivf.quantizer == VEC0_IVF_QUANTIZER_NONE);
    sqlite3_free(col.name);
  }

  // oversample with a quantizer
  {
    const char *input = "v float[768] indexed by ivf(nlist=128, "
                        "quantizer=binary, oversample=10)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.ivf.quantizer == VEC0_IVF_QUANTIZER_BINARY);
    assert(col.ivf.oversample == 10);
    assert(col.ivf.nlist == 128);
    sqlite3_free(col.name);
  }

  // Every option, keywords in any case
  {
    const char *input = "v float[768] distance_metric=cosine INDEXED BY "
                        "IVF(NLIST=256, NPROBE=16, QUANTIZER=INT8, "
                        "OVERSAMPLE=4)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.distance_metric == VEC0_DISTANCE_METRIC_COSINE);
    assert(col.ivf.nlist == 256);
    assert(col.ivf.nprobe == 16);
    assert(col.ivf.quantizer == VEC0_IVF_QUANTIZER_INT8);
    assert(col.ivf.oversample == 4);
    sqlite3_free(col.name);
  }

  {
    const char *input =
        "v float[768] indexed by ivf(quantizer=binary, oversample=5)";
    rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
    assert(rc == SQLITE_OK);
    assert(col.ivf.nlist == 128);
    assert(col.ivf.nprobe == 10);
    assert(col.ivf.quantizer == VEC0_IVF_QUANTIZER_BINARY);
    assert(col.ivf.oversample == 5);
    sqlite3_free(col.name);
  }

  const char *errors[] = {
      // an explicit nprobe past nlist
      "v float[4] indexed by ivf(nlist=4, nprobe=10)",
      "v float[4] indexed by ivf(bogus=1)",
      "v float[4] indexed by hnsw()",
      "v float[4] indexed by ivf(nlist=65537)",
      "v float[4] indexed by ivf(nlist=-1)",
      "v float[4] indexed by ivf(nprobe=0)",
      // oversample only ranks a quantizer's candidates
      "v float[768] indexed by ivf(oversample=10)",
      "v float[768] indexed by ivf(quantizer=binary, oversample=0)",
      "v float[768] indexed by ivf(quantizer=pq)",
      // the binary quantizer packs 8 dimensions to a byte
      "v float[12] indexed by ivf(quantizer=binary)",
      // only float32 columns
      "v int8[8] indexed by ivf()",
      "v bit[8] indexed by ivf()",
      // whole keywords and values, all digits, no trailing comma
      "v float[8] indexed by ivf(quantizer=bin)",
      "v float[8] indexed by ivf(nli=8)",
      "v float[8] indexed by ivf(nlist=8x)",
      "v float[8] indexed by ivf(nlist=8,)",
      "v float[8] indexed by ivf(quantizer=int8, oversample=99999999999)",
      "v float[8] indexed by ivf",
      "v float[8] indexed by ivf(",
  };
  for (size_t i = 0; i < countof(errors); i++) {
    rc = vec0_parse_vector_column(errors[i], (int)strlen(errors[i]), &col,
                                  true);
    assert(rc == SQLITE_ERROR);
  }

  printf("  All vec0_parse_vector_column_ivf tests passed.\n");
}

void test_ivf_quantize_int8() {
  printf("Starting %s...\n", __func__);

  // Values in [-1, 1] scale to [-127, 127], truncating toward zero
  {
    float src[] = {0.0f, 1.0f, -1.0f, 0.5f};
    int8_t dst[4];
    ivf_quantize_int8(src, dst, 4);
    assert(dst[0] == 0);
    assert(dst[1] == 127);
    assert(dst[2] == -127);
    assert(dst[3] == 63);
  }

  // Values past [-1, 1] clamp, and NaN is 127
  {
    float src[] = {2.0f, -3.0f, 100.0f, -0.01f, NAN, INFINITY, -INFINITY};
    int8_t dst[7];
    ivf_quantize_int8(src, dst, 7);
    assert(dst[0] == 127);
    assert(dst[1] == -127);
    assert(dst[2] == 127);
    assert(dst[3] == (int8_t)(-0.01f * 127.0f));
    assert(dst[4] == 127);
    assert(dst[5] == 127);
    assert(dst[6] == -127);
  }

  {
    float src[] = {0.0f, -0.0f, 0.75f};
    int8_t dst[3];
    ivf_quantize_int8(src, dst, 3);
    assert(dst[0] == 0);
    assert(dst[1] == 0);
    assert(dst[2] == (int8_t)(0.75f * 127.0f));
  }

  printf("  All ivf_quantize_int8 tests passed.\n");
}

void test_ivf_quantize_binary() {
  printf("Starting %s...\n", __func__);

  // A value above 0 sets its bit, the first value in the lowest bit
  {
    float src[] = {1.0f, -1.0f, 0.5f, -0.5f, 0.0f, 0.1f, -0.1f, 2.0f};
    uint8_t dst[1];
    ivf_quantize_binary(src, dst, 8);
    assert(dst[0] == 0xA5);
  }

  {
    float src[] = {1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f, 7.0f, 8.0f};
    uint8_t dst[1];
    ivf_quantize_binary(src, dst, 8);
    assert(dst[0] == 0xFF);
  }

  {
    float src[] = {-1.0f, -2.0f, 0.0f, -0.0f, -5.0f, -6.0f, -7.0f, NAN};
    uint8_t dst[1] = {0xFF};
    ivf_quantize_binary(src, dst, 8);
    assert(dst[0] == 0x00);
  }

  {
    float src[16];
    for (int i = 0; i < 16; i++) {
      src[i] = (i % 2 == 0) ? 1.0f : -1.0f;
    }
    uint8_t dst[2];
    ivf_quantize_binary(src, dst, 16);
    assert(dst[0] == 0x55);
    assert(dst[1] == 0x55);
  }

  printf("  All ivf_quantize_binary tests passed.\n");
}

void test_ivf_kmeans() {
  printf("Starting %s...\n", __func__);

  // Three clusters of 2-dimensional points around (0, 0), (10, 0), (0, 10)
  float vectors[30 * 2];
  for (int i = 0; i < 30; i++) {
    float offset = (float)(i % 10) / 10.0f;
    vectors[i * 2] = (i / 10 == 1 ? 10.0f : 0.0f) + offset;
    vectors[i * 2 + 1] = (i / 10 == 2 ? 10.0f : 0.0f) - offset;
  }

  float centroids[3 * 2];
  assert(ivf_kmeans(vectors, 30, 2, 3, 25, 0, centroids) == SQLITE_OK);
  int found[3] = {0, 0, 0};
  for (int c = 0; c < 3; c++) {
    float x = centroids[c * 2], y = centroids[c * 2 + 1];
    // each cluster's mean is its corner moved by (0.45, -0.45)
    if (fabsf(x - 0.45f) < 1e-4 && fabsf(y + 0.45f) < 1e-4) {
      found[0]++;
    } else if (fabsf(x - 10.45f) < 1e-4 && fabsf(y + 0.45f) < 1e-4) {
      found[1]++;
    } else if (fabsf(x - 0.45f) < 1e-4 && fabsf(y - 9.55f) < 1e-4) {
      found[2]++;
    }
  }
  assert(found[0] == 1 && found[1] == 1 && found[2] == 1);

  // The same seed gives the same centroids
  {
    float a[3 * 2], b[3 * 2];
    assert(ivf_kmeans(vectors, 30, 2, 3, 25, 7, a) == SQLITE_OK);
    assert(ivf_kmeans(vectors, 30, 2, 3, 25, 7, b) == SQLITE_OK);
    assert(memcmp(a, b, sizeof(a)) == 0);
  }

  // As many centroids as vectors: each vector is one
  {
    float few[3 * 2] = {1.0f, 1.0f, 5.0f, 5.0f, 9.0f, 9.0f};
    float out[3 * 2];
    assert(ivf_kmeans(few, 3, 2, 3, 25, 0, out) == SQLITE_OK);
    for (int v = 0; v < 3; v++) {
      int matches = 0;
      for (int c = 0; c < 3; c++) {
        matches += out[c * 2] == few[v * 2] && out[c * 2 + 1] == few[v * 2 + 1];
      }
      assert(matches == 1);
    }
  }

  // More centroids than vectors, or none
  assert(ivf_kmeans(vectors, 2, 2, 3, 25, 0, centroids) == SQLITE_MISUSE);
  assert(ivf_kmeans(vectors, 30, 2, 0, 25, 0, centroids) == SQLITE_MISUSE);
  assert(ivf_kmeans(vectors, 0, 2, 1, 25, 0, centroids) == SQLITE_MISUSE);

  printf("  All ivf_kmeans tests passed.\n");
}

#else

void test_vec0_parse_vector_column_ivf() {
  printf("Starting %s...\n", __func__);
  struct VectorColumnDefinition col;
  // a build without the IVF index has no ivf() to parse
  const char *input = "v float[4] indexed by ivf()";
  int rc = vec0_parse_vector_column(input, (int)strlen(input), &col, true);
  assert(rc == SQLITE_ERROR);
  printf("  All vec0_parse_vector_column_ivf tests passed.\n");
}

#endif /* SQLITE_VEC_EXPERIMENTAL_IVF_ENABLE */

int main() {
  printf("Starting unit tests...\n");
  test_vec0_token_next();
  test_vec0_scanner();
  test_vec0_parse_vector_column();
  test_vec0_parse_partition_key_definition();
  test_vec0_fullscan_schema_rollback();
#if SQLITE_VEC_ENABLE_RESCORE
  test_rescore_quantize_float_to_bit();
  test_rescore_quantize_float_to_int8();
  test_rescore_quantized_byte_size();
  test_vec0_parse_vector_column_rescore();
#endif
#if SQLITE_VEC_ENABLE_DISKANN
  test_vec0_parse_vector_column_diskann();
  test_diskann_validity_bitmap();
  test_diskann_neighbor_ids();
  test_diskann_quantize_binary();
  test_diskann_quantize_int8();
  test_diskann_node_init_sizes();
  test_diskann_node_set_clear_neighbor();
  test_diskann_prune_select();
  test_diskann_config_defaults();
  test_diskann_candidate_list_operations();
  test_diskann_visited_set_operations();
#endif
  test_vec0_parse_vector_column_ivf();
#if SQLITE_VEC_EXPERIMENTAL_IVF_ENABLE
  test_ivf_quantize_int8();
  test_ivf_quantize_binary();
  test_ivf_kmeans();
#endif
  printf("All unit tests passed.\n");
}
