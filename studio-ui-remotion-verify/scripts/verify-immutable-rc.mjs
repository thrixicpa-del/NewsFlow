import { bundledFfmpegPath, verifyFrozenCoreAssets } from "./verify-frozen-core-assets.mjs";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

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

// A self-consistent inventory can still describe an unusable LFS pointer.
// Require and verify the exact preferred runtime path, not an imageio fallback.
const coreRelative = "win-unpacked/resources/core-bin";
const coreExeRelative = `${coreRelative}/NewsFlowCore.exe`;
const ffmpegRelative = `${coreRelative}/${bundledFfmpegPath}`;
for (const required of [coreExeRelative, ffmpegRelative]) {
  const entries = hashes.artifacts.filter((entry) => String(entry.path).replace(/\\/g, "/") === required);
  if (entries.length !== 1) {
    throw new Error(`Required Core artifact absent from inventory or duplicated: ${required}`);
  }
}
const packagedCoreSha = createHash("sha256")
  .update(readFileSync(path.join(artifactRoot, coreExeRelative))).digest("hex");
if (packagedCoreSha !== String(manifest.coreBinSha256).toLowerCase()) {
  throw new Error("Packaged Core identity mismatch with build manifest");
}
verifyFrozenCoreAssets(path.join(artifactRoot, coreRelative), { smoke: args.includes("--media-smoke") });

process.stdout.write(`IMMUTABLE_RC_VERIFY=PASS ${artifactRoot}\n`);
