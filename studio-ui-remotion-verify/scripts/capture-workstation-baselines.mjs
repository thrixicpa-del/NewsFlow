import { app, BrowserWindow, nativeImage } from "electron";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import process from "node:process";

if (process.env.NEWSFLOW_TEST_MODE !== "1") {
  throw new Error("Visual capture is test-only. Set NEWSFLOW_TEST_MODE=1.");
}

const root = process.cwd();
const artifactRoot = path.join(root, ".artifacts", "workstation-visual-baselines");
const testUserData = path.join(tmpdir(), "NewsFlow-workstation-visual-test-user-data");
// Approved references are versioned test fixtures so a clean checkout can run
// the same comparison. Current captures and manifests remain disposable.
const baselineRoot = path.join(root, "tests", "visual-baselines", "approved");
const currentRoot = path.join(artifactRoot, "current");
const sourceUrl = process.env.NEWSFLOW_VISUAL_BASELINE_URL || "http://127.0.0.1:5174/";
const updateBaselines = process.env.NEWSFLOW_UPDATE_VISUAL_BASELINES === "1";
const requestedCaseIds = process.env.NEWSFLOW_VISUAL_CASES?.split(",").map((value) => value.trim()).filter(Boolean);

const cases = [
  { id: "dashboard-empty", steps: ["Центр управления"], expectedTitle: "Центр управления" },
  { id: "topics-empty", steps: ["Генерация идей"], expectedTitle: "Генерация идей" },
  { id: "topics-narrow", steps: ["Генерация идей"], expectedTitle: "Генерация идей", viewport: { width: 390, height: 844 } },
  { id: "scenarios-empty", steps: ["Новости"], expectedTitle: "Новости и сценарии" },
  { id: "scripts-empty", steps: ["Готовые сценарии"], expectedTitle: "Готовые сценарии" },
  { id: "templates-empty", steps: ["Шаблоны"], expectedTitle: "Шаблоны и промпты" },
  { id: "agents-empty", steps: ["Агенты NewsFlow"], expectedTitle: "Агенты NewsFlow" },
  { id: "covers-empty", steps: ["ОБЛОЖКИ И ГЕНЕРАЦИИ", "Обложки YouTube"], expectedTitle: "Обложки YouTube" },
  { id: "covers-narrow", fixture: "covers-84", steps: ["ОБЛОЖКИ И ГЕНЕРАЦИИ", "Обложки YouTube"], expectedTitle: "Обложки YouTube", viewport: { width: 390, height: 844 } },
  { id: "covers-failed", fixture: "task-states", steps: ["ОБЛОЖКИ И ГЕНЕРАЦИИ", "Обложки YouTube"], expectedTitle: "Обложки YouTube" },
  { id: "covers-84", fixture: "covers-84", steps: ["ОБЛОЖКИ И ГЕНЕРАЦИИ", "Обложки YouTube"], expectedTitle: "Обложки YouTube", performanceBudgetMs: 3000 },
  { id: "covers-inspector", fixture: "covers-84", steps: ["ОБЛОЖКИ И ГЕНЕРАЦИИ", "Обложки YouTube", "1. Визуальная проверка обложки 01"], expectedTitle: "Обложки YouTube" },
  { id: "covers-configuration", steps: ["ОБЛОЖКИ И ГЕНЕРАЦИИ", "Обложки YouTube", "Настроить студию"], expectedTitle: "Обложки YouTube", expectedDialog: "Настройки Visual Production Studio" },
  { id: "cover-gallery-empty", steps: ["ОБЛОЖКИ И ГЕНЕРАЦИИ", "Галерея обложек"], expectedTitle: "Галерея обложек" },
  { id: "media-empty", steps: ["ОБЛОЖКИ И ГЕНЕРАЦИИ", "Картинки и видео"], expectedTitle: "Картинки и видео" },
  { id: "footage-empty", steps: ["ПРОИЗВОДСТВО", "Футажи — поиск"], expectedTitle: "Футажи" },
  { id: "cutter-empty", steps: ["ПРОИЗВОДСТВО", "Футажи — нарезка"], expectedTitle: "Нарезка футажей" },
  { id: "voice-empty", steps: ["ПРОИЗВОДСТВО", "Озвучка — очередь"], expectedTitle: "Очередь озвучки" },
  { id: "voice-waiting", fixture: "task-states", steps: ["ПРОИЗВОДСТВО", "Озвучка — очередь"], expectedTitle: "Очередь озвучки" },
  { id: "voice-84", fixture: "voice-84", steps: ["ПРОИЗВОДСТВО", "Озвучка — очередь"], expectedTitle: "Очередь озвучки", performanceBudgetMs: 3000 },
  { id: "audio-inspector", fixture: "voice-84", steps: ["ПРОИЗВОДСТВО", "Озвучка — готовые MP3", "1. Визуальная проверка сценария 01"], expectedTitle: "Готовые MP3" },
  { id: "voice-provider-readiness", steps: ["ПРОИЗВОДСТВО", "Озвучка — голоса", "Проверить готовность провайдеров"], expectedTitle: "Профили голосов", expectedDialog: "Готовность провайдеров озвучки" },
  { id: "voice-profiles-empty", steps: ["ПРОИЗВОДСТВО", "Озвучка — голоса"], expectedTitle: "Профили голосов" },
  { id: "audio-empty", steps: ["ПРОИЗВОДСТВО", "Озвучка — готовые MP3"], expectedTitle: "Готовые MP3" },
  { id: "montage-empty", steps: ["ПРОИЗВОДСТВО", "Монтаж"], expectedTitle: "Монтаж" },
  { id: "montage-ready", fixture: "task-states", steps: ["ПРОИЗВОДСТВО", "Монтаж"], expectedTitle: "Монтаж" },
  { id: "montage-84", fixture: "montage-84", steps: ["ПРОИЗВОДСТВО", "Монтаж"], expectedTitle: "Монтаж", performanceBudgetMs: 3000 },
  { id: "montage-inspector", fixture: "montage-84", steps: ["ПРОИЗВОДСТВО", "Монтаж", "Инспектор MP4"], expectedTitle: "Монтаж" },
  { id: "montage-configuration", steps: ["ПРОИЗВОДСТВО", "Монтаж", "Настроить монтаж"], expectedTitle: "Монтаж", expectedDialog: "Настройки Fast News монтажа" },
  { id: "publication-empty", steps: ["ПУБЛИКАЦИЯ", "Публикация YouTube"] },
  { id: "publication-paused", fixture: "task-states", steps: ["ПУБЛИКАЦИЯ", "Публикация YouTube"] },
  { id: "publication-84", fixture: "publication-84", steps: ["ПУБЛИКАЦИЯ", "Публикация YouTube"], expectedText: "Визуальный ролик 01", performanceBudgetMs: 3000 },
  { id: "publication-narrow", fixture: "publication-84", steps: ["ПУБЛИКАЦИЯ", "Публикация YouTube"], expectedText: "Визуальный ролик 01", viewport: { width: 390, height: 844 } },
  { id: "publication-day-plan", fixture: "publication-84", steps: ["ПУБЛИКАЦИЯ", "Публикация YouTube", "План дня"], expectedText: "04:15", performanceBudgetMs: 3000 },
  { id: "publication-queue-ads", fixture: "publication-84", steps: ["ПУБЛИКАЦИЯ", "Публикация YouTube", "Очередь"], expectedText: "AUTO + MANUAL 39s", performanceBudgetMs: 3000 },
  { id: "publication-receipt", fixture: "publication-receipt", steps: ["ПУБЛИКАЦИЯ", "Публикация YouTube", "История", "Визуальный receipt публикации"], expectedDialog: "Визуальный receipt публикации" },
  { id: "seo-empty", steps: ["ПУБЛИКАЦИЯ", "SEO-пакеты"], expectedTitle: "SEO-пакеты" },
  { id: "tags-empty", steps: ["ПУБЛИКАЦИЯ", "Теги"], expectedTitle: "Теги" },
  { id: "seo-ready", fixture: "metadata-ready", steps: ["ПУБЛИКАЦИЯ", "SEO-пакеты"], expectedTitle: "SEO-пакеты" },
  { id: "tags-ready", fixture: "metadata-ready", steps: ["ПУБЛИКАЦИЯ", "Теги"], expectedTitle: "Теги" },
  { id: "analytics-oauth-waiting", fixture: "analytics-oauth-waiting", oauthAdapter: true, steps: ["ПУБЛИКАЦИЯ", "Аналитика", "OAuth"], expectedTitle: "Аналитика и каналы", expectedText: "Ожидаем входа в Google" },
  { id: "outputs-empty", steps: ["ПУБЛИКАЦИЯ", "Результаты"], expectedTitle: "Результаты" },
  { id: "sidebar-collapsed", steps: ["Свернуть навигацию"], expectedTitle: "Центр управления" },
  { id: "sessions-empty", steps: ["НАСТРОЙКИ", "Сессии Chrome"], expectedTitle: "Сессии Chrome" },
  { id: "knowledge-empty", steps: ["НАСТРОЙКИ", "База проекта"], expectedTitle: "База проекта" },
  { id: "keys-discard-dialog", actions: [{ click: "НАСТРОЙКИ" }, { click: "API-ключи" }, { click: "Добавить ключ" }, { fill: { label: "API-ключ", value: "visual-fixture-key" } }, { click: "Центр управления" }], expectedTitle: "API-ключи", expectedDialog: "Несохранённые изменения", cleanupSteps: ["Не сохранять"] },
  { id: "task-states-inspector", fixture: "task-states", steps: ["Центр управления", "Открыть задачу: Озвучка ожидает провайдера"], expectedTitle: "Центр управления" },
];

