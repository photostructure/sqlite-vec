const { join } = require("node:path");
const { arch, platform } = require("node:process");
const { readdirSync, statSync } = require("node:fs");

const ENTRYPOINT_BASE_NAME = "vec0";

function extensionSuffix(platform) {
  if (platform === "win32") return "dll";
  if (platform === "darwin") return "dylib";
  return "so";
}

/**
 * Detect if running on musl libc (Alpine Linux, etc.)
 * Uses detect-libc's primary heuristic: check for musl dynamic linker
 */
function isMusl() {
  if (platform !== "linux") return false;
  try {
    const files = readdirSync("/lib");
    return files.some((f) => f.startsWith("ld-musl-"));
  } catch {
    return false;
  }
}

/**
 * When running inside an Electron app packaged with ASAR, native extensions
 * are unpacked to app.asar.unpacked/. Replace the path segment so
 * db.loadExtension() can find the real file on disk.
 * Outside Electron this is a no-op (paths never contain "app.asar").
 */
function asarUnpack(filePath) {
  return filePath.replace("app.asar", "app.asar.unpacked");
}

function getLoadablePath() {
  // Platform-specific subdirectory (e.g., darwin-arm64, linux-x64, linux-x64-musl)
  const platformDir =
    platform === "linux" && isMusl()
      ? `${platform}-${arch}-musl`
      : `${platform}-${arch}`;
  const loadablePath = join(
    __dirname,
    "dist",
    platformDir,
    `${ENTRYPOINT_BASE_NAME}.${extensionSuffix(platform)}`
  );

  if (!statSync(loadablePath, { throwIfNoEntry: false })) {
    const supported = [
      "darwin-x64",
      "darwin-arm64",
      "linux-x64",
      "linux-x64-musl",
      "linux-arm64",
      "linux-arm64-musl",
      "win32-x64",
      "win32-arm64",
    ];
    throw new Error(
      `Loadable extension for sqlite-vec not found for ${platformDir} at ${loadablePath}. ` +
        `Supported platforms: ${supported.join(", ")}.`
    );
  }

  return asarUnpack(loadablePath);
}

function load(db) {
  db.loadExtension(getLoadablePath());
}

module.exports = { getLoadablePath, load };
