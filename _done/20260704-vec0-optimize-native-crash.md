# TPP: `optimize` compaction hard-crashes the host process (native SIGTRAP)

**Status:** in progress (2026-07-05). Diagnosis sharpened from the crash dumps;
five concrete robustness bugs in the optimize/delete path found and fixed
(hardening + leak + error-masking + a latent double-free guard + blob-size/offset
validation), with a regression test — all ASan-clean, minimal diff, existing
suite green. **The exact heap-corruption trigger is still not reproduced**
synthetically despite exhaustive fuzzing; a definitive repro most likely needs
the reporter's actual database. See "Investigation log (2026-07-05)" at the
bottom.

## Summary

The fork-only `optimize` command (`INSERT INTO t(t) VALUES('optimize')`) can
**hard-crash the host process** with a native `EXC_BREAKPOINT` / `SIGTRAP`
instead of returning an error. It happens intermittently during heavy
insert/delete churn on a `vec0` table that has metadata columns. Because a
native abort cannot be caught by the calling application's `try/catch`, this
takes down the whole process.

The fix has two goals:

1. **Never crash the caller.** On any unexpected or malformed internal state,
   `optimize` must return `SQLITE_ERROR` (and set a vtab error message), not
   trap/abort. A recoverable error the embedder can catch is always preferable
   to killing their process.
2. **Be correct** for tables that have metadata columns (integer **and** text).
   Reproduce, find the actual defect, fix it, and add a regression test.

## Who hit this

A PhotoStructure beta user (macOS 15.7, Apple Silicon) with a ~1M-file library
mid initial import. Sync crashed ~2×/night; the watchdog restarted it each time.
PhotoStructure bundles this fork as `@photostructure/sqlite-vec@1.1.1`.

## Evidence (crash dumps + logs)

8 macOS `.ips` crash reports (2026-06-09 → 06-15), **all identical**:

- Path: `/home/mrm/src/photostructure/dl/chance/ps-vec0-dumps/*.ips`
- Exception: `EXC_BREAKPOINT (SIGTRAP)`, faulting thread = the app's main thread.
- Faulting stack (top frames):
  ```
  vec0.dylib          vec0Update_SpecialInsert_OptimizeCopyMetadata
  vec0.dylib          vec0Update_SpecialInsert_Optimize
  phstr_sqlite.node   sqlite3VdbeExec / sqlite3_step / sqlite3_exec
                      (below vec0: blob read/write → accessPayload)
  ```
- Logs (`/home/mrm/src/photostructure/dl/chance/ps-vec0-logslice/`) show
  `optimize` on the table **succeeding many times** and only occasionally
  crashing — it is **data-dependent / intermittent**, not every call.
- The `brk`/SIGTRAP surfaces inside the SQLite core (`accessPayload`, in
  `phstr_sqlite.node`), reached from the blob read/write that
  `OptimizeCopyMetadata` performs. On Apple Silicon in an `-O3` release build
  (no sanitizer), that signature is consistent with **prior heap corruption
  caught later by an allocator integrity check** — i.e. something in the
  compaction path writes/uses memory it shouldn't, and the process dies at the
  next allocation. Confirm this with a sanitizer build.

## Where the code is

- `vec0Update_SpecialInsert_OptimizeCopyMetadata` (`sqlite-vec.c` ~line 9865)
- `vec0Update_SpecialInsert_Optimize` (`sqlite-vec.c` ~line 9952)
- This is fork-only code (not in upstream asg017). Introduced by commits
  `6815d95` (add optimize), `042d093` (test/docs), `9facf1a` (exclusive-access
  note).

## What triggers it (the reporter's table)

PhotoStructure's table has **three metadata columns including a TEXT column**,
and rows churn heavily (bulk insert + a DELETE-then-INSERT re-sync pattern that
fragments chunks, so `optimize` has real work to do):

```sql
CREATE VIRTUAL TABLE AssetFileHash USING vec0(
  assetFileId     INTEGER,
  lHash           bit[192],
  capturedAtLocal INTEGER,
  capturedAtFuzzy INTEGER,
  bname           TEXT      -- values frequently > 12 bytes → long-value shadow table
);
```

Notes to investigate (leads, not conclusions):

- `OptimizeCopyMetadata` copies the INTEGER (8-byte) and TEXT (16-byte inline
  "view") slots between chunks, but does **not** appear to touch the
  `_metadatatextNN` long-value shadow table. Long text values (`n > 12`) are
  keyed by row rowid (which the compaction preserves), so this may be benign —
  but it is under-tested and worth verifying.
- Suspect edge cases: a compaction pass that rolls to a *second* new chunk
  mid-loop, partition/chunk-boundary handling, or an offset/size passed to
  `sqlite3_blob_read/write` that is valid-looking but wrong.

## How to reproduce

The repo already has a sanitizer target — `Makefile`:
`ASAN_CFLAGS := -fsanitize=address,undefined`. Build with it and construct a
repro that mirrors the reporter's workload:

