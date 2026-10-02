import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { readStrictUtf8CoverText } from './strict-text-file.js';

type StrictTextIo = {
  statSync: (path: string) => { size: number };
  readFileSync: (path: string) => Buffer;
};

const readWithIo = readStrictUtf8CoverText as unknown as (
  path: string,
  io: StrictTextIo,
) => string;

describe('readStrictUtf8CoverText', () => {
  it('preserves UTF-8 Cyrillic, emoji, CRLF, LF, tab and a leading BOM', () => {
    const folder = mkdtempSync(path.join(tmpdir(), 'newsflow-cover-text-'));
    const file = path.join(folder, 'covers.txt');
    writeFileSync(file, Buffer.from('\ufeffТема\r\nМОЙ\tHEADLINE ✨\nМой subheadline\r\n', 'utf8'));

    expect(readStrictUtf8CoverText(file)).toBe('Тема\r\nМОЙ\tHEADLINE ✨\nМой subheadline\r\n');
  });

  it('rejects an oversized file before the full read', () => {
    const io: StrictTextIo = {
      statSync: vi.fn(() => ({ size: 1_000_001 })),
      readFileSync: vi.fn(() => Buffer.from('must never be read')),
    };

    expect(() => readWithIo('oversized.txt', io)).toThrow('больше 1 МБ');
    expect(io.readFileSync).not.toHaveBeenCalled();
  });

  it('rejects malformed UTF-8 instead of guessing a legacy encoding', () => {
    const folder = mkdtempSync(path.join(tmpdir(), 'newsflow-cover-text-'));
    const file = path.join(folder, 'broken.txt');
    writeFileSync(file, Buffer.from([0xc3, 0x28]));

    expect(() => readStrictUtf8CoverText(file)).toThrow('корректным UTF-8');
  });

  it.each([
    ['NUL', Buffer.from('Тема\0headline', 'utf8')],
    ['forbidden C0 control', Buffer.from('Тема\u0001headline', 'utf8')],
    ['DEL', Buffer.from('Тема\u007fheadline', 'utf8')],
  ])('rejects %s control content', (_label, content) => {
    const folder = mkdtempSync(path.join(tmpdir(), 'newsflow-cover-text-'));
    const file = path.join(folder, 'binary.txt');
    writeFileSync(file, content);

    expect(() => readStrictUtf8CoverText(file)).toThrow('недопустимые управляющие символы');
  });
});
