import { app, BrowserWindow, dialog, ipcMain, Menu, shell, type IpcMainInvokeEvent } from 'electron';
import { execFile, spawn } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ensureTclRuntime } from './core-runtime.js';
import { environmentWindowTitle, isolatedElectronUserDataRoot } from './test-user-data.js';
import { ALLOWED_CORE_COMMANDS } from './allowed-core-commands.js';

const isolatedUserDataRoot = isolatedElectronUserDataRoot(process.env);
if (isolatedUserDataRoot) app.setPath('userData', isolatedUserDataRoot);

const dirname = path.dirname(fileURLToPath(import.meta.url));
// The packaged bridge and its PyInstaller support files are shipped together
// in `resources/core-bin`.  Running it with the old, non-existent `core`
// working directory makes Electron report the generic "safe mode" notice.
const coreRoot = app.isPackaged ? path.join(process.resourcesPath, 'core-bin') : path.resolve(dirname, '../..');
const configuredPython = process.env.NEWSFLOW_PYTHON;
const developmentPython = 'C:\\Users\\borov\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe';
const remotionRunner = app.isPackaged
  // Remotion bundles with webpack and changes the current directory while it
  // resolves the entry point.  A path inside app.asar looks readable to Node,
  // but it is not a real directory and Chromium cannot chdir into it.  The
  // renderer source is deliberately unpacked by electron-builder below.
  ? path.join(process.resourcesPath, 'app.asar.unpacked', 'remotion', 'render.mjs')
  : path.resolve(dirname, '../remotion/render.mjs');

const approvedOpenPaths = new Set<string>();

function normalizedExistingPath(candidate: unknown): string | null {
  if (typeof candidate !== 'string' || !path.isAbsolute(candidate)) return null;
  const normalized = path.normalize(path.resolve(candidate));
  return existsSync(normalized) ? normalized : null;
}

function registerApprovedOpenPaths(value: unknown, depth = 0): void {
  if (depth > 8 || value === null || value === undefined) return;
  const directPath = normalizedExistingPath(value);
  if (directPath) {
    approvedOpenPaths.add(directPath);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((entry) => registerApprovedOpenPaths(entry, depth + 1));
  } else if (typeof value === 'object') {
    Object.values(value as Record<string, unknown>).forEach((entry) => registerApprovedOpenPaths(entry, depth + 1));
  }
}

async function openApprovedPath(target: unknown): Promise<string> {
  const normalized = normalizedExistingPath(target);
  if (!normalized || !approvedOpenPaths.has(normalized)) {
    throw new Error('Этот путь не был выдан текущим runtime NewsFlow.');
  }
  return shell.openPath(normalized);
}

function assertAllowedCoreCommand(command: unknown): asserts command is string {
  if (typeof command !== 'string' || !ALLOWED_CORE_COMMANDS.has(command)) {
    throw new Error('Недопустимая команда NewsFlow.');
  }
}

function pythonExecutable() {
  // Portable builds carry a PyInstaller bridge, so they do not depend on a
  // developer Python installation. An override is development-only: a
  // packaged release must use the verified core placed beside that release,
  // never an older nested preview core or a machine-level interpreter.
  if (app.isPackaged) {
    // A portable self-extracting EXE can omit PyInstaller's underscore-prefixed
    // Tcl directory. Repair only the extracted runtime resources, before the
    // core process starts; user projects and production libraries are never
    // involved in this operation.
    ensureTclRuntime(coreRoot, path.join(process.resourcesPath, 'core-tcl-data'));
    const bundledCore = path.join(process.resourcesPath, 'core-bin', 'NewsFlowCore.exe');
    if (!existsSync(bundledCore)) {
      throw new Error(`В сборке не найдено актуальное ядро NewsFlow: ${bundledCore}`);
    }
    return bundledCore;
  }
  return configuredPython || (existsSync(developmentPython) ? developmentPython : 'python');
}

