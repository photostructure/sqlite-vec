#ifndef SQLITE_VEC_H
#define SQLITE_VEC_H

#ifndef SQLITE_CORE
#include "sqlite3ext.h"
#else
#include "sqlite3.h"
#endif

#ifdef SQLITE_VEC_STATIC
  #define SQLITE_VEC_API __attribute__((visibility("default")))
#else
  #ifdef _WIN32
    #define SQLITE_VEC_API __declspec(dllexport)
  #else
    #define SQLITE_VEC_API __attribute__((visibility("default")))
  #endif
#endif

#define SQLITE_VEC_VERSION "v0.3.3"
// TODO rm
#define SQLITE_VEC_DATE "2026-02-05T04:24:54Z+0000"
#define SQLITE_VEC_SOURCE "952874d55feb7358ad5a1dd4677a1e6863c0b908"


#define SQLITE_VEC_VERSION_MAJOR 0
#define SQLITE_VEC_VERSION_MINOR 3
#define SQLITE_VEC_VERSION_PATCH 3

#ifdef __cplusplus
extern "C" {
#endif

SQLITE_VEC_API int sqlite3_vec_init(sqlite3 *db, char **pzErrMsg,
                  const sqlite3_api_routines *pApi);

#ifdef __cplusplus
}  /* end of the 'extern "C"' block */
#endif

#endif /* ifndef SQLITE_VEC_H */
