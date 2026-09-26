import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { verifyCoreAssets } from './verify-core-assets.mjs';

const appRoot = process.cwd();
const repoRoot = path.resolve(appRoot, '..');
const packageJson = JSON.parse(fs.readFileSync(path.join(appRoot, 'package.json'), 'utf8'));
const lockPath = path.join(appRoot, 'core-runtime-lock.json');
if (!fs.existsSync(lockPath)) {
  throw new Error('Не найден core-runtime-lock.json для проверки Frozen Core.');
}
const lock = JSON.parse(fs.readFileSync(lockPath, 'utf8'));

const requiredSources = [
  'scriptor/bridge.py',
  'scriptor/ai_index.py',
  'scriptor/config.py',
  'scriptor/core.py',
  'scriptor/runner.py',
  'scriptor/story_planner.py',
  'scriptor/openai_client.py',
  'scriptor/timeline.py',
  'scriptor/thumbnail_prompt_v2.py',
  'scriptor/observability.py',
  'bridge_main.py',
];

if (lock.format !== 1
    || typeof lock.coreRevision !== 'string'
    || !/^[0-9a-f]{64}$/i.test(String(lock.coreExeSha256 || ''))
    || !Number.isSafeInteger(lock.coreExeSize)
    || !/^[0-9a-f]{40}$/i.test(String(lock.builtFromGitSha || ''))
    || !lock.sourceGitBlobs
    || typeof lock.sourceGitBlobs !== 'object') {
  throw new Error('core-runtime-lock.json имеет некорректный формат.');
}
if (String(packageJson.version || '') !== String(lock.appVersion || '')) {
  throw new Error('Версия core-runtime lock не совпадает с package.json.');
}
for (const source of requiredSources) {
  if (!/^[0-9a-f]{40}$/i.test(String(lock.sourceGitBlobs[source] || ''))) {
    throw new Error(`core-runtime lock не содержит identity для ${source}.`);
  }
}

const coreResource = packageJson.build?.extraResources?.find((resource) => resource.to === 'core-bin');
if (!coreResource?.from) {
  throw new Error('В package.json не указан ресурс core-bin для portable-сборки.');
}
const normalizedResource = String(coreResource.from).replace(/\\/g, '/');
if (!normalizedResource.split('/').includes(lock.coreRevision)) {
  throw new Error(
    `package.json указывает core-bin, не совпадающий с lock revision ${lock.coreRevision}.`,
  );
}

const coreDirectory = path.resolve(appRoot, coreResource.from);
const candidates = [
  path.join(coreDirectory, 'NewsFlowCore', 'NewsFlowCore.exe'),
  path.join(coreDirectory, 'NewsFlowCore.exe'),
];
const executable = candidates.find((candidate) => fs.existsSync(candidate));
if (!executable) {
  throw new Error(`Не найдено ядро NewsFlow: ${candidates.join(' или ')}`);
}

const sha256 = (file) => createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const gitBlobSha = (file) => {
  const content = fs.readFileSync(file);
  return createHash('sha1')
    .update(Buffer.from(`blob ${content.length}\0`, 'utf8'))
    .update(content)
    .digest('hex');
};

const actualCoreSha = sha256(executable);
if (actualCoreSha.toLowerCase() !== lock.coreExeSha256.toLowerCase()) {
  throw new Error(
    `Frozen Core SHA-256 не совпадает с lock: expected ${lock.coreExeSha256}; found ${actualCoreSha}.`,
  );
}
const actualCoreSize = fs.statSync(executable).size;
if (actualCoreSize !== lock.coreExeSize) {
  throw new Error(
    `Frozen Core size не совпадает с lock: expected ${lock.coreExeSize}; found ${actualCoreSize}.`,
  );
}

for (const relative of requiredSources) {
  const source = path.resolve(repoRoot, relative);
  if (!fs.existsSync(source)) {
    throw new Error(`Не найден core source: ${relative}.`);
  }
  const actualBlob = gitBlobSha(source);
  const expectedBlob = lock.sourceGitBlobs[relative].toLowerCase();
  if (actualBlob !== expectedBlob) {
    throw new Error(
      `Frozen Core не соответствует текущему исходному коду (${relative}). ` +
      `expected blob ${expectedBlob}; found ${actualBlob}. Пересоберите core-bin.`,
    );
  }
}

verifyCoreAssets(path.dirname(executable));

console.log(
  `Ядро NewsFlow актуально по содержимому: ${executable}; ` +
  `revision=${lock.coreRevision}; source=${lock.builtFromGitSha}`,
);
