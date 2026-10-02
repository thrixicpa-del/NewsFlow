"""Storage/transport replay only, not new live/model-quality evidence."""
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import run_live as live


class ReplayIsolation(unittest.TestCase):
    def test_same_requests_without_network(self):
        source = Path(__file__).parent
        records = json.loads((source / "ledger.json").read_text(encoding="utf-8"))
        output = source / "offline-replay"
        output.mkdir(exist_ok=True)
        position = 0

        def offline_request(_client, method, path, payload):
            nonlocal position
            self.assertEqual((method, path), ("POST", "/v1/responses"))
            record = records[position]
            self.assertEqual(payload, record["request"])
            position += 1
            return {"output_text": record["visible_response"], "id": record["response_id"],
                    "model": record["model"], "status": record["status"],
                    "incomplete_details": record["incomplete_details"], "usage": record["usage"]}

        with patch.object(live, "OUT", output), patch.object(live, "unprotect", return_value="synthetic-replay"), \
                patch.object(live.OpenAITextClient, "_request", offline_request), patch.dict(os.environ, {
                    "NEWSFLOW_LIVE_316_APPROVED": "1", "NEWSFLOW_LIVE_CREDENTIAL_SOURCE": str(source / "offline_credentials.json"),
                }):
            live.LiveEvaluation("test_bounded_ab").test_bounded_ab()
        self.assertEqual(position, len(records))
        print("OFFLINE_REPLAY_ONLY=17 MATCHING_REQUESTS; REAL_API_CALLS=0", flush=True)
