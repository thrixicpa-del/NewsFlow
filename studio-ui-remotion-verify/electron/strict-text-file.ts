import { readFileSync } from 'node:fs';
import { TextDecoder } from 'node:util';

const MAX_COVER_TEXT_IMPORT_BYTES = 1_000_000;

/** Read one user TXT exactly once with no legacy-codepage guessing. */
export function readStrictUtf8CoverText(path: string): string {
  const bytes = readFileSync(path);
  if (bytes.byteLength > MAX_COVER_TEXT_IMPORT_BYTES) {
    throw new Error('TXT с текстами обложек больше 1 МБ. Разделите его на несколько файлов.');
  }
  try {
    return new TextDecoder('utf-8', { fatal: true, ignoreBOM: false }).decode(bytes);
  } catch {
    throw new Error('TXT с текстами обложек должен быть корректным UTF-8. ANSI/legacy-кодировки не поддерживаются.');
  }
}
