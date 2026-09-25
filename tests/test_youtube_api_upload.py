"""Unit contracts for the resumable YouTube transfer loop."""

from __future__ import annotations

import unittest

from scriptor.youtube_api import consume_resumable_upload


class _Status:
    def __init__(self, sent: int, total: int) -> None:
        self.resumable_progress = sent
        self.total_size = total


class _Request:
    def __init__(self, responses: list[object]) -> None:
        self.responses = iter(responses)

    def next_chunk(self):
        outcome = next(self.responses)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ResumableUploadTests(unittest.TestCase):
    def test_reports_actual_chunk_progress_until_youtube_returns_an_id(self) -> None:
        progress: list[dict] = []
        response = consume_resumable_upload(
            _Request([(_Status(25, 100), None), (_Status(100, 100), {"id": "yt-1"})]),
            on_progress=progress.append,
            sleep=lambda _: None,
        )

        self.assertEqual(response, {"id": "yt-1"})
        self.assertEqual(progress, [
            {"bytesSent": 25, "totalBytes": 100, "percent": 25},
            {"bytesSent": 100, "totalBytes": 100, "percent": 100},
        ])

    def test_retries_only_transient_transport_errors_with_a_bound(self) -> None:
        waits: list[float] = []
        response = consume_resumable_upload(
            _Request([TimeoutError("network"), (_Status(4, 4), {"id": "yt-2"})]),
            sleep=waits.append,
        )

        self.assertEqual(response["id"], "yt-2")
        self.assertEqual(waits, [1.0])

    def test_does_not_mask_non_transient_failure_as_a_success(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid metadata"):
            consume_resumable_upload(
                _Request([ValueError("invalid metadata")]),
                sleep=lambda _: None,
            )
