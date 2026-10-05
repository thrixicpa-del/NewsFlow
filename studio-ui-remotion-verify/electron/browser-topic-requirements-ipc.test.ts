import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const mainSource = readFileSync(resolve(process.cwd(), 'electron/main.ts'), 'utf8');
const preloadSource = readFileSync(resolve(process.cwd(), 'electron/preload.cts'), 'utf8');

describe('browser topic requirements-file IPC', () => {
  it('returns only an operator-selected path for a later visible ChatGPT attachment', () => {
    const handler = mainSource.match(
      /handleTrusted\('newsflow:choose-browser-scenario-requirements',[\s\S]*?\n\}\);/,
    )?.[0];
    expect(handler).toContain("properties: ['openFile']");
    expect(handler).toContain("extensions: ['txt', 'md', 'markdown']");
    expect(handler).toContain("result.canceled ? '' : result.filePaths[0] || ''");
    expect(handler).not.toContain('readFileSync');
  });

  it('exposes only the trusted chooser channel to the renderer', () => {
    expect(preloadSource).toContain(
      "chooseBrowserScenarioRequirements: () => ipcRenderer.invoke('newsflow:choose-browser-scenario-requirements')",
    );
  });
});