const selectedCases = requestedCaseIds?.length
  ? cases.filter((visualCase) => requestedCaseIds.includes(visualCase.id))
  : cases;

if (!selectedCases.length || (requestedCaseIds && selectedCases.length !== requestedCaseIds.length)) {
  throw new Error(`Unknown visual baseline case: ${requestedCaseIds?.join(", ") || "none"}`);
}

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function startDisposableVite() {
  if (process.env.NEWSFLOW_VISUAL_BASELINE_URL) return null;
  const viteCli = path.join(root, "node_modules", "vite", "bin", "vite.js");
  const vite = spawn(process.execPath, [viteCli, "--host", "127.0.0.1", "--port", "5174", "--strictPort"], {
    cwd: root,
    stdio: "ignore",
    windowsHide: true,
    env: { ...process.env, ELECTRON_RUN_AS_NODE: "1" },
  });
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(sourceUrl);
      if (response.ok) return vite;
    } catch {
      // The development server is still starting.
    }
    await delay(100);
  }
  vite.kill();
  throw new Error(`Disposable Vite server did not become available: ${sourceUrl}`);
}

async function stopDisposableVite(vite) {
  if (!vite || vite.exitCode !== null) return;
  // Electron's Node-mode Vite child can retain Chromium descendants on
  // Windows. It is spawned above with an isolated test root, so terminating
  // this exact child tree is safe and prevents a release gate deadlock.
  if (process.platform === "win32" && vite.pid) {
    const taskkill = spawn("taskkill.exe", ["/pid", String(vite.pid), "/t", "/f"], {
      stdio: "ignore",
      windowsHide: true,
    });
    await Promise.race([once(taskkill, "close"), delay(5_000)]);
  } else {
    vite.kill("SIGTERM");
  }
  if (vite.exitCode === null) await Promise.race([once(vite, "exit"), delay(5_000)]);
}

