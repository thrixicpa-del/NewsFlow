import { app, BrowserWindow, ipcMain } from 'electron';
import { spawn, execFileSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
if (process.env.NEWSFLOW_TEST_MODE !== '1') throw Error('This source smoke requires NEWSFLOW_TEST_MODE=1.');
const ui = process.cwd();
const artifacts = path.join(ui, '.artifacts', 'gpu-chunk-control');
mkdirSync(artifacts, { recursive: true });
const repo = path.resolve(ui, '..');
const storage = mkdtempSync('D:/NewsFlow-RC/qa-gpu-block-');
const env = { ...process.env, NEWSFLOW_TEST_MODE: '1', NEWSFLOW_TEST_ROOT: storage, LOCALAPPDATA: storage, NEWSFLOW_PRODUCTION_LOCALAPPDATA: 'C:/Users/borov/AppData/Local', PYTHONIOENCODING: 'utf-8' };
writeFileSync(path.join(storage, 'preload.cjs'), `const {contextBridge,ipcRenderer}=require('electron');contextBridge.exposeInMainWorld('newsflowDesktop',{snapshot:()=>ipcRenderer.invoke('qa-gpu-block','snapshot',{}),command:(name,payload)=>ipcRenderer.invoke('qa-gpu-block',name,payload)});`);
app.setPath('userData', path.join(storage, 'electron'));
app.on('window-all-closed', event => event.preventDefault());
const core = (name, payload = {}) => {
  assert(['snapshot', 'save-montage-settings'].includes(name));
  const result = JSON.parse(execFileSync('python', ['-m', 'scriptor.bridge', name, JSON.stringify(payload)], { cwd: repo, env, encoding: 'utf8', windowsHide: true, timeout: 30000 }));
  assert(!result.error, result.error);
  return result;
};
const vite = spawn(process.execPath, [path.join(ui, 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5176', '--strictPort'], { cwd: ui, env: { ...env, ELECTRON_RUN_AS_NODE: '1' }, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
let viteOutput = '';
let viteError;
vite.stdout.on('data', data => { viteOutput += data.toString(); });
vite.stderr.on('data', data => { viteOutput += data.toString(); });
vite.on('error', error => { viteError = error; });
let win;
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function run() {
try {
  await app.whenReady();
  execFileSync('python', ['-c', 'from scriptor.config import Settings,save_settings; save_settings(Settings(montage_renderer="ffmpeg",montage_renderer_explicit=True))'], { cwd: repo, env, windowsHide: true });
  console.log('QA Electron ready');
  let ready = false;
  for (let i = 0; i < 100; i++) {
    if (viteError) throw viteError;
    assert.equal(vite.exitCode, null, 'Own Vite child exited: '+viteOutput);
    // Only the process we spawned may supply the source under test. A server
    // from another checkout on this port must never count as readiness.
    if (viteOutput.includes('http://127.0.0.1:5176/')) {
      try { if ((await fetch('http://127.0.0.1:5176/')).ok) { ready = true; break; } } catch {}
    }
    await delay(100);
  }
  assert(ready, 'Own Vite child did not become ready: '+viteOutput);
  ipcMain.handle('qa-gpu-block', (_event, name, payload) => core(name, payload));
  console.log('QA Vite ready');
  win = new BrowserWindow({ show: false, width: 1000, height: 800, useContentSize: true, webPreferences: { preload: path.join(storage, 'preload.cjs'), contextIsolation: true, nodeIntegration: false } });
  win.webContents.session.webRequest.onBeforeRequest({ urls: ['http://*/*', 'https://*/*'] }, (details, done) => done({ cancel: !details.url.startsWith('http://127.0.0.1:5176/') }));
  await Promise.race([win.loadURL('http://127.0.0.1:5176/'), delay(15000).then(() => { throw Error('QA page load timeout'); })]);
  console.log('QA UI loaded');
  const click = async label => {
    console.log('QA click '+label);
    for (let i = 0; i < 100; i++) {
      if (await win.webContents.executeJavaScript(`(() => { const label=${JSON.stringify(label)};const b=[...document.querySelectorAll('button')].find(b=>b.offsetParent!==null&&(b.textContent.trim()===label||b.getAttribute('aria-label')===label||(label==='Быстрый GPU-таймлайн'&&b.textContent.includes(label)))); if(!b)return false;b.click();return true;})()`)) { await delay(100); return; }
      await delay(100);
    }
    throw Error('Missing control: '+label);
  };
  console.log('QA navigate');
  await click('ПРОИЗВОДСТВО');
  await click('Монтаж');
  await click('Настроить монтаж');
  await click('Быстрый GPU-таймлайн');
  const fill = value => win.webContents.executeJavaScript(`(() => {const field=document.querySelector('input[aria-describedby="gpu-chunk-size-hint"]');if(!field)throw Error('Missing GPU field');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(field,${JSON.stringify(value)});field.dispatchEvent(new Event('input',{bubbles:true}));field.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await fill('37');
  await delay(100);
  await click('Сохранить выбор');
  await delay(500);
  assert.equal(core('snapshot').montageSettings.gpuChunkSize, 37);
  await click('Закрыть');
  await delay(500);
  await click('Настроить монтаж');
  await delay(500);
  console.log('QA persisted renderer '+core('snapshot').montageSettings.renderer);
  assert.equal(await win.webContents.executeJavaScript(`document.querySelector('input[aria-describedby="gpu-chunk-size-hint"]')?.value`), '37');
  const layouts = [];
  for (const width of [1000, 600, 390]) {
    win.setContentSize(width, 800);
    await delay(150);
    layouts.push(await win.webContents.executeJavaScript(`(() => { const d=document.querySelector('[role="dialog"]');const input=d.querySelector('input[aria-describedby="gpu-chunk-size-hint"]'); const box=input.getBoundingClientRect();const container=input.parentElement.getBoundingClientRect();return {width:innerWidth,document:document.documentElement.scrollWidth,dialog:d.clientWidth,scroll:d.scrollWidth,inputWidth:box.width,inputRight:box.right,containerRight:container.right};})()`));
    const current = layouts.at(-1);
    assert(current.document <= current.width + 1, JSON.stringify(current));
    assert(current.scroll <= current.dialog + 1, JSON.stringify(current));
    assert(current.inputRight <= current.containerRight + 1, JSON.stringify(current));
    assert(current.inputRight <= current.width, JSON.stringify(current));
    assert(current.inputWidth > 0);
  }
  await fill('0');
  await delay(100);
  assert.equal(await win.webContents.executeJavaScript(`[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Сохранить выбор').disabled`), true);
  assert.equal(core('snapshot').montageSettings.gpuChunkSize, 37);
  writeFileSync(path.join(artifacts, 'smoke-result.json'), JSON.stringify({ storage, layouts, saved: 37, invalidRetainsSaved: true, providers: 0 }, null, 2));
  console.log('SOURCE_ELECTRON_GPU_CONTROL_SMOKE=PASS');
} catch (error) { console.error(error); process.exitCode = 1; }
finally {
  win?.destroy();
  if (vite.pid && vite.exitCode === null) execFileSync('taskkill.exe', ['/PID', String(vite.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
  app.exit(process.exitCode || 0);
}
}
void run();
