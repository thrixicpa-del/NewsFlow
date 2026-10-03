import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const mainSource = readFileSync(resolve(process.cwd(), 'electron/main.ts'), 'utf8');
const preloadSource = readFileSync(resolve(process.cwd(), 'electron/preload.cts'), 'utf8');

describe('cover prompt TXT Electron IPC contract', () => {
  it('registers one trusted TXT chooser that reuses the strict UTF-8 reader', () => {
    const handler = mainSource.match(
      /handleTrusted\('newsflow:choose-cover-prompt-pairs',[\s\S]*?\n\}\);/,
    )?.[0];

    expect(handler).toBeTruthy();
    expect(handler).toContain("properties: ['openFile']");
    expect(handler).not.toContain('multiSelections');
    expect(handler).toContain("extensions: ['txt']");
    expect(handler).toContain("result.canceled ? ''");
    expect(handler).toContain('readStrictUtf8CoverText(file)');
  });

  it('exposes the exact trusted chooser channel through the sandboxed preload', () => {
    expect(preloadSource).toContain(
      "chooseCoverPromptPairs: () => ipcRenderer.invoke('newsflow:choose-cover-prompt-pairs')",
    );
  });
});
