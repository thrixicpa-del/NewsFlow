// Source Electron smoke harness. Python owns fixtures, the live lock and all
// four full process restarts; only the OS file dialog is replaced here.
import { app, BrowserWindow, dialog, ipcMain, shell } from 'electron';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

assert.equal(process.env.NEWSFLOW_TEST_MODE, '1', 'Use the isolated Python test launcher');
assert(process.env.NEWSFLOW_TEST_ROOT);
const root = path.resolve(process.env.NEWSFLOW_TEST_ROOT);
const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const stage = process.argv[2];
assert(['choose-and-cancel', 'restart-remove', 'restart-clear', 'restart-empty'].includes(stage));
const ownedPath = (value) => {
  assert(value, 'Missing test-owned path');
  const resolved = path.resolve(value);
  const relative = path.relative(root, resolved);
  assert(relative && !relative.startsWith('..') && !path.isAbsolute(relative), `Path outside owned root: ${resolved}`);
  assert(existsSync(resolved), `Fixture directory/file does not exist: ${resolved}`);
  return resolved;
};
const local = ownedPath(process.env.LOCALAPPDATA);
ownedPath(process.env.TEMP);
ownedPath(process.env.TMP);
const artifacts = ownedPath(path.join(root, 'artifacts'));
// Set before app readiness/session creation, including the harness itself.
// Production main sets the same value again when imported below.
const electronProfile = path.join(root, 'electron-user-data');
mkdirSync(electronProfile, { recursive: true });
app.setPath('userData', electronProfile);
app.setPath('sessionData', electronProfile);
const fixtureFiles = JSON.parse(process.env.NEWSFLOW_BROWSER_DOCUMENTS_FIXTURES || '[]').map(ownedPath);
assert.equal(fixtureFiles.length, 3);
const lock = path.join(local, 'NewsFlow', 'browser-topic-scenarios.lock');
const evidence = { status: 'RUNNING', stage, chooserCalls: 0, commands: [], unexpectedCommands: [], externalRequests: [] };
app.on('session-created', (created) => {
  created.webRequest.onBeforeRequest({ urls: ['http://*/*', 'https://*/*'] }, (details, done) => {
    evidence.externalRequests.push(details.url);
    done({ cancel: true });
  });
});
const allowedCommands = new Set(['save-browser-topic-scenario-settings', 'cancel-browser-topic-scenarios']);
const results = [];
const originalHandle = ipcMain.handle.bind(ipcMain);
ipcMain.handle = (channel, handler) => originalHandle(channel, async (event, ...args) => {
  if (channel === 'newsflow:command') {
    const [name, payload] = args;
    if (!allowedCommands.has(name)) {
      evidence.unexpectedCommands.push(name);
      throw Error(`Offline smoke forbids command ${name}`);
    }
    evidence.commands.push({ name, payload });
  }
  const result = await handler(event, ...args);
  if (channel === 'newsflow:command') results.push({ name: args[0], result });
  return result;
});
dialog.showOpenDialog = async (...args) => {
  const options = args.at(-1);
  assert.deepEqual(options.properties, ['openFile', 'multiSelections']);
  assert.deepEqual(options.filters[0].extensions, ['txt', 'md', 'markdown']);
  assert.equal(stage, 'choose-and-cancel');
  evidence.chooserCalls += 1;
  return { canceled: false, filePaths: fixtureFiles };
};
shell.openExternal = async (url) => { evidence.externalRequests.push(url); throw Error('External browser launches forbidden'); };
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const until = async (label, predicate, timeout = 30000) => {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await delay(100);
  }
  throw Error(`Timed out: ${label}`);
};
let win;
const evaluate = (fn, value) => win.webContents.executeJavaScript(`(${fn.toString()})(${JSON.stringify(value) ?? ''})`);
const click = async (name) => {
  await until(`click ${name}`, () => evaluate((label) => {
    const button = [...document.querySelectorAll('button')].find((item) =>
      item.offsetParent !== null && (item.textContent.trim() === label || item.getAttribute('aria-label') === label));
    if (!button || button.disabled) return false;
    button.click();
    return true;
  }, name));
};
const displayedFiles = () => evaluate(() => [...document.querySelectorAll('.nf-scenarios input[readonly]')].map((input) => input.value));
const snapshot = () => evaluate(() => window.newsflowDesktop.snapshot());
const save = async (expected) => {
  const previous = results.filter((entry) => entry.name === 'save-browser-topic-scenario-settings').length;
  await click('Сохранить настройки');
  await until('real Python settings save response', () => results.filter((entry) => entry.name === 'save-browser-topic-scenario-settings').length > previous);
  const result = results.filter((entry) => entry.name === 'save-browser-topic-scenario-settings').at(-1).result;
  assert.deepEqual(result.browserTopicScenarios.requirementsFiles, expected);
  assert.equal(result.browserTopicScenarios.requirementsFile, expected[0] || '');
};

