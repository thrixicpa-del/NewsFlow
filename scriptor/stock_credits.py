"""Attribution sidecars for the assets actually used in an exported montage."""
import json
from pathlib import Path


def stage_stock_credits(project, staged_output: Path, final_output: Path) -> list[tuple[Path, Path]]:
    materials = {}
    fields = ("provider", "asset_id", "title", "source_url", "license", "license_url", "author", "kind", "originalSha256")
    for position, clip in enumerate(project.clips, 1):
        record = clip.stock_provenance
        if not record:
            continue
        key = (record.get("provider"), record.get("asset_id"), record.get("originalSha256"))
        if key not in materials:
            materials[key] = {field: record.get(field, "") for field in fields}
            materials[key].update({"scenes": [], "changes": "Selected interval; scaling/cropping and optional silent video/image animation in montage"})
        materials[key]["scenes"].append(position)
    if (not materials and not project.source_policy
            and not final_output.with_suffix(".stocks.json").exists()
            and not final_output.with_suffix(".stocks.txt").exists()):
        return []
    staged_output.parent.mkdir(parents=True, exist_ok=True)
    manifest = staged_output.with_suffix(".stocks.json")
    credits = staged_output.with_suffix(".stocks.txt")
    manifest.write_text(json.dumps({"schema": "newsflow-stock-credits/v1", "materials": list(materials.values())}, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["Stock media credits / Источники материалов", ""]
    if not materials:
        lines.append("No stock media used in this export / В этом экспорте стоки не использовались")
    for record in materials.values():
        lines.extend((str(record["title"]), f"Author: {record['author']}", f"Source: {record['source_url']}",
                      f"License: {record['license']} — {record['license_url']}", f"Changes: {record['changes']}", ""))
    credits.write_text("\n".join(lines), encoding="utf-8")
    return [(manifest, final_output.with_suffix(".stocks.json")), (credits, final_output.with_suffix(".stocks.txt"))]
