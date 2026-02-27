
# ── compiler ──────────────────────────────────────────────────────────────────────
CC  ?= gcc
AR  ?= ar

# Capture user-provided flags before we append platform-specific ones
EXT_CFLAGS  := $(CFLAGS) $(CPPFLAGS)
EXT_LDFLAGS := $(LDFLAGS)

# ── platform detection ────────────────────────────────────────────────────────────
ifeq ($(shell uname -s),Darwin)
  PLATFORM := darwin
else ifeq ($(OS),Windows_NT)
  PLATFORM := windows
else
  PLATFORM := linux
endif

ifeq ($(PLATFORM),darwin)
  LOADABLE_EXTENSION := dylib
  # Unresolved SQLite symbols resolve at load time — standard for SQLite extensions
  CFLAGS += -undefined dynamic_lookup
  LDLIBS += -ldl -lm
else ifeq ($(PLATFORM),linux)
  LOADABLE_EXTENSION := so
  LDLIBS += -ldl -lm
else
  LOADABLE_EXTENSION := dll
  # Windows: -ldl not needed (Win32 API), math is linked by default
endif

# ── SIMD (auto-enabled on Apple Silicon and x86_64 Mac) ──────────────────────────
ifndef OMIT_SIMD
  ifeq ($(shell uname -sm),Darwin x86_64)
    CFLAGS += -mavx -DSQLITE_VEC_ENABLE_AVX
  else ifeq ($(shell uname -sm),Darwin arm64)
    CFLAGS += -mcpu=apple-m1 -DSQLITE_VEC_ENABLE_NEON
  endif
endif

# ── optional: use Homebrew SQLite headers/libs on macOS ──────────────────────────
ifdef USE_BREW_SQLITE
  CFLAGS += -I/opt/homebrew/opt/sqlite/include -L/opt/homebrew/opt/sqlite/lib
endif

# ── Python (for running tests) ───────────────────────────────────────────────────
ifdef python
  PYTHON := $(python)
else ifneq (,$(wildcard tests/.venv/bin/python))
  PYTHON := tests/.venv/bin/python
else
  PYTHON := python3
endif

# ── install paths ─────────────────────────────────────────────────────────────────
INSTALL_PREFIX      ?= /usr/local
INSTALL_LIB_DIR     ?= $(INSTALL_PREFIX)/lib
INSTALL_INCLUDE_DIR ?= $(INSTALL_PREFIX)/include
INSTALL_BIN_DIR     ?= $(INSTALL_PREFIX)/bin

# ── output targets ────────────────────────────────────────────────────────────────
prefix          := dist
TARGET_LOADABLE := $(prefix)/vec0.$(LOADABLE_EXTENSION)
TARGET_STATIC   := $(prefix)/libsqlite_vec0.a
TARGET_STATIC_H := $(prefix)/sqlite-vec.h
TARGET_CLI      := $(prefix)/sqlite3

OBJS_DIR  := $(prefix)/.objs
LIBS_DIR  := $(prefix)/.libs
BUILD_DIR := $(prefix)/.build

$(prefix) $(OBJS_DIR) $(LIBS_DIR) $(BUILD_DIR):
	mkdir -p $@

# ── primary build targets ─────────────────────────────────────────────────────────
.PHONY: all loadable static cli clean

all: loadable static cli

loadable: $(TARGET_LOADABLE)
static:   $(TARGET_STATIC)
cli:      $(TARGET_CLI)

$(TARGET_LOADABLE): sqlite-vec.c sqlite-vec.h | $(prefix)
	$(CC) \
		-fPIC -shared \
		-fvisibility=hidden \
		-Wall -Wextra \
		-Ivendor/ \
		-O3 \
		$(CFLAGS) $(EXT_CFLAGS) \
		$< -o $@ \
		$(EXT_LDFLAGS) $(LDLIBS)

$(TARGET_STATIC): sqlite-vec.c sqlite-vec.h | $(prefix) $(OBJS_DIR)
	$(CC) -Ivendor/ -fvisibility=hidden \
		$(CFLAGS) $(EXT_CFLAGS) \
		-DSQLITE_CORE -DSQLITE_VEC_STATIC \
		-O3 -c $< -o $(OBJS_DIR)/vec.o
	$(AR) rcs $@ $(OBJS_DIR)/vec.o

$(TARGET_STATIC_H): sqlite-vec.h | $(prefix)
	cp $< $@