function actionTracePayload(payload: unknown) {
  // The renderer has no filesystem access and receives no diagnostic log. It
  // sends only an opaque action ID through the existing generic IPC payload so
  // the bridge's local trace and returned result can be correlated.
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) return payload;
  return { ...payload as Record<string, unknown>, _actionTrace: { id: crypto.randomUUID() } };
}

type CorePayloadTransport = { path: string; dispose: () => void };

function createCorePayloadTransport(payload: unknown): CorePayloadTransport {
  const directory = mkdtempSync(path.join(tmpdir(), 'newsflow-core-payload-'));
  const payloadPath = path.join(directory, 'payload.json');
  writeFileSync(payloadPath, JSON.stringify(payload ?? {}), { encoding: 'utf8', mode: 0o600 });
  return {
    path: payloadPath,
    dispose: () => rmSync(directory, { recursive: true, force: true, maxRetries: 2 }),
  };
}

function callCore(command: string, payload: unknown = {}) {
  return new Promise<unknown>((resolve, reject) => {
    const executable = pythonExecutable();
    const bundled = app.isPackaged && executable.toLowerCase().endsWith('.exe') && executable.includes('core-bin');
    const tracedPayload = actionTracePayload(payload);
    const args = bundled ? [command] : ['-m', 'scriptor.bridge', command];
    let transport: CorePayloadTransport;
    try {
      transport = createCorePayloadTransport(tracedPayload);
    } catch (error) {
      reject(error instanceof Error ? error : new Error(String(error)));
      return;
    }
    // The dedicated Chrome profile inherits the parent process' show state on
    // Windows. Do not hide the short-lived core process that starts OAuth, or
    // Chrome can exit without creating its visible authorization window.
    const windowsHide = command !== 'start-youtube-channel-handoff';
    try {
      execFile(executable, args,
      {
        windowsHide,
        cwd: coreRoot,
        maxBuffer: 1024 * 1024 * 8,
        env: {
          ...process.env,
          PYTHONPATH: coreRoot,
          // The Python queue invokes this Electron runtime in Node mode, so a
          // packaged NewsFlow has a real Remotion renderer without requiring
          // a separately installed Node.js or a global Remotion CLI.
          NEWSFLOW_REMOTION_NODE: process.execPath,
          NEWSFLOW_REMOTION_RUNNER: remotionRunner,
          NEWSFLOW_REMOTION_FRAME_CONCURRENCY: process.env.NEWSFLOW_REMOTION_FRAME_CONCURRENCY || '2',
          NEWSFLOW_BRIDGE_PAYLOAD_FILE: transport.path,
        },
      }, (error, stdout, stderr) => {
        transport.dispose();
        if (error) {
          try {
            const response = JSON.parse(stdout);
            if (response?.error) return reject(new Error(String(response.error)));
          } catch { /* process error below is the useful fallback */ }
          return reject(new Error(stderr || error.message));
        }
        try {
          const response = JSON.parse(stdout);
          registerApprovedOpenPaths(response);
          resolve(response);
        } catch { reject(new Error(`Некорректный ответ ядра: ${stdout || stderr}`)); }
      });
    } catch (error) {
      transport.dispose();
      reject(error instanceof Error ? error : new Error(String(error)));
    }
  });
}

type OAuthJobState = 'waiting' | 'succeeded' | 'failed' | 'cancelled';
type PublicOAuthJob = { id: string; channelIndex: number; state: OAuthJobState; expiresAt: string; message?: string };
type PrivateOAuthJob = PublicOAuthJob & { session: Record<string, unknown> };
const youtubeOAuthJobs = new Map<string, PrivateOAuthJob>();

