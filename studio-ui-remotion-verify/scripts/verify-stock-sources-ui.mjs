// Offline source Electron smoke: all controls use real preload, trusted IPC and Core.
import { app, BrowserWindow, ipcMain, shell } from 'electron';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

assert.equal(process.env.NEWSFLOW_TEST_MODE, '1');
assert(process.env.NEWSFLOW_TEST_ROOT);
// Software compositing makes screenshots independent of this machine's GPU.
app.disableHardwareAcceleration();
const root = path.resolve(process.env.NEWSFLOW_TEST_ROOT);
const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const stage = process.argv[2];
assert(['configure', 'restart'].includes(stage));
for (const value of [process.env.LOCALAPPDATA, process.env.APPDATA, process.env.TEMP, process.env.TMP]) {
  assert(value);
  const relative = path.relative(root, path.resolve(value));
  assert(relative && !relative.startsWith('..') && !path.isAbsolute(relative), 'Environment must remain test-owned');
  assert(existsSync(value));
}
const artifacts = path.join(root, 'artifacts');
assert(existsSync(artifacts));
const profile = path.join(root, 'electron-user-data');
mkdirSync(profile, { recursive: true });
app.setPath('userData', profile);
app.setPath('sessionData', profile);
const evidence = { status: 'RUNNING', stage, commands: [], unexpectedCommands: [], externalRequests: [] };
const secrets = ['synthetic-pexels-one', 'synthetic-pexels-two', 'synthetic-pixabay-one', 'synthetic-pixabay-two'];
const assertSafe = (value) => {
  const json = JSON.stringify(value);
  for (const secret of secrets) assert(!json.includes(secret), 'Secret exposed in renderer snapshot');
};
app.on('session-created', (created) => {
  created.webRequest.onBeforeRequest({ urls: ['http://*/*', 'https://*/*'] }, (details, done) => {
    evidence.externalRequests.push(details.url);
    done({ cancel: true });
  });
});
shell.openExternal = async (url) => { evidence.externalRequests.push(url); throw Error('Offline smoke forbids external launches'); };
const allowed = new Set(['save-montage-settings', 'save-montage-stock-keys']);
const results = [];
const originalHandle = ipcMain.handle.bind(ipcMain);
ipcMain.handle = (channel, handler) => originalHandle(channel, async (event, ...args) => {
  if (channel === 'newsflow:command') {
    const [name, payload] = args;
    if (!allowed.has(name)) {
      evidence.unexpectedCommands.push(name);
      throw Error(`Offline smoke forbids command ${name}`);
    }
    // Record safe command metadata only. New key values must never enter logs.
    evidence.commands.push({ name, ...(payload?.keys ? { provider: payload.provider, keyCount: payload.keys.length } : { payload }) });
  }
  let result;
  try {
    result = await handler(event, ...args);
  } catch (error) {
    if (channel === 'newsflow:command') results.push({ name: args[0], error });
    throw error;
  }
  if (channel === 'newsflow:command' || channel === 'newsflow:snapshot') assertSafe(result);
  if (channel === 'newsflow:command') results.push({ name: args[0], result });
  return result;
});
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
const click = async (name) => until(`click ${name}`, () => evaluate((label) => {
  const button = [...document.querySelectorAll('button')].find((item) => item.offsetParent !== null &&
    (item.textContent.trim() === label || item.getAttribute('aria-label') === label));
  if (!button || button.disabled) return false;
  button.click();
  return true;
}, name));
const field = (name, value) => evaluate(({ name, value }) => {
  const labels = [...document.querySelectorAll('label')];
  const control = labels.find((label) => label.querySelector('span')?.textContent === name || label.textContent.trim() === name)?.querySelector('input,select,textarea');
  if (!control) throw Error(`Missing field ${name}`);
  const prototype = control.tagName === 'SELECT' ? HTMLSelectElement.prototype : control.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(prototype, 'value').set.call(control, value);
  control.dispatchEvent(new Event(control.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
}, { name, value });
const checkbox = (name, checked) => evaluate(({ name, checked }) => {
  const control = [...document.querySelectorAll('input[type=checkbox]')].find((input) => input.getAttribute('aria-label') === name || input.closest('label')?.textContent.trim() === name);
  if (!control || control.disabled) throw Error(`Missing enabled checkbox ${name}`);
  if (control.checked !== checked) control.click();
}, { name, checked });
const waitCommand = async (name, action) => {
  const before = results.length;
  await action();
  await until(`real Python response ${name}`, () => results.slice(before).some((entry) => entry.name === name));
  const response = results.slice(before).find((entry) => entry.name === name);
  if (response.error) throw response.error;
  return response.result;
};
const snapshot = () => evaluate(() => window.newsflowDesktop.snapshot());
const safeSettings = (settings) => ({ localVideoZoom: settings.localVideoZoom, sourceMode: settings.sourceMode, stockSources: settings.stockSources, stockTrim: settings.stockTrim, stockUseLibrary: settings.stockUseLibrary, downloadWorkers: settings.downloadWorkers, stockLibraryFolder: settings.stockLibraryFolder, stockKeys: settings.stockKeys });
const checkFinal = (settings) => {
  assert.equal(settings.sourceMode, 'stock');
  assert.deepEqual(settings.stockSources, ['pexels', 'wikimedia', 'nasa']);
  assert.equal(settings.stockTrim, false);
  assert.equal(settings.localVideoZoom, true);
  assert.equal(settings.stockUseLibrary, false);
  assert.equal(settings.downloadWorkers, 64);
  assert(path.isAbsolute(settings.stockLibraryFolder));
  assert(settings.stockLibraryFolder.startsWith(root));
  assert.equal(settings.stockKeys.length, 3);
  assert.equal(settings.stockKeys.filter((key) => key.active).length, 2);
  assert.equal(settings.stockKeys.filter((key) => key.provider === 'pexels').length, 2);
  assert.equal(settings.stockKeys.filter((key) => key.provider === 'pixabay').length, 1);
  for (const key of settings.stockKeys) assert.deepEqual(Object.keys(key).sort(), ['active', 'id', 'label', 'provider']);
  assertSafe(settings);
};

async function main() {
  try {
    // Do not top-level await readiness: Electron's ESM bootstrap owns it.
    await import(pathToFileURL(path.join(repo, 'studio-ui-remotion-verify/dist-electron/main.js')).href);
    await app.whenReady();
    await until('real application window', () => Boolean(win = BrowserWindow.getAllWindows()[0]));
    win.webContents.setBackgroundThrottling(false);
    await until('real renderer snapshot', async () => !win.webContents.isLoadingMainFrame() && evaluate(() => Boolean(window.newsflowDesktop && document.querySelector('.nf-page-header h1'))));
    // The shell initially renders its empty fallback. Wait for the disposable
    // fixture's distinctive target to reach React before opening draft settings.
    await until('initial persisted snapshot rendered', () => evaluate(() => document.querySelector('input[aria-label="Цель выпуска"]')?.value === '137'));
    if (!await evaluate(() => [...document.querySelectorAll('button')].some((button) => button.offsetParent !== null && button.textContent.trim() === 'Монтаж'))) await click('ПРОИЗВОДСТВО');
    await click('Монтаж');
    await click('Настроить монтаж');
    await until('stock controls', () => evaluate(() => Boolean(document.querySelector('#nf-select-источники-футажей'))));
    if (stage === 'configure') {
      const save = () => waitCommand('save-montage-settings', () => click('Сохранить выбор'));
      assert.equal((await snapshot()).montageSettings.localVideoZoom, false);
      await checkbox('Плавное приближение локальных видео', true);
      for (const mode of ['local', 'hybrid', 'stock']) {
        await field('Источники футажей', mode);
        const state = await save();
        assert.equal(state.montageSettings.sourceMode, mode);
      }
      await checkbox('Использовать стоки с моими футажами', true);
      assert.equal((await save()).montageSettings.sourceMode, 'hybrid');
      await checkbox('Использовать стоки с моими футажами', false);
      assert.equal((await save()).montageSettings.sourceMode, 'local');
      await field('Источники футажей', 'stock');
      await checkbox('Все вместе', true);
      await checkbox('Все вместе', false);
      assert.equal(await evaluate(() => [...document.querySelectorAll('.montage-short-mode fieldset fieldset input[type="checkbox"]')].filter((input) => input.checked).length), 0);
      assert.equal(await evaluate(() => [...document.querySelectorAll('button')].find((button) => button.textContent.trim() === 'Сохранить выбор').disabled), true);
      await checkbox('Все вместе', true);
      assert.equal(await evaluate(() => [...document.querySelectorAll('.montage-short-mode fieldset fieldset input[type="checkbox"]')].filter((input) => input.checked).length), 6);
      await checkbox('Pixabay', false);
      await checkbox('Coverr', false);
      await checkbox('Обрезать стоковые видео', false);
      await checkbox('Использовать библиотеку скачанных стоков', false);
      await field('Скачивание и нарезка', '64');
      assert.deepEqual((await save()).montageSettings.stockSources, ['pexels', 'wikimedia', 'nasa']);
      await field('Новые API-ключи стоков', secrets.slice(0, 2).join('\n'));
      assert.equal(await evaluate(() => getComputedStyle(document.querySelector('#nf-textarea-новые-api-ключи-стоков')).webkitTextSecurity), 'disc');
      await waitCommand('save-montage-stock-keys', () => click('Добавить ключи'));
      await until('secret input cleared after save', () => evaluate(() => document.querySelector('#nf-textarea-новые-api-ключи-стоков').value === ''));
      await field('Провайдер API-ключей', 'pixabay');
      await field('Новые API-ключи стоков', secrets.slice(2).join('\n'));
      const added = await waitCommand('save-montage-stock-keys', () => click('Добавить ключи'));
      assert.equal(added.montageSettings.stockKeys.length, 4);
      const pexels = added.montageSettings.stockKeys.find((key) => key.provider === 'pexels');
      const pixabay = added.montageSettings.stockKeys.filter((key) => key.provider === 'pixabay').at(-1);
      await waitCommand('save-montage-stock-keys', () => checkbox(`Активен ${pexels.label}`, false));
      await waitCommand('save-montage-stock-keys', () => click(`Удалить ${pixabay.label}`));
    }
    const final = (await snapshot()).montageSettings;
    checkFinal(final);
    await until('safe key metadata visibly rendered', () => evaluate(() => document.body.textContent.includes('Pexels: активно 1 из 2') && document.body.textContent.includes('Pixabay: активно 1 из 1')));
    const visible = await evaluate(() => ({ mode: document.querySelector('#nf-select-источники-футажей').value, trim: [...document.querySelectorAll('label')].find((label) => label.textContent.trim() === 'Обрезать стоковые видео').querySelector('input').checked, raw: document.body.innerText }));
    assert.equal(visible.mode, 'stock');
    assert.equal(visible.trim, false);
    assert.equal(await evaluate(() => [...document.querySelectorAll('label')].find((label) => label.textContent.trim() === 'Плавное приближение локальных видео').querySelector('input').checked), true);
    assert(visible.raw.includes(final.stockLibraryFolder));
    assert.equal(await evaluate(() => [...document.querySelectorAll('label')].find((label) => label.textContent.trim() === 'Использовать библиотеку скачанных стоков').querySelector('input').checked), false);
    assertSafe(visible);
    assert.deepEqual(evidence.unexpectedCommands, []);
    assert.deepEqual(evidence.externalRequests, []);
    evidence.finalSettings = safeSettings(final);
    await evaluate(() => document.querySelector('#nf-select-источники-футажей').scrollIntoView({ block: 'start' }));
    await evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    writeFileSync(path.join(artifacts, `${stage}-sources.png`), (await win.webContents.capturePage(undefined, { stayAwake: true })).toPNG());
    await evaluate(() => document.querySelector('section[aria-label="API-ключи стоков"]').scrollIntoView({ block: 'start' }));
    await evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    writeFileSync(path.join(artifacts, `${stage}-keys.png`), (await win.webContents.capturePage(undefined, { stayAwake: true })).toPNG());
    evidence.status = 'PASS';
    console.log(`SOURCE_ELECTRON_STOCK_SOURCES_${stage}=PASS`);
  } catch (error) {
    evidence.status = 'FAIL';
    evidence.error = String(error?.stack || error);
    console.error(evidence.error);
    if (win && !win.isDestroyed()) {
      try { writeFileSync(path.join(artifacts, `${stage}-failure.png`), (await win.webContents.capturePage()).toPNG()); } catch { /* Preserve the primary failure even if Chromium cannot capture. */ }
    }
    process.exitCode = 1;
  } finally {
    writeFileSync(path.join(artifacts, `${stage}.json`), JSON.stringify(evidence, null, 2));
    for (const window of BrowserWindow.getAllWindows()) window.destroy();
    app.exit(evidence.status === 'PASS' ? 0 : 1);
  }
}
void main();
