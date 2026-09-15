import fs from 'node:fs';
import path from 'node:path';

// Electron Builder copies these native files to resources/remotion-binaries.
// Check their *contents*, not just their directory entries: an antivirus/ACL
// issue can leave an entry visible while Node is unable to open it, which used
// to produce a broken portable build only after the user clicked Render.
const root = process.cwd();
const compositor = path.join(
  root,
  'node_modules',
  '.pnpm',
  '@remotion+compositor-win32-x64-msvc@4.0.515',
  'node_modules',
  '@remotion',
  'compositor-win32-x64-msvc',
);
const rendererManifest = path.join(root, 'node_modules', '@remotion', 'renderer', 'package.json');
const required = [
  path.join(compositor, 'ffmpeg.exe'),
  path.join(compositor, 'ffprobe.exe'),
  rendererManifest,
];

const failed = [];
for (const filename of required) {
  try {
    const handle = fs.openSync(filename, 'r');
    fs.closeSync(handle);
  } catch (error) {
    failed.push(`${filename}: ${error.code ?? error.message}`);
  }
}

if (failed.length > 0) {
  console.error('Remotion packaging preflight failed. Do not ship this build.');
  for (const line of failed) console.error(`- ${line}`);
  console.error('Repair the local pnpm dependency tree, then build again.');
  process.exit(1);
}

console.log('NewsFlow Remotion native-assets preflight passed.');
