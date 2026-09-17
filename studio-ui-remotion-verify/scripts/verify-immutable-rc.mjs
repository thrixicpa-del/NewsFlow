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

process.stdout.write(`IMMUTABLE_RC_VERIFY=PASS ${artifactRoot}\n`);
