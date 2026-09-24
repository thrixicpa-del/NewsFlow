// Critical external resources are not covered by the Frozen Core EXE hash.
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

export const BUNDLED_FFMPEG = '_internal/assets/ffmpeg.exe';

export function verifyCoreAssets(coreDirectory) {
  const lock = JSON.parse(fs.readFileSync(new URL('../core-assets-lock.json', import.meta.url), 'utf8'));
  const expected = lock.ffmpeg;
  if (lock.format !== 1 || !Number.isSafeInteger(expected?.size) || expected.size < 64
      || !/^[0-9a-f]{64}$/.test(String(expected?.sha256 || ''))) {
    throw new Error('CORE_ASSET_INVALID: invalid core-assets-lock.json');
  }
  const root = path.resolve(coreDirectory);
  const executable = path.join(root, BUNDLED_FFMPEG);
  const fail = (reason) => { throw new Error(`CORE_ASSET_INVALID: ${BUNDLED_FFMPEG}: ${reason}`); };
  if (!fs.existsSync(executable) || !fs.lstatSync(executable).isFile()) fail('required file missing');
  if (!fs.realpathSync(executable).startsWith(`${fs.realpathSync(root)}${path.sep}`)) fail('resource escapes Core');
  const content = fs.readFileSync(executable);
  if (content.subarray(0, 128).toString('ascii').startsWith('version https://git-lfs.github.com/spec/v1')) {
    fail('LFS pointer, not an executable; rebuild from hydrated assets (do not mutate this Core)');
  }
  const peOffset = content.length >= 64 ? content.readUInt32LE(60) : -1;
  if (content.subarray(0, 2).toString('ascii') !== 'MZ' || peOffset < 64
      || peOffset > content.length - 4 || !content.subarray(peOffset, peOffset + 4).equals(Buffer.from('PE\0\0'))) {
    fail('invalid Windows PE executable');
  }
  if (content.length !== expected.size) fail(`size mismatch: expected ${expected.size}; found ${content.length}`);
  const digest = createHash('sha256').update(content).digest('hex');
  if (digest !== expected.sha256) fail(`SHA-256 mismatch: expected ${expected.sha256}; found ${digest}`);
  return { executable, sha256: digest, size: content.length };
}

export function runCoreMediaSmoke(executable, runner = spawnSync) {
  // The caller supplies the verified package path; never search PATH/imageio.
  const binary = path.resolve(executable);
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'newsflow-core-media-'));
  const output = path.join(root, 'probe.mp4');
  const environment = { ...process.env };
  delete environment.FFREPORT;
  const invoke = (phase, args) => {
    const result = runner(binary, args, {
      cwd: root, env: environment, encoding: 'utf8', timeout: 20000,
      maxBuffer: 1024 * 1024, windowsHide: true, shell: false,
    });
    if (result.error || result.status !== 0) {
      throw new Error(`CORE_MEDIA_SMOKE=FAIL phase=${phase}: ${result.error?.message || result.stderr || result.status}`);
    }
  };
  try {
    invoke('version', ['-nostdin', '-version']);
    invoke('encode', [
      '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
      '-f', 'lavfi', '-i', 'color=c=black:s=64x64:r=5:d=0.2',
      '-an', '-frames:v', '1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', output,
    ]);
    if (!fs.existsSync(output) || fs.statSync(output).size === 0) {
      throw new Error('CORE_MEDIA_SMOKE=FAIL: encoder produced no MP4');
    }
    invoke('decode', ['-nostdin', '-hide_banner', '-loglevel', 'error', '-i', output, '-map', '0:v:0', '-f', 'null', '-']);
    console.log(`CORE_MEDIA_SMOKE=PASS executable=${binary} encode=PASS decode=PASS`);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const index = args.indexOf('--directory');
  if (index < 0 || !args[index + 1]) throw new Error('--directory <Frozen Core directory> is required');
  const verified = verifyCoreAssets(args[index + 1]);
  console.log(`CORE_ASSETS_VERIFY=PASS sha256=${verified.sha256} size=${verified.size}`);
  if (args.includes('--media-smoke')) runCoreMediaSmoke(verified.executable);
}
