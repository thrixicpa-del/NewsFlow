import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { releaseChannel } from "./release-channel.mjs";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(appRoot, "..");
const args = process.argv.slice(2);
const valueAfter = (name, fallback = "") => args.includes(name) ? args[args.indexOf(name) + 1] || fallback : fallback;
const output = valueAfter("--output", path.join(appRoot, "build-manifest.json"));
const buildType = valueAfter("--type", "DEV");
const channel = releaseChannel(buildType);
const hash = (file) => createHash("sha256").update(readFileSync(file)).digest("hex");
const git = (...gitArgs) => execFileSync("git", gitArgs, { cwd: repoRoot, encoding: "utf8" }).trim();
const packageJson = JSON.parse(readFileSync(path.join(appRoot, "package.json"), "utf8"));
const config = readFileSync(path.join(repoRoot, "scriptor", "config.py"), "utf8");
const schema = config.match(/SETTINGS_SCHEMA_VERSION\s*=\s*(\d+)/)?.[1];
const coreRoot = packageJson.build.extraResources.find((entry) => entry.to === "core-bin")?.from;
const coreFile = coreRoot && path.join(coreRoot, "NewsFlowCore.exe");
if (!schema || !coreFile || !existsSync(coreFile)) throw new Error("Current core-bin or storage schema marker is unavailable");
const manifest = {
  format: 1,
  appVersion: packageJson.version,
  gitSha: git("rev-parse", "HEAD"),
  gitBranch: git("branch", "--show-current"),
  coreBinSha256: hash(coreFile),
  buildTimestamp: new Date().toISOString(),
  storageSchemaVersion: Number(schema),
  lockfileSha256: hash(path.join(appRoot, "pnpm-lock.yaml")),
  buildType: channel.name,
};
writeFileSync(output, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
process.stdout.write(`BUILD_MANIFEST=PASS ${output}\n`);
