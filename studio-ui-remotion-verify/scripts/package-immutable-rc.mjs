import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { releaseChannel } from "./release-channel.mjs";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const valueAfter = (name, fallback = "") => args.includes(name) ? args[args.indexOf(name) + 1] || fallback : fallback;
const outputRoot = valueAfter("--output-root", process.env.NEWSFLOW_RC_OUTPUT_ROOT || "");
const buildType = valueAfter("--type", "TEST");
const rc = valueAfter("--rc");
const target = valueAfter("--target", "portable");
const dryRun = args.includes("--dry-run");

if (!outputRoot) throw new Error("--output-root or NEWSFLOW_RC_OUTPUT_ROOT is required");
const channel = releaseChannel(buildType);
if (!new Set(["portable", "nsis"]).has(target)) throw new Error("--target must be portable or nsis");

const node = process.execPath;
const run = (command, commandArgs, options = {}) => execFileSync(command, commandArgs, {
  cwd: appRoot,
  stdio: "inherit",
  ...options,
  // Node cannot directly exec a Windows .cmd shim. The local pnpm shim is
  // intentionally used so the pinned runtime remains on PATH; invoke just
  // that command class through cmd while native executables stay direct.
  shell: process.platform === "win32" && command.toLowerCase().endsWith(".cmd"),
});

const createWindowsPackagingWorkdir = () => {
  if (process.platform !== "win32") return { cwd: appRoot, dispose: () => {} };

  // NSIS cannot resolve electron-builder template paths beyond MAX_PATH. A
  // nested worktree plus pnpm's virtual store can exceed that limit even
  // though the template exists. Map only this disposable packaging command
  // through a free DOS drive and always remove the mapping in `finally`.
  const drive = ["N", "M", "L", "K", "J", "I", "H", "G"]
    .map((letter) => `${letter}:`)
    .find((candidate) => !existsSync(`${candidate}\\`));
  if (!drive) throw new Error("No free DOS drive is available for Windows packaging");

  execFileSync("subst.exe", [drive, appRoot], { stdio: "inherit" });
  return {
    cwd: `${drive}\\`,
    dispose: () => execFileSync("subst.exe", [drive, "/D"], { stdio: "inherit" }),
  };
};
const prepared = execFileSync(node, ["scripts/prepare-immutable-rc.mjs", "--output-root", outputRoot, "--type", channel.name, "--rc", rc], { cwd: appRoot, encoding: "utf8" });
const artifactRoot = prepared.trim().split(/\r?\n/).at(-1);

if (dryRun) {
  process.stdout.write(`IMMUTABLE_RC_DRY_RUN=PASS\n${artifactRoot}\n`);
  process.exit(0);
}

const stagingRoot = path.join(path.resolve(outputRoot), ".staging", path.basename(artifactRoot));
mkdirSync(stagingRoot, { recursive: true });
let packagingWorkdir;
try {
  const pnpm = process.platform === "win32" ? "pnpm.cmd" : "pnpm";
  run(pnpm, ["verify:custom-direction-ui"]);
  run(pnpm, ["verify:build-runtime"]);
  run(pnpm, ["verify:core-runtime"]);
  run(pnpm, ["verify:security"]);
  run(pnpm, ["verify:secrets"]);
  run(pnpm, ["verify:dependencies"]);
  run(pnpm, ["verify:remotion-native-assets"]);
  run(pnpm, ["build"]);
  packagingWorkdir = createWindowsPackagingWorkdir();
  run(pnpm, ["exec", "electron-builder", "--win", target, "--config", `--config.directories.output="${stagingRoot}"`], { cwd: packagingWorkdir.cwd });
  run(node, ["scripts/verify-portable.mjs", stagingRoot]);
  cpSync(stagingRoot, artifactRoot, { recursive: true, force: false, errorOnExist: true });
  run(node, ["scripts/finalize-immutable-rc.mjs", "--directory", artifactRoot]);
  run(node, ["scripts/verify-immutable-rc.mjs", "--directory", artifactRoot]);
  process.stdout.write(`IMMUTABLE_RC_PACKAGE=PASS\n${artifactRoot}\n`);
} finally {
  packagingWorkdir?.dispose();
  rmSync(stagingRoot, { recursive: true, force: true });
}
