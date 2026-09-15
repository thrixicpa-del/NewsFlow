/*
 * Lightweight source-level regression gate that can run before dependencies
 * are restored. It catches the controls that are live in the current delivery:
 * publication assignment, per-channel notes and SEO description prefixes.
 * A full Vite/Electron build still runs after this check in CI/release.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const app = readFileSync(resolve(root, 'src/ui/App.tsx'), 'utf8');
const declarations = readFileSync(resolve(root, 'src/desktop.d.ts'), 'utf8');
const requiredAppFragments = [
  'function PublicationDashboard',
  'move-publication-job-channel',
  'Перенести / время',
  'function ChannelMetadataEditor',
  'Заметки по каналу',
  'function SeoPrefixRanges',
  'Вступления к SEO-описанию',
  'exportDaVinciXml: enabled',
  'davinciAutoImport: enabled ? davinciAutoImport : false',
];
const requiredTypeFragments = [
  'operatorNotes',
  'descriptionPrefixRanges',
  'descriptionPrefixPresets',
];
const missing = [
  ...requiredAppFragments.filter((fragment) => !app.includes(fragment)).map((fragment) => `App.tsx: ${fragment}`),
  ...requiredTypeFragments.filter((fragment) => !declarations.includes(fragment)).map((fragment) => `desktop.d.ts: ${fragment}`),
];
if (missing.length) {
  console.error(`NewsFlow montage UI contract failed:\n${missing.map((entry) => `- ${entry}`).join('\n')}`);
  process.exit(1);
}
console.log(`NewsFlow montage UI contract passed: ${requiredAppFragments.length + requiredTypeFragments.length} controls/types found.`);