async function clickVisibleButton(window, label) {
  const deadline = Date.now() + 20_000;
  while (Date.now() < deadline) {
    const clicked = await window.webContents.executeJavaScript(`(() => {
      const label = ${JSON.stringify(label)};
      const button = [...document.querySelectorAll('.nf-sidebar-nav button'), ...document.querySelectorAll('button')].find((candidate) =>
        candidate.offsetParent !== null && (candidate.textContent?.trim() === label || candidate.getAttribute('aria-label') === label),
      );
      if (!button) return false;
      button.click();
      return true;
    })()`);
    if (clicked) {
      await delay(50);
      return;
    }
    await delay(50);
  }
  const renderedDocument = await window.webContents.executeJavaScript("document.documentElement.outerHTML.slice(0, 1200)");
  const importDiagnostic = await window.webContents.executeJavaScript("import('/src/main.tsx').then(() => 'module-loaded').catch((error) => String(error))");
  throw new Error(`Visual baseline navigation control not found: ${label}. Module: ${importDiagnostic}. Document: ${renderedDocument}`);
}

async function fillVisibleField(window, label, value) {
  const filled = await window.webContents.executeJavaScript(`(() => {
    const labelText = ${JSON.stringify(label)};
    const value = ${JSON.stringify(value)};
    const label = [...document.querySelectorAll('label')].find((candidate) =>
      candidate.offsetParent !== null && candidate.textContent?.trim().startsWith(labelText),
    );
    const field = label?.querySelector('input, textarea, select');
    if (!(field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement || field instanceof HTMLSelectElement)) return false;
    const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(field), 'value')?.set;
    setter?.call(field, value);
    field.dispatchEvent(new Event('input', { bubbles: true }));
    field.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  })()`);
  if (!filled) throw new Error(`Visual baseline input not found: ${label}`);
  await delay(50);
}

