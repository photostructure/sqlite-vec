---
title: vec_npy_file can't read files over 2 GiB on Windows
section: vec_npy_each
---

# TPP: vec_npy_file can't read files over 2 GiB on Windows

Complete: the two independent changes are ready to review and commit separately.

- [x] Reproduce text-mode corruption and the over-2-GiB failure on Windows.
- [x] Open NumPy files in binary mode; pin SUB and CRLF bytes in separate test cases.
- [x] Use 64-bit file offsets and check seek/tell failures.
- [x] Remove the Windows skip with a sparse fixture that avoids large allocation.
- [x] Verify the full Python extension suite, C unit tests, and OMIT_FS build on Windows.
- [x] Review the diff and check formatting of the changed lines.

## Evidence and decisions

- `test_vec_npy_file_binary_mode` fails before `fopen(..., "rb")`: both a
  float containing `0x1A` and one containing CRLF return no vectors.
- MSVC `fseek(..., SEEK_END)` succeeds above 2 GiB, but `ftell()` returns
  `-1` with `errno=EINVAL`; `_ftelli64()` reports the full size.
- Python's ordinary `truncate()` allocates the full file on NTFS. Even a fresh
  file marked with `FSCTL_SET_SPARSE` allocated most of its size when truncated.
  Marking it sparse before seeking and writing the final byte allocated only
  64 KiB in the probe. The regression uses this approach in pytest's temporary directory.
- The existing `size_t` shape checks remain in place. File length and available
  data size stay 64-bit without narrowing through `size_t` on 32-bit targets.
- POSIX uses `fseeko`/`ftello`; feature macros precede all headers to expose these
  APIs and request 64-bit offsets. POSIX execution remains for Linux/macOS CI.

## Validation

- `python -m pytest tests/test-loadable.py -k npy -q` passes, including the full
  scan in `test_vec_npy_file_over_2gib` without a Windows skip.
- `python -m pytest tests/test-*.py -q` passes on the native MSVC build. Existing
  unrelated TODO and slow-test skips remain.

Keep the binary-mode fix and its parametrized test in one commit. Keep the
64-bit offsets, sparse large-file fixture, and this completed plan in another.

Black and formatting of the changed C lines pass. Whole-file clang-format checks
flag unchanged code in the baseline, so those unrelated lines remain outside
these fixes.

## Second opinion

Verdict: LAND

- Batch 1 (`sqlite-vec.c`, `tests/test-loadable.py`, `CHANGELOG.md`), binary mode:
  two passes; Codex LAND, Claude LAND.
- Batch 2 (the same files plus this plan), 64-bit offsets and sparse fixture:
  two passes; Codex LAND, Claude LAND.

| ID | Scope | Model | Finding | Severity | Accept/Veto | Evidence | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R502-A | Binary mode | Claude | Missing release note | Medium | Accept | The new note describes the reproduced SUB/CRLF failures. | LAND |
| R019-A | Large files | Claude | Stale platform qualifier | Medium | Accept | Removed the qualifier after the Windows regression passed. | LAND |
| R019-B | POSIX macros | Claude | Missing inline rationale | Medium quality | Accept, clarification only | Comment explains strict C consumers; macro logic retained per the GNU libc feature-test contract. | LAND |

The [GNU libc feature-test contract](https://sourceware.org/glibc/manual/latest/html_node/Feature-Test-Macros.html)
explains how strict compiler flags affect API visibility and how 64-bit file
offsets are selected. No runtime defect was found in the implemented fixes.

Commit notes: keep binary mode, its test, and its release note separate from
64-bit offsets, the sparse fixture, the other release-note edits, and this plan.
Proposed subjects: `fix(sqlite-vec.c): read numpy files in binary mode` and
`fix(sqlite-vec.c): read numpy files over 2 GiB on Windows`.