1. Create a `vec0` table with a `bit[N]` vector **plus** at least one INTEGER and
   one TEXT metadata column.
2. Insert enough rows to span **multiple chunks** (default chunk size 1024), with
   some TEXT values > 12 bytes.
3. Delete a substantial, scattered subset to fragment chunks.
4. Run `INSERT INTO t(t) VALUES('optimize')`.

Iterate on row counts / delete patterns until ASan/UBSan flags the fault. Add
the minimized case as a regression test in the fork's suite.

## Desired outcome

- ASan/UBSan-clean `optimize` over metadata-bearing tables.
- `optimize` returns `SQLITE_ERROR` (never aborts) on any internal
  inconsistency.
- A regression test covering the metadata-copy compaction path.
- Cut a patch release so PhotoStructure can bump the dependency.

## Coordination

- Host/build repo: `/home/mrm/src/node-sqlite` (`@photostructure/sqlite`,
  `phstr_sqlite.node`) — see its companion TPP
  `20260704-vec0-optimize-native-crash.md`. It has the ASan build harness and
  loads this extension for tests; use it to get a sanitizer build of the full
  stack if a standalone repro is hard to trigger.
- PhotoStructure's only interim mitigations are (a) its general sync crash-loop
  circuit breaker, which pauses sync after repeated process exits, and
  (b) disabling similarity search entirely (`enableSimilaritySearch=false`),
  which now safely skips `optimize` without corrupting the database. Both are
  blunt — affected users either see paused sync or lose similarity search until
  this fix ships. **This is the real cure**, so it matters.

---

## Investigation log (2026-07-05)

### Diagnosis, sharpened from the actual crash dumps

Parsed all 8 `.ips` reports (`app_version 2026.4.9-beta`, macOS 15.7 / 26.4,
Apple Silicon). All identical. The real faulting stack (bottom→top of the vec0
frames), which is more precise than the summary in the TPP header:

```
sqlite3_exec → sqlite3_step → sqlite3VdbeExec
 → vec0Update_SpecialInsert_Optimize+1208
  → vec0Update_SpecialInsert_OptimizeCopyMetadata+584
   → blobReadWrite+224
    → accessPayload+376
     → sqlite3MemMalloc+36        ← the brk (EXC_BREAKPOINT) fires HERE
```

`accessPayload` calls `malloc` only to (re)allocate the cursor's overflow
page-list (`aOverflow`), sized from the cell's `nPayload`. The trap is inside
`malloc_zone_malloc` servicing a **small, normal** allocation → this is
**libmalloc's free-list integrity check firing**, i.e. heap corruption that
happened *earlier* and is detected at the next allocation. Register state at the
trap even shows the poisoned block held text-like bytes (`x21 = 0x2020…20`,
eight ASCII spaces). This confirms the TPP's "heap corruption caught later"
hypothesis and rules the crash site itself in as a *victim*, not the cause.

**Key structural fact:** `blobReadWrite` bounds-checks `iOffset + n > p->nByte`
(sqlite3.c) and returns `SQLITE_ERROR` for any out-of-range blob offset. So
`OptimizeCopyMetadata`'s own blob reads/writes **cannot** run out of bounds no
matter how wrong the offset math is — they'd get a clean error. The corrupting
write is therefore *elsewhere* (a heap-buffer-overflow / double-free / UAF that
libmalloc catches at the next malloc), which is also why a release build traps
while a plain error would be expected.

### Reproduction attempts — all CLEAN (this is itself a finding)

Built ASan+UBSan and `SQLITE_DEBUG` (btree/cell asserts) harnesses on Linux, and
a NEON release build under **Guard Malloc** (`libgmalloc`) on an M1
(`ssh m1`, repo at `~/src/sqlite-vec`) — the reporter's exact platform (NEON;
my Linux build was scalar). Fuzzers exercised, at `chunk_size` 8 / 64 / 256 /
1024 (reporter uses default 1024), file-backed WAL and `:memory:`, up to ~50k
rows × 30 churn rounds and >2000 optimize passes per run:

- insert / delete-by-rowid / delete-by-**metadata-column** / optimize
- plain KNN **and** metadata-filtered KNN (INT `>`/`=`, TEXT `=`/`>=`/`<>`,
  incl. long-value `_metadatatextNN` reads)
- the **PhotoStructure-faithful** pattern (see below)

Every run was ASan/UBSan-clean, Guard-Malloc-clean, and `PRAGMA integrity_check`
clean. Since ASan is *stricter* than macOS libmalloc for heap overflows, a clean
ASan run means the **exercised paths are memory-safe**. The trigger is a state my
loops don't reach. Scratch harnesses live at
`sqlite-vec/scratch-repro.c`, `scratch-fuzz.c`, `scratch-fuzz2.c` (untracked).

