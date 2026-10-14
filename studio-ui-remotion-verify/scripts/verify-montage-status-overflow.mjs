import { app, BrowserWindow } from 'electron';
import { spawn, execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import assert from 'node:assert/strict';

if (process.env.NEWSFLOW_TEST_MODE !== '1') throw Error('Layout regression requires NEWSFLOW_TEST_MODE=1');
const root = process.cwd();
const storage = mkdtempSync(path.join(process.env.NEWSFLOW_QA_ROOT || tmpdir(), 'newsflow-layout-'));
const artifactRoot = path.join(root, '.artifacts', 'montage-status-overflow');
mkdirSync(artifactRoot, { recursive: true });
app.setPath('userData', path.join(storage, 'electron'));
app.on('window-all-closed', event => event.preventDefault());
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let vite;
let win;
async function run() {
  const results = [];
  try {
    await app.whenReady();
    vite = spawn(process.execPath, [path.join(root, 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5177', '--strictPort'], {
      cwd: root, env: { ...process.env, ELECTRON_RUN_AS_NODE: '1' }, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
    });
    let output = '';
    let startError;
    vite.stdout.on('data', data => { output += data; });
    vite.stderr.on('data', data => { output += data; });
    vite.on('error', error => { startError = error; });
    let ready = false;
    for (let n = 0; n < 100; n++) {
      if (startError) throw startError;
      assert.equal(vite.exitCode, null, output);
      if (output.includes('http://127.0.0.1:5177/')) {
        try { if ((await fetch('http://127.0.0.1:5177/')).ok) { ready = true; break; } } catch {}
      }
      await delay(100);
    }
    assert(ready, 'Own Vite child never became ready: '+output);
    win = new BrowserWindow({ show: false, width: 1440, height: 900, useContentSize: true, webPreferences: { contextIsolation: true, nodeIntegration: false, backgroundThrottling: false } });
    win.webContents.session.webRequest.onBeforeRequest({ urls: ['http://*/*', 'https://*/*'] }, (request, done) => done({ cancel: !request.url.startsWith('http://127.0.0.1:5177/') }));
    await win.loadURL('http://127.0.0.1:5177/');
    await win.webContents.executeJavaScript(`import('/scripts/fixtures/montage-overflow.tsx').then(m=>m.install())`);
    const click = async label => {
      for (let n = 0; n < 100; n++) {
        if (await win.webContents.executeJavaScript(`(() => {const label=${JSON.stringify(label)};const button=[...document.querySelectorAll('button')].find(b=>b.offsetParent!==null&&(b.textContent.trim()===label||b.getAttribute('aria-label')===label));if(!button)return false;button.click();return true;})()`)) { await delay(100); return; }
        await delay(50);
      }
      throw Error('Missing visible button: '+label);
    };
    await click('ПРОИЗВОДСТВО');
    await click('Монтаж');
    for (const width of [1440, 1000, 600, 390]) {
      win.setContentSize(width, 900);
      await delay(150);
      let baseline;
      const stages = process.env.NEWSFLOW_LAYOUT_CONCAT_FIRST === '1'
        ? ['Ожидает', 'Склейка', 'Рендеринг', 'Ошибка', 'Готово']
        : ['Ожидает', 'Рендеринг', 'Склейка', 'Ошибка', 'Готово'];
      for (const stage of stages) {
        await win.webContents.executeJavaScript(`import('/scripts/fixtures/montage-overflow.tsx').then(m=>m.setStage(${JSON.stringify(stage)}))`);
        for (let n = 0; n < 60; n++) {
          const current = await win.webContents.executeJavaScript(`document.querySelector('.task-progress span')?.textContent.includes(${JSON.stringify(stage)})`);
          if (current) break;
          await delay(50);
        }
        const measured = await win.webContents.executeJavaScript(`(() => {
          const view = document.querySelector('.nf-montage');
          const box = view.getBoundingClientRect();
          const cards = [...document.querySelectorAll('.montage-task')];
          return { viewport:innerWidth, document:document.documentElement.scrollWidth, workspace:box.width, workspaceRight:box.right,
            cards:cards.map(card=>({width:card.getBoundingClientRect().width,right:card.getBoundingClientRect().right,scroll:card.scrollWidth,client:card.clientWidth})),
            phase:document.querySelector('.task-progress span')?.textContent,
            queue:[...document.querySelectorAll('.montage-ready-list button')].map(e=>({scroll:e.scrollWidth,client:e.clientWidth})),
            progress:[...document.querySelectorAll('.task-progress span')].map(e=>({scroll:e.scrollWidth,client:e.clientWidth,overflow:getComputedStyle(e).textOverflow})),
            timeline:(()=>{const t=document.querySelector('.project-timeline');if(!t)return null;t.scrollLeft=t.scrollWidth;return {width:t.getBoundingClientRect().width,scroll:t.scrollWidth,client:t.clientWidth,left:t.scrollLeft,clips:t.children.length};})(),
            ancestors:[...(function*(e){while(e){yield e;e=e.parentElement;}})(cards[0])].slice(0,5).map(e=>({className:e.className,width:e.getBoundingClientRect().width,columns:getComputedStyle(e).gridTemplateColumns})) };
        })()`);
        results.push({ width, stage, ...measured });
        baseline ??= measured;
        assert(measured.phase.includes(stage), 'Snapshot phase did not refresh');
        assert.equal(measured.cards.length, 4);
        assert(measured.document <= width + 1, JSON.stringify(results.at(-1)));
        assert(measured.workspaceRight <= width + 1, JSON.stringify(results.at(-1)));
        assert(measured.document <= baseline.document + 1, 'Status refresh widened document');
        assert(measured.cards.every(card => card.right <= measured.workspaceRight + 1 && card.width <= measured.workspace && card.scroll <= card.client + 1), JSON.stringify(results.at(-1)));
        assert(measured.cards.every((card, index) => Math.abs(card.width - baseline.cards[index].width) <= 1), 'Status refresh widened task cards');
        assert(measured.queue.every(row=>row.scroll <= row.client + 1), JSON.stringify(results.at(-1)));
        assert(measured.progress.every(label=>label.scroll <= label.client + 1 || label.overflow === 'ellipsis'), JSON.stringify(results.at(-1)));
        if (stage !== 'Ожидает') {
          assert.equal(measured.timeline.clips, 160);
          assert(measured.timeline.width <= measured.workspace, 'Timeline escaped workspace');
          assert(measured.timeline.left > 0, 'Long timeline must remain scrollable internally');
        }
      }
      await click('Инспектор MP4');
      const inspector = await win.webContents.executeJavaScript(`(() => {const d=document.querySelector('[role="dialog"]');const t=d.querySelector('[aria-label="Происхождение MP4"]');return {text:t?.textContent,client:d.clientWidth,scroll:d.scrollWidth};})()`);
      assert(inspector.text.includes('clip.mp4 SAR=13824:13825 frame=12345'), 'Full diagnostic lost in Inspector');
      assert(inspector.scroll <= inspector.client + 1, 'Inspector widened its Sheet');
      await click('Закрыть');
      await delay(200);
      await click('Настроить монтаж');
      assert(await win.webContents.executeJavaScript(`Boolean(document.querySelector('[role="dialog"]'))`), 'Settings must remain reachable');
      await click('Закрыть');
      await delay(200);
    }
    console.log('MONTAGE_STATUS_OVERFLOW=PASS');
  } catch (error) { console.error(error); process.exitCode = 1; }
  finally {
    writeFileSync(path.join(artifactRoot, 'measurements.json'), JSON.stringify({ storage, results }, null, 2));
    win?.destroy();
    if (vite?.pid && vite.exitCode === null) {
      if (process.platform === 'win32') execFileSync('taskkill.exe', ['/PID', String(vite.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
      else vite.kill();
    }
    app.exit(process.exitCode || 0);
  }
}
void run();
