import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { releaseChannel } from "./release-channel.mjs";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(appRoot, "..");
const args = process.argv.slice(2);
const valueAfter = (name, fallback = "") => args.includes(name) ? args[args.indexOf(name) + 1] || fallback : fallback;
const outputRoot = valueAfter("--output-root");
const buildType = valueAfter("--type", "TEST");
const rc = valueAfter("--rc");

if (!outputRoot) throw new Error("--output-root is required");
const channel = releaseChannel(buildType);
if (!/^\d{2,}$/.test(rc)) throw new Error("--rc must contain at least two digits");

const packageJson = JSON.parse(readFileSync(path.join(appRoot, "package.json"), "utf8"));
const gitSha = execFileSync("git", ["rev-parse", "--short=8", "HEAD"], { cwd: repoRoot, encoding: "utf8" }).trim();
const directoryName = `NewsFlow-${packageJson.version}-${channel.name.toLowerCase()}-rc${rc}-${gitSha}`;
const target = path.resolve(outputRoot, directoryName);

try {
  mkdirSync(target, { recursive: false });
} catch (error) {
  if (error && typeof error === "object" && error.code === "EEXIST") {
    throw new Error(`Immutable RC already exists and will not be overwritten: ${target}`);
  }
  throw error;
}

try {
  execFileSync(process.execPath, ["scripts/write-build-manifest.mjs", "--output", path.join(target, "build-manifest.json"), "--type", channel.name], { cwd: appRoot, stdio: "inherit" });
  writeFileSync(path.join(target, "artifact-hashes.json"), `${JSON.stringify({ format: 1, artifacts: [] }, null, 2)}\n`, "utf8");
} catch (error) {
  throw new Error(`Immutable RC preparation failed; retain the empty directory for investigation: ${target}`, { cause: error });
}

process.stdout.write(`IMMUTABLE_RC=PASS\n${target}\n`);