$(OBJS_DIR)/sqlite3.o: vendor/sqlite3.c | $(OBJS_DIR)
	$(CC) -c -g3 -O3 \
		-DSQLITE_EXTRA_INIT=core_init \
		-DSQLITE_CORE \
		-DSQLITE_ENABLE_STMT_SCANSTATUS \
		-DSQLITE_ENABLE_BYTECODE_VTAB \
		-DSQLITE_ENABLE_EXPLAIN_COMMENTS \
		-I./vendor $< -o $@

$(LIBS_DIR)/sqlite3.a: $(OBJS_DIR)/sqlite3.o | $(LIBS_DIR)
	$(AR) rcs $@ $<

$(BUILD_DIR)/shell-new.c: vendor/shell.c | $(BUILD_DIR)
	sed 's/\/\*extra-version-info\*\//EXTRA_TODO/g' $< > $@

$(OBJS_DIR)/shell.o: $(BUILD_DIR)/shell-new.c | $(OBJS_DIR)
	$(CC) -c -g3 -O3 \
		-I./vendor \
		-DSQLITE_ENABLE_STMT_SCANSTATUS \
		-DSQLITE_ENABLE_BYTECODE_VTAB \
		-DSQLITE_ENABLE_EXPLAIN_COMMENTS \
		-DEXTRA_TODO="\"CUSTOMBUILD:sqlite-vec\n\"" \
		$< -o $@

$(LIBS_DIR)/shell.a: $(OBJS_DIR)/shell.o | $(LIBS_DIR)
	$(AR) rcs $@ $<

$(OBJS_DIR)/sqlite-vec.o: sqlite-vec.c | $(OBJS_DIR)
	$(CC) -c -g3 -fvisibility=hidden -Ivendor/ -I./ $(CFLAGS) $(EXT_CFLAGS) $< -o $@

$(LIBS_DIR)/sqlite-vec.a: $(OBJS_DIR)/sqlite-vec.o | $(LIBS_DIR)
	$(AR) rcs $@ $<

$(TARGET_CLI): sqlite-vec.h \
               $(LIBS_DIR)/sqlite-vec.a \
               $(LIBS_DIR)/shell.a \
               $(LIBS_DIR)/sqlite3.a \
               examples/sqlite3-cli/core_init.c | $(prefix)
	$(CC) -g3 \
		-fvisibility=hidden \
		-Ivendor/ -I./ \
		-DSQLITE_CORE \
		-DSQLITE_VEC_STATIC \
		-DSQLITE_THREADSAFE=0 \
		-DSQLITE_ENABLE_FTS4 \
		-DSQLITE_ENABLE_STMT_SCANSTATUS \
		-DSQLITE_ENABLE_BYTECODE_VTAB \
		-DSQLITE_ENABLE_EXPLAIN_COMMENTS \
		-DSQLITE_EXTRA_INIT=core_init \
		$(CFLAGS) $(EXT_CFLAGS) \
		$(EXT_LDFLAGS) \
		examples/sqlite3-cli/core_init.c \
		$(LIBS_DIR)/shell.a $(LIBS_DIR)/sqlite3.a $(LIBS_DIR)/sqlite-vec.a \
		-o $@ \
		$(LDLIBS)

# ── header generation ─────────────────────────────────────────────────────────────
sqlite-vec.h: sqlite-vec.h.tmpl VERSION
	VERSION=$(shell cat VERSION) \
	DATE=$(shell date -r VERSION +'%FT%TZ%z') \
	SOURCE=$(shell git log -n 1 --pretty=format:%H -- VERSION) \
	VERSION_MAJOR=$$(echo $$VERSION | cut -d. -f1) \
	VERSION_MINOR=$$(echo $$VERSION | cut -d. -f2) \
	VERSION_PATCH=$$(echo $$VERSION | cut -d. -f3 | cut -d- -f1) \
	envsubst < $< > $@

clean:
	rm -rf dist

# ── Windows MSVC builds ───────────────────────────────────────────────────────────
# Requires ilammy/msvc-dev-cmd to put cl.exe in PATH (see npm-release.yaml).
.PHONY: loadable-msvc-x64 loadable-msvc-arm64

loadable-msvc-x64: sqlite-vec.c sqlite-vec.h | $(prefix)
	cl.exe /W4 /sdl /guard:cf /Qspectre /ZH:SHA_256 /Ivendor/ /O2 /LD sqlite-vec.c /Fe$(TARGET_LOADABLE) /link /DYNAMICBASE /NXCOMPAT /guard:cf /CETCOMPAT

