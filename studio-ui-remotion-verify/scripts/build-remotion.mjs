/*
 * Build the React montage once, before electron-builder packs the desktop app.
 *
 * Bundling at render time caused the old portable build to invoke esbuild from
 * app.asar, which Windows cannot spawn.  The final application therefore gets
 * a normal static Remotion bundle and the renderer only has to encode media.
 */
import { existsSync } from 'node:fs';
import { rm } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { bundle } from '@remotion/bundler';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const entryPoint = resolve(root, 'remotion', 'src', 'index.ts');
const outDir = resolve(root, 'remotion-bundle');

if (!existsSync(entryPoint)) {
  throw new Error(`Не найден исходник Remotion: ${entryPoint}`);
}

await rm(outDir, { recursive: true, force: true });
const location = await bundle({ entryPoint, outDir, enableCaching: true });
console.log(`NewsFlow Remotion bundle ready: ${location}`);
