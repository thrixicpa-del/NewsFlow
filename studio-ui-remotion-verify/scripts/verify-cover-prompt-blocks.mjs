import assert from 'node:assert/strict';
import { app, BrowserWindow } from 'electron';
import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';

if (process.env.NEWSFLOW_TEST_MODE !== '1' || !process.env.NEWSFLOW_TEST_ROOT) throw Error('Disposable profile required');
const report = process.env.NEWSFLOW_BLOCKS_REPORT;
if (!report || !path.resolve(report).startsWith(path.resolve(process.env.NEWSFLOW_TEST_ROOT) + path.sep)) throw Error('Disposable evidence required');
app.setPath('userData', path.join(process.env.NEWSFLOW_TEST_ROOT, 'electron-blocks'));
app.on('browser-window-created', (_event, win) => win.hide());
const watchdog = setTimeout(() => app.exit(2), 90000);
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let win;
async function until(fn, label) {
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) { if (await fn()) return; await delay(100); }
  throw Error('Timeout: ' + label);
}
app.whenReady().then(async () => {
  try {
    await import(new URL('../dist-electron/main.js', import.meta.url).href);
    await until(async () => {
      win = BrowserWindow.getAllWindows()[0];
      return win && !win.webContents.isLoading() && win.webContents.executeJavaScript('Boolean(window.newsflowDesktop)');
    }, 'preload');
    const js = code => win.webContents.executeJavaScript(code);
    const snapshot = () => js('window.newsflowDesktop.snapshot()');
    async function click(text) {
      await until(() => js(`(()=>{const e=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)});if(!e||e.disabled)return false;e.click();return true;})()`), text);
    }
    async function fill(label, value) {
      await js(`(()=>{const p=[...document.querySelectorAll('label')].find(e=>e.querySelector('span')?.textContent===${JSON.stringify(label)});const e=p?.querySelector('input,textarea,select');if(!e)throw Error('Missing field');const proto=e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:e.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    }
    await click('ОБЛОЖКИ И ГЕНЕРАЦИИ');
    await click('Обложки YouTube');
    if (process.env.NEWSFLOW_BLOCKS_STAGE === 'restart') {
      const expected = JSON.parse(await readFile(report, 'utf8'));
      const state = await snapshot();
      assert.deepEqual(state.covers.map(r => r.production_item_id), expected.ids);
      assert.deepEqual(state.covers.map(r => r.manual_prompt_variants.map(v => v.id)), expected.variants);
      assert.deepEqual(state.covers.map(r => r.paths.length), [4, 2, 1]);
      assert.equal(state.coverSettings.manualMissingOnly, false);
      await until(() => js("[...document.querySelectorAll('label')].some(e=>e.textContent==='Только недостающие варианты — готовые сохранить' && e.querySelector('input')?.checked===false)"), 'persisted checkbox');
      await writeFile(report + '.restart.json', JSON.stringify({ status: 'PASS', ids: expected.ids, imageCounts: [4, 2, 1] }));
    } else {
      const text = 'Тема: Сад\n\nGarden one\n\nGarden two\n\nGarden three\n\nТема: Хлеб\n\nBread one\n\nBread two\n\nТема: Музыка\n\nPiano one';
      async function add(source, count) {
        await click('Добавить несколько промптов');
        await fill('Темы и промпты', source);
        await click('Проверить привязку');
        await until(() => js("Boolean(document.querySelector('[aria-label=\"Предпросмотр привязки промптов\"]'))"), 'preview');
        assert.equal(await js("[...document.querySelectorAll('[aria-label=\"Предпросмотр привязки промптов\"] li')].length"), count);
        if (process.env.NEWSFLOW_CAPTURE_UI_SCREENSHOTS === '1') {
          win.showInactive(); await delay(250);
          await writeFile(report + '.png', (await win.webContents.capturePage()).toPNG()); win.hide();
        }
        await click('Добавить в обложки');
        await until(() => js("!document.querySelector('textarea[id=\"nf-input-темы-и-промпты\"]') && ![...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='Проверить привязку')"), 'committed form');
      }
      await add(text, 6);
      let state = await snapshot();
      assert.deepEqual(state.covers.map(r => r.image_prompt_options.length), [3, 2, 1]);
      const ids = state.covers.map(r => r.production_item_id);
      assert.equal(new Set(ids).size, 3);
      await add('Тема: Сад\n\nGarden four', 1);
      await add('Тема: Сад\n\nGarden four', 1);
      state = await snapshot();
      assert.deepEqual(state.covers.map(r => r.image_prompt_options.length), [4, 2, 1]);
      assert.deepEqual(state.covers.map(r => r.production_item_id), ids);
      await js("[...document.querySelectorAll('label')].find(e=>e.textContent==='Только недостающие варианты — готовые сохранить').querySelector('input').click()");
      await until(async () => (await snapshot()).coverSettings.manualMissingOnly === false, 'saved checkbox');
      await writeFile(report, JSON.stringify({ status: 'PASS', realUI: true, ids, variants: state.covers.map(r => r.manual_prompt_variants.map(v => v.id)) }));
    }
    clearTimeout(watchdog); app.exit(0);
  } catch (error) {
    console.error(error);
    if (win) console.error((await win.webContents.executeJavaScript('document.body.innerText')).slice(-7000));
    clearTimeout(watchdog); app.exit(1);
  }
});
