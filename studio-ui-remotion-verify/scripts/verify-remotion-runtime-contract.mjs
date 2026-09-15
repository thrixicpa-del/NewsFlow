/*
 * Source-level regression check for the portable Remotion architecture.
 * It runs without installing packages, so it catches the old app.asar/esbuild
 * mistake before an expensive Electron package build is started.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const packageJson = JSON.parse(readFileSync(resolve(root, 'package.json'), 'utf8'));
const renderer = readFileSync(resolve(root, 'remotion', 'render.mjs'), 'utf8');
const portableCheck = readFileSync(resolve(root, 'scripts', 'verify-portable.mjs'), 'utf8');

const expected = [
  ['build:remotion before packaging', String(packageJson.scripts.build || '').includes('build:remotion')],
  ['prebuilt bundle script', typeof packageJson.scripts['build:remotion'] === 'string'],
  ['prebuilt bundle is included in the installer', JSON.stringify(packageJson.build.files || []).includes('remotion-bundle/**/*')],
  ['renderer adapter is unpacked for Node mode', JSON.stringify(packageJson.build.asarUnpack || []).includes('remotion/render.mjs')],
  ['unpacked static bundle', JSON.stringify(packageJson.build.asarUnpack || []).includes('remotion-bundle/**/*')],
  ['native compositor is pinned by the renderer lockfile', renderer.includes('@remotion/compositor-win32-x64-msvc') ||
    JSON.stringify(packageJson.build.extraResources || []).includes('@remotion+compositor-win32-x64-msvc@4.0.515')],
  ['native compositor is copied outside app.asar', JSON.stringify(packageJson.build.extraResources || []).includes('remotion-binaries')],
  ['renderer checks prebuilt bundle', renderer.includes("'remotion-bundle'") && renderer.includes("'index.html'")],
  ['renderer uses the external native binaries directory', renderer.includes("'remotion-binaries'") && renderer.includes('NEWSFLOW_REMOTION_BINARIES_DIRECTORY')],
  ['renderer lazily imports bundler only for development', renderer.includes("await import('@remotion/bundler')")],
  ['portable checker requires prebuilt bundle', portableCheck.includes("'remotion-bundle', 'index.html'")],
  ['portable checker accepts both core layouts', portableCheck.includes('coreCandidates')],
];

const missing = expected.filter(([, ok]) => !ok).map(([name]) => name);
if (missing.length) {
  console.error(`NewsFlow Remotion runtime contract failed: ${missing.join(', ')}`);
  process.exit(1);
}
console.log(`NewsFlow Remotion runtime contract passed: ${expected.length} safeguards found.`);
