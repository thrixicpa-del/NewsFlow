import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { readStrictUtf8CoverText } from './strict-text-file.js';

describe('readStrictUtf8CoverText', () => {
  it('preserves UTF-8 Cyrillic, emoji, CRLF and a leading BOM', () => {
    const folder = mkdtempSync(path.join(tmpdir(), 'newsflow-cover-text-'));
    const file = path.join(folder, 'covers.txt');
    writeFileSync(file, Buffer.from('\ufeffТема\r\nМОЙ HEADLINE ✨\r\nМой subheadline\r\n', 'utf8'));

    expect(readStrictUtf8CoverText(file)).toBe('Тема\r\nМОЙ HEADLINE ✨\r\nМой subheadline\r\n');
  });

  it('rejects malformed UTF-8 instead of guessing a legacy encoding', () => {
    const folder = mkdtempSync(path.join(tmpdir(), 'newsflow-cover-text-'));
    const file = path.join(folder, 'broken.txt');
    writeFileSync(file, Buffer.from([0xc3, 0x28]));

    expect(() => readStrictUtf8CoverText(file)).toThrow('корректным UTF-8');
  });
});
