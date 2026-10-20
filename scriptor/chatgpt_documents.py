"""Conservative composer-only upload evidence; file selection is not upload proof."""
from __future__ import annotations

from pathlib import Path


def requirement_paths(files: object, legacy: str = "") -> list[str]:
    if files is not None and not isinstance(files, list):
        raise ValueError("requirementsFiles должен быть списком файлов")
    values = files if files is not None else ([legacy] if legacy else [])
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def read_requirements(paths: list[str]) -> list[dict]:
    documents = []
    for path in paths:
        source = Path(path)
        if not source.is_file():
            raise ValueError(f"Файл требований не найден: {source.name}")
        if source.suffix.casefold() not in {".txt", ".md", ".markdown"}:
            raise ValueError(f"Требования должны быть TXT или Markdown: {source.name}")
        try:
            data = source.read_bytes()
            text = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").strip()
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"Не удалось прочитать UTF-8 документ: {source.name}") from exc
        if not text:
            raise ValueError(f"Пустой документ требований: {source.name}")
        documents.append({"path": str(source), "name": source.name, "text": text, "data": data})
    return documents


UPLOAD_EVIDENCE = r"""documents => {
  const editor = document.querySelector('#prompt-textarea,textarea[data-id="root"],div[contenteditable="true"][data-testid*="composer"],textarea,div[contenteditable="true"]');
  const composer = editor?.closest('form') || editor?.closest('[data-testid*="composer"]') || editor?.parentElement;
  if (!composer) return {ready:[], failed:[], pending:documents.map(d=>d.name)};
  const cards = [...composer.querySelectorAll('[data-testid*="attachment"],[data-testid*="file"],[data-filename]')];
  const typed = (editor.value ?? editor.innerText ?? '').replace(/\r\n?/g,'\n');
  const busySelector = '[aria-busy="true"],[role="progressbar"],[data-state="uploading"],[data-state="processing"],[data-testid*="spinner"]';
  const bad = node => node.matches('[data-state="error"],[data-state="failed"]') || Boolean(node.querySelector('[role="alert"],[data-state="error"],[data-state="failed"]')) || /upload failed|failed to upload|ошибка загрузки|не удалось загрузить/i.test(node.textContent || '');
  const ready=[],failed=[],pending=[];
  for (const d of documents) {
    const matching=cards.filter(node => {
      const label=node.getAttribute('data-filename');
      if (label) return label===d.name;
      const text=(node.innerText || node.textContent || '').trim();
      return text.startsWith(d.name) && (text.length===d.name.length || /\s/.test(text[d.name.length]));
    });
    // Automation itself prefills the companion prompt; only a later addition
    // of the complete document can prove an operator's manual paste.
    if (d.text && typed.split(d.text).length-1 > (d.baselineOccurrences || 0)) {ready.push(d.name); continue;}
    if (matching.some(bad)) {failed.push(d.name); continue;}
    if (matching.length && !matching.some(node => node.matches(busySelector) || node.querySelector(busySelector)) && !composer.querySelector(busySelector)) ready.push(d.name);
    else pending.push(d.name);
  }
  return {ready,failed,pending};
}"""
