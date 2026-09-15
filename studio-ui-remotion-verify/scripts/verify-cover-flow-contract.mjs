import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const app = readFileSync(resolve(root, 'src/ui/App.tsx'), 'utf8');
const required = [
  "const faceMode = mode === 'fastgen-full' || automaticTextWithFace ? 'auto' : 'with';",
  'const automaticTextWithFace = mode === \'fastgen-text-auto-face\';',
  'FastGen текст + лицо NewsFlow (автоматически)',
  'faceMode, textMode: fastgenText ? \'fastgen\' : \'overlay\', localFaceOnly',
  'Режим «Всё через FastGen»',
  'setUseCustomPrompt(true)',
  'value={template}',
  'Поле пустое: дополнительные правила не передаются.',
  'cover-variant-delete-panel',
  'Отдельные референсы для ИИ-промптов',
  'reference-preview',
  'Учитывать референсы FastGen',
  'Референсы ({range.paths.length}/10)',
  'encodeURIComponent',
  'CoverPreviewImage',
  'cover-image-load-error',
  'Новые промпты созданы',
  'Повторить с новыми',
  'aiReferenceMode',
  'Отправить выбранные в FastGen',
  'Диапазоны для ИИ',
  'select-cover-visual-reference',
  'Загрузить референс для выбранной темы',
  "const fastgenText = mode !== 'newsflow-full';",
  'currentProfile: true',
  'value="__none__"',
  'visual_reference_to_fastgen',
  'buildMode: mode, faceMode, textMode: fastgenText ? \'fastgen\' : \'overlay\', localFaceOnly',
  'Также отправить общий набор ИИ-референсов в FastGen',
  'sendToFastgen: event.target.checked',
  'mass-cover-selection-summary',
  'Новых промптов готово:',
  'Создать новые промпты для выбранных',
  'Повторить текущие выбранных',
  'Повторить с новыми',
  'Модель для массовой генерации',
  'Открыть папку обложек',
  "indices: [index], currentProfile: true, operation",
  'newsflow_preview',
];
const missing = required.filter(fragment => !app.includes(fragment));
if (missing.length) {
  console.error(`Cover-flow contract failed:\n${missing.map(item => `- ${item}`).join('\n')}`);
  process.exit(1);
}
console.log(`Cover-flow contract passed: ${required.length} cover interactions found.`);