loadable-msvc-arm64: sqlite-vec.c sqlite-vec.h | $(prefix)
	cl.exe /W4 /sdl /guard:cf /ZH:SHA_256 /Ivendor/ /O2 /LD sqlite-vec.c /Fe$(TARGET_LOADABLE) /link /DYNAMICBASE /NXCOMPAT /guard:cf

# ── testing ───────────────────────────────────────────────────────────────────────
.PHONY: test test-loadable test-loadable-snapshot-update test-snapshots-update \
        test-loadable-watch test-unit test-all

test: cli
	dist/sqlite3 :memory: '.read test.sql'

test-loadable: loadable
	$(PYTHON) -m pytest -vv -s -x tests/test-*.py

test-loadable-snapshot-update: loadable
	$(PYTHON) -m pytest -vv tests/test-loadable.py --snapshot-update

test-snapshots-update: loadable
	$(PYTHON) -m pytest -vv tests/test-*.py --snapshot-update

test-loadable-watch:
	watchexec --exts c,py,Makefile --clear -- make test-loadable

test-unit: | $(prefix)
	$(CC) tests/test-unit.c sqlite-vec.c vendor/sqlite3.c \
		-I./ -Ivendor -DSQLITE_CORE -o $(prefix)/test-unit -lm
	$(prefix)/test-unit

test-all: test test-loadable test-unit

# ── memory / sanitizer testing ────────────────────────────────────────────────────
.PHONY: loadable-asan test-valgrind test-asan test-ubsan test-tsan \
        test-memory test-memory-all lint-clang-tidy

ASAN_CFLAGS  := -fsanitize=address,undefined -fno-omit-frame-pointer -g -O1
ASAN_LDFLAGS := -fsanitize=address,undefined

$(prefix)/vec0-asan.$(LOADABLE_EXTENSION): sqlite-vec.c sqlite-vec.h | $(prefix)
	$(CC) \
		-fPIC -shared \
		-fvisibility=hidden \
		-Wall -Wextra \
		-Ivendor/ \
		$(ASAN_CFLAGS) \
		$(CFLAGS) $(EXT_CFLAGS) \
		$< -o $@ \
		$(ASAN_LDFLAGS) $(EXT_LDFLAGS) $(LDLIBS)

loadable-asan: $(prefix)/vec0-asan.$(LOADABLE_EXTENSION)

$(prefix)/memory-test: tests/memory-test.c sqlite-vec.c vendor/sqlite3.c | $(prefix)
	$(CC) -g -O0 \
		-fvisibility=hidden \
		-Ivendor/ -I./ \
		-DSQLITE_CORE \
		-DSQLITE_VEC_STATIC \
		-DSQLITE_THREADSAFE=0 \
		$(CFLAGS) $(EXT_CFLAGS) \
		tests/memory-test.c sqlite-vec.c vendor/sqlite3.c -o $@ \
		$(EXT_LDFLAGS) $(LDLIBS)

test-valgrind: $(prefix)/memory-test
	@./scripts/valgrind-test.sh

test-asan:
	@./scripts/sanitizers-test.sh asan

test-ubsan:
	@./scripts/sanitizers-test.sh ubsan

test-tsan:
	@./scripts/sanitizers-test.sh tsan

# Excludes TSan (may have false positives with third-party code)
test-memory: test-valgrind test-asan test-ubsan

test-memory-all: test-valgrind test-asan test-ubsan test-tsan

lint-clang-tidy:
	@./scripts/clang-tidy.sh

# ── code formatting ───────────────────────────────────────────────────────────────
.PHONY: format lint

FORMAT_FILES := sqlite-vec.h sqlite-vec.c

format: $(FORMAT_FILES)
	clang-format -i $(FORMAT_FILES)
	black tests/test-loadable.py

lint: SHELL := /bin/bash
lint:
	diff -u <(cat $(FORMAT_FILES)) <(clang-format $(FORMAT_FILES))

# ── install / uninstall ───────────────────────────────────────────────────────────
.PHONY: install uninstall

install:
	install -d $(INSTALL_LIB_DIR) $(INSTALL_INCLUDE_DIR)
	install -m 644 sqlite-vec.h $(INSTALL_INCLUDE_DIR)
	@[ -f $(TARGET_LOADABLE) ] && install -m 644 $(TARGET_LOADABLE) $(INSTALL_LIB_DIR) || true
	@[ -f $(TARGET_STATIC)   ] && install -m 644 $(TARGET_STATIC)   $(INSTALL_LIB_DIR) || true
	@[ -f $(TARGET_CLI)      ] && install -m 755 $(TARGET_CLI)      $(INSTALL_BIN_DIR) || true
	ldconfig

