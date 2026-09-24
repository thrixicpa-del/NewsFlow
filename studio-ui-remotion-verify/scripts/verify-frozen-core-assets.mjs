import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, realpathSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

export const bundledFfmpegPath = '_internal/assets/ffmpeg.exe';

function assetContract() {
  const contract = JSON.parse(readFileSync(new URL('../frozen-core-assets.json', import.meta.url), 'utf8'));
  const asset = contract.ffmpeg;
  if (contract.format !== 1 || !asset
      || asset.sourcePath !== 'assets/ffmpeg.exe' || asset.bundledPath !== bundledFfmpegPath
      || !Number.isSafeInteger(asset.size) || asset.size < 64
      || !/^[0-9a-f]{64}$/.test(String(asset.sha256 || ''))) {
    throw new Error('Invalid frozen-core-assets.json FFmpeg contract');
  }
  return asset;
}

// Execute only the supplied, verified binary. Never resolve PATH/imageio or
// write beside an immutable Core/candidate. All generated media is disposable.
export function smokeFfmpeg(executable) {
  const run = (args) => {
    const result = spawnSync(executable, args, {
      encoding: 'utf8', windowsHide: true, timeout: 30000, maxBuffer: 2 * 1024 * 1024,
    });
    if (result.error || result.status !== 0) {
      throw new Error(`Packaged FFmpeg smoke failed: ${executable}; ${result.error?.message || result.stderr || result.status}`);
    }
    return result.stdout;
  };
  if (!run(['-version']).startsWith('ffmpeg version ')) {
    throw new Error(`Packaged FFmpeg version output is invalid: ${executable}`);
  }
  const temporary = mkdtempSync(path.join(tmpdir(), 'newsflow-packaged-ffmpeg-'));
  try {
    const output = path.join(temporary, 'smoke.mp4');
    run(['-hide_banner', '-nostdin', '-loglevel', 'error',
      '-f', 'lavfi', '-i', 'testsrc=size=64x64:rate=10',
      '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000',
      '-t', '0.2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-y', output]);
    if (!existsSync(output) || statSync(output).size === 0) {
      throw new Error('Packaged FFmpeg smoke produced no MP4');
    }
    run(['-hide_banner', '-nostdin', '-loglevel', 'error', '-xerror', '-i', output,
      '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-']);
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
  console.log(`PACKAGED_FFMPEG_SMOKE=PASS executable=${executable} video=h264 audio=aac`);
}

export function verifyFrozenCoreAssets(coreDirectory, { smoke = false } = {}) {
  const asset = assetContract();
  const executable = path.resolve(coreDirectory, asset.bundledPath);
  if (!existsSync(executable) || !statSync(executable).isFile()) {
    throw new Error(`FFmpeg payload missing: ${executable}`);
  }
  const root = realpathSync(coreDirectory);
  if (!realpathSync(executable).startsWith(`${root}${path.sep}`)) {
    throw new Error(`FFmpeg payload escapes Core directory: ${executable}`);
  }
  const bytes = readFileSync(executable);
  if (bytes.subarray(0, 128).toString('ascii').startsWith('version https://git-lfs.github.com/spec/v1')) {
    throw new Error(`Git LFS pointer bundled as FFmpeg: ${executable}. Rebuild Core from hydrated assets; do not edit immutable artifacts.`);
  }
  if (bytes.length !== asset.size) {
    throw new Error(`FFmpeg size mismatch: ${executable}; expected ${asset.size}, found ${bytes.length}`);
  }
  const peOffset = bytes.length >= 64 ? bytes.readUInt32LE(60) : bytes.length;
  if (bytes.subarray(0, 2).toString('ascii') !== 'MZ' || peOffset < 64
      || peOffset + 4 > bytes.length || !bytes.subarray(peOffset, peOffset + 4).equals(Buffer.from('PE\0\0'))) {
    throw new Error(`FFmpeg is not a PE executable: ${executable}`);
  }
  const sha256 = createHash('sha256').update(bytes).digest('hex');
  if (sha256 !== asset.sha256) {
    throw new Error(`FFmpeg SHA-256 mismatch: ${executable}; expected ${asset.sha256}, found ${sha256}`);
  }
  if (smoke) smokeFfmpeg(executable);
  return { executable, sha256, size: bytes.length };
}

if (process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url) {
  const args = process.argv.slice(2);
  const index = args.indexOf('--core-directory');
  if (index < 0 || !args[index + 1] || args[index + 1].startsWith('--')) {
    throw new Error('--core-directory is required');
  }
  const result = verifyFrozenCoreAssets(args[index + 1], { smoke: args.includes('--smoke') });
  console.log(`FROZEN_CORE_ASSETS=PASS sha256=${result.sha256} size=${result.size}`);
}
