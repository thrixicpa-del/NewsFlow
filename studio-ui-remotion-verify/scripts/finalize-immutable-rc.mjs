import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";

const args = process.argv.slice(2);
const directoryArgument = args.includes("--directory") ? args[args.indexOf("--directory") + 1] : "";
if (!directoryArgument) throw new Error("--directory is required");

const artifactRoot = path.resolve(directoryArgument);
const manifestPath = path.join(artifactRoot, "build-manifest.json");
if (!existsSync(manifestPath)) throw new Error("Immutable RC directory must contain build-manifest.json");

const files = [];
const walk = (current) => {
  for (const entry of readdirSync(current, { withFileTypes: true })) {
    const absolute = path.join(current, entry.name);
    if (entry.isDirectory()) {
      walk(absolute);
      continue;
    }
    if (!entry.isFile()) continue;
    const relative = path.relative(artifactRoot, absolute).split(path.sep).join("/");
    if (relative === "artifact-hashes.json") continue;
    files.push({
      path: relative,
      sha256: createHash("sha256").update(readFileSync(absolute)).digest("hex"),
      size: statSync(absolute).size,
    });
  }
};

walk(artifactRoot);
files.sort((left, right) => left.path.localeCompare(right.path));
if (!files.some((entry) => entry.path.toLowerCase().endsWith(".exe"))) {
  throw new Error("Immutable RC finalization requires a packaged .exe artifact");
}

const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
writeFileSync(path.join(artifactRoot, "artifact-hashes.json"), `${JSON.stringify({
  format: 1,
  gitSha: manifest.gitSha,
  coreBinSha256: manifest.coreBinSha256,
  artifacts: files,
}, null, 2)}\n`, "utf8");
process.stdout.write(`IMMUTABLE_RC_FINALIZED=PASS ${artifactRoot}\n`);