async function main() {
try {
  // All monkeypatches precede the real production main module import. The
  // application retains its real trusted sender check, preload and Core spawn.
  await import(pathToFileURL(path.join(repo, 'studio-ui-remotion-verify/dist-electron/main.js')).href);
  await app.whenReady();
  await until('real application window', () => {
    win = BrowserWindow.getAllWindows()[0];
    return Boolean(win);
  });
  await until('real renderer snapshot', async () => {
    if (win.webContents.isLoadingMainFrame()) return false;
    return evaluate(() => Boolean(window.newsflowDesktop && document.querySelector('.nf-page-header h1')));
  });
  if (!await evaluate(() => [...document.querySelectorAll('button')].some((button) => button.offsetParent !== null && button.textContent.trim() === 'ChatGPT — темы'))) {
    await click('ПОДГОТОВКА');
  }
  await click('ChatGPT — темы');
  await until('browser topic form', () => evaluate(() => Boolean(document.querySelector('.nf-scenarios select'))));
  const initial = (await snapshot()).browserTopicScenarios;
  evidence.initialFiles = initial.requirementsFiles;
  evidence.initialRunning = initial.running;
  const initialExpected = stage === 'choose-and-cancel' || stage === 'restart-empty' ? []
    : stage === 'restart-remove' ? fixtureFiles : fixtureFiles.slice(1);
  assert.deepEqual(initial.requirementsFiles, initialExpected);
  assert.equal(initial.running, stage === 'choose-and-cancel');
  if (stage === 'choose-and-cancel') {
    // Header/form mounting precedes App's initial asynchronous snapshot. The
    // restored owner lock makes Cancel enabled only after that snapshot reaches
    // React; editing before then lets hydration reset the unsaved file mode.
    await until('restored active queue rendered', () => evaluate(() => {
      const cancel = [...document.querySelectorAll('button')].find((button) =>
        button.offsetParent !== null && button.textContent.trim() === 'Отменить генерацию');
      return Boolean(cancel && !cancel.disabled);
    }));
    await evaluate(() => {
      const label = [...document.querySelectorAll('label')].find((item) => item.querySelector('span')?.textContent === 'Источник требований');
      const field = label?.querySelector('select');
      if (!field) throw Error('Missing requirements source selector');
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(field, 'file');
      field.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await click('Добавить файлы');
    await until('all selected paths displayed', async () => JSON.stringify(await displayedFiles()) === JSON.stringify(fixtureFiles));
    await save(fixtureFiles);
    const owner = JSON.parse(readFileSync(lock, 'utf8'));
    assert.equal(owner.pid, Number(process.env.NEWSFLOW_BROWSER_DOCUMENTS_OWNER));
    assert.equal(owner.cancelled, false);
    await click('Отменить генерацию');
    await until('actual Core cancellation response', () => results.some((entry) => entry.name === 'cancel-browser-topic-scenarios'));
    assert.equal(JSON.parse(readFileSync(lock, 'utf8')).cancelled, true);
  } else {
    await until('persisted paths displayed after full restart', async () => JSON.stringify(await displayedFiles()) === JSON.stringify(initialExpected));
    if (stage === 'restart-remove') {
      await click(`Удалить файл: ${fixtureFiles[0]}`);
      await save(fixtureFiles.slice(1));
    } else if (stage === 'restart-clear') {
      for (const file of fixtureFiles.slice(1)) await click(`Удалить файл: ${file}`);
      await save([]);
    }
    assert.equal(await evaluate(() => [...document.querySelectorAll('button')].find((button) => button.textContent.trim() === 'Отменить генерацию')?.disabled), true);
  }
  const final = (await snapshot()).browserTopicScenarios;
  evidence.finalFiles = final.requirementsFiles;
  evidence.finalLegacyFile = final.requirementsFile;
  assert.deepEqual(evidence.unexpectedCommands, []);
  assert.deepEqual(evidence.externalRequests, []);
  assert.equal(evidence.chooserCalls, stage === 'choose-and-cancel' ? 1 : 0);
  writeFileSync(path.join(artifacts, `${stage}.png`), (await win.webContents.capturePage()).toPNG());
  evidence.status = 'PASS';
  console.log(`SOURCE_ELECTRON_BROWSER_DOCUMENTS_${stage}=PASS`);
} catch (error) {
  evidence.status = 'FAIL';
  evidence.error = String(error?.stack || error);
  console.error(evidence.error);
  process.exitCode = 1;
} finally {
  writeFileSync(path.join(artifacts, `${stage}.json`), JSON.stringify(evidence, null, 2));
  // Fully exit this owned process; Python starts a fresh main/preload/renderer
  // for the next stage, proving persistence beyond a React remount.
  for (const window of BrowserWindow.getAllWindows()) window.destroy();
  app.exit(process.exitCode || 0);
}
}
// Electron holds readiness until its ESM entry module finishes evaluation.
// A top-level await app.whenReady() would deadlock its own bootstrap.
void main();
