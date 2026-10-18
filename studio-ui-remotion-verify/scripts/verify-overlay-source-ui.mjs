import assert from 'node:assert/strict';
import { app, BrowserWindow } from 'electron';
import { writeFile } from 'node:fs/promises';
import path from 'node:path';
if (process.env.NEWSFLOW_TEST_MODE !== '1' || !process.env.NEWSFLOW_TEST_ROOT) throw new Error('Disposable canonical test profile required');
app.on('browser-window-created', (_event, window) => window.hide());
app.setPath('userData', path.join(process.env.NEWSFLOW_TEST_ROOT, 'electron-user-data'));
const hardDeadline=setTimeout(()=>{ console.error('OVERLAY_UI_BOOTSTRAP_TIMEOUT'); app.exit(2); },90000);
const delay=(ms)=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn,label){const deadline=Date.now()+30000;while(Date.now()<deadline){const value=await fn();if(value)return value;await delay(100);}throw Error('Timed out: '+label);}
let win;
app.whenReady().then(async () => {
try {
  console.log('OVERLAY_UI_APP_READY');
  await import(new URL('../dist-electron/main.js', import.meta.url).href);
  console.log('OVERLAY_UI_MAIN_IMPORTED');
  await until(async()=>{win=BrowserWindow.getAllWindows()[0];return win&&!win.webContents.isLoading()&&await win.webContents.executeJavaScript('Boolean(window.newsflowDesktop)');},'actual preload');
  const js=(code)=>win.webContents.executeJavaScript(code);
  async function click(label){await until(()=>js(`(()=>{const b=[...document.querySelectorAll('button')].find(e=>e.textContent.trim()===${JSON.stringify(label)});if(!b||b.disabled)return false;b.click();return true;})()`),'button '+label);}
  async function open(){await click('ПРОИЗВОДСТВО');await click('Монтаж');await click('Наложения');await until(()=>js(`Boolean(document.querySelector('input[aria-label="X, px"]'))`),'overlay properties');}
  const snapshot=()=>js(`window.newsflowDesktop.snapshot().then(s=>({template:s.montageSettings.overlayTemplate,tasks:s.montageTasks}))`);
  await until(async()=>!!(await snapshot()).template,'backend snapshot');
  await open();
  const contrast=await js(`(()=>{
    const rgb=s=>(s.match(/[0-9.]+/g)||[]).map(Number);
    const bg=e=>{for(let p=e;p;p=p.parentElement){const c=rgb(getComputedStyle(p).backgroundColor);if(c.length===3||c[3]===1)return c.slice(0,3);}return[8,17,29];};
    const luminance=c=>c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);
    return [...document.querySelectorAll('.nf-overlay-panel button:not(:disabled), .nf-overlay-panel input:not(:disabled):not([type=checkbox]):not([type=color]), .nf-overlay-panel select:not(:disabled)')].map(e=>{const a=luminance(rgb(getComputedStyle(e).color)),b=luminance(bg(e));return {name:e.getAttribute('aria-label')||e.textContent||e.tagName,ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};});
  })()`);
  assert(contrast.every(c=>c.ratio>=4.5),JSON.stringify(contrast.filter(c=>c.ratio<4.5)));
  if(process.env.NEWSFLOW_OVERLAY_UI_STAGE==='restart') {
    const current=await snapshot();
    assert.equal(current.template.layouts['16:9'][0].x,41);
    assert.equal(current.tasks.find(t=>t.index===0).status,'Готово');
    assert.equal(current.tasks.find(t=>t.index===1).overlayTemplate.layouts['16:9'][0].x,41);
    assert.equal(current.template.librarySources.length,2);
    assert.equal(current.template.layouts['16:9'].length,7,'Defaults retain all candidates');
    const saved=JSON.parse(await (await import('node:fs/promises')).readFile(process.env.NEWSFLOW_OVERLAY_UI_CHOICES,'utf8'));
    assert.deepEqual(current.tasks.find(t=>t.index===0).overlayTemplate,saved,'Restart keeps random choices');
    await writeFile(process.env.NEWSFLOW_OVERLAY_UI_REPORT,JSON.stringify({status:'PASS',fullProcessRestart:true,defaultAndIndividualTemplatesRetained:true}));
    console.log('OVERLAY_RESTART=PASS');app.exit(0);return;
  }
  await js(`(()=>{const e=document.querySelector('input[aria-label="X, px"]');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'41');e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  assert.equal(await js(`document.querySelector('input[aria-label="X, px"]').value`),'41');
  const geometry=await js(`document.querySelector('[aria-label="Слой предпросмотра Source logo"]').style.left`);
  assert(Math.abs(parseFloat(geometry)-41/1920*100)<.001,'Numeric preview must update immediately');
  await click('Сохранить для новых');
  await until(async()=>((await snapshot()).template.layouts['16:9'][0]?.x===41),'actual core default persistence');
  let current=await snapshot();assert.equal(current.tasks[0].overlayTemplate.layouts['16:9'][0].x,20,'Existing queued snapshot must stay unchanged');
  const loaded=new Promise(resolve=>win.webContents.once('did-finish-load',resolve));win.webContents.reload();await loaded;
  await open();
  assert.equal(await js(`document.querySelector('input[aria-label="X, px"]').value`),'41','Reload persistence');
  await click('9:16');assert.equal(await js(`document.querySelector('input[aria-label="X, px"]').value`),'11','Independent vertical layout');await click('16:9');
  // The actual queue selection and apply button use the same public UI as the operator.
  await until(()=>js(`(()=>{const b=[...document.querySelectorAll('.montage-queue .montage-ready-list button')].find(e=>e.textContent.includes('Overlay source QA'));if(!b)return false;b.click();return true;})()`),'queue row');
  await click('Применить к выбранным (1)');
  await click('Заменить индивидуальные');
  await until(async()=>((await snapshot()).tasks[0]?.overlayTemplate?.layouts['16:9'][0]?.x===41),'selected queue core persistence');
  current=await snapshot();assert.equal(current.tasks[0].overlayTemplateIndividualized,true);
  await click('Применить ко всей очереди (2)'); await click('Заменить индивидуальные');
  await until(async()=>((await snapshot()).tasks.find(t=>t.index===1)?.overlayTemplate?.layouts['16:9'][0]?.x===41),'all queue includes no-MP3 row');
  await click('Экспортировать наложения без подбора');
  await until(async()=>{const task=(await snapshot()).tasks.find(t=>t.index===0);if(task?.status==='Ошибка')throw Error(task.error);return task?.status==='Готово';},'actual queued MP4 export');
  current=await snapshot();
  async function setControl(scope,label,value){
    await js(`(()=>{const parent=${scope};const e=parent.querySelector('[aria-label='+${JSON.stringify(JSON.stringify(label))}+']');if(!e)throw Error('Missing control '+${JSON.stringify(label)});const proto=e.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  }
  for(const [number,root,kind,name] of [[1,process.env.NEWSFLOW_OVERLAY_UI_LIBRARY,'image','Pictures'],[2,process.env.NEWSFLOW_OVERLAY_UI_VIDEO_LIBRARY,'video','Subscribe']]){
    await click('Добавить папку / группу');
    const scope=`document.querySelector('[aria-label="Папка наложений ${number}"]')`;
    await setControl(scope,'Название группы',name);
    await setControl(scope,'Папка группы',root);
    await setControl(scope,'Файлы группы',kind);
    await js(`(()=>{const p=${scope};[...p.querySelectorAll('button')].find(e=>e.textContent.trim()==='Добавить файлы группы').click();})()`);
    const first=kind==='image'?'image-0.png':'video-0.mp4';
    await click(first);
    await js(`document.querySelector('input[aria-label="Использовать постоянно"]').click()`);
    assert.equal(await js(`document.querySelector('input[aria-label="Использовать постоянно"]').checked`),true);
  }
  await click('Сохранить для новых');
  await until(async()=>((await snapshot()).template.librarySources?.length===2),'multiple-root default persistence');
  await click('Применить к выбранным (1)');await click('Заменить индивидуальные');
  await until(async()=>((await snapshot()).tasks.find(t=>t.index===0)?.overlayTemplate?.layouts['16:9'].length===5),'two sources random plus permanent materialized');
  current=await snapshot();
  const choice=current.tasks.find(t=>t.index===0).overlayTemplate;
  for(const source of choice.librarySources){
    const rows=choice.layouts['16:9'].filter(row=>row.librarySourceId===source.id);
    assert.equal(rows.length,2);assert.equal(rows.filter(row=>row.randomGroup).length,1);assert.equal(rows.filter(row=>!row.randomGroup).length,1);
  }
  await writeFile(process.env.NEWSFLOW_OVERLAY_UI_CHOICES,JSON.stringify(choice));
  await click('Экспортировать наложения без подбора');
  await until(async()=>{const task=(await snapshot()).tasks.find(t=>t.index===0);if(task?.status==='Ошибка')throw Error(task.error);return task?.status==='Готово'&&!task.overlayNeedsRender;},'multiple roots actual MP4 export');
  await until(()=>js(`(()=>{const b=[...document.querySelectorAll('button')].find(e=>e.textContent.trim()==='Экспортировать наложения без подбора');return b&&!b.disabled;})()`),'multiple roots export unlock');
  current=await snapshot();assert.deepEqual(current.tasks.find(t=>t.index===0).overlayTemplate,choice,'Render never rerolls');
  // Check the visible dashboard also observes the saved completion, rather than
  // accepting an IPC-only success while the UI remains on a stale progress row.
  await until(()=>js(`Boolean([...document.querySelectorAll('.montage-task.done')].find(e=>e.textContent.includes('Overlay source QA')))`),'visible ready status');
  // Re-export an already completed row: a cloned old Ready snapshot must not
  // unlock polling before the new background attempt emits a fresh revision.
  const previousAttempt=current.tasks.find(t=>t.index===0).updatedAt;
  await click('Экспортировать наложения без подбора');
  await until(async()=>{const task=(await snapshot()).tasks.find(t=>t.index===0);if(task?.status==='Ошибка')throw Error(task.error);return task?.status==='Готово'&&task.updatedAt!==previousAttempt;},'fresh completed re-export');
  await until(()=>js(`(()=>{const b=[...document.querySelectorAll('button')].find(e=>e.textContent.trim()==='Экспортировать наложения без подбора');return b&&!b.disabled&&Boolean([...document.querySelectorAll('.montage-task.done')].find(e=>e.textContent.includes('Overlay source QA')));})()`),'visible re-export completion and unlocked controls');
  current=await snapshot();
  await js(`document.querySelector('.nf-overlay-panel')?.scrollIntoView({block:'start'})`);
  assert.deepEqual(current.tasks.find(t=>t.index===0).overlayTemplate,choice,'Completed re-export keeps the exact saved choices');
  const report={status:'PASS',multipleRoots:true,randomAndPermanentTogether:true,stableRandomChoices:true,visibleReady:true,reExportAlreadyReady:true,readableControls:true,allQueueIncludesNoMP3:true,actualQueuedMP4:true,actualMain:true,actualPreload:true,actualCore:true,numericPreview:true,defaultsPreserveQueue:true,reloadPersists:true,independentLayouts:true,selectedQueueApplied:true,template:current.template};
  await writeFile(process.env.NEWSFLOW_OVERLAY_UI_REPORT,JSON.stringify(report,null,2));
  win.showInactive(); await delay(500);
  const screenshot=await win.webContents.capturePage(); win.hide();await writeFile(process.env.NEWSFLOW_OVERLAY_UI_SCREENSHOT,screenshot.toPNG());
  console.log('OVERLAY_SOURCE_UI=PASS');
  app.exit(0);
} catch(error){console.error(error);if(win)console.error((await win.webContents.executeJavaScript('document.body.innerText')).slice(-16000));app.exit(1);}
});