async function installVisualOauthAdapter(window) {
  const installed = await window.webContents.executeJavaScript(`(() => {
    const job = { id: "visual-oauth-waiting", channelIndex: 0, state: "waiting", expiresAt: "2099-01-01T00:00:00Z", message: "Тестовый OAuth handoff: внешний браузер не открывался." };
    window.newsflowDesktop = {
      ...(window.newsflowDesktop || {}),
      startYoutubeOAuthHandoff: async () => job,
      youtubeOAuthHandoffStatus: async () => job,
      cancelYoutubeOAuthHandoff: async () => ({ ...job, state: "cancelled" }),
    };
    return window.newsflowDesktop.startYoutubeOAuthHandoff !== undefined;
  })()`);
  if (!installed) throw new Error("Visual OAuth adapter was not installed.");
}

async function waitForVisualSettle(window) {
  await window.webContents.executeJavaScript(`document.fonts.ready.then(() => new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  }))`);
  // Wait for the renderer's actual transition state rather than an arbitrary
  // delay: a Radix portal can mount after the click handler has returned.
  await window.webContents.executeJavaScript(`new Promise((resolve) => {
    const deadline = performance.now() + 1500;
    const check = () => {
      const running = document.getAnimations().some((animation) => animation.playState === 'running');
      if (!running || performance.now() >= deadline) return resolve(undefined);
      requestAnimationFrame(check);
    };
    requestAnimationFrame(check);
  })`);
  await delay(40);
}

function pixelDifference(left, right) {
  if (left.length !== right.length) return 1;
  let changed = 0;
  for (let index = 0; index < left.length; index += 4) {
    if (left[index] !== right[index] || left[index + 1] !== right[index + 1] || left[index + 2] !== right[index + 2] || left[index + 3] !== right[index + 3]) changed += 1;
  }
  return changed / (left.length / 4);
}

