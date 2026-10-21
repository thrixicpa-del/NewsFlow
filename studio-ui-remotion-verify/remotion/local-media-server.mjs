import { createReadStream } from 'node:fs';
import { realpath, stat } from 'node:fs/promises';
import { createServer } from 'node:http';
import { resolve } from 'node:path';

const mimeFor = (file) => {
  const lower = file.toLowerCase();
  if (lower.endsWith('.mp4') || lower.endsWith('.m4v')) return 'video/mp4';
  if (lower.endsWith('.webm')) return 'video/webm';
  if (lower.endsWith('.mov')) return 'video/quicktime';
  if (lower.endsWith('.mp3')) return 'audio/mpeg';
  if (lower.endsWith('.wav')) return 'audio/wav';
  if (lower.endsWith('.m4a') || lower.endsWith('.aac')) return 'audio/mp4';
  return 'application/octet-stream';
};

const pathKey = (file) => process.platform === 'win32' ? file.toLowerCase() : file;

export async function createLocalMediaServer(mediaFiles) {
  // A random loopback port is not authorization. Snapshot only this manifest's
  // inputs before listening, and pin their resolved targets against link swaps.
  const allowed = new Map();
  for (const file of mediaFiles) {
    if (typeof file !== 'string' || !file) continue;
    const absolute = resolve(file);
    try {
      allowed.set(pathKey(absolute), await realpath(absolute));
    } catch { /* Missing selected media remains a 404, never a broader lookup. */ }
  }
  return createServer(async (request, response) => {
    try {
      const requestUrl = new URL(request.url || '/', 'http://127.0.0.1');
      if (requestUrl.pathname !== '/media') throw new Error('Not found');
      const encoded = requestUrl.searchParams.get('src');
      const requested = resolve(encoded ? Buffer.from(encoded, 'base64url').toString('utf8') : '');
      const file = allowed.get(pathKey(requested));
      if (!file || pathKey(await realpath(requested)) !== pathKey(file)) throw new Error('Not found');
      const info = await stat(file);
      if (!info.isFile()) throw new Error('Not a file');
      const size = info.size;
      const range = request.headers.range;
      response.setHeader('Access-Control-Allow-Origin', '*');
      response.setHeader('Access-Control-Allow-Headers', 'Range');
      response.setHeader('Accept-Ranges', 'bytes');
      response.setHeader('Content-Type', mimeFor(file));
      response.setHeader('Cache-Control', 'no-store');
      if (!range) {
        response.writeHead(200, { 'Content-Length': size });
        createReadStream(file).pipe(response);
        return;
      }
      const match = /^bytes=(\d*)-(\d*)$/.exec(range.trim());
      let start = Number.NaN;
      let end = size - 1;
      if (match?.[1]) {
        start = Number(match[1]);
        if (match[2]) end = Math.min(Number(match[2]), size - 1);
      } else if (match?.[2]) {
        start = Math.max(0, size - Number(match[2]));
      }
      if (!Number.isSafeInteger(start) || start >= size || end < start) {
        response.writeHead(416, { 'Content-Range': `bytes */${size}`, 'Content-Length': 0 });
        response.end();
        return;
      }
      response.writeHead(206, {
        'Content-Range': `bytes ${start}-${end}/${size}`,
        'Content-Length': end - start + 1,
      });
      createReadStream(file, { start, end }).pipe(response);
    } catch {
      response.writeHead(404);
      response.end();
    }
  });
}