async function startYoutubeOAuthHandoff(input: { index: number; includeMonetary: boolean }): Promise<PublicOAuthJob> {
  if ([...youtubeOAuthJobs.values()].some(job => job.channelIndex === input.index && job.state === 'waiting')) {
    throw new Error('Для этого канала уже ожидается подтверждение Google.');
  }
  const started = await callCore('start-youtube-channel-handoff', input) as { session?: Record<string, unknown> };
  const session = started.session;
  if (!session || typeof session.sessionId !== 'string' || typeof session.expiresAt !== 'string') {
    throw new Error('Ядро NewsFlow не вернуло сессию входа.');
  }
  const id = crypto.randomUUID();
  const job: PrivateOAuthJob = { id, channelIndex: input.index, state: 'waiting', expiresAt: session.expiresAt, session };
  youtubeOAuthJobs.set(id, job);
  void callCore('finish-youtube-channel-handoff', { index: input.index, session }).then(() => {
    const current = youtubeOAuthJobs.get(id);
    if (current?.state === 'waiting') {
      current.state = 'succeeded';
      current.message = 'Канал подключён.';
    }
  }).catch((error: unknown) => {
    const current = youtubeOAuthJobs.get(id);
    if (current?.state === 'waiting') {
      current.state = 'failed';
      current.message = error instanceof Error ? error.message : 'Не удалось завершить вход.';
    }
  });
  return { id: job.id, channelIndex: job.channelIndex, state: job.state, expiresAt: job.expiresAt };
}

async function cancelYoutubeOAuthHandoff(id: string): Promise<PublicOAuthJob> {
  const job = youtubeOAuthJobs.get(id);
  if (!job) throw new Error('Сессия входа не найдена.');
  if (job.state === 'waiting') await callCore('cancel-youtube-channel-handoff', { session: job.session });
  job.state = 'cancelled';
  job.message = 'Вход в Google отменён.';
  return { id: job.id, channelIndex: job.channelIndex, state: job.state, expiresAt: job.expiresAt, message: job.message };
}

function startMontageQueue(payload: unknown = {}): Promise<void> {
  const executable = pythonExecutable();
  const bundled = app.isPackaged && executable.toLowerCase().endsWith('.exe') && executable.includes('core-bin');
  const tracedPayload = actionTracePayload(payload);
  const args = bundled ? ['run-montage-queue', JSON.stringify(tracedPayload)] : ['-m', 'scriptor.bridge', 'run-montage-queue', JSON.stringify(tracedPayload)];
  return new Promise((resolve, reject) => {
    const child = spawn(executable, args, { windowsHide: true, cwd: coreRoot, detached: false, stdio: 'ignore', env: { ...process.env, PYTHONPATH: coreRoot, NEWSFLOW_REMOTION_NODE: process.execPath, NEWSFLOW_REMOTION_RUNNER: remotionRunner, NEWSFLOW_REMOTION_FRAME_CONCURRENCY: process.env.NEWSFLOW_REMOTION_FRAME_CONCURRENCY || '2' } });
    child.once('error', (error) => reject(new Error(`Не удалось запустить очередь монтажа: ${error.message}`)));
    child.once('spawn', () => {
      child.unref();
      resolve();
    });
  });
}

function readFootageIndexStatus() {
  // Indexing can run for a long time. Reading this tiny local status file is
  // deliberately independent from a full Python snapshot, which may include
  // slow project-wide checks and used to leave the progress panel stale.
  const root = process.env.LOCALAPPDATA || app.getPath('userData');
  const statusPath = path.join(root, 'NewsFlow', 'footage-index-status.json');
  try {
    return JSON.parse(readFileSync(statusPath, 'utf8'));
  } catch {
    return {};
  }
}