function pixelDifferenceDetails(left, right, width) {
  if (left.length !== right.length) return { fraction: 1, bounds: "image-size-mismatch" };
  let changed = 0;
  let minX = width;
  let minY = left.length / 4 / width;
  let maxX = -1;
  let maxY = -1;
  for (let index = 0; index < left.length; index += 4) {
    if (left[index] === right[index] && left[index + 1] === right[index + 1] && left[index + 2] === right[index + 2] && left[index + 3] === right[index + 3]) continue;
    changed += 1;
    const pixel = index / 4;
    const x = pixel % width;
    const y = Math.floor(pixel / width);
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  }
  return { fraction: changed / (left.length / 4), bounds: changed ? `${minX},${minY}–${maxX},${maxY}` : "none" };
}

async function captureStablePage(window) {
  let previousPng = null;
  let stableFrames = 0;
  for (let frame = 0; frame < 18; frame += 1) {
    const currentPng = (await window.webContents.capturePage()).toPNG();
    if (previousPng) {
      const previousImage = nativeImage.createFromBuffer(previousPng);
      const currentImage = nativeImage.createFromBuffer(currentPng);
      if (pixelDifference(currentImage.toBitmap(), previousImage.toBitmap()) === 0) {
        stableFrames += 1;
        if (stableFrames >= 14) return currentPng;
      } else {
        stableFrames = 0;
      }
    }
    previousPng = currentPng;
    await delay(100);
  }
  return previousPng;
}