uninstall:
	rm -f $(INSTALL_LIB_DIR)/$(notdir $(TARGET_LOADABLE))
	rm -f $(INSTALL_LIB_DIR)/$(notdir $(TARGET_STATIC))
	rm -f $(INSTALL_BIN_DIR)/$(notdir $(TARGET_CLI))
	rm -f $(INSTALL_INCLUDE_DIR)/sqlite-vec.h
	ldconfig

# ── documentation site ────────────────────────────────────────────────────────────
.PHONY: site-dev site-build

site-dev:
	npm --prefix site run dev

site-build:
	npm --prefix site run build

# ── misc ──────────────────────────────────────────────────────────────────────────
.PHONY: progress publish-release

progress:
	deno run --allow-read=sqlite-vec.c scripts/progress.ts

publish-release:
	./scripts/publish-release.sh

# ── WASM ──────────────────────────────────────────────────────────────────────────
.PHONY: wasm

WASM_DIR := $(prefix)/.wasm

$(WASM_DIR): | $(prefix)
	mkdir -p $@

SQLITE_WASM_VERSION         := 3450300
SQLITE_WASM_YEAR            := 2024
SQLITE_WASM_SRCZIP          := $(BUILD_DIR)/sqlite-src.zip
SQLITE_WASM_COMPILED_SQLITE3C := $(BUILD_DIR)/sqlite-src-$(SQLITE_WASM_VERSION)/sqlite3.c
SQLITE_WASM_COMPILED_MJS    := $(BUILD_DIR)/sqlite-src-$(SQLITE_WASM_VERSION)/ext/wasm/jswasm/sqlite3.mjs
SQLITE_WASM_COMPILED_WASM   := $(BUILD_DIR)/sqlite-src-$(SQLITE_WASM_VERSION)/ext/wasm/jswasm/sqlite3.wasm

TARGET_WASM_LIB  := $(WASM_DIR)/libsqlite_vec.wasm.a
TARGET_WASM_MJS  := $(WASM_DIR)/sqlite3.mjs
TARGET_WASM_WASM := $(WASM_DIR)/sqlite3.wasm
TARGET_WASM      := $(TARGET_WASM_MJS) $(TARGET_WASM_WASM)

$(SQLITE_WASM_SRCZIP): | $(BUILD_DIR)
	curl -o $@ https://www.sqlite.org/$(SQLITE_WASM_YEAR)/sqlite-src-$(SQLITE_WASM_VERSION).zip
	touch $@

$(SQLITE_WASM_COMPILED_SQLITE3C): $(SQLITE_WASM_SRCZIP) | $(BUILD_DIR)
	rm -rf $(BUILD_DIR)/sqlite-src-$(SQLITE_WASM_VERSION)/
	unzip -q -o $< -d $(BUILD_DIR)
	(cd $(BUILD_DIR)/sqlite-src-$(SQLITE_WASM_VERSION)/ && ./configure --enable-all && make sqlite3.c)
	touch $@

$(TARGET_WASM_LIB): examples/wasm/wasm.c sqlite-vec.c | $(BUILD_DIR) $(WASM_DIR)
	emcc -O3 -I./ -Ivendor -DSQLITE_CORE -c examples/wasm/wasm.c    -o $(BUILD_DIR)/wasm.wasm.o
	emcc -O3 -I./ -Ivendor -DSQLITE_CORE -c sqlite-vec.c            -o $(BUILD_DIR)/sqlite-vec.wasm.o
	emar rcs $@ $(BUILD_DIR)/wasm.wasm.o $(BUILD_DIR)/sqlite-vec.wasm.o

$(SQLITE_WASM_COMPILED_MJS) $(SQLITE_WASM_COMPILED_WASM): \
    $(SQLITE_WASM_COMPILED_SQLITE3C) $(TARGET_WASM_LIB)
	(cd $(BUILD_DIR)/sqlite-src-$(SQLITE_WASM_VERSION)/ext/wasm && \
		make sqlite3_wasm_extra_init.c=../../../../.wasm/libsqlite_vec.wasm.a \
		     jswasm/sqlite3.mjs jswasm/sqlite3.wasm)

$(TARGET_WASM_MJS): $(SQLITE_WASM_COMPILED_MJS)
	cp $< $@

$(TARGET_WASM_WASM): $(SQLITE_WASM_COMPILED_WASM)
	cp $< $@

wasm: $(TARGET_WASM)
