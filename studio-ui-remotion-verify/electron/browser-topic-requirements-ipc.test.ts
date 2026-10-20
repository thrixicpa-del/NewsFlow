import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { runInNewContext } from 'node:vm';
import { describe, expect, it } from 'vitest';

const mainSource = readFileSync(resolve(process.cwd(), 'electron/main.ts'), 'utf8');
const preloadSource = readFileSync(resolve(process.cwd(), 'electron/preload.cts'), 'utf8');

describe('browser topic requirements-file IPC', () => {
  it.each([false, true])('selects multiple TXT and Markdown paths without reading their contents (cancelled=%s)', async (canceled) => {
    const handlerSource = mainSource.match(
      /handleTrusted\('newsflow:choose-browser-scenario-requirements-files',[\s\S]*?\n\}\);/,
    )?.[0];
    expect(handlerSource).toBeTruthy();
    let handler!: () => Promise<string[]>;
    let options: unknown;
    const paths = ['C:/disposable/a.txt', 'C:/disposable/b.md', 'C:/disposable/c.markdown'];
    runInNewContext(handlerSource!, {
      handleTrusted: (_channel: string, callback: typeof handler) => { handler = callback; },
      dialog: { showOpenDialog: async (value: unknown) => { options = value; return { canceled, filePaths: paths }; } },
    });
    expect(await handler()).toEqual(canceled ? [] : paths);
    expect(options).toEqual({ properties: ['openFile', 'multiSelections'], filters: [{ name: 'Требования TXT / Markdown', extensions: ['txt', 'md', 'markdown'] }] });
  });

  it('routes the renderer multi-file chooser to the dedicated native channel', async () => {
    const entry = preloadSource.match(/chooseBrowserScenarioRequirementsFiles: (\(\) => ipcRenderer.invoke\('[^']+'\))/)?.[1];
    expect(entry).toBeTruthy();
    let calledChannel = '';
    const chooser = runInNewContext(`(${entry})`, { ipcRenderer: { invoke: async (channel: string) => { calledChannel = channel; return ['C:/disposable/a.txt']; } } });
    expect(await chooser()).toEqual(['C:/disposable/a.txt']);
    expect(calledChannel).toBe('newsflow:choose-browser-scenario-requirements-files');
  });
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