async function captureBaselines() {
  await rm(testUserData, { recursive: true, force: true });
  await mkdir(testUserData, { recursive: true });
  await writeFile(path.join(testUserData, ".newsflow-test-root"), "workstation visual baseline only\n");
  app.setPath("userData", testUserData);
  await app.whenReady();
  await mkdir(currentRoot, { recursive: true });
  if (updateBaselines) await mkdir(baselineRoot, { recursive: true });
  const vite = await startDisposableVite();
  const window = new BrowserWindow({
    show: false,
    width: 1440,
    height: 960,
    useContentSize: true,
    webPreferences: { contextIsolation: true, backgroundThrottling: false },
  });
  window.webContents.on("console-message", (_event, level, message) => {
    if (level >= 2 && !message.includes("Electron Security Warning")) console.error(`Visual renderer console: ${message}`);
  });
  window.webContents.on("did-fail-load", (_event, code, description, url) => {
    console.error(`Visual renderer load failed (${code}): ${description} ${url}`);
  });
  try {
    const results = [];
    for (const visualCase of selectedCases) {
      const viewport = visualCase.viewport ?? { width: 1440, height: 960 };
      await window.setContentSize(viewport.width, viewport.height);
      const url = new URL(sourceUrl);
      if (visualCase.fixture) url.searchParams.set("visual-fixture", visualCase.fixture);
      if (window.webContents.getURL().startsWith(sourceUrl)) {
        try {
          await window.webContents.executeJavaScript("localStorage.clear()");
        } catch {
          // A failed disposable preference reset must never read or write user data.
        }
      }
      await window.loadURL(url.href);
      const actualViewport = await window.webContents.executeJavaScript("({ width: window.innerWidth, height: window.innerHeight })");
      if (actualViewport.width !== viewport.width || actualViewport.height !== viewport.height) {
        throw new Error(`${visualCase.id}: requested ${viewport.width}x${viewport.height}, rendered ${actualViewport.width}x${actualViewport.height}`);
      }
      if (visualCase.oauthAdapter) await installVisualOauthAdapter(window);
      // Prime the first compositor frame before an overlay-only case. Without
      // this, a cold Electron renderer can capture a Radix portal before its
      // first fully composed frame even when the DOM is already stable.
      if (visualCase.expectedDialog) await captureStablePage(window);
      const navigationStartedAt = performance.now();
      const actions = visualCase.actions || visualCase.steps.map((step) => ({ click: step }));
      for (const action of actions) {
        if (action.click) await clickVisibleButton(window, action.click);
        if (action.fill) await fillVisibleField(window, action.fill.label, action.fill.value);
      }
      if (visualCase.expectedTitle) {
        const renderedTitle = await window.webContents.executeJavaScript("document.querySelector('.nf-page-header h1')?.textContent?.trim() ?? ''");
        if (!renderedTitle.includes(visualCase.expectedTitle)) {
          throw new Error(`${visualCase.id}: expected workspace title ${visualCase.expectedTitle}, got ${renderedTitle || "none"}`);
        }
      }
      if (visualCase.expectedDialog) {
        const renderedDialog = await window.webContents.executeJavaScript(`(() => {
          const expected = ${JSON.stringify(visualCase.expectedDialog)};
          return [...document.querySelectorAll('[role="dialog"]')].some((dialog) =>
            dialog.textContent?.includes(expected),
          );
        })()`);
        if (!renderedDialog) {
          const diagnostic = await window.webContents.executeJavaScript(`JSON.stringify({
            title: document.querySelector('.nf-page-header h1')?.textContent?.trim(),
            inputs: [...document.querySelectorAll('input')].map((input) => ({ type: input.type, value: input.value })),
            dialogs: [...document.querySelectorAll('[role="dialog"]')].map((dialog) => dialog.textContent?.trim()),
          })`);
          throw new Error(`${visualCase.id}: expected visible dialog ${visualCase.expectedDialog}; state ${diagnostic}`);
        }
      }
      if (visualCase.expectedText) {
        const visibleText = await window.webContents.executeJavaScript(`document.body.innerText.includes(${JSON.stringify(visualCase.expectedText)})`);
        if (!visibleText) throw new Error(`${visualCase.id}: expected visible text ${visualCase.expectedText}`);
      }
      const navigationMs = performance.now() - navigationStartedAt;
      if (visualCase.performanceBudgetMs && navigationMs > visualCase.performanceBudgetMs) {
        throw new Error(`${visualCase.id}: route navigation took ${navigationMs.toFixed(0)}ms, exceeding ${visualCase.performanceBudgetMs}ms`);
      }
      await waitForVisualSettle(window);
      const currentPath = path.join(currentRoot, `${visualCase.id}.png`);
      const currentPng = await captureStablePage(window);
      await writeFile(currentPath, currentPng);
      const baselinePath = path.join(baselineRoot, `${visualCase.id}.png`);
      if (updateBaselines) {
        await writeFile(baselinePath, currentPng);
        results.push({ id: visualCase.id, status: "baseline-updated", changedPixels: 0, navigationMs: Math.round(navigationMs) });
      } else {
        const baselinePng = await readFile(baselinePath);
        const baselineImage = nativeImage.createFromBuffer(baselinePng);
        // Normalize both operands through PNG decoding. `capturePage()` can keep
        // a platform-specific alpha representation while a saved PNG is decoded
        // to straight RGBA; comparing those raw buffers reports an all-pixel
        // regression for an otherwise identical modal capture.
        const currentImage = nativeImage.createFromBuffer(currentPng);
        const details = pixelDifferenceDetails(currentImage.toBitmap(), baselineImage.toBitmap(), currentImage.getSize().width);
        const changedPixels = details.fraction;
        if (changedPixels > 0.002) {
          throw new Error(`${visualCase.id}: visual difference ${(changedPixels * 100).toFixed(3)}% exceeds 0.200%; bounds ${details.bounds}`);
        }
        results.push({ id: visualCase.id, status: "matched", changedPixels, navigationMs: Math.round(navigationMs) });
      }
      for (const label of visualCase.cleanupSteps || []) await clickVisibleButton(window, label);
    }
    await writeFile(path.join(artifactRoot, "manifest.json"), JSON.stringify({ sourceUrl, dataRoot: testUserData, results }, null, 2));
    console.log(JSON.stringify(results));
  } finally {
    if (!window.isDestroyed()) window.destroy();
    await stopDisposableVite(vite);
    app.exit();
  }
}

void captureBaselines().then(
  () => process.exit(0),
  (error) => {
    console.error(error);
    app.exit();
    process.exit(1);
  },
);
