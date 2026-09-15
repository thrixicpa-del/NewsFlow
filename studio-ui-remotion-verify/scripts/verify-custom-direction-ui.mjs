import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const app = readFileSync(resolve(root, 'src/ui/App.tsx'), 'utf8');
const required = [
  'const [customTopic, setCustomTopic] = useState("");',
  'const addTopic = async () => {',
  'const topic = customTopic.trim();',
  'await command("add-topic", { topic });',
  'setCustomTopic("");',
  'placeholder="Новая тема — например: Ближний Восток и нефть"',
  'const [referenceUrl, setReferenceUrl] = useState("");',
  'const [referenceLabel, setReferenceLabel] = useState("");',
  'const url = referenceUrl.trim();',
  'await command("add-idea-reference-channel", { url, label });',
  'setReferenceUrl("");',
  'placeholder="https://www.youtube.com/@channel"',
  'placeholder="Название канала (необязательно)"',
  'const plannedTopicCount = data.ideaPlan.length;',
  'const plannedVectorCount = data.ideaPlan.reduce(',
  'const selectedVectorCount = selected.length * Math.max(1, Number(vectors) || 1);',
  'const [planCountDrafts, setPlanCountDrafts] = useState<Record<string, string>>({});',
  'planCountDrafts[item.topic] ?? String(item.count)',
  'setPlanCountDrafts((current) => ({ ...current, [item.topic]: event.target.value }))',
  'const requestedTopics = selected.length ? selected : [];',
  'topics: requestedTopics,',
  'requirements,',
  'Направление: {data.ideaResultSources[idea]}',
  'выбрано · {selectedVectorCount} роликов будет создано',
  'Уже добавлено в план',
  'направлений · {plannedVectorCount} роликов',
];
const missing = required.filter((fragment) => !app.includes(fragment));
if (missing.length || app.includes('window.prompt("Новое новостное направление")') || app.includes('window.prompt("Публичная ссылка на YouTube-канал", "")')) {
  console.error(`Custom direction UI contract failed:\n${missing.map((entry) => `- ${entry}`).join('\n')}`);
  process.exit(1);
}
console.log(`Custom direction UI contract passed: ${required.length} controls found.`);
