"""Opt-in, bounded live Covers copy evaluation; credentials never enter evidence."""
import hashlib
import json
import os
import subprocess
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scriptor import bridge
from scriptor.config import Settings, config_path, load_settings, save_settings
from scriptor.openai_client import OpenAITextClient
from scriptor.security import unprotect

OUT = Path(__file__).resolve().parent
CASES = [
    {"id": "tariffs", "title": "ТРАМП ПОВЫСИЛ ПОШЛИНЫ ДЛЯ КИТАЯ — ПЕКИН ВВЁЛ ОТВЕТНЫЕ СБОРЫ",
     "script": "Трамп повысил пошлины на китайские товары. Пекин ввёл ответные сборы на американские товары. Импортёры оплачивают более высокие сборы, торговый спор усилился.", "entities": ["Трамп", "Китай", "Пекин"]},
    {"id": "prices", "title": "ЦЕНЫ НА ПОМИДОРЫ НЕ ПАДАЮТ — ПОКУПАТЕЛИ НЕДОВОЛЬНЫ",
     "script": "Помидоры остаются дорогими. Покупатели жалуются на высокие цены и сокращают покупки. Магазины пока не снизили стоимость помидоров.", "entities": ["покупатели", "магазины", "помидоры"]},
    {"id": "protest", "title": "МУЖЧИНА ВЫШЕЛ ПРОТИВ ВОЙНЫ НА КРАСНУЮ ПЛОЩАДЬ — МОСКОВСКИЙ СУД ОТПРАВИЛ ЕГО ПОД АРЕСТ",
     "script": "Мужчина вышел на Красную площадь с антивоенным плакатом. Его задержали. Московский суд отправил участника протеста под арест.", "entities": ["Красная площадь", "Московский суд"]},
    {"id": "technology", "title": "КОМПАНИЯ АЛЬФА ОТМЕНИЛА ОБНОВЛЕНИЕ — ПОЛЬЗОВАТЕЛИ ПОТЕРЯЛИ ДОСТУП К ДОКУМЕНТАМ",
     "script": "После обновления приложения пользователи потеряли доступ к документам. Компания Альфа отменила обновление и восстановила предыдущую версию. Часть документов пока недоступна, инженеры продолжают восстановление.", "entities": ["Альфа", "пользователи", "документы"]},
]


def write(name, value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)
    (OUT / name).write_text(text, encoding="utf-8")


class LiveEvaluation(unittest.TestCase):
    def test_bounded_ab(self):
        if os.environ.get("NEWSFLOW_LIVE_316_APPROVED") != "1":
            self.skipTest("explicit live approval required")
        root = Path(os.environ["NEWSFLOW_TEST_ROOT"]).resolve()
        self.assertTrue(config_path().resolve().is_relative_to(root))
        # Explicit read-only credential source; never call load/save_settings on it.
        credential_source = Path(os.environ["NEWSFLOW_LIVE_CREDENTIAL_SOURCE"])
        raw = json.loads(credential_source.read_text(encoding="utf-8"))
        selected = next(row for row in raw.get("openai_api_keys", [])
                        if row.get("active", True) and row.get("secret_protected"))
        secret = unprotect(selected["secret_protected"])
        self.assertTrue(bool(secret.strip()))
        model = raw.get("openai_model") or Settings().openai_model
        del raw, selected
        ledger = []
        lock = threading.Lock()
        context = {}
        original_request = OpenAITextClient._request

        def capture(client, method, path, payload=None):
            if method != "POST" or path != "/v1/responses":
                raise RuntimeError("Unexpected live route")
            with lock:
                if len(ledger) >= 24:
                    raise RuntimeError("Live budget exhausted")
                entry = {"order": len(ledger) + 1, **context, "route": path, "request": payload}
                ledger.append(entry)
            try:
                result = original_request(client, method, path, payload)
                visible = result.get("output_text", "") or "\n".join(
                    block["text"] for item in result.get("output", [])
                    for block in item.get("content", [])
                    if block.get("type") in {"output_text", "text"} and block.get("text")
                )
                entry.update(response_id=result.get("id"), model=result.get("model"),
                             status=result.get("status"), incomplete_details=result.get("incomplete_details"),
                             usage=result.get("usage"), visible_response=visible,
                             response_chars=len(visible), response_sha256=hashlib.sha256(visible.encode()).hexdigest())
            except Exception as error:
                entry.update(error_type=type(error).__name__, status_code=getattr(error, "status_code", None))
                raise
            finally:
                write("ledger.json", ledger)
            return result

        results = []
        write("dataset.json", CASES)
        write("manifest.json", {"source_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                                "configured_model": model, "max_http_attempts": 24, "provider": "OpenAI",
                                "input_provenance": "Synthetic diagnostic fixtures, not verified real news",
                                "run_id": OUT.name, "secrets_included": False})
        with patch.object(OpenAITextClient, "_request", capture), patch.object(bridge, "snapshot", return_value={}):
            for case in CASES:
                for tabloid in (False, True):
                    if len(ledger) >= 24:
                        break
                    mode = "TABLOID" if tabloid else "STANDARD"
                    context.update(case=case["id"], mode=mode)
                    settings = load_settings()
                    settings.openai_api_keys = [SimpleNamespace(secret=secret, label="Live acceptance", active=True)]
                    settings.openai_model = model
                    settings.cover_queue = [{**case, "production_item_id": "synthetic:" + case["id"],
                                             "scenario_index": 1, "status": "Ожидает"}]
                    save_settings(settings)
                    # Actual normal Word Engine handlers, isolated persistence only.
                    bridge.generate_cover_texts({"provider": "openai", "useDefault": True,
                                                 "force": True, "tabloidMode": tabloid,
                                                 "indices": [0], "productionItemIds": ["synthetic:" + case["id"]]})
                    row = load_settings().cover_queue[0]
                    record = {"case": case["id"], "mode": mode, "title": case["title"], "row": row}
                    results.append(record)
                    write("results.json", results)
                    print(json.dumps({"case": case["id"], "mode": mode,
                                      "headline": row.get("cover_headline"), "subheadline": row.get("cover_subheadline"),
                                      "headline_status": row.get("headline_status"), "subheadline_status": row.get("subheadline_status"),
                                      "calls_so_far": len(ledger)}, ensure_ascii=False), flush=True)
        self.assertLessEqual(len(ledger), 24)
        self.assertNotIn(secret, json.dumps(ledger))
        self.assertNotIn(secret, json.dumps(results))
        print("REAL_HTTP_ATTEMPTS=" + str(len(ledger)), flush=True)
