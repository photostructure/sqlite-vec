# Fuzz targets

libFuzzer targets for sqlite-vec, built with ASan and UBSan. `.github/workflows/fuzz.yaml`
runs each one for 60 seconds on every push to `main` and nightly.

Build all targets into `targets/` after running `scripts/vendor.sh`. The
Makefile uses Homebrew LLVM if it is installed, since Apple's clang has no
libFuzzer, and otherwise the first of `clang-18`, `clang-17`, and `clang` it
finds; set `FUZZ_CC` to override:

```
make -C tests/fuzz all
```

Run one target from `tests/fuzz`, with its dictionary if it has one, and its
seed corpus. A target name uses underscores; its source, dictionary, and corpus
use hyphens:

```
ASAN_OPTIONS=detect_leaks=1 ./targets/vec0_create \
  -dict=./vec0-create.dict -max_total_time=60 \
  ./corpus/vec0-create
```

libFuzzer adds the inputs it finds to the corpus directory, which
`.gitignore` excludes except for the tracked seeds, and writes `crash-*`,
`leak-*`, and `timeout-*` reproducers to the current directory.
