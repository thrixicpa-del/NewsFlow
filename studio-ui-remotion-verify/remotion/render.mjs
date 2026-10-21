/*
 * Invoked by the Python core through Electron in Node mode. Keeping this
 * adapter next to the Electron dependencies makes the packaged installer
 * self-contained: it does not require a global Node.js or a Remotion CLI.
 */
import { readFile, mkdir, rm, stat, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createLocalMediaServer } from './local-media-server.mjs';

const here = dirname(fileURLToPath(import.meta.url));
// The final application does not bundle React at render time.  It receives a
// prebuilt static composition in app.asar.unpacked/remotion-bundle, produced
// by scripts/build-remotion.mjs before electron-builder runs.  This avoids
// spawning esbuild from app.asar on Windows.
const packedModules = process.resourcesPath && existsSync(join(process.resourcesPath, 'app.asar'))
  ? join(process.resourcesPath, 'app.asar', 'node_modules')
  : '';
const importRuntime = async (packageFile, developmentPackage) => packedModules
  ? import(pathToFileURL(join(packedModules, packageFile)).href)
  : import(developmentPackage);
const { renderMedia, selectComposition } = await importRuntime('@remotion/renderer/dist/index.js', '@remotion/renderer');
const [manifestPath, outputPath, concurrencyRaw = '1', parallelJobsRaw = '1'] = process.argv.slice(2);

if (!manifestPath || !outputPath) {
  console.error('Usage: render.mjs <manifest.json> <output.mp4> [concurrency]');
  process.exit(2);
}

const project = JSON.parse(await readFile(manifestPath, 'utf8'));
// Chroma/alpha/audio finishing is shared by all renderers in the Python core.
// A standalone manifest must fail before it can publish a layer-less MP4.
const activeOverlayLayers = project.overlayTemplate?.layouts?.[project.aspectRatio] || [];
const overlaySources = new Map((project.overlayTemplate?.librarySources || []).map((source) => [source.id, source]));
const layerIsActive = (layer) => {
  if (layer.enabled === false) return false;
  if (!layer.librarySourceId) return true;
  const source = overlaySources.get(layer.librarySourceId);
  // Unknown references are invalid rather than permission to silently drop a layer.
  return !source || (source.enabled !== false && (!source.kind || source.kind === 'all' || source.kind === layer.kind));
};
if (project.requiresOverlayFinishing || project.overlay?.src
    || activeOverlayLayers.some(layerIsActive)) {
  throw new Error('OVERLAY_FINISHING_REQUIRED: экспортируйте проект через NewsFlow — наложения требуют общего этапа композиции.');
}

const requestedConcurrency = Math.max(1, Number.parseInt(concurrencyRaw, 10) || 1);
const parallelJobs = Math.max(1, Number.parseInt(parallelJobsRaw, 10) || 1);
const concurrency = requestedConcurrency;
const timeoutInMilliseconds = Math.max(60_000, Number.parseInt(process.env.NEWSFLOW_REMOTION_TIMEOUT_MS || '180000', 10) || 180000);
// The native Remotion compositor and its ffmpeg/ffprobe executables are
// unpacked by electron-builder. `require('@remotion/compositor-…').dir`
// still points into app.asar, which Windows cannot spawn from. Pass the real
// unpacked directory to the renderer explicitly for every final render.
// Native Windows executables must never live inside app.asar.  electron-builder
// copies this package to the separate `resources/remotion-binaries` folder via
// extraResources.  The old app.asar.unpacked location is kept only as a
// compatibility fallback for a development preview.
const packagedBinaries = packedModules ? join(process.resourcesPath, 'remotion-binaries') : '';
const legacyUnpackedBinaries = packedModules
  ? join(process.resourcesPath, 'app.asar.unpacked', 'node_modules', '@remotion', 'compositor-win32-x64-msvc')
  : '';
const remotionBinariesDirectory = process.env.NEWSFLOW_REMOTION_BINARIES_DIRECTORY
  || (existsSync(join(packagedBinaries, 'ffmpeg.exe')) ? packagedBinaries : legacyUnpackedBinaries || null);
if (packedModules && (!remotionBinariesDirectory || !existsSync(join(remotionBinariesDirectory, 'ffmpeg.exe')))) {
  throw new Error('Установщик NewsFlow неполный: не найдена папка resources/remotion-binaries с ffmpeg.exe. Переустановите актуальную сборку NewsFlow.');
}
const compositionId = project.aspectRatio === '9:16'
  ? 'NewsFlowMontage9x16'
  : project.aspectRatio === '1:1' ? 'NewsFlowMontage1x1' : 'NewsFlowMontage16x9';

const status = (stage, progress = null) => {
  process.stdout.write(`${JSON.stringify({ type: 'newsflow-remotion', stage, progress })}\n`);
};

