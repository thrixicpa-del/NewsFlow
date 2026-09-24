/*
 * Packaging regression check for the native executables used by Remotion.
 * Electron can read JavaScript from app.asar but Windows cannot spawn an EXE
 * inside it, so these files must live in a separate resources folder in every
 * preview build. This check turns the former runtime ENOENT into a build
 * failure.
 */
import { existsSync, statSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { readFileSync } from 'node:fs';

const root = resolve(import.meta.dirname, '..');
const packageJson = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8'));
const configuredOutput = packageJson.build?.directories?.output || `release-${packageJson.version}`;
// Do not keep a hard-coded release number here. A stale release folder made a
// previous package check green while it inspected an older portable build.
const releaseRoot = resolve(root, process.argv[2] || configuredOutput, 'win-unpacked');
const resources = join(releaseRoot, 'resources');
const required = [
  join(resources, 'app.asar'),
  join(resources, 'app.asar.unpacked', 'remotion', 'render.mjs'),
  join(resources, 'app.asar.unpacked', 'remotion-bundle', 'index.html'),
  join(resources, 'remotion-binaries', 'ffmpeg.exe'),
  join(resources, 'remotion-binaries', 'ffprobe.exe'),
  // A portable self-extractor can occasionally omit an underscore-prefixed
  // directory. The main process restores this backup before starting Python.
  join(resources, 'core-tcl-data', 'init.tcl'),
];
const coreCandidates = [
  join(resources, 'core-bin', 'NewsFlowCore.exe'),
  join(resources, 'core-bin', 'NewsFlowCore', 'NewsFlowCore.exe'),
];
// RC02 passed the native checks while ../scriptor was omitted by subst.
// Require actual source files: a missing/empty directory is not a payload.
const requiredScriptor = [
  join(resources, 'core', 'scriptor', '__init__.py'),
  join(resources, 'core', 'scriptor', 'bridge.py'),
];
const missing = required.filter((entry) => !existsSync(entry));
for (const file of requiredScriptor) {
  if (!existsSync(file) || !statSync(file).isFile() || statSync(file).size === 0) {
    missing.push(file);
  }
}
if (!coreCandidates.some((entry) => existsSync(entry))) {
  missing.push(`one of: ${coreCandidates.join(' | ')}`);
}
if (!existsSync(join(resources, 'core-bin', '_internal', '_tcl_data', 'init.tcl'))) {
  missing.push(join(resources, 'core-bin', '_internal', '_tcl_data', 'init.tcl'));
}
if (missing.length) {
  console.error('NewsFlow portable verification failed. Missing unpacked runtime files:');
  missing.forEach((entry) => console.error(`- ${entry}`));
  process.exit(1);
}

console.log(`NewsFlow portable verification passed: ${required.length + requiredScriptor.length} runtime files found.`);