### What PhotoStructure actually does (verified in its source)

- Table has **no partition keys** and 4 metadata columns
  (`assetFileId INT, capturedAtLocal INT, capturedAtFuzzy INT, bname TEXT`) +
  `lHash bit[192]`. Default `chunk_size` (1024) → TEXT metadata chunk blob is
  16 KB, i.e. **spans overflow pages** (matches the `accessPayload` frame).
- Re-sync = `DELETE FROM AssetFileHash WHERE assetFileId = X; INSERT …`
  (`syncAssetFileHash()`), i.e. **delete by a metadata column, not rowid**, and
  **INSERT without an explicit rowid** (vec0 auto-assigns), with **1–2 rows per
  `assetFileId`**. `optimize` is a plain autocommit `db.exec("INSERT INTO
  AssetFileHash(AssetFileHash) VALUES('optimize')")` (`SqliteVecMaintenance`),
  run on a schedule (nightly here → 2 crashes/night). `fuzz2` mirrors all of this.
- Both nightly optimizes crash during the import window → the crash is
  **reliable on the accumulated DB state**, not truly random. That state is what
  we can't yet synthesize.

### Hypotheses ruled out

- **Direct blob OOB in `OptimizeCopyMetadata`** — impossible (`nByte` check).
- **Double-free of `blobChunksValidity`/`bufferChunksValidity`** via the
  `SQLITE_EMPTY` branch of `vec0Update_InsertNextAvailableStep` — real latent
  hazard, but unreachable during optimize (a live row's partition/table always
  has ≥1 chunk, so `vec0_get_latest_chunk_rowid` never returns `SQLITE_EMPTY`
  mid-optimize). Guarded anyway (Fix C).
- **Added/removed metadata columns (ALTER)** — vec0 rejects
  `ALTER TABLE … ADD COLUMN` ("virtual tables may not be altered"); a
  `writable_schema` hack would leave the new column's shadow tables missing and
  fail the *next INSERT*, not crash `optimize`. PhotoStructure migrates by
  DROP+recreate (fresh, consistent table). So a metadata-layout mismatch between
  old and new chunks is not reachable in normal use. Fix D still turns any such
  mismatch into a clean `SQLITE_ERROR`.
- **Metadata-filter KNN heap overflow** — fuzzed hard, clean; the `rowids`/
  `buffer` allocations are size-validated and indexed in-bounds.

### Fixes landed this session (sqlite-vec.c, ~67 insertions; regression test added)

All in the fork-only optimize/delete path. Diff is minimal and hand-applied (an
automated `make format` reflowed the whole 11k-line file and was discarded).

- **A** `OptimizeCopyMetadata` `done:` no longer masks a read/write error with
  the `sqlite3_blob_close` result (and no longer leaks `dstBlob` when the src
  close fails).
- **B** `vectorDatas[]` (from `vec0_get_vector_data`, `sqlite3_malloc`) is now
  freed after each row and on every error path (was leaked every row → tens of
  MB per large optimize).
- **C** `blobChunksValidity`/`bufferChunksValidity` are nulled after free/close
  in the loop and freed in `cleanup:`, closing the latent double-free.
- **D** `OptimizeCopyMetadata` validates both metadata blobs are exactly
  `vec0_metadata_chunk_size(kind, chunk_size)` and both offsets are in
  `[0, chunk_size)` before any read/write → returns `SQLITE_ERROR` instead of
  proceeding on malformed state (the TPP's "never crash the caller" goal).
- **E** `vec0Update_Delete` now propagates a failing `…_ClearMetadata` rc
  instead of returning `SQLITE_OK`.
- Regression test: `tests/test-optimize-metadata-compaction.py` (2 cases,
  single-pass + repeated churn; asserts metadata/vector integrity + KNN + actual
  compaction; long-TEXT values so the `_metadatatext` copy path is hit).

These are correct and worth shipping regardless, but **none is confirmed to be
the field crash** — the direct path is memory-safe, so the corruption is still
unlocated.

### Next steps (in priority order)

1. **Get the reporter's actual database** (or a copy of just the `AssetFileHash*`
   shadow tables). The crash is reliable on that state; running `optimize` on it
   under the M1 Guard-Malloc / ASan build should pinpoint the corrupting write in
   one shot. This is by far the highest-leverage next action.
2. Failing that, reproduce **at scale** (a single `optimize` over ~1M rows) and
   with a **concurrent reader connection** in the same process (the two
   dimensions the fuzzers don't cover). A large M1 run is in flight.
3. Consider an **MSan** (uninitialized-read) build — ASan/UBSan/Guard-Malloc
   would all miss an uninitialized value used as a size/offset feeding a later
   OOB; MSan would catch it.
4. Ship the fixes above as a patch release so PhotoStructure can bump the dep and
   re-enable space reclamation; the hardening (Fix D) converts a whole class of
   malformed-state failures from process-abort into a catchable error.
