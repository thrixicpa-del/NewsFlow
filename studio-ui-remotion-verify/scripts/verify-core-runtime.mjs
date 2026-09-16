import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const appRoot = process.cwd();
const packageJson = JSON.parse(fs.readFileSync(path.join(appRoot, 'package.json'), 'utf8'));
const coreResource = packageJson.build?.extraResources?.find((resource) => resource.to === 'core-bin');

if (!coreResource?.from) {
  throw new Error('В package.json не указан ресурс core-bin для portable-сборки.');
}

const coreDirectory = path.resolve(appRoot, coreResource.from);
const candidates = [
  path.join(coreDirectory, 'NewsFlowCore', 'NewsFlowCore.exe'),
  path.join(coreDirectory, 'NewsFlowCore.exe'),
];
const executable = candidates.find((candidate) => fs.existsSync(candidate));

if (!executable) {
  throw new Error(`Не найдено свежее ядро NewsFlow: ${candidates.join(' или ')}`);
}

const sourceBridge = path.resolve(appRoot, '..', 'scriptor', 'bridge.py');
const sourceTimeline = path.resolve(appRoot, '..', 'scriptor', 'timeline.py');
const sourceScenarioCore = path.resolve(appRoot, '..', 'scriptor', 'core.py');
const sourcePromptBuilder = path.resolve(appRoot, '..', 'scriptor', 'thumbnail_prompt_v2.py');
const sourceObservability = path.resolve(appRoot, '..', 'scriptor', 'observability.py');
const sourceMain = path.resolve(appRoot, '..', 'bridge_main.py');
const binaryTime = fs.statSync(executable).mtimeMs;
// The provider prompt is imported by bridge.py but is a distinct source file.
// Track it explicitly: otherwise a portable build could pass this guard while
// embedding a core compiled before a prompt-builder repair.
const staleSource = [sourceBridge, sourceTimeline, sourceScenarioCore, sourcePromptBuilder, sourceObservability, sourceMain]
  .filter((file) => fs.existsSync(file))
  .find((file) => fs.statSync(file).mtimeMs > binaryTime);

if (staleSource) {
  throw new Error(
    `Ядро NewsFlow старее исходного кода (${path.basename(staleSource)}). ` +
      'Сначала пересоберите core-bin, иначе portable-версия запустит старую логику.',
  );
}

console.log(`Ядро NewsFlow актуально: ${executable}`);
