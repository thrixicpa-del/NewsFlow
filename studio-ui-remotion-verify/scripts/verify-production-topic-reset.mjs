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
    const title = 'Повторная тема QA 406';
    async function click(text) {
      await until(() => js(`(()=>{const e=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)});if(!e||e.disabled)return false;e.click();return true;})()`), text);
    }
    async function fill(label, value) {
      await js(`(()=>{const p=[...document.querySelectorAll('label')].find(e=>e.querySelector('span')?.textContent===${JSON.stringify(label)});const e=p?.querySelector('input,textarea');if(!e)throw Error('Missing field');const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    }
    await click('Новости');
    if (process.env.NEWSFLOW_TOPIC_RESET_STAGE === 'restart') {
      const state = await snapshot();
      const expected = JSON.parse(await readFile(process.env.NEWSFLOW_TOPIC_RESET_REPORT, 'utf8'));
      assert.equal(state.scenarios.length, 1);
      assert.equal(state.scenarios[0].productionItemId, expected.newId);
      await until(() => js(`Boolean([...document.querySelectorAll('.scenario-title')].some(e=>e.textContent.includes(${JSON.stringify(title)}))) || document.body.innerText.includes(${JSON.stringify(title)})`), 'visible persisted topic');
      await writeFile(process.env.NEWSFLOW_TOPIC_RESET_RESTART_REPORT, JSON.stringify({status:'PASS', persistedId:expected.newId}));
      app.exit(0); return;
    }
    await fill('Идеи для сценариев', title);
    await click('Добавить все');
    await until(async () => (await snapshot()).scenarios.length === 1, 'initial topic');
    const first = (await snapshot()).scenarios[0].productionItemId;
    assert(first);
    await click('Генерация идей');
    await click('Удалить всё производство');
    await fill('Контрольная фраза', 'УДАЛИТЬ ПРОИЗВОДСТВО');
    await click('Подтвердить удаление');
    await until(async () => (await snapshot()).scenarios.length === 0, 'confirmed reset');
    await click('Новости');
    await fill('Идеи для сценариев', title + '\n' + title.toUpperCase());
    await click('Добавить все');
    await until(async () => (await snapshot()).scenarios.length === 1, 'same topic after reset');
    const state = await snapshot();
    const second = state.scenarios[0].productionItemId;
    assert(second); assert.notEqual(second, first);
    await until(() => js(`document.body.innerText.includes(${JSON.stringify(title)})`), 'visible new topic');
    await writeFile(process.env.NEWSFLOW_TOPIC_RESET_REPORT, JSON.stringify({status:'PASS',oldId:first,newId:second,realUI:true,batchDedup:true}));
    app.exit(0);
  } catch(error) {
    console.error(error);
    if(win) console.error((await win.webContents.executeJavaScript('document.body.innerText')).slice(-8000));
    app.exit(1);
  }
});
