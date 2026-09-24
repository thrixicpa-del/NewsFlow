/*
 * Pre-package guard: a new installer must contain the current, verified
 * runtime contract rather than an old core, lock resolution or legacy path.
 * It is intentionally source-only and never reads or writes user storage.
 */
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import process from 'node:process';

const appRoot = process.cwd();
const sourceRoot = resolve(appRoot, '..');
const packageJson = JSON.parse(readFileSync(resolve(appRoot, 'package.json'), 'utf8'));
const lockfilePath = resolve(appRoot, 'pnpm-lock.yaml');
const lockfile = readFileSync(lockfilePath, 'utf8');
const configSource = readFileSync(resolve(sourceRoot, 'scriptor', 'config.py'), 'utf8');
const bridgeSource = readFileSync(resolve(sourceRoot, 'scriptor', 'bridge.py'), 'utf8');
const timelineSource = readFileSync(resolve(sourceRoot, 'scriptor', 'timeline.py'), 'utf8');
const sessionSource = readFileSync(resolve(sourceRoot, 'scriptor', 'session.py'), 'utf8');
const promptSourcePath = resolve(sourceRoot, 'scriptor', 'thumbnail_prompt_v2.py');
const specSource = readFileSync(resolve(sourceRoot, 'Scriptor.spec'), 'utf8');
const electronMainSource = readFileSync(resolve(appRoot, 'electron', 'main.ts'), 'utf8');

function fail(message) {
  throw new Error(`Build runtime protection failed: ${message}`);
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

if (!/^[0-9]+\.[0-9]+\.[0-9]+/.test(String(packageJson.version || ''))) {
  fail('package.json must provide a semantic runtime version marker.');
}
if (!/SETTINGS_SCHEMA_VERSION\s*=\s*\d+/.test(configSource)
    || !configSource.includes('schema_version')
    || !configSource.includes('SettingsSchemaVersionError')) {
  fail('current Settings schema marker or downgrade protection is missing.');
}
if (!existsSync(promptSourcePath) || !bridgeSource.includes('thumbnail_prompt_v2')) {
  fail('Universal V2 prompt builder is not on the active bridge path.');
}
if (!sessionSource.includes('def migrate_legacy_session')
    || !sessionSource.includes('Legacy Scriptor state is deliberately excluded')) {
  fail('legacy session state is still an automatic runtime fallback.');
}
if (!specSource.includes('["bridge_main.py"]') || specSource.includes('["main.py"]')) {
  fail('the packaged Python entry point is not the current bridge entry point.');
}
if (!electronMainSource.includes("const bundledCore = path.join(process.resourcesPath, 'core-bin', 'NewsFlowCore.exe');")
    || electronMainSource.includes('legacyBundledCore')) {
  fail('the Electron package path can select an old embedded core layout.');
}
if (!timelineSource.includes('renderer: str = "ffmpeg"')
    || !timelineSource.includes('proxy-v3-loop-short-source')
    || !timelineSource.includes('"h264_nvenc", "-preset", "p4"')
    || !timelineSource.includes('"libx264", "-preset", "veryfast"')) {
  fail('FAST NEWS Montage is missing the current FFmpeg default, cache generation or encoder preset.');
}
const montageQueueRender = /render_project\(\s*project,\s*staged_output,\s*progress=progress,\s*renderer=settings\.montage_renderer,/m;
if (!bridgeSource.includes('def run_montage_queue(payload: dict)')
    || !bridgeSource.includes('def _run_montage_queue_unlocked(payload: dict)')
    || !montageQueueRender.test(bridgeSource)) {
  fail('FAST NEWS Montage queue is not wired to the current bridge and render service.');
}

const directDependencies = {...(packageJson.dependencies || {}), ...(packageJson.devDependencies || {})};
for (const [name, requested] of Object.entries(directDependencies)) {
  const matcher = new RegExp(`\\n      ['"]?${escapeRegExp(name)}['"]?:\\n\\s+specifier:\\s+([^\\n]+)\\n\\s+version:\\s+([^\\n]+)`);
  const entry = lockfile.match(matcher);
  if (!entry) {
    fail(`lockfile has no resolved importer entry for ${name}.`);
  }
  if (entry[1].trim() !== String(requested)) {
    fail(`lockfile specifier for ${name} differs from package.json.`);
  }
  if (!entry[2].trim() || entry[2].trim() === '0.0.0') {
    fail(`lockfile has no concrete resolved version for ${name}.`);
  }
}

const coreResource = packageJson.build?.extraResources?.find((resource) => resource.to === 'core-bin');
if (!coreResource?.from || !String(coreResource.from).includes(packageJson.version)) {
  fail('core-bin source does not carry the package runtime version marker.');
}

console.log(
  `Build runtime protection passed: ${packageJson.version}; ` +
  `${Object.keys(directDependencies).length} direct lock entries; current schema/runtime paths verified.`,
);
