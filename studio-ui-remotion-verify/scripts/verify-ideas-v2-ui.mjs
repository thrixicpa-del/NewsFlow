import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const app = readFileSync(resolve(root, 'src/ui/App.tsx'), 'utf8');
const types = readFileSync(resolve(root, 'src/desktop.d.ts'), 'utf8');
const requiredApp = [
  'const productionItem = data.ideaProductionItems?.find((item) => item.title === idea);',
  'Режим: {productionItem.framing_type || "EDITORIAL"}',
  'СНГ {productionItem.cis_audience_relevance_score ?? "—"}',
  'Риск фактичности: {productionItem.factual_risk_score || "UNKNOWN"}',
  'Legacy-элемент: пересоздайте его, чтобы получить оценки V2.',
  'Production duplicates: {data.ideaRejectedItems?.filter((item) => item.reason === "production_duplicate").length ?? 0}',
  'Сценарный overlap {rejected.script_overlap ?? "—"}',
  'Ближайший дубль: {rejected.nearest_duplicate || "—"}',
];
const requiredTypes = [
  'framing_type?: \'FACTUAL\' | \'EDITORIAL\' | \'HYPOTHETICAL\';',
  'factual_risk_score?: \'LOW\' | \'MEDIUM\' | \'HIGH\' | \'UNKNOWN\';',
  'cis_audience_relevance_score?: number;',
  'information_payload?: Record<string, unknown>;',
  'script_overlap?: number;',
  'event_bundle_overlap?: number;',
  'payload_overlap?: number;',
];
const missing = [
  ...requiredApp.filter((fragment) => !app.includes(fragment)).map((entry) => `UI: ${entry}`),
  ...requiredTypes.filter((fragment) => !types.includes(fragment)).map((entry) => `Types: ${entry}`),
];

if (missing.length) {
  console.error(`Ideas Engine V2 UI contract failed:\n${missing.map((entry) => `- ${entry}`).join('\n')}`);
  process.exit(1);
}

console.log(`Ideas Engine V2 UI contract passed: ${requiredApp.length + requiredTypes.length} checks.`);
