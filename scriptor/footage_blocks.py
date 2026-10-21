"""Manual, read-only footage roots and durable ProductionItem assignments."""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from .footage import FootageItem, scan_folders


def _key(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def _root(value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Укажите корневую папку блока футажей")
    try:
        root = Path(value).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError("Папка блока футажей недоступна")
        return root
    except (OSError, RuntimeError) as error:
        raise ValueError("Папка блока футажей недоступна") from error


def block_files(root: str) -> list[FootageItem]:
    """Scan only this root; canonical escapes (including junctions) fail closed."""
    canonical = _root(root)
    try:
        items = scan_folders([str(canonical)])
        for item in items:
            resolved = Path(item.path).resolve(strict=True)
            if not resolved.is_relative_to(canonical):
                raise ValueError("Файл блока выходит за пределы его корневой папки")
            item.path = str(resolved)
        return items
    except (OSError, RuntimeError) as error:
        raise ValueError("Не удалось прочитать файлы блока футажей") from error


def _block(settings, block_id: str) -> dict:
    matches = [row for row in settings.footage_blocks if row.get("id") == block_id]
    if len(matches) != 1:
        raise ValueError("Блок футажей не найден или его ID неоднозначен")
    return matches[0]


def upsert_block(settings, payload: dict) -> dict:
    """Validate before replacing settings; files are only read, never changed."""
    name = " ".join(str(payload.get("name") or "").split())
    if not name:
        raise ValueError("Укажите название блока футажей")
    identity = str(payload.get("blockId") or "").strip()
    if identity:
        _block(settings, identity)
    if any(_key(row.get("name")) == _key(name) and row.get("id") != identity
           for row in settings.footage_blocks):
        raise ValueError("Блок с таким названием уже существует")
    root = _root(payload.get("root"))
    row = {"id": identity or str(uuid.uuid4()), "name": name, "root": str(root),
           "videoCount": len(block_files(str(root)))}
    settings.footage_blocks = [dict(row) if item.get("id") == identity else item
                              for item in settings.footage_blocks]
    if not identity:
        settings.footage_blocks.append(dict(row))
    return dict(row)


def delete_block(settings, block_id: str) -> None:
    # Retain dangling assignments so deletion cannot silently choose another root.
    _block(settings, block_id)
    settings.footage_blocks = [row for row in settings.footage_blocks if row.get("id") != block_id]


def list_blocks(settings) -> list[dict]:
    """Cheap UI snapshot: counts are refreshed only by an explicit CRUD edit."""
    rows = []
    for block in settings.footage_blocks:
        try:
            available = Path(block.get("root", "")).is_dir() if block.get("root") else False
        except OSError:
            available = False
        rows.append({**block, "available": available})
    return rows


def parse_topic_block_pairs(text: str) -> list[tuple[str, str]]:
    """Every nonempty paragraph is one field, alternating topic and block."""
    if not isinstance(text, str):
        raise TypeError("Импорт ожидает текст UTF-8")
    normalized = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    paragraphs = [value.strip() for value in re.split(r"\n[ \t]*\n(?:[ \t]*\n)*", normalized) if value.strip()]
    if not paragraphs or len(paragraphs) % 2:
        raise ValueError("TXT должен содержать пары непустых абзацев: тема, затем блок")
    return list(zip(paragraphs[::2], paragraphs[1::2]))


def _topics_by_id(topics: list[dict]) -> dict[str, dict]:
    indexed = {}
    for topic in topics:
        identity = str(topic.get("id") or "").strip()
        if not identity or identity in indexed or not _key(topic.get("title")):
            raise ValueError("У темы отсутствует уникальный Product ID или название")
        indexed[identity] = topic
    return indexed


def resolve_assignments(settings, pairs: list[tuple[str, str]], topics: list[dict], *,
                        confirm_overwrite: bool = False) -> list[dict]:
    """Pure full-batch validation; callers create native new topics beforehand."""
    indexed = _topics_by_id(topics)
    resolved = {}
    for title, block_name in pairs:
        matches = [(identity, topic) for identity, topic in indexed.items() if _key(topic["title"]) == _key(title)]
        if len(matches) != 1:
            raise ValueError(f"Тема не найдена или неоднозначна: {title}")
        blocks = [row for row in settings.footage_blocks if _key(row.get("name")) == _key(block_name)]
        if len(blocks) != 1:
            raise ValueError(f"Блок не найден или неоднозначен: {block_name}")
        block = blocks[0]
        _block(settings, block["id"])
        root = _root(block.get("root"))
        identity, topic = matches[0]
        if identity in resolved and resolved[identity]["blockId"] != block["id"]:
            raise ValueError(f"Для темы указаны разные блоки: {title}")
        existing = settings.footage_block_assignments.get(identity, {})
        if (existing.get("origin") == "manual" and existing.get("blockId") != block["id"]
                and not confirm_overwrite):
            raise ValueError(f"Подтвердите замену ручного назначения: {title}")
        resolved[identity] = {"title": topic["title"], "productionItemId": identity,
                              "blockId": block["id"], "blockName": block["name"], "root": str(root)}
    if not resolved:
        raise ValueError("Нет назначений для импорта")
    return list(resolved.values())


def assign_block(settings, pid: str, block_id: str, topics: list[dict]) -> None:
    if pid not in _topics_by_id(topics):
        raise ValueError("Тема с указанным Product ID не найдена")
    block = _block(settings, block_id)
    _root(block.get("root"))
    settings.footage_block_assignments = {**settings.footage_block_assignments,
                                         pid: {"blockId": block_id, "origin": "manual"}}


def apply_assignments(settings, resolved: list[dict]) -> None:
    """Apply one already confirmed, validated batch without partial updates."""
    assignments = dict(settings.footage_block_assignments)
    for row in resolved:
        identity = str(row.get("productionItemId") or "").strip()
        if not identity:
            raise ValueError("Для назначения необходим Product ID")
        block = _block(settings, row.get("blockId"))
        _root(block.get("root"))
        existing = assignments.get(identity, {})
        if existing.get("origin") == "manual" and existing.get("blockId") == block["id"]:
            continue
        assignments[identity] = {"blockId": block["id"], "origin": "import"}
    settings.footage_block_assignments = assignments


def get_block_snapshot(settings, pid: str) -> dict:
    if not settings.montage_use_footage_blocks:
        return {"enabled": False, "productionItemId": pid}
    assignment = settings.footage_block_assignments.get(pid, {})
    if not assignment.get("blockId"):
        raise ValueError("Для темы не назначен блок футажей")
    block = _block(settings, assignment["blockId"])
    root = _root(block.get("root"))
    return {"enabled": True, "productionItemId": pid, "blockId": block["id"],
            "name": block["name"], "root": str(root)}
