import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { BUNDLED_FFMPEG, verifyCoreAssets, runCoreMediaSmoke } from "./verify-core-assets.mjs";

const args = process.argv.slice(2);
const directoryArgument = args.includes("--directory") ? args[args.indexOf("--directory") + 1] : "";
if (!directoryArgument) throw new Error("--directory is required");

const artifactRoot = path.resolve(directoryArgument);
const manifestPath = path.join(artifactRoot, "build-manifest.json");
const hashesPath = path.join(artifactRoot, "artifact-hashes.json");
if (!existsSync(manifestPath) || !existsSync(hashesPath)) {
  throw new Error("Immutable RC requires build-manifest.json and artifact-hashes.json");
}

const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
const hashes = JSON.parse(readFileSync(hashesPath, "utf8"));
if (!manifest.gitSha || !manifest.coreBinSha256 || !manifest.buildType) {
  throw new Error("Build manifest is missing immutable release identity fields");
}
if (hashes.gitSha !== manifest.gitSha || hashes.coreBinSha256 !== manifest.coreBinSha256) {
  throw new Error("Artifact hashes do not match build manifest identity");
}
if (!Array.isArray(hashes.artifacts) || !hashes.artifacts.some((entry) => String(entry.path).toLowerCase().endsWith(".exe"))) {
  throw new Error("Artifact hashes do not contain a packaged EXE");
}

for (const entry of hashes.artifacts) {
  const relative = String(entry.path || "");
  if (!relative || path.isAbsolute(relative) || relative.split(/[\\/]/).includes("..")) {
    throw new Error(`Unsafe artifact hash path: ${relative}`);
  }
  const file = path.resolve(artifactRoot, relative);
  if (!file.startsWith(`${artifactRoot}${path.sep}`) || !existsSync(file)) {
    throw new Error(`Artifact listed in hashes is missing: ${relative}`);
  }
  const sha256 = createHash("sha256").update(readFileSync(file)).digest("hex");
  if (sha256 !== entry.sha256 || statSync(file).size !== entry.size) {
    throw new Error(`Artifact hash mismatch: ${relative}`);
  }
}

// A self-consistent inventory does not prove that declared sources were copied.
// This catches the RC02 subst omission even when hashes were finalized afterward.
const requiredScriptor = [
  "win-unpacked/resources/core/scriptor/__init__.py",
  "win-unpacked/resources/core/scriptor/bridge.py",
];
for (const relative of requiredScriptor) {
  const file = path.join(artifactRoot, relative);
  if (!existsSync(file) || !statSync(file).isFile() || statSync(file).size === 0) {
    throw new Error(`Missing or empty packaged Scriptor file: ${relative}`);
  }
  if (!hashes.artifacts.some((entry) => String(entry.path).replace(/\\/g, "/") === relative)) {
    throw new Error(`Artifact hashes omit required Scriptor file: ${relative}`);
  }
}

// A generated hash list can consistently describe a broken resource.
// Validate the exact runtime-preferred file against the independent asset lock.
const coreDirectory = path.join(artifactRoot, "win-unpacked", "resources", "core-bin");
const asset = verifyCoreAssets(coreDirectory);
const requiredAsset = `win-unpacked/resources/core-bin/${BUNDLED_FFMPEG}`;
if (!hashes.artifacts.some((entry) => String(entry.path).replace(/\\/g, "/") === requiredAsset)) {
  throw new Error("Artifact hashes omit required FFmpeg resource");
}
if (args.includes("--media-smoke")) runCoreMediaSmoke(asset.executable);

process.stdout.write(`IMMUTABLE_RC_VERIFY=PASS ${artifactRoot}\n`);
