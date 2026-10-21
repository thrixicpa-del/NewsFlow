import assert from 'node:assert/strict';
import { app, BrowserWindow } from 'electron';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

if (process.env.NEWSFLOW_TEST_MODE !== '1' || !process.env.NEWSFLOW_TEST_ROOT) throw Error('Disposable profile required');
app.setPath('userData', path.join(process.env.NEWSFLOW_TEST_ROOT, 'electron-user-data'));
app.on('browser-window-created', (_event, window) => window.hide());
setTimeout(() => app.exit(2), 60000);
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(fn, label) {
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) { if (await fn()) return; await delay(100); }
  throw Error('Timeout: ' + label);
}
let win;
app.whenReady().then(async () => {
  try {
    await import(new URL('../dist-electron/main.js', import.meta.url).href);
    await until(async () => {
      win = BrowserWindow.getAllWindows()[0];
      return win && !win.webContents.isLoading() && win.webContents.executeJavaScript('Boolean(window.newsflowDesktop)');
    }, 'real preload');
    const js = code => win.webContents.executeJavaScript(code);
    const snapshot = () => js('window.newsflowDesktop.snapshot()');
    async function click(text) {
      await until(() => js(`(()=>{const e=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)});if(!e||e.disabled)return false;e.click();return true;})()`), text);
    }
    async function fill(label, value) {
      await js(`(()=>{const p=[...document.querySelectorAll('label')].find(e=>e.querySelector('span')?.textContent===${JSON.stringify(label)});const e=p?.querySelector('input,textarea');if(!e)throw Error('Missing field: '+${JSON.stringify(label)});const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    }
    const reportPath = process.env.NEWSFLOW_STANDALONE_COVER_REPORT;
    async function capture(name) {
      if (process.env.NEWSFLOW_CAPTURE_UI_SCREENSHOTS !== '1') return;
      win.showInactive();
      await delay(300);
      await writeFile(path.join(path.dirname(reportPath), name), (await win.webContents.capturePage()).toPNG());
      win.hide();
    }
    await click('ОБЛОЖКИ И ГЕНЕРАЦИИ');
    await click('Обложки YouTube');
    if (process.env.NEWSFLOW_STANDALONE_COVER_STAGE === 'restart') {
      const expected = JSON.parse(await readFile(reportPath, 'utf8'));
      const state = await snapshot();
      assert.deepEqual(state.covers.map(row => row.production_item_id), expected.newIds);
      assert.equal(state.covers[0].image_prompt, 'A greenhouse closeup');
      assert.equal(state.scenarios.length, 0);
      await until(() => js("document.body.innerText.includes('Сад: новая теплица') && document.body.innerText.includes('Кулинария: хлеб')"), 'visible persisted topics');
      await capture('restart.png');
      await writeFile(process.env.NEWSFLOW_STANDALONE_COVER_RESTART_REPORT, JSON.stringify({status:'PASS', ids:expected.newIds}));
      app.exit(0); return;
    }
    const text = 'Сад: новая теплица\nA greenhouse closeup\nКулинария: хлеб\nFresh bread closeup';
    async function add() {
      await click('Добавить темы и промпты');
      await fill('Темы и промпты', text);
      await capture('editor.png');
      await click('Добавить в обложки');
      await until(async () => (await snapshot()).covers.length === 2, 'standalone topics');
      const state = await snapshot();
      assert.equal(state.scenarios.length, 0);
      assert.equal(state.covers[0].image_prompt, 'A greenhouse closeup');
      const ids = state.covers.map(row => row.production_item_id);
      assert.equal(new Set(ids).size, 2);
      assert(ids.every(id => id && !id.startsWith('legacy-cover:')));
      return ids;
    }
    const oldIds = await add();
    await click('Генерация идей');
    await click('Удалить всё производство');
    await fill('Контрольная фраза', 'УДАЛИТЬ ПРОИЗВОДСТВО');
    await click('Подтвердить удаление');
    await until(async () => (await snapshot()).covers.length === 0, 'reset');
    await click('Обложки YouTube');
    const newIds = await add();
    assert(newIds.every(id => !oldIds.includes(id)));
    await writeFile(reportPath, JSON.stringify({status:'PASS', realUI:true, oldIds, newIds}));
    app.exit(0);
  } catch(error) {
    console.error(error);
    if(win) console.error((await win.webContents.executeJavaScript('document.body.innerText')).slice(-8000));
    app.exit(1);
  }
});
