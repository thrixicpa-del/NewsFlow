import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const app = readFileSync(resolve(root, 'src/ui/App.tsx'), 'utf8');
const required = [
  'const fastgenText = true;',
  'const localFaceOnly = false;',
  'const faceMode = "auto";',
  'FastGen всё + мои лица',
  'FastGen сам рисует сцену, лица и текст; пользовательский PNG не загружается.',
  'buildMode: "fastgen-full-my-face",',
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
  'currentProfile: true',
  'value="__none__"',
  'visual_reference_to_fastgen',
  'buildMode: mode,',
  'Также отправить общий набор ИИ-референсов в FastGen',
  'sendToFastgen: event.target.checked',
  'mass-cover-selection-summary',
  'Новых промптов готово:',
  'Создать новые промпты для выбранных',
  'Повторить текущие выбранных',
  'Повторить с новыми',
  'Модель для массовой генерации',
  'Открыть папку обложек',
  'currentProfile: true,\n      operation,',
  'newsflow_preview',
];
const missing = required.filter(fragment => !app.includes(fragment));
const retiredRoutes = [
  'fastgen-text-auto-face',
  'fastgen-text-local-face',
  'newsflow-full',
  'FastGen + NewsFlow всё',
  'FastGen текст + лицо NewsFlow',
];
const retired = retiredRoutes.filter(fragment => app.includes(fragment));
if (missing.length || retired.length) {
  console.error([
    missing.length ? `Cover-flow contract missing:\n${missing.map(item => `- ${item}`).join('\n')}` : '',
    retired.length ? `Retired cover routes are still visible:\n${retired.map(item => `- ${item}`).join('\n')}` : '',
  ].filter(Boolean).join('\n'));
  process.exit(1);
}
console.log(`Cover-flow contract passed: ${required.length} cover interactions found.`);