let fastGenResumeRunning = false;
async function resumeFastGenAtHourlyReset() {
  // FastGen refreshes quotas at HH:00. Waiting until HH:01 avoids racing the
  // provider's accounting and works even while the covers screen is closed.
  if (fastGenResumeRunning || new Date().getMinutes() !== 1) return;
  try {
    const state = await callCore('snapshot') as { covers?: Array<{ status?: string; rate_limit_wait_until?: string }> };
    const now = Date.now();
    const due = (state.covers || []).some((cover) =>
      cover.status === 'Ожидает лимит FastGen' &&
      (!cover.rate_limit_wait_until || new Date(cover.rate_limit_wait_until).getTime() <= now),
    );
    if (!due) return;
    fastGenResumeRunning = true;
    await callCore('refresh-fastgen');
    await callCore('resume-cover-generation');
  } catch {
    // The queued rows stay persisted; the next minute-01 check retries them.
  } finally {
    fastGenResumeRunning = false;
  }
}

function createWindow() {
  const window = new BrowserWindow({
    width: 1440, height: 900, minWidth: 720, minHeight: 720,
    backgroundColor: '#07101d', title: environmentWindowTitle(process.env),
    webPreferences: { preload: path.join(dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  window.setMenuBarVisibility(false);
  window.webContents.setWindowOpenHandler(({ url }) => {
    try {
      const target = new URL(url);
      if (target.protocol === 'https:' || target.protocol === 'http:') void shell.openExternal(target.toString());
    } catch { /* invalid renderer target remains blocked */ }
    return { action: 'deny' };
  });
  window.webContents.on('will-navigate', (event, url) => {
    if (url !== window.webContents.getURL()) event.preventDefault();
  });
  void window.loadFile(path.join(dirname, '../dist/index.html'));
}

app.whenReady().then(() => {
  Menu.setApplicationMenu(null);
  createWindow();
  setInterval(() => void resumeFastGenAtHourlyReset(), 15_000);
  void resumeFastGenAtHourlyReset();
  app.on('activate', () => { if (!BrowserWindow.getAllWindows().length) createWindow(); });
});
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit(); });

function assertTrustedIpcSender(event: IpcMainInvokeEvent): void {
  const window = BrowserWindow.fromWebContents(event.sender);
  const senderUrl = event.senderFrame?.url || '';
  if (!window || event.sender !== window.webContents || !senderUrl.startsWith('file:')) {
    throw new Error('IPC отклонён: недоверенный renderer.');
  }
}

type TrustedIpcHandler = (event: IpcMainInvokeEvent, ...args: any[]) => unknown;
function handleTrusted(channel: string, handler: TrustedIpcHandler): void {
  ipcMain.handle(channel, (event, ...args) => {
    assertTrustedIpcSender(event);
    return handler(event, ...args);
  });
}

handleTrusted('newsflow:snapshot', () => callCore('snapshot'));
handleTrusted('newsflow:footage-index-status', () => readFootageIndexStatus());
handleTrusted('newsflow:open-path', (_event, target: unknown) => openApprovedPath(target));
handleTrusted('newsflow:save-settings', (_event, patch: unknown) => callCore('save-settings', patch));
handleTrusted('newsflow:command', async (_event, command: unknown, payload: unknown) => {
  assertAllowedCoreCommand(command);
  if (command === 'run-montage-queue') {
    await startMontageQueue(payload);
    await new Promise(resolve => setTimeout(resolve, 180));
    return callCore('snapshot');
  }
  return callCore(command, payload);
});
handleTrusted('newsflow:youtube-oauth-start', (_event, input: { index: number; includeMonetary: boolean }) => startYoutubeOAuthHandoff(input));
handleTrusted('newsflow:youtube-oauth-status', (_event, id: string) => {
  const job = youtubeOAuthJobs.get(id);
  return job ? { id: job.id, channelIndex: job.channelIndex, state: job.state, expiresAt: job.expiresAt, message: job.message } : null;
});
handleTrusted('newsflow:youtube-oauth-cancel', (_event, id: string) => cancelYoutubeOAuthHandoff(id));
handleTrusted('newsflow:choose-folder', async () => {
  const result = await dialog.showOpenDialog({ properties: ['openDirectory', 'createDirectory'] });
  return result.canceled ? '' : result.filePaths[0] || '';
});
handleTrusted('newsflow:choose-videos', async () => {
  const result = await dialog.showOpenDialog({ properties: ['openFile', 'multiSelections'], filters: [{ name: 'Видео', extensions: ['mp4', 'mov', 'mkv', 'webm', 'avi', 'm4v'] }] });
  return result.canceled ? [] : result.filePaths;
});
handleTrusted('newsflow:choose-images', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openFile', 'multiSelections'],
    filters: [{ name: 'Изображения', extensions: ['png', 'jpg', 'jpeg', 'webp'] }],
  });
  return result.canceled ? [] : result.filePaths;
});
handleTrusted('newsflow:choose-audio', async () => {
  const result = await dialog.showOpenDialog({ properties: ['openFile', 'multiSelections'], filters: [{ name: 'Аудио или ZIP', extensions: ['mp3', 'wav', 'm4a', 'aac', 'ogg', 'flac', 'zip'] }] });
  return result.canceled ? '' : result.filePaths[0] || '';
});
handleTrusted('newsflow:choose-audio-files', async () => {
  const result = await dialog.showOpenDialog({ properties: ['openFile', 'multiSelections'], filters: [{ name: 'Аудио или ZIP', extensions: ['mp3', 'wav', 'm4a', 'aac', 'ogg', 'flac', 'zip'] }] });
  return result.canceled ? [] : result.filePaths;
});
handleTrusted('newsflow:choose-json', async () => {
  const result = await dialog.showOpenDialog({ properties: ['openFile'], filters: [{ name: 'Google OAuth JSON', extensions: ['json'] }] });
  return result.canceled ? '' : result.filePaths[0] || '';
});
handleTrusted('newsflow:choose-prompt-text', async () => {
  const result = await dialog.showOpenDialog({ properties: ['openFile'], filters: [{ name: 'Промпты', extensions: ['txt', 'md', 'markdown'] }] });
  const file = result.canceled ? '' : result.filePaths[0] || '';
  if (!file) return '';
  const text = readFileSync(file, 'utf8');
  if (text.length > 1_000_000) throw new Error('Файл промпта больше 1 МБ. Разделите его на несколько TXT-файлов.');
  return text;
});
handleTrusted('newsflow:choose-scenario-texts', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openFile', 'multiSelections'],
    filters: [{ name: 'Сценарии TXT / Markdown', extensions: ['txt', 'md', 'markdown'] }],
  });
  if (result.canceled) return [];
  return result.filePaths.map(file => {
    const text = readFileSync(file, 'utf8');
    if (text.length > 1_000_000) throw new Error(`Файл «${path.basename(file)}» больше 1 МБ. Разделите его на несколько TXT.`);
    return { title: path.parse(file).name, text };
  }).filter(item => item.text.trim());
});
handleTrusted('newsflow:choose-save-path', async (_event, suggestedName: string) => {
  const result = await dialog.showSaveDialog({
    defaultPath: suggestedName || 'Сценарии.txt',
    filters: [{ name: 'Текстовые файлы', extensions: ['txt'] }],
  });
  return result.canceled ? '' : result.filePath || '';
});
handleTrusted('newsflow:choose-zip-save-path', async (_event, suggestedName: string) => {
  const result = await dialog.showSaveDialog({
    defaultPath: suggestedName || 'Обложки NewsFlow.zip',
    filters: [{ name: 'ZIP-архив', extensions: ['zip'] }],
  });
  return result.canceled ? '' : result.filePath || '';
});
handleTrusted('newsflow:choose-audio-save-path', async (_event, suggestedName: string) => {
  const result = await dialog.showSaveDialog({
    defaultPath: suggestedName || 'Озвучка.mp3',
    filters: [{ name: 'MP3', extensions: ['mp3'] }],
  });
  return result.canceled ? '' : result.filePath || '';
});
