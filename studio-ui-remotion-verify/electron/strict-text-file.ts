import { readFileSync, statSync } from 'node:fs';
import { TextDecoder } from 'node:util';

const MAX_COVER_TEXT_IMPORT_BYTES = 1_000_000;
const FORBIDDEN_CONTROL_CHARACTERS = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/u;

type StrictTextIo = {
  statSync: (path: string) => { size: number };
  readFileSync: (path: string) => Buffer;
};

const DEFAULT_STRICT_TEXT_IO: StrictTextIo = { statSync, readFileSync };

/** Read one user TXT exactly once with no legacy-codepage guessing. */
export function readStrictUtf8CoverText(path: string, io: StrictTextIo = DEFAULT_STRICT_TEXT_IO): string {
  if (io.statSync(path).size > MAX_COVER_TEXT_IMPORT_BYTES) {
    throw new Error('TXT с текстами обложек больше 1 МБ. Разделите его на несколько файлов.');
  }
  const bytes = io.readFileSync(path);
  // The file can grow between statSync and readFileSync; never accept that race.
  if (bytes.byteLength > MAX_COVER_TEXT_IMPORT_BYTES) {
    throw new Error('TXT с текстами обложек больше 1 МБ. Разделите его на несколько файлов.');
  }
  return decodeStrictUtf8(bytes, 'TXT с текстами обложек');
}

/** Block pair files have no arbitrary pair/size cap and are never truncated. */
export function readStrictUtf8FootageBlockText(path: string): string {
  return decodeStrictUtf8(readFileSync(path), 'TXT с назначениями блоков');
}

function decodeStrictUtf8(bytes: Buffer, label: string): string {
  let text: string;
  try {
    text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: false }).decode(bytes);
  } catch {
    throw new Error(`${label} должен быть корректным UTF-8. ANSI/legacy-кодировки не поддерживаются.`);
  }
  if (FORBIDDEN_CONTROL_CHARACTERS.test(text)) {
    throw new Error(`${label} содержит недопустимые управляющие символы. Используйте обычный UTF-8 текст.`);
  }
  return text;
}