// Development still creates a cached bundle on demand.  Released applications
// use the static bundle above and never run webpack/esbuild during a render.
const bundleCacheRoot = join(process.env.LOCALAPPDATA || tmpdir(), 'NewsFlow', 'RemotionBundleCache', 'v2');
const bundleReady = join(bundleCacheRoot, '.newsflow-ready');
const bundleLock = `${bundleCacheRoot}.lock`;
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const getSharedBundle = async () => {
  const packagedBundle = packedModules
    ? join(process.resourcesPath, 'app.asar.unpacked', 'remotion-bundle')
    : '';
  if (packagedBundle) {
    if (!existsSync(join(packagedBundle, 'index.html'))) {
      throw new Error('Установщик NewsFlow неполный: не найдена предсобранная композиция Remotion. Переустановите актуальную сборку NewsFlow.');
    }
    return { serveUrl: packagedBundle, reused: true, packaged: true };
  }
  if (existsSync(bundleReady)) return { serveUrl: bundleCacheRoot, reused: true };
  // The parent does not exist on a clean NewsFlow installation. Creating it
  // before trying to make the lock is essential: otherwise `mkdir(v2.lock)`
  // fails with ENOENT and every renderer merely waits forever.
  await mkdir(dirname(bundleCacheRoot), { recursive: true });
  let ownsLock = false;
  for (let attempt = 0; attempt < 360; attempt += 1) {
    if (existsSync(bundleReady)) return { serveUrl: bundleCacheRoot, reused: true };
    try {
      await mkdir(bundleLock);
      ownsLock = true;
      break;
    } catch {
      try {
        const age = Date.now() - (await stat(bundleLock)).mtimeMs;
        if (age > 10 * 60 * 1000) await rm(bundleLock, { recursive: true, force: true });
      } catch {
        // Another renderer may have completed between stat and remove.
      }
      status('Ожидание общей композиции Remotion', 7);
      await delay(500);
    }
  }
  if (!ownsLock) throw new Error('Не удалось дождаться общей сборки Remotion. Нажмите «Перезапустить выбранные».');
  try {
    await rm(bundleCacheRoot, { recursive: true, force: true });
    await mkdir(bundleCacheRoot, { recursive: true });
    const { bundle } = await import('@remotion/bundler');
    const entryPoint = join(here, 'src', 'index.ts');
    const serveUrl = await bundle({ entryPoint, outDir: bundleCacheRoot, enableCaching: true });
    await writeFile(bundleReady, new Date().toISOString(), 'utf8');
    return { serveUrl, reused: false };
  } finally {
    await rm(bundleLock, { recursive: true, force: true });
  }
};

// Remotion's compositor can fetch HTTP assets but deliberately rejects raw
// `file:///` URLs. This private loopback server never exposes a directory: a
// request contains the exact, encoded local filename from the timeline.
const mediaServer = await createLocalMediaServer([
  ...(project.sequences || []).map((sequence) => sequence.src),
  project.voiceover?.src,
  project.overlay?.src,
]);

await new Promise((resolve, reject) => {
  mediaServer.once('error', reject);
  mediaServer.listen(0, '127.0.0.1', resolve);
});
const address = mediaServer.address();
const mediaPort = typeof address === 'object' && address ? address.port : 0;
const hosted = (file) => file ? `http://127.0.0.1:${mediaPort}/media?src=${encodeURIComponent(Buffer.from(file).toString('base64url'))}` : '';
const hostedProject = {
  ...project,
  sequences: (project.sequences || []).map((sequence) => ({ ...sequence, src: hosted(sequence.src) })),
  voiceover: { ...(project.voiceover || {}), src: hosted(project.voiceover?.src || '') },
  overlay: { ...(project.overlay || {}), src: hosted(project.overlay?.src || '') },
};

try {
  status('Сборка композиции Remotion', 5);
  const sharedBundle = await getSharedBundle();
  const serveUrl = sharedBundle.serveUrl;
  if (sharedBundle.packaged) status('Используется предсобранная композиция Remotion', 8);
  else if (sharedBundle.reused) status('Используется готовая композиция Remotion', 8);
  status('Подготовка таймлайна Remotion', 10);
  const composition = await selectComposition({ serveUrl, id: compositionId, inputProps: { project: hostedProject } });
  const requestedEnd = Math.max(0, Number(project.durationInFrames || 1) - 1);
  // A bounded preview is useful for diagnostics; production calls never set it.
  const previewLimit = Number.parseInt(process.env.NEWSFLOW_REMOTION_MAX_FRAMES || '', 10);
  const endFrame = Number.isFinite(previewLimit) && previewLimit > 0
    ? Math.min(requestedEnd, previewLimit - 1)
    : requestedEnd;

  await renderMedia({
    serveUrl,
    composition,
    codec: 'h264',
    outputLocation: outputPath,
    binariesDirectory: remotionBinariesDirectory,
    inputProps: { project: hostedProject },
    frameRange: [0, endFrame],
    concurrency,
    timeoutInMilliseconds,
    onProgress: ({ progress }) => status('Рендер Remotion', 10 + Math.round(progress * 85)),
  });
  status('MP4 Remotion готов', 100);
} finally {
  await new Promise((resolve) => mediaServer.close(resolve));
}
