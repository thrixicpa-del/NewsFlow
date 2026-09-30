import asyncio
import json
import threading
import unittest
from hashlib import sha256
from pathlib import Path

from scriptor.core import ScenarioRequest
from scriptor.openai_client import OpenAIResponseIncompleteError
from scriptor.runner import (
    Job,
    ParallelRunner,
    RunState,
    _planner_schema_reason,
    looks_like_action_required,
    scenario_length_status,
    scenario_output_token_budget,
)
from scriptor.story_planner import calculate_story_part_targets, story_plan_from_dict


class FakeClient:
    def __init__(self):
        self.active = 0
        self.peak = 0

    async def generate(self, prompt, on_progress=None):
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        if "NewsFlow Story Planner" in prompt:
            return ParallelRunnerTests._story_plan_json(1)
        return "result"


class ParallelRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_incomplete_writer_part_is_durable_but_never_accepted_or_retried_on_resume(self):
        """A delivered partial P2 is reviewable, not a new Writer attempt."""
        class IncompleteWriterClient:
            def __init__(self):
                self.calls = []

            async def generate(self, prompt, on_progress=None, **kwargs):
                self.calls.append(prompt)
                if "NewsFlow Story Planner" in (kwargs.get("instructions") or prompt):
                    return ParallelRunnerTests._story_plan_json(3)
                if "CURRENT PART: P1" in prompt:
                    return "А" * 4999
                if "CURRENT PART: P2" in prompt:
                    raise OpenAIResponseIncompleteError(
                        "OpenAI returned incomplete response",
                        status="incomplete",
                        visible_text="Частичный текст P2",
                        response_id="resp_p2_partial",
                        incomplete_reason="max_output_tokens",
                    )
                raise AssertionError("P3 must not start after a partial P2")

        request = ScenarioRequest(0, "Тема", "Шаблон", target_chars=15000)
        client = IncompleteWriterClient()
        job = (await ParallelRunner(client, 1).run([request]))[0]

        self.assertEqual(job.state, RunState.PAUSED)
        self.assertEqual([part["part_id"] for part in job.accepted_story_parts], ["P1"])
        self.assertEqual(job.writer_partial_response["part_id"], "P2")
        self.assertEqual(job.writer_partial_response["text"], "Частичный текст P2")
        self.assertEqual(job.writer_partial_response["status"], "incomplete")
        self.assertEqual(sum("CURRENT PART: P3" in call for call in client.calls), 0)

        class NoReplayClient:
            async def generate(self, *_args, **_kwargs):
                raise AssertionError("ordinary resume must not repeat a delivered Writer call")

        resumed = (await ParallelRunner(NoReplayClient(), 1).run(
            [request], resume_jobs={0: job},
        ))[0]
        self.assertEqual(resumed.state, RunState.PAUSED)
        self.assertEqual([part["part_id"] for part in resumed.accepted_story_parts], ["P1"])

    async def test_planner_adapter_without_text_format_uses_explicit_legacy_request(self):
        """Do not silently send a split Planner request after dropping its schema."""
        class LegacyPlannerClient:
            def __init__(self):
                self.calls = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None,
                               instructions=None):
                self.calls.append((prompt, instructions))
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(1)
                return "Г" * 5000

        client = LegacyPlannerClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "MANUAL_LEGACY_TEMPLATE", target_chars=5000),
        ])

        self.assertEqual(jobs[0].state, RunState.DONE, jobs[0].error)
        planner_prompt, planner_instructions = client.calls[0]
        self.assertIn("NewsFlow Story Planner", planner_prompt)
        self.assertIn("MANUAL_LEGACY_TEMPLATE", planner_prompt)
        self.assertIsNone(planner_instructions)

    async def test_low_density_map_starts_one_writer_call_per_part_without_planner_recovery(self):
        """The prior live map remains runnable; material density is advisory."""
        evidence = (
            Path(__file__).resolve().parents[1]
            / "docs" / "verification" / "evidence"
            / "scenario-live-293-event-spine-20260930-143000"
            / "response-01-visible.txt"
        ).read_text(encoding="utf-8")

        class StageClient:
            def __init__(self):
                self.calls = []

            async def generate(
                self, prompt, on_progress=None, max_output_tokens=None, instructions=None,
                text_format=None,
            ):
                self.calls.append((prompt, instructions, max_output_tokens, text_format))
                if instructions and "NewsFlow Story Planner" in instructions:
                    return evidence
                if "CURRENT PART: P1" in prompt:
                    return "А" * 3999
                if "CURRENT PART: P2" in prompt:
                    return "Б" * 3999
                if "CURRENT PART: P3" in prompt:
                    return "В" * 3998
                raise AssertionError("unexpected stage request")

            async def generate_fresh(self, *_args, **_kwargs):
                raise AssertionError("low atom count must not trigger Planner recovery")

        client = StageClient()
        request = ScenarioRequest(
            0, "Тема", "MANUAL_STAGE_TEMPLATE", target_chars=12000,
            allowed_min=11500, allowed_max=12500,
        )
        job = (await ParallelRunner(client, 1).run([request]))[0]

        self.assertEqual(job.state, RunState.DONE)
        self.assertEqual(len(client.calls), 4)
        self.assertIn("NewsFlow Story Planner", client.calls[0][1])
        self.assertNotIn("MANUAL_STAGE_TEMPLATE", client.calls[0][1])
        self.assertIn("MANUAL_STAGE_TEMPLATE", client.calls[0][0])
        self.assertEqual(client.calls[0][3]["type"], "json_schema")
        self.assertTrue(client.calls[0][3]["strict"])
        self.assertTrue(all(call[3] is None for call in client.calls[1:]))
        self.assertEqual(
            ["P1", "P2", "P3"],
            [record["part_id"] for record in job.accepted_story_parts],
        )

    @staticmethod
    def _story_plan_json(part_count: int) -> str:
        roles = ["COMPLETE"] if part_count == 1 else ["OPENING", *(["MIDDLE"] * (part_count - 2)), "FINAL"]
        return json.dumps({
            "state_transition_contract": "BEFORE_DEVELOPMENT_AFTER",
            "thesis": "Одна последовательная история без второго смыслового круга.",
            "macro_blocks": [{"id": "M1", "purpose": "Развитие истории"}],
            "content_atoms": [
                {"id": f"C{index:03d}", "summary": f"Новый материал {index}", "owner_part_id": f"P{index}",
                 "content_kind": "SUPPORTED",
                 "state_before": f"Состояние до шага {index}.",
                 "state_after": f"Состояние после шага {index}.",
                 "changed_subject": f"Рабочий объект {index}",
                 "development": f"исполнитель выполнил действие {index}",
                 "resulting_state": f"рабочий объект {index} получил новый статус",
                 "writer_material": [
                     f"объект {index} работал в прежнем порядке",
                     f"исполнитель выполнил действие {index} над объектом",
                     f"ответственная служба проверила изменение объекта {index}",
                     f"участники получили новый статус объекта {index}",
                     f"следующий шаг использует результат действия {index}",
                 ]}
                for index in range(1, part_count + 1)
            ],
            "parts": [
                {
                    "id": f"P{index}", "role": roles[index - 1],
                    "purpose": f"Смысловой блок {index}", "macro_id": "M1",
                    "content_ids": [f"C{index:03d}"], "opens": [], "closes": [],
                    "transition_direction": f"к блоку {index + 1}" if index < part_count else "финал",
                }
                for index in range(1, part_count + 1)
            ],
        }, ensure_ascii=False)

    def test_character_boundaries_use_the_actual_python_string_length(self):
        request = ScenarioRequest(0, "S", "P", target_chars=12500, allowed_min=10000, allowed_max=15000)

        self.assertEqual(scenario_length_status(request, "а" * 9999), ("SHORT", 9999))
        self.assertEqual(scenario_length_status(request, "а" * 10000), ("READY", 10000))
        self.assertEqual(scenario_length_status(request, "а" * 15000), ("READY", 15000))
        self.assertEqual(scenario_length_status(request, "а" * 15001), ("LONG", 15001))

    def test_planner_schema_reasons_cover_stable_validator_failures(self):
        """Recovery routing receives the specific local validator category."""
        cases = {
            "story plan requires BEFORE_DEVELOPMENT_AFTER state transition contract": "INVALID_TRANSITION_CONTRACT",
            "story plan atom requires structured concrete change": "MISSING_TRANSITION_FIELDS",
            "story plan atom must describe an observable concrete change": "ABSTRACT_OR_NONCONCRETE_TRANSITION",
            "story plan content atoms must be materially distinct": "ATOM_SEMANTIC_DUPLICATE",
            "story plan parts must own materially distinct semantic content": "PART_SEMANTIC_DUPLICATE",
            "story plan part P1 requires at least 3 distinct content atoms for semantic density": "SEMANTIC_DENSITY",
            "story plan requires exactly 2 parts": "PART_COUNT",
            "story plan part IDs must be ordered as P2": "PART_ID_ORDER",
            "story plan part P1 role must be OPENING": "PART_ROLE",
            "story plan part P1 references unknown macro block": "PART_MACRO_REF",
            "story plan part P1 requires content_ids": "PART_CONTENT_IDS",
            "story plan content atom ownership must cover every planned atom exactly once": "CONTENT_OWNERSHIP",
            "story plan content_kind must be SUPPORTED or DRAMATIZED": "INVALID_CONTENT_KIND",
            "story plan requires thesis": "MISSING_THESIS",
            "story plan requires macro_blocks": "MISSING_MACRO_BLOCKS",
            "story plan requires content_atoms": "MISSING_CONTENT_ATOMS",
            "story planner must return strict JSON": "NON_JSON",
            "story planner response must be an object": "NON_OBJECT_JSON",
        }

        for message, expected in cases.items():
            with self.subTest(message=message):
                self.assertEqual(_planner_schema_reason(ValueError(message)), expected)

    async def test_long_script_is_planned_before_three_writer_parts_without_generic_continuation(self):
        class PlannedClient:
            def __init__(self):
                self.prompts = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(3)
                if "CURRENT PART: P1" in prompt:
                    return "А" * 5000
                if "CURRENT PART: P2" in prompt:
                    return "Б" * 5000
                if "CURRENT PART: P3" in prompt:
                    return "В" * 5000
                raise AssertionError(f"unexpected provider prompt: {prompt[:200]}")

            async def generate_fresh(self, *_args, **_kwargs):
                raise AssertionError("normal planned flow must not use generic continuation")

        client = PlannedClient()
        request = ScenarioRequest(0, "Тема", "USER WRITING CONTRACT", target_chars=15000,
                                  allowed_min=14000, allowed_max=16000)
        jobs = await ParallelRunner(client, 1).run([request])

        self.assertEqual(len(client.prompts), 4)
        self.assertIn("NewsFlow Story Planner", client.prompts[0])
        self.assertIn("CURRENT PART: P1", client.prompts[1])
        self.assertIn("CURRENT PART: P2", client.prompts[2])
        self.assertIn("CURRENT PART: P3", client.prompts[3])
        self.assertTrue(all("ПРОДОЛЖИ" not in prompt for prompt in client.prompts))
        self.assertTrue(all(jobs[0].result not in prompt for prompt in client.prompts))
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertEqual(jobs[0].actual_chars, 15004)

    async def test_part_counts_one_through_seven_use_the_same_story_orchestration(self):
        for part_count in range(1, 8):
            with self.subTest(part_count=part_count):
                target_chars = part_count * 5000

                class RangeClient:
                    def __init__(self, expected_parts, target):
                        self.expected_parts = expected_parts
                        self.target = target
                        self.prompts = []

                    async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                        self.prompts.append(prompt)
                        if "NewsFlow Story Planner" in prompt:
                            return ParallelRunnerTests._story_plan_json(self.expected_parts)
                        match = __import__("re").search(
                            r"CURRENT TARGET: approximately (\d+) characters", prompt,
                        )
                        if not match:
                            raise AssertionError("multipart writer must receive an active part target")
                        part_match = __import__("re").search(r"CURRENT PART: P(\d+)", prompt)
                        if not part_match:
                            raise AssertionError("multipart writer must identify its planned part")
                        char = chr(0x0410 + int(part_match.group(1)))
                        return char * int(match.group(1))

                    async def generate_fresh(self, *_args, **_kwargs):
                        raise AssertionError("normal planned flow must not use generic continuation")

                client = RangeClient(part_count, target_chars)
                jobs = await ParallelRunner(client, 1).run([
                    ScenarioRequest(
                        0, f"Тема {part_count}", "OPERATOR CONTRACT",
                        target_chars=target_chars,
                        allowed_min=target_chars,
                        allowed_max=target_chars,
                    ),
                ])

                job = jobs[0]
                self.assertEqual(job.state, RunState.DONE)
                self.assertEqual(job.length_status, "READY")
                self.assertEqual(job.actual_chars, target_chars)
                self.assertTrue(all("ПРОДОЛЖИ" not in prompt for prompt in client.prompts))

                if part_count == 1:
                    self.assertEqual(len(client.prompts), 2)
                    self.assertIn("NewsFlow Story Planner", client.prompts[0])
                    self.assertIn("CURRENT PART: P1", client.prompts[1])
                    self.assertIn("CURRENT ROLE: COMPLETE", client.prompts[1])
                    self.assertEqual(len(job.accepted_story_parts), 1)
                    continue

                self.assertEqual(len(client.prompts), part_count + 1)
                self.assertIn("NewsFlow Story Planner", client.prompts[0])
                writer_prompts = client.prompts[1:]
                self.assertEqual(len(job.accepted_story_parts), part_count)
                self.assertIn("CURRENT ROLE: OPENING", writer_prompts[0])
                self.assertIn("CURRENT ROLE: FINAL", writer_prompts[-1])
                for middle_prompt in writer_prompts[1:-1]:
                    self.assertIn("CURRENT ROLE: MIDDLE", middle_prompt)
                    self.assertIn("NO GLOBAL FINAL", middle_prompt)

    async def test_remaining_part_targets_stay_aligned_with_reserved_material_after_a_shorter_part(self):
        class RebalanceClient:
            def __init__(self):
                self.prompts = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(3)
                match = __import__("re").search(
                    r"CURRENT TARGET: approximately (\d+) characters", prompt,
                )
                target = int(match.group(1))
                if "CURRENT PART: P1" in prompt:
                    return "А" * 4000
                return "Б" * target if "CURRENT PART: P2" in prompt else "В" * target

        client = RebalanceClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "OPERATOR CONTRACT", target_chars=15000,
                            allowed_min=15000, allowed_max=15000),
        ])

        p2_prompt = next(prompt for prompt in client.prompts if "CURRENT PART: P2" in prompt)
        p3_prompt = next(prompt for prompt in client.prompts if "CURRENT PART: P3" in prompt)
        # A short accepted prefix is immutable.  Its missing volume must not
        # silently turn P2/P3 into larger assignments than their Story Map
        # material was planned to support.
        self.assertIn("CURRENT TARGET: approximately 4999 characters", p2_prompt)
        self.assertIn("CURRENT TARGET: approximately 4998 characters", p3_prompt)
        self.assertEqual(jobs[0].actual_chars, 14001)
        self.assertEqual(jobs[0].length_status, "SHORT")
        self.assertEqual(jobs[0].state, RunState.DONE)

    async def test_early_overlong_part_is_accepted_without_length_retry(self):
        class EarlyLongClient:
            def __init__(self):
                self.fresh_calls = 0

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(2)
                target = int(__import__("re").search(
                    r"CURRENT TARGET: approximately (\d+) characters", prompt,
                ).group(1))
                if "CURRENT PART: P1" in prompt:
                    return "А" * 12000
                return "Б" * target

            async def generate_fresh(self, *_args, **_kwargs):
                self.fresh_calls += 1
                raise AssertionError("length alone must not trigger another provider request")

        client = EarlyLongClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "CONTRACT", target_chars=10000,
                            allowed_min=9000, allowed_max=11000),
        ])

        self.assertEqual(client.fresh_calls, 0)
        self.assertEqual(jobs[0].state, RunState.DONE, jobs[0].error)
        self.assertEqual(jobs[0].length_status, "LONG")
        self.assertGreater(jobs[0].actual_chars, 11000)
        self.assertEqual([row["part_id"] for row in jobs[0].accepted_story_parts], ["P1", "P2"])

    async def test_short_final_multipart_part_is_accepted_without_length_retry(self):
        class FinalLengthClient:
            def __init__(self):
                self.fresh_calls = 0

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(2)
                target = int(__import__("re").search(
                    r"CURRENT TARGET: approximately (\d+) characters", prompt,
                ).group(1))
                if "CURRENT PART: P2" in prompt:
                    return "Б" * 1000
                return "А" * target

            async def generate_fresh(self, *_args, **_kwargs):
                self.fresh_calls += 1
                raise AssertionError("SHORT final must not trigger another provider request")

        client = FinalLengthClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "CONTRACT", target_chars=10000,
                            allowed_min=10000, allowed_max=10000),
        ])

        self.assertEqual(client.fresh_calls, 0)
        self.assertEqual(jobs[0].state, RunState.DONE, jobs[0].error)
        self.assertEqual(jobs[0].length_status, "SHORT")
        self.assertLess(jobs[0].actual_chars, 10000)
        self.assertEqual([row["part_id"] for row in jobs[0].accepted_story_parts], ["P1", "P2"])

    async def test_three_part_short_final_finishes_without_rewriting_prefix_or_extra_calls(self):
        class ShortFinalClient:
            def __init__(self):
                self.planner_calls = 0
                self.writer_parts = []
                self.fresh_calls = 0

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "NewsFlow Story Planner" in prompt:
                    self.planner_calls += 1
                    return ParallelRunnerTests._story_plan_json(3)
                part = __import__("re").search(r"CURRENT PART: (P\d+)", prompt).group(1)
                target = int(__import__("re").search(
                    r"CURRENT TARGET: approximately (\d+) characters", prompt,
                ).group(1))
                self.writer_parts.append(part)
                if part == "P1":
                    return "А" * target
                if part == "P2":
                    return "Б" * target
                return "В" * 500

            async def generate_fresh(self, *_args, **_kwargs):
                self.fresh_calls += 1
                raise AssertionError("length alone must never trigger a fresh request")

        client = ShortFinalClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(
                0, "Тема", "CONTRACT", target_chars=15000,
                allowed_min=15000, allowed_max=15000,
            ),
        ])

        job = jobs[0]
        self.assertEqual(client.planner_calls, 1)
        self.assertEqual(client.writer_parts, ["P1", "P2", "P3"])
        self.assertEqual(client.fresh_calls, 0)
        self.assertEqual(job.state, RunState.DONE, job.error)
        self.assertEqual(job.length_status, "SHORT")
        self.assertEqual([row["part_id"] for row in job.accepted_story_parts], ["P1", "P2", "P3"])
        self.assertEqual(job.accepted_story_parts[0]["text"], "А" * 4999)
        self.assertEqual(job.accepted_story_parts[1]["text"], "Б" * 4999)
        self.assertEqual(job.accepted_story_parts[2]["text"], "В" * 500)

    async def test_short_final_is_durable_done_and_does_not_require_manual_retry(self):
        class StickyFinalClient:
            def __init__(self):
                self.planner_calls = 0
                self.final_calls = 0
                self.fresh_calls = 0

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "NewsFlow Story Planner" in prompt:
                    self.planner_calls += 1
                    return ParallelRunnerTests._story_plan_json(2)
                target = int(__import__("re").search(
                    r"CURRENT TARGET: approximately (\d+) characters", prompt,
                ).group(1))
                if "CURRENT PART: P2" in prompt:
                    self.final_calls += 1
                    return "Б" * 1000
                return "А" * target

            async def generate_fresh(self, *_args, **_kwargs):
                self.fresh_calls += 1
                raise AssertionError("length alone must not request retry")

        client = StickyFinalClient()
        request = ScenarioRequest(
            0, "Тема", "CONTRACT", target_chars=10000,
            allowed_min=10000, allowed_max=10000,
        )
        result = (await ParallelRunner(client, 1).run([request]))[0]

        self.assertEqual(result.state, RunState.DONE)
        self.assertEqual(result.length_status, "SHORT")
        self.assertEqual([row["part_id"] for row in result.accepted_story_parts], ["P1", "P2"])
        self.assertEqual(client.planner_calls, 1)
        self.assertEqual(client.final_calls, 1)
        self.assertEqual(client.fresh_calls, 0)

    async def test_long_final_multipart_part_is_accepted_without_trim_or_retry(self):
        class LongFinalClient:
            def __init__(self):
                self.fresh_calls = 0

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(2)
                target = int(__import__("re").search(
                    r"CURRENT TARGET: approximately (\d+) characters", prompt,
                ).group(1))
                if "CURRENT PART: P2" in prompt:
                    return "Б" * (target + 2000)
                return "А" * target

            async def generate_fresh(self, *_args, **_kwargs):
                self.fresh_calls += 1
                raise AssertionError("LONG final must not trigger another provider request")

        client = LongFinalClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "CONTRACT", target_chars=10000,
                            allowed_min=10000, allowed_max=10000),
        ])

        self.assertEqual(client.fresh_calls, 0)
        self.assertEqual(jobs[0].state, RunState.DONE, jobs[0].error)
        self.assertEqual(jobs[0].length_status, "LONG")
        self.assertGreater(jobs[0].actual_chars, 10000)
        self.assertEqual(len(jobs[0].accepted_story_parts[1]["text"]), 6999)

    async def test_fifty_thousand_story_uses_ten_owned_parts(self):
        class TenPartClient:
            def __init__(self):
                self.prompts = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(10)
                match = __import__("re").search(r"CURRENT PART: P(\d+)", prompt)
                return chr(0x0400 + int(match.group(1))) * 5000

        client = TenPartClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "OPERATOR CONTRACT", target_chars=50000,
                            allowed_min=48000, allowed_max=52000),
        ])
        self.assertEqual(len(client.prompts), 11)
        self.assertEqual(len(jobs[0].accepted_story_parts), 10)
        self.assertEqual(jobs[0].state, RunState.DONE)

    async def test_one_hundred_fifty_thousand_story_uses_thirty_owned_parts_and_bounded_context(self):
        class ThirtyPartClient:
            def __init__(self):
                self.prompts = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(30)
                match = __import__("re").search(r"CURRENT PART: P(\d+)", prompt)
                if not match:
                    raise AssertionError("writer prompt must name exactly one planned part")
                return chr(0x0400 + int(match.group(1))) * 5000

        client = ThirtyPartClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "OPERATOR CONTRACT", target_chars=150000,
                            allowed_min=145000, allowed_max=155000),
        ])
        self.assertEqual(len(client.prompts), 31)
        part_17_prompt = next(prompt for prompt in client.prompts if "CURRENT PART: P17" in prompt)
        self.assertIn("P18/M1: Смысловой блок 18", part_17_prompt)
        self.assertIn("C018 [SUPPORTED]: Новый материал 18", part_17_prompt)
        self.assertIn("EARLIER USED IDS: C001, C002", part_17_prompt)
        self.assertIn("USED CONTENT (do not repeat): C011 [SUPPORTED]: Новый материал 11", part_17_prompt)
        self.assertIn("FUTURE RESERVED IDS ONLY: P20: [C020]", part_17_prompt)
        self.assertIn("PREVIOUS SEAM TAIL", part_17_prompt)
        self.assertNotIn(chr(0x0401) * 5000, part_17_prompt)
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertEqual(len(jobs[0].accepted_story_parts), 30)

    async def test_planner_material_and_writer_targets_scale_without_final_deficit_transfer(self):
        """Every size plans complete material and keeps each Writer to its reserved budget."""
        cases = (
            0, 2000, 6000, 9000, 9001, 10000, 12000, 12501,
            20000, 24999, 30000, 50000, 75001, 100000,
        )

        for target_chars in cases:
            with self.subTest(target_chars=target_chars):
                targets = calculate_story_part_targets(target_chars)

                class MatrixClient:
                    def __init__(self, planned_targets):
                        self.planned_targets = planned_targets
                        self.planner_budgets = []
                        self.writer_prompts = []

                    async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                        if "NewsFlow Story Planner" in prompt:
                            self.planner_budgets.append(max_output_tokens)
                            return ParallelRunnerTests._story_plan_json(len(self.planned_targets))
                        self.writer_prompts.append(prompt)
                        target_match = __import__("re").search(
                            r"CURRENT TARGET: approximately (\d+) characters", prompt,
                        )
                        if target_match is None:
                            if "CURRENT TARGET: no explicit character target" not in prompt:
                                raise AssertionError("zero-target Writer prompt lost its natural-length contract")
                            return "Б"
                        current = int(target_match.group(1))
                        # P1 is deliberately short. Later assignments must
                        # still reflect their reserved material, not fill P1's
                        # deficit in the FINAL part.
                        if "CURRENT PART: P1" in prompt and len(self.planned_targets) > 1:
                            return "А" * max(1, current // 2)
                        return "Б" * current

                client = MatrixClient(targets)
                request = ScenarioRequest(
                    0, "Масштабируемая тема", "CONTRACT",
                    target_chars=target_chars,
                    allowed_min=max(1, target_chars - 500) if target_chars else 0,
                    allowed_max=target_chars + 500 if target_chars else 0,
                )
                job = (await ParallelRunner(client, 1).run([request]))[0]

                self.assertEqual([part.id for part in story_plan_from_dict(job.story_plan).parts], [
                    f"P{index}" for index in range(1, len(targets) + 1)
                ])
                self.assertEqual(len(client.writer_prompts), len(targets))
                self.assertEqual(
                    [row["target_chars"] for row in job.accepted_story_parts], list(targets),
                )
                self.assertTrue(all("MATERIAL ALLOCATION:" in prompt for prompt in client.writer_prompts))
                self.assertTrue(all(
                    "CURRENT EVENT SEQUENCE (the only content to develop):" in prompt
                    and "[SUPPORTED]:\n  1. объект" in prompt
                    and "ответственная служба проверила изменение" in prompt
                    and "следующий шаг использует результат" in prompt
                    for prompt in client.writer_prompts
                ))
                self.assertEqual(
                    client.planner_budgets,
                    [scenario_output_token_budget(request, 1536 + len(targets) * 1536)],
                )
                self.assertEqual(job.state, RunState.DONE)

        # 50k+ maps are complete multi-part maps; their Planner allowance must
        # scale past the old 8192 ceiling instead of truncating tail atoms.
        self.assertGreater(
            scenario_output_token_budget(
                ScenarioRequest(0, "T", "P", target_chars=50000),
                1536 + len(calculate_story_part_targets(50000)) * 1536,
            ),
            8192,
        )

    async def test_headline_only_multipart_story_completes_without_capacity_pause(self):
        class HeadlineOnlyClient:
            def __init__(self):
                self.prompts = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    if "Even if only a headline is available" not in prompt:
                        raise AssertionError("headline-only planner rule is missing")
                    return ParallelRunnerTests._story_plan_json(2)
                if "CURRENT PART: P1" in prompt:
                    return "А" * 4999
                if "CURRENT PART: P2" in prompt:
                    return "Б" * 4999
                raise AssertionError("writer must receive one owned planned part")

        client = HeadlineOnlyClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Headline only", "", target_chars=10000,
                            allowed_min=9000, allowed_max=11000),
        ])

        self.assertEqual(len(client.prompts), 3)
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertEqual(jobs[0].story_planner_status, "READY")
        self.assertEqual(len(jobs[0].accepted_story_parts), 2)

    async def test_headline_only_targets_finish_at_two_three_and_six_parts(self):
        for target_chars, expected_parts in ((10000, 2), (15000, 3), (30000, 6)):
            with self.subTest(target_chars=target_chars):
                class HeadlineOnlyClient:
                    def __init__(self, current_parts=expected_parts):
                        self.expected_parts = current_parts
                        self.prompts = []

                    async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                        self.prompts.append(prompt)
                        if "NewsFlow Story Planner" in prompt:
                            return ParallelRunnerTests._story_plan_json(self.expected_parts)
                        part = __import__("re").search(r"CURRENT PART: P(\d+)", prompt)
                        target = __import__("re").search(
                            r"CURRENT TARGET: approximately (\d+) characters", prompt,
                        )
                        if not part or not target:
                            raise AssertionError("headline-only writer requires one planned part and target")
                        return chr(0x0410 + int(part.group(1))) * int(target.group(1))

                client = HeadlineOnlyClient()
                jobs = await ParallelRunner(client, 1).run([
                    ScenarioRequest(0, "Headline only", "", target_chars=target_chars,
                                    allowed_min=target_chars - 100, allowed_max=target_chars + 100),
                ])

                self.assertEqual(jobs[0].state, RunState.DONE, jobs[0].error)
                self.assertEqual(jobs[0].story_planner_status, "READY")
                self.assertEqual(len(jobs[0].accepted_story_parts), expected_parts)

    async def test_transport_wrapped_planner_json_goes_directly_to_writers_without_repair(self):
        class WrappedPlannerClient:
            def __init__(self):
                self.prompts = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    return "Here is the JSON:\n```json\n" + ParallelRunnerTests._story_plan_json(2) + "\n```"
                if "structural repairer" in prompt:
                    raise AssertionError("valid wrapped JSON must not trigger structural repair")
                target = int(__import__("re").search(
                    r"CURRENT TARGET: approximately (\d+) characters", prompt,
                ).group(1))
                return "Т" * target

        client = WrappedPlannerClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "контекст", target_chars=10000,
                            allowed_min=9000, allowed_max=11000),
        ])

        self.assertEqual(jobs[0].state, RunState.DONE, jobs[0].error)
        self.assertEqual(len(jobs[0].accepted_story_parts), 2)
        self.assertEqual(sum("NewsFlow Story Planner" in p for p in client.prompts), 1)

    async def test_non_topology_planner_schema_failure_gets_one_fresh_retry_before_any_writer(self):
        class PlannerRetryClient:
            def __init__(self):
                self.initial_planner_calls = 0
                self.structural_calls = 0
                self.fresh_calls = 0
                self.writer_calls = 0
                self.fresh_prompt = ""

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "structural repairer" in prompt:
                    self.structural_calls += 1
                    return json.dumps({
                        "parts": json.loads(ParallelRunnerTests._story_plan_json(2))["parts"],
                    }, ensure_ascii=False)
                if "NewsFlow Story Planner" in prompt:
                    self.initial_planner_calls += 1
                    raw = json.loads(ParallelRunnerTests._story_plan_json(2))
                    raw["content_atoms"][0].pop("content_kind")
                    return json.dumps(raw, ensure_ascii=False)
                self.writer_calls += 1
                target = int(__import__("re").search(
                    r"CURRENT TARGET: approximately (\d+) characters", prompt,
                ).group(1))
                return "Т" * target

            async def generate_fresh(self, prompt, on_progress=None, max_output_tokens=None):
                if "FRESH STORY PLANNER RETRY" not in prompt:
                    raise AssertionError("schema recovery must use the bounded fresh Planner path")
                self.fresh_calls += 1
                return ParallelRunnerTests._story_plan_json(2)

        client = PlannerRetryClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "контекст", target_chars=10000,
                            allowed_min=9000, allowed_max=11000),
        ])

        self.assertEqual(client.initial_planner_calls, 1)
        self.assertEqual(client.structural_calls, 0)
        self.assertEqual(client.fresh_calls, 1)
        self.assertEqual(client.writer_calls, 2)
        self.assertEqual(jobs[0].state, RunState.DONE, jobs[0].error)
        self.assertEqual(len(jobs[0].accepted_story_parts), 2)

    async def test_missing_transition_fields_skip_structural_repair_and_use_one_fresh_planner(self):
        """Atom-contract failures cannot be repaired by changing only parts."""
        class TransitionRecoveryClient:
            def __init__(self):
                self.structural_calls = 0
                self.fresh_calls = 0
                self.writer_calls = 0

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "structural repairer" in prompt:
                    self.structural_calls += 1
                    raise AssertionError("missing transition fields must skip parts-only repair")
                if "NewsFlow Story Planner" in prompt:
                    raw = json.loads(ParallelRunnerTests._story_plan_json(2))
                    raw["content_atoms"][0].pop("state_after")
                    return json.dumps(raw, ensure_ascii=False)
                self.writer_calls += 1
                target = int(__import__("re").search(
                    r"CURRENT TARGET: approximately (\d+) characters", prompt,
                ).group(1))
                return "Т" * target

            async def generate_fresh(self, prompt, on_progress=None, max_output_tokens=None):
                self.fresh_calls += 1
                self.fresh_prompt = prompt
                if "MISSING_TRANSITION_FIELDS" not in prompt:
                    raise AssertionError("fresh retry must carry only a safe normalized reason")
                return ParallelRunnerTests._story_plan_json(2)

        client = TransitionRecoveryClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "контекст", target_chars=10000,
                            allowed_min=9000, allowed_max=11000),
        ])

        self.assertEqual(client.structural_calls, 0)
        self.assertEqual(client.fresh_calls, 1)
        self.assertIn("state_before, changed_subject, development, resulting_state and state_after", client.fresh_prompt)
        self.assertIn("state_transition_contract=BEFORE_DEVELOPMENT_AFTER", client.fresh_prompt)
        self.assertEqual(client.writer_calls, 2)
        self.assertEqual(jobs[0].state, RunState.DONE, jobs[0].error)

    async def test_invalid_atom_precedes_wrong_part_count_and_skips_structural_repair(self):
        """The Runner must classify atoms before topology from the same malformed map."""
        class OrderedValidationClient:
            def __init__(self):
                self.structural_calls = 0
                self.fresh_prompt = ""
                self.planner_calls = 0

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "structural repairer" in prompt:
                    self.structural_calls += 1
                    raise AssertionError("invalid atoms must not be hidden by part-count repair")
                if "NewsFlow Story Planner" in prompt:
                    self.planner_calls += 1
                    raw = json.loads(ParallelRunnerTests._story_plan_json(3))
                    raw["parts"] = raw["parts"][:1]
                    raw["content_atoms"][0].pop("state_after")
                    return json.dumps(raw, ensure_ascii=False)
                target = int(__import__("re").search(
                    r"CURRENT TARGET: approximately (\d+) characters", prompt,
                ).group(1))
                return "Т" * target

            async def generate_fresh(self, prompt, on_progress=None, max_output_tokens=None):
                self.fresh_prompt = prompt
                return ParallelRunnerTests._story_plan_json(3)

        client = OrderedValidationClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "контекст", target_chars=12000,
                            allowed_min=11000, allowed_max=13000),
        ])

        self.assertEqual(client.structural_calls, 0)
        self.assertIn("MISSING_TRANSITION_FIELDS", client.fresh_prompt)
        self.assertIn("EXACT_PART_COUNT=3; P1=OPENING; P2=MIDDLE; P3=FINAL", client.fresh_prompt)
        self.assertEqual(jobs[0].state, RunState.DONE, jobs[0].error)

    async def test_structured_transition_does_not_trigger_lexical_planner_recovery(self):
        """A lexical diagnostic cannot spend a fresh Planner call."""
        marker = "UNIQUE_ABSTRACT_PLANNER_PAYLOAD_293"

        class AbstractTransitionClient:
            def __init__(self):
                self.structural_calls = 0
                self.fresh_prompt = ""
                self.planner_calls = 0

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "structural repairer" in prompt:
                    self.structural_calls += 1
                    raise AssertionError("abstract transition must skip structural repair")
                if "NewsFlow Story Planner" in prompt:
                    self.planner_calls += 1
                    raw = json.loads(ParallelRunnerTests._story_plan_json(2))
                    raw["thesis"] = marker
                    raw["content_atoms"][0].update({
                        "summary": "Известное событие воспринимается как более жёсткая фаза",
                        "changed_subject": "смысл прежнего события",
                        "development": "событие воспринимается как более важный сигнал",
                        "resulting_state": "политическая цена воспринимается как выросшая",
                    })
                    return json.dumps(raw, ensure_ascii=False)
                target = int(__import__("re").search(
                    r"CURRENT TARGET: approximately (\d+) characters", prompt,
                ).group(1))
                return "Т" * target

            async def generate_fresh(self, prompt, on_progress=None, max_output_tokens=None):
                self.fresh_prompt = prompt
                return ParallelRunnerTests._story_plan_json(2)

        client = AbstractTransitionClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "контекст", target_chars=10000,
                            allowed_min=9000, allowed_max=11000),
        ])

        self.assertEqual(client.structural_calls, 0)
        self.assertEqual(client.fresh_prompt, "")
        self.assertEqual(client.planner_calls, 1)
        self.assertEqual(jobs[0].state, RunState.DONE, jobs[0].error)

    async def test_three_part_planner_has_budget_for_a_complete_transition_map(self):
        """A 12k plan owns nine rich atoms and cannot fit in the old 2k cap."""
        class BudgetClient:
            def __init__(self):
                self.planner_budgets = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "NewsFlow Story Planner" in prompt:
                    self.planner_budgets.append(max_output_tokens)
                    return ParallelRunnerTests._story_plan_json(3)
                target = int(__import__("re").search(
                    r"CURRENT TARGET: approximately (\d+) characters", prompt,
                ).group(1))
                return "Т" * target

        client = BudgetClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "контекст", target_chars=12000,
                            allowed_min=11500, allowed_max=12500),
        ])

        self.assertEqual(jobs[0].state, RunState.DONE, jobs[0].error)
        self.assertEqual(client.planner_budgets, [6144])

    async def test_scenario_runner_never_requests_or_persists_cover_face_metadata(self):
        """Cover identity work belongs to Covers, never Planner/Writer execution."""
        class ScenarioOnlyClient:
            def __init__(self):
                self.prompts = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    raw = json.loads(ParallelRunnerTests._story_plan_json(2))
                    for key in tuple(raw):
                        if key.startswith("cover_"):
                            raw.pop(key)
                    return json.dumps(raw, ensure_ascii=False)
                target = int(__import__("re").search(
                    r"CURRENT TARGET: approximately (\d+) characters", prompt,
                ).group(1))
                return "Т" * target

        client = ScenarioOnlyClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "контекст", target_chars=10000,
                            allowed_min=9000, allowed_max=11000),
        ])

        self.assertEqual(jobs[0].state, RunState.DONE, jobs[0].error)
        self.assertEqual(jobs[0].story_planner_status, "READY")
        self.assertFalse(any(key.startswith("cover_") for key in jobs[0].story_plan))
        self.assertFalse(any(
            "COVER FACE RESOLUTION" in prompt or "Cover Face Resolver" in prompt
            for prompt in client.prompts
        ))

    async def test_malformed_cover_metadata_cannot_block_a_valid_story(self):
        """Legacy/provider cover fields are ignored even when their values are invalid."""
        class LegacyCoverClient:
            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "NewsFlow Story Planner" in prompt:
                    raw = json.loads(ParallelRunnerTests._story_plan_json(1))
                    raw.update({
                        "cover_face_required": False,
                        "cover_people_candidates": "not a candidate list",
                        "cover_primary_person": {"name": "Европейский Союз", "entity_type": "organization"},
                        "cover_face_resolution_status": "NEEDS_REVIEW",
                    })
                    return json.dumps(raw, ensure_ascii=False)
                target = int(__import__("re").search(
                    r"CURRENT TARGET: approximately (\d+) characters", prompt,
                ).group(1))
                return "Т" * target

        jobs = await ParallelRunner(LegacyCoverClient(), 1).run([
            ScenarioRequest(0, "Тема", "контекст", target_chars=6000,
                            allowed_min=5000, allowed_max=7000),
        ])

        self.assertEqual(jobs[0].state, RunState.DONE, jobs[0].error)
        self.assertEqual(jobs[0].story_planner_status, "READY")
        self.assertFalse(any(key.startswith("cover_") for key in jobs[0].story_plan))

    async def test_legacy_cover_plan_resumes_without_a_face_marker_or_provider_call(self):
        """r27 Story Maps keep their accepted prefix and resume as pure story work."""
        from scriptor.story_planner import parse_story_plan_response

        request = ScenarioRequest(0, "Тема", "контекст", target_chars=6000,
                                  allowed_min=5000, allowed_max=7000)
        persisted = parse_story_plan_response(
            ParallelRunnerTests._story_plan_json(1), (6000,),
        ).to_dict()
        persisted.update({
            "length_contract": {"target_chars": 6000, "allowed_min": 5000, "allowed_max": 7000},
            "cover_face_required": True,
            "cover_primary_person": {"name": "Старое лицо", "entity_type": "organization"},
            "cover_face_resolution_status": "FACE_REPAIR_DEFERRED",
        })

        class ResumeClient:
            def __init__(self):
                self.prompts = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompts.append(prompt)
                target = int(__import__("re").search(
                    r"CURRENT TARGET: approximately (\d+) characters", prompt,
                ).group(1))
                return "Т" * target

        client = ResumeClient()
        jobs = await ParallelRunner(client, 1).run(
            [request],
            resume_jobs={0: Job(
                request, RunState.WAITING, story_plan=persisted,
                story_planner_status="FACE_REPAIR_DEFERRED",
            )},
        )

        self.assertEqual(jobs[0].state, RunState.DONE, jobs[0].error)
        self.assertEqual(jobs[0].story_planner_status, "READY")
        self.assertFalse(any(
            "COVER FACE RESOLUTION" in prompt or "Cover Face Resolver" in prompt
            for prompt in client.prompts
        ))

    async def test_exhausted_planner_schema_recovery_persists_safe_diagnostics(self):
        """Repeated invalid Planner replies expose a safe, durable recovery code."""
        class InvalidPlannerClient:
            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                return json.dumps({"macro_blocks": [], "content_atoms": [], "parts": []})

            async def generate_fresh(self, prompt, on_progress=None, max_output_tokens=None):
                return json.dumps({"macro_blocks": [], "content_atoms": [], "parts": []})

        jobs = await ParallelRunner(InvalidPlannerClient(), 1).run([
            ScenarioRequest(0, "Тема", "контекст", target_chars=10000,
                            allowed_min=9000, allowed_max=11000),
        ])

        self.assertEqual(jobs[0].state, RunState.PAUSED)
        self.assertEqual(jobs[0].story_planner_status, "SCHEMA_RECOVERY_EXHAUSTED")
        self.assertIn("FRESH_SCHEMA:MISSING_THESIS", jobs[0].error)
        self.assertNotIn("story plan requires", jobs[0].error)
        self.assertEqual(jobs[0].accepted_story_parts, [])
        self.assertEqual(jobs[0].story_planner_failure["phase"], "FRESH_SCHEMA")
        self.assertEqual(jobs[0].story_planner_failure["reason"], "MISSING_THESIS")
        self.assertEqual(jobs[0].story_planner_failure["initial_reason"], "MISSING_THESIS")
        self.assertEqual(jobs[0].story_planner_failure["recovery_route"], "FRESH_DIRECT")
        self.assertEqual(jobs[0].story_planner_failure["fresh_reason"], "MISSING_THESIS")
        self.assertEqual(jobs[0].story_planner_failure["response_chars"], "54")
        self.assertRegex(jobs[0].story_planner_failure["response_sha256"], r"^[0-9a-f]{64}$")

    async def test_real_parser_ownership_failure_uses_parts_only_repair(self):
        """The real ownership parser error is repairable without a fresh Planner."""
        invalid_plan = json.loads(self._story_plan_json(2))
        invalid_plan["content_atoms"][0]["owner_part_id"] = "P3"

        class OwnershipFailureClient:
            def __init__(self):
                self.structural_calls = 0
                self.fresh_calls = 0

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "structural repairer" in prompt:
                    self.structural_calls += 1
                    return json.dumps({
                        "parts": json.loads(ParallelRunnerTests._story_plan_json(2))["parts"],
                    }, ensure_ascii=False)
                if "NewsFlow Story Planner" not in prompt:
                    target = int(__import__("re").search(
                        r"CURRENT TARGET: approximately (\d+) characters", prompt,
                    ).group(1))
                    return "Т" * target
                return json.dumps(invalid_plan, ensure_ascii=False)

            async def generate_fresh(self, prompt, on_progress=None, max_output_tokens=None):
                self.fresh_calls += 1
                raise AssertionError("correctable ownership must not regenerate the Story Map")

        client = OwnershipFailureClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "контекст", target_chars=10000,
                            allowed_min=9000, allowed_max=11000),
        ])

        self.assertEqual(client.structural_calls, 1)
        self.assertEqual(client.fresh_calls, 0)
        self.assertEqual(jobs[0].state, RunState.DONE, jobs[0].error)
        self.assertEqual(len(jobs[0].accepted_story_parts), 2)

    async def test_exhausted_planner_never_persists_raw_fresh_provider_payload(self):
        """Actual Runner diagnostics retain only a fingerprint of invalid provider prose."""
        from scriptor.session import _session_data

        marker = "UNIQUE_PROVIDER_PAYLOAD_MARKER_290_sk_test_never_persist"
        fresh_response = f"not valid Story Map {marker}"

        class PrivateInvalidPlannerClient:
            def __init__(self):
                self.fresh_prompt = ""
                self.writer_calls = 0

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "structural repairer" in prompt:
                    return json.dumps({"parts": []})
                if "NewsFlow Story Planner" not in prompt:
                    self.writer_calls += 1
                    raise AssertionError("Writer must not run after Planner recovery exhausts")
                return json.dumps({"macro_blocks": [], "content_atoms": [], "parts": []})

            async def generate_fresh(self, prompt, on_progress=None, max_output_tokens=None):
                self.fresh_prompt = prompt
                return fresh_response

        client = PrivateInvalidPlannerClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "контекст", target_chars=10000,
                            allowed_min=9000, allowed_max=11000),
        ])
        persisted = _session_data(["Тема"], jobs)
        serialized = json.dumps(persisted, ensure_ascii=False)
        diagnostics = persisted["jobs"][0]["story_planner_failure"]

        self.assertEqual(jobs[0].story_planner_status, "SCHEMA_RECOVERY_EXHAUSTED")
        self.assertEqual(client.writer_calls, 0)
        self.assertNotIn(marker, client.fresh_prompt)
        self.assertNotIn(marker, jobs[0].error)
        self.assertNotIn(marker, serialized)
        self.assertNotIn("sk_test_never_persist", serialized)
        self.assertEqual(set(diagnostics), {
            "phase", "reason", "initial_reason", "recovery_route", "fresh_reason",
            "structural_repair_reason", "response_chars", "response_sha256",
        })
        self.assertEqual(diagnostics["initial_reason"], "MISSING_THESIS")
        self.assertEqual(diagnostics["recovery_route"], "FRESH_DIRECT")
        self.assertEqual(diagnostics["fresh_reason"], "NON_JSON")
        self.assertEqual(diagnostics["structural_repair_reason"], "")
        self.assertEqual(diagnostics["response_chars"], str(len(fresh_response)))
        self.assertEqual(diagnostics["response_sha256"], sha256(fresh_response.encode("utf-8")).hexdigest())

    async def test_missing_thesis_uses_one_bounded_fresh_planner_recovery(self):
        """The live failure class gets a usable Story Map before Writer starts."""
        class MissingThesisClient:
            def __init__(self):
                self.fresh_calls = 0
                self.writer_calls = 0

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "structural repairer" in prompt:
                    raise AssertionError("missing thesis must skip parts-only repair")
                if "NewsFlow Story Planner" in prompt:
                    raw = json.loads(ParallelRunnerTests._story_plan_json(2))
                    raw.pop("thesis")
                    return json.dumps(raw, ensure_ascii=False)
                self.writer_calls += 1
                target = int(__import__("re").search(
                    r"CURRENT TARGET: approximately (\d+) characters", prompt,
                ).group(1))
                return "Т" * target

            async def generate_fresh(self, prompt, on_progress=None, max_output_tokens=None):
                self.fresh_calls += 1
                self.assertIn("FRESH STORY PLANNER RETRY", prompt)
                return ParallelRunnerTests._story_plan_json(2)

            def assertIn(self, member, container):
                if member not in container:
                    raise AssertionError(f"{member!r} missing")

        client = MissingThesisClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "контекст", target_chars=10000,
                            allowed_min=9000, allowed_max=11000),
        ])

        self.assertEqual(client.fresh_calls, 1)
        self.assertEqual(client.writer_calls, 2)
        self.assertEqual(jobs[0].state, RunState.DONE, jobs[0].error)

    async def test_wrong_part_count_gets_one_structural_repair_then_exact_two_part_story(self):
        class StructuralRepairClient:
            def __init__(self):
                self.calls = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None,
                               instructions=None, text_format=None):
                self.calls.append((prompt, instructions, text_format))
                if "NewsFlow Story Planner" in (instructions or ""):
                    raw = json.loads(ParallelRunnerTests._story_plan_json(2))
                    raw["parts"] = raw["parts"][:1]
                    return json.dumps(raw, ensure_ascii=False)
                if "structural repairer" in (instructions or ""):
                    return json.dumps({"parts": json.loads(ParallelRunnerTests._story_plan_json(2))["parts"]}, ensure_ascii=False)
                target = __import__("re").search(r"CURRENT TARGET: approximately (\d+) characters", prompt)
                return "С" * int(target.group(1))

        client = StructuralRepairClient()
        jobs = await ParallelRunner(client, 1).run([ScenarioRequest(0, "Тема", "контекст", target_chars=10000, allowed_min=9000, allowed_max=11000)])
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertEqual([part["part_id"] for part in jobs[0].accepted_story_parts], ["P1", "P2"])
        self.assertEqual(sum("NewsFlow Story Planner" in instructions for _prompt, instructions, _format in client.calls), 1)
        self.assertEqual(sum("structural repairer" in instructions for _prompt, instructions, _format in client.calls), 1)
        self.assertEqual(client.calls[0][2]["name"], "newsflow_story_plan")
        repair = next(call for call in client.calls if "structural repairer" in call[1])
        self.assertEqual(repair[2]["name"], "newsflow_story_plan_parts_repair")

    async def test_failed_structural_repair_persists_only_safe_repair_reason_before_fresh_failure(self):
        """A failed parts-only repair exposes its code, never either provider payload."""
        class FailedRepairClient:
            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "structural repairer" in prompt:
                    return json.dumps({"parts": []})
                raw = json.loads(ParallelRunnerTests._story_plan_json(2))
                raw["parts"] = raw["parts"][:1]
                return json.dumps(raw, ensure_ascii=False)

            async def generate_fresh(self, prompt, on_progress=None, max_output_tokens=None):
                raw = json.loads(ParallelRunnerTests._story_plan_json(2))
                raw["parts"] = raw["parts"][:1]
                return json.dumps(raw, ensure_ascii=False)

        jobs = await ParallelRunner(FailedRepairClient(), 1).run([
            ScenarioRequest(0, "Тема", "контекст", target_chars=10000,
                            allowed_min=9000, allowed_max=11000),
        ])

        failure = jobs[0].story_planner_failure
        self.assertEqual(jobs[0].state, RunState.PAUSED)
        self.assertEqual(failure["initial_reason"], "PART_COUNT")
        self.assertEqual(failure["recovery_route"], "STRUCTURAL_REPAIR")
        self.assertEqual(failure["structural_repair_reason"], "CONTENT_OWNERSHIP")
        self.assertEqual(failure["fresh_reason"], "PART_COUNT")

    async def test_structural_repair_reassigns_one_or_three_part_atoms_before_writers_finish(self):
        """Bounded topology repair fixes realistic 1→2 and 3→2 ownership before prose starts."""
        for returned_parts in (1, 3):
            with self.subTest(returned_parts=returned_parts):
                class StructuralOwnershipClient:
                    def __init__(self):
                        self.prompts = []

                    async def generate(self, prompt, on_progress=None, max_output_tokens=None, _case=returned_parts):
                        self.prompts.append(prompt)
                        if "NewsFlow Story Planner" in prompt:
                            raw = json.loads(ParallelRunnerTests._story_plan_json(2))
                            if _case == 1:
                                raw["parts"] = raw["parts"][:1]
                                raw["parts"][0]["content_ids"] = ["C001", "C002"]
                                for atom in raw["content_atoms"]:
                                    atom["owner_part_id"] = "P1"
                            else:
                                raw["content_atoms"].append({
                                    "id": "C003", "summary": "Кульминация", "owner_part_id": "P3",
                                    "content_kind": "SUPPORTED",
                                    "state_before": "Состояние до кульминации.",
                                    "state_after": "Состояние после кульминации.",
                                    "changed_subject": "Рабочий объект кульминации",
                                    "development": "исполнитель выполнил кульминационное действие",
                                    "resulting_state": "рабочий объект получил новый статус",
                                })
                                raw["parts"].append({
                                    "id": "P3", "role": "FINAL", "purpose": "Кульминация", "macro_id": "M1",
                                    "content_ids": ["C003"], "opens": [], "closes": [], "transition_direction": "финал",
                                })
                            return json.dumps(raw, ensure_ascii=False)
                        if "structural repairer" in prompt:
                            repaired = json.loads(ParallelRunnerTests._story_plan_json(2))["parts"]
                            if _case == 3:
                                repaired[1]["content_ids"] = ["C002", "C003"]
                            return json.dumps({"parts": repaired}, ensure_ascii=False)
                        target = __import__("re").search(r"CURRENT TARGET: approximately (\d+) characters", prompt)
                        return "С" * int(target.group(1))

                client = StructuralOwnershipClient()
                jobs = await ParallelRunner(client, 1).run([
                    ScenarioRequest(0, "Тема", "контекст", target_chars=10000, allowed_min=9000, allowed_max=11000),
                ])

                self.assertEqual(jobs[0].state, RunState.DONE, jobs[0].error)
                self.assertEqual([part["part_id"] for part in jobs[0].accepted_story_parts], ["P1", "P2"])
                repaired_atoms = {atom["id"]: atom["owner_part_id"] for atom in jobs[0].story_plan["content_atoms"]}
                self.assertEqual(repaired_atoms["C001"], "P1")
                self.assertEqual(repaired_atoms["C002"], "P2")
                if returned_parts == 3:
                    self.assertEqual(repaired_atoms["C003"], "P2")

    async def test_resume_uses_persisted_plan_and_starts_at_first_unfinished_part(self):
        from scriptor.story_planner import (
            calculate_story_part_targets,
            parse_story_plan_response,
        )

        class ResumeClient:
            def __init__(self):
                self.prompts = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    raise AssertionError("resume must not regenerate a valid persisted plan")
                match = __import__("re").search(r"CURRENT PART: P(\d+)", prompt)
                return chr(0x0410 + int(match.group(1))) * 5000

        request = ScenarioRequest(0, "Тема", "OPERATOR CONTRACT", target_chars=30000,
                                  allowed_min=28000, allowed_max=32000)
        plan = parse_story_plan_response(
            self._story_plan_json(6), calculate_story_part_targets(request.target_chars),
        )
        job = __import__("scriptor.runner", fromlist=["Job"]).Job(
            request=request,
            story_plan=plan.to_dict(),
            accepted_story_parts=[
                {"part_id": f"P{index}", "text": chr(0x0410 + index) * 5000,
                 "content_ids": [f"C{index:03d}"], "target_chars": 5000}
                for index in range(1, 5)
            ],
        )
        client = ResumeClient()
        jobs = await ParallelRunner(client, 1).run([request], resume_jobs={0: job})
        self.assertEqual(len(client.prompts), 2)
        self.assertIn("CURRENT PART: P5", client.prompts[0])
        self.assertIn("CURRENT PART: P6", client.prompts[1])
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertEqual(len(jobs[0].accepted_story_parts), 6)

    async def test_resume_with_changed_length_contract_pauses_without_discarding_accepted_prefix(self):
        from scriptor.runner import Job
        from scriptor.story_planner import (
            calculate_story_part_targets,
            parse_story_plan_response,
        )

        old_request = ScenarioRequest(
            0, "Тема", "OLD", target_chars=10000,
            allowed_min=9000, allowed_max=11000,
        )
        old_plan = parse_story_plan_response(
            ParallelRunnerTests._story_plan_json(2),
            calculate_story_part_targets(10000),
        )
        job = Job(
            request=old_request,
            story_plan=old_plan.to_dict(),
            accepted_story_parts=[{
                "part_id": "P1",
                "text": "А" * 4999,
                "content_ids": ["C001"],
                "target_chars": 4999,
            }],
        )

        class NoProviderCalls:
            async def generate(self, *_args, **_kwargs):
                raise AssertionError("changed length must not call provider or discard accepted prose")

        new_request = ScenarioRequest(
            0, "Тема", "NEW", target_chars=15000,
            allowed_min=14000, allowed_max=16000,
        )
        result = (await ParallelRunner(NoProviderCalls(), 1).run(
            [new_request], resume_jobs={0: job},
        ))[0]

        self.assertEqual(result.state, RunState.PAUSED)
        self.assertEqual(result.length_status, "PLAN_LENGTH_CHANGED")
        self.assertEqual(len(result.accepted_story_parts), 1)
        self.assertEqual(result.result, "А" * 4999)
        self.assertIn("явный перезапуск", result.error)

    async def test_legacy_resume_without_length_metadata_migrates_old_request_before_comparison(self):
        from scriptor.runner import Job
        from scriptor.story_planner import (
            calculate_story_part_targets,
            parse_story_plan_response,
        )

        old_request = ScenarioRequest(
            0, "Тема", "OLD", target_chars=10000,
            allowed_min=9000, allowed_max=11000,
        )
        old_plan = parse_story_plan_response(
            ParallelRunnerTests._story_plan_json(2),
            calculate_story_part_targets(10000),
        ).to_dict()
        self.assertNotIn("length_contract", old_plan)
        job = Job(
            request=old_request,
            story_plan=old_plan,
            accepted_story_parts=[{
                "part_id": "P1",
                "text": "А" * 4999,
                "content_ids": ["C001"],
                "target_chars": 4999,
            }],
        )

        class NoProviderCalls:
            async def generate(self, *_args, **_kwargs):
                raise AssertionError("legacy changed max must be caught before provider use")

        new_request = ScenarioRequest(
            0, "Тема", "NEW", target_chars=10000,
            allowed_min=9000, allowed_max=9500,
        )
        result = (await ParallelRunner(NoProviderCalls(), 1).run(
            [new_request], resume_jobs={0: job},
        ))[0]

        self.assertEqual(result.state, RunState.PAUSED)
        self.assertEqual(result.length_status, "PLAN_LENGTH_CHANGED")
        self.assertEqual(result.result, "А" * 4999)
        self.assertEqual(result.story_plan["length_contract"], {
            "target_chars": 10000,
            "allowed_min": 9000,
            "allowed_max": 11000,
        })

    async def test_malformed_persisted_length_metadata_fails_safe_without_provider_calls(self):
        from scriptor.runner import Job
        from scriptor.story_planner import (
            calculate_story_part_targets,
            parse_story_plan_response,
        )

        request = ScenarioRequest(
            0, "Тема", "CURRENT", target_chars=10000,
            allowed_min=9000, allowed_max=11000,
        )
        plan = parse_story_plan_response(
            ParallelRunnerTests._story_plan_json(2),
            calculate_story_part_targets(10000),
        ).to_dict()
        plan["length_contract"] = "corrupt"
        job = Job(
            request=request,
            story_plan=plan,
            accepted_story_parts=[{
                "part_id": "P1",
                "text": "А" * 4999,
                "content_ids": ["C001"],
                "target_chars": 4999,
            }],
        )

        class NoProviderCalls:
            async def generate(self, *_args, **_kwargs):
                raise AssertionError("corrupt length metadata must fail safe")

        result = (await ParallelRunner(NoProviderCalls(), 1).run(
            [request], resume_jobs={0: job},
        ))[0]

        self.assertEqual(result.state, RunState.PAUSED)
        self.assertEqual(result.length_status, "PLAN_LENGTH_CHANGED")
        self.assertEqual(result.accepted_story_parts, job.accepted_story_parts)

    async def test_resume_with_changed_maximum_pauses_even_when_part_targets_match(self):
        """A persisted prefix must not silently adopt a narrower max contract."""
        from scriptor.runner import Job
        from scriptor.story_planner import (
            calculate_story_part_targets,
            parse_story_plan_response,
        )

        old_request = ScenarioRequest(
            0, "Тема", "OLD", target_chars=10000,
            allowed_min=9000, allowed_max=11000,
        )
        old_plan = parse_story_plan_response(
            ParallelRunnerTests._story_plan_json(2),
            calculate_story_part_targets(10000),
        )
        persisted_plan = old_plan.to_dict()
        persisted_plan["length_contract"] = {
            "target_chars": 10000,
            "allowed_min": 9000,
            "allowed_max": 11000,
        }
        job = Job(
            request=old_request,
            story_plan=persisted_plan,
            accepted_story_parts=[{
                "part_id": "P1",
                "text": "А" * 4999,
                "content_ids": ["C001"],
                "target_chars": 4999,
            }],
        )

        class NoProviderCalls:
            async def generate(self, *_args, **_kwargs):
                raise AssertionError("changed maximum must require an explicit restart")

        new_request = ScenarioRequest(
            0, "Тема", "NEW", target_chars=10000,
            allowed_min=9000, allowed_max=9500,
        )
        result = (await ParallelRunner(NoProviderCalls(), 1).run(
            [new_request], resume_jobs={0: job},
        ))[0]

        self.assertEqual(result.state, RunState.PAUSED)
        self.assertEqual(result.length_status, "PLAN_LENGTH_CHANGED")
        self.assertEqual(result.accepted_story_parts, job.accepted_story_parts)
        self.assertEqual(result.result, "А" * 4999)

    async def test_new_story_plan_persists_its_complete_length_contract(self):
        class ContractClient:
            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(2)
                target = int(__import__("re").search(
                    r"CURRENT TARGET: approximately (\d+) characters", prompt,
                ).group(1))
                return "А" * target

        request = ScenarioRequest(
            0, "Тема", "CONTRACT", target_chars=10000,
            allowed_min=9000, allowed_max=11000,
        )
        result = (await ParallelRunner(ContractClient(), 1).run([request]))[0]

        self.assertEqual(result.state, RunState.DONE)
        self.assertEqual(result.story_plan["length_contract"], {
            "target_chars": 10000,
            "allowed_min": 9000,
            "allowed_max": 11000,
        })

    async def test_writer_part_label_is_not_accepted_as_scenario_prose(self):
        class LabelClient:
            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(2)
                if "CURRENT PART: P1" in prompt:
                    return "PART 1: техническая разметка вместо сценария"
                raise AssertionError("the next part must not start after an invalid accepted part")

        jobs = await ParallelRunner(LabelClient(), 1).run([
            ScenarioRequest(0, "Тема", "CONTRACT", target_chars=10000,
                            allowed_min=9000, allowed_max=11000),
        ])
        self.assertEqual(jobs[0].state, RunState.PAUSED)
        self.assertEqual(jobs[0].accepted_story_parts, [])
        self.assertIn("P1", jobs[0].error)


    async def test_multipart_writer_refusal_pauses_same_unaccepted_part_without_regeneration(self):
        class RetryMultipartClient:
            def __init__(self):
                self.planner_calls = 0
                self.writer_calls = []
                self.fresh_calls = 0

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "NewsFlow Story Planner" in prompt:
                    self.planner_calls += 1
                    return ParallelRunnerTests._story_plan_json(2)
                match = __import__("re").search(r"CURRENT PART: P(\d+)", prompt)
                part_id = int(match.group(1))
                self.writer_calls.append(part_id)
                if part_id == 1:
                    return "К сожалению, я не могу написать такой сценарий. Измените тему."
                raise AssertionError("P2 must not start after an unaccepted P1")

            async def generate_fresh(self, *_args, **_kwargs):
                self.fresh_calls += 1
                raise AssertionError("Writer refusal must not trigger regeneration")

        client = RetryMultipartClient()
        job = (await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Военная тема", "CONTRACT", target_chars=10000,
                            allowed_min=9000, allowed_max=11000),
        ]))[0]

        self.assertEqual(client.planner_calls, 1)
        self.assertEqual(client.fresh_calls, 0)
        self.assertEqual(client.writer_calls, [1])
        self.assertEqual(job.state, RunState.PAUSED)
        self.assertEqual(job.accepted_story_parts, [])

    async def test_multipart_writer_structural_label_pauses_without_regeneration(self):
        class RetryLabelClient:
            def __init__(self):
                self.fresh_calls = 0
                self.writer_calls = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(2)
                if "CURRENT PART: P1" in prompt:
                    self.writer_calls.append("P1")
                    return "PART 1: техническая разметка вместо готового текста"
                self.writer_calls.append("P2")
                raise AssertionError("P2 must not start after a structural P1 response")

            async def generate_fresh(self, *_args, **_kwargs):
                self.fresh_calls += 1
                raise AssertionError("Structural Writer output must not trigger regeneration")

        client = RetryLabelClient()
        job = (await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Тема", "CONTRACT", target_chars=10000,
                            allowed_min=9000, allowed_max=11000),
        ]))[0]

        self.assertEqual(client.fresh_calls, 0)
        self.assertEqual(client.writer_calls, ["P1"])
        self.assertEqual(job.state, RunState.PAUSED)
        self.assertEqual(job.accepted_story_parts, [])
    def test_structural_writer_filter_rejects_part_labels_but_not_normal_part_prose(self):
        self.assertTrue(ParallelRunner._writer_output_is_structural("PART 1: техническая разметка"))
        self.assertTrue(ParallelRunner._writer_output_is_structural("Часть 2: продолжение"))
        self.assertTrue(ParallelRunner._writer_output_is_structural("P3: служебный блок"))
        self.assertFalse(ParallelRunner._writer_output_is_structural(
            "Часть экспертов считает, что переговоры зашли в тупик."
        ))
        self.assertFalse(ParallelRunner._writer_output_is_structural(
            "Часть территории оказалась под ударом, после чего ситуация изменилась."
        ))
        self.assertFalse(ParallelRunner._writer_output_is_structural(
            "Part of the evidence was published later."
        ))


    def test_writer_runtime_gate_rejects_only_technical_failures(self):
        filler = (
            "В этом и заключается главный нерв ситуации. "
            "Именно поэтому пространство для манёвра сузилось. "
            "Это меняет политическую рамку переговоров. "
            "По сути, новая конфигурация делает баланс менее устойчивым. "
            "В этой точке выросла политическая цена решения. "
            "Москва получила новый сигнал о смене логики. "
            "Именно поэтому поле выбора стало ещё уже."
        )
        event_prose = (
            "Ночью Россия нанесла удар по нескольким районам Киева. "
            "После тревоги городские службы перевели критические объекты на резервное питание. "
            "Утром украинская сторона направила партнёрам запрос на дополнительные средства защиты."
        )

        runner = ParallelRunner(FakeClient(), 1)
        self.assertFalse(runner._writer_output_unusable(filler))
        self.assertFalse(runner._writer_output_unusable(event_prose))
        self.assertFalse(runner._writer_output_unusable(
            "Это драматизированная реконструкция событий, а не подтверждённая хроника. "
            "Россия нанесла удар по Киеву."
        ))
        self.assertTrue(runner._writer_output_unusable(""))
        self.assertTrue(runner._writer_output_unusable("P2: служебный блок"))
        self.assertTrue(runner._writer_output_unusable(
            "К сожалению, я не могу написать такой сценарий. Измените тему."
        ))

    async def test_writer_style_is_never_regenerated_at_runtime(self):
        filler = (
            "В этом и заключается главный нерв ситуации. "
            "Именно поэтому пространство для манёвра сузилось. "
            "Это меняет политическую рамку переговоров. "
            "По сути, новая конфигурация делает баланс менее устойчивым. "
            "В этой точке выросла политическая цена решения. "
            "Москва получила новый сигнал о смене логики."
        )

        class NoRewriteClient:
            def __init__(self):
                self.planner_calls = 0
                self.writer_calls = []
                self.fresh_calls = 0

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "NewsFlow Story Planner" in prompt:
                    self.planner_calls += 1
                    return ParallelRunnerTests._story_plan_json(2)
                if "CURRENT PART: P1" in prompt:
                    self.writer_calls.append("P1")
                    return "А" * 5000
                if "CURRENT PART: P2" in prompt:
                    self.writer_calls.append("P2")
                    return filler
                raise AssertionError("unexpected writer part")

            async def generate_fresh(self, *_args, **_kwargs):
                self.fresh_calls += 1
                raise AssertionError("Writer prose must never be regenerated")

        client = NoRewriteClient()
        job = (await ParallelRunner(client, 1).run([ScenarioRequest(
            0, "Тема", "CONTRACT", target_chars=10000,
            allowed_min=9000, allowed_max=11000,
        )]))[0]

        self.assertEqual(client.planner_calls, 1)
        self.assertEqual(client.writer_calls, ["P1", "P2"])
        self.assertEqual(client.fresh_calls, 0)
        self.assertEqual(job.accepted_story_parts[0]["text"], "А" * 5000)
        self.assertEqual(job.accepted_story_parts[1]["text"], filler)
        self.assertEqual(job.state, RunState.DONE, job.error)
    def test_detects_claude_request_to_rephrase_but_not_normal_script(self):
        self.assertTrue(looks_like_action_required("К сожалению, я не могу написать это. Переформулируйте тему."))
        self.assertTrue(looks_like_action_required("Please rephrase the topic and try again."))
        self.assertFalse(looks_like_action_required("Герой сказал: «Я не могу уйти», но затем продолжил путь." * 30))
        self.assertFalse(looks_like_action_required(
            "Юристы заявили, что удар нарушает правила ведения войны. " * 30
        ))
        self.assertFalse(looks_like_action_required(
            "Эвакуацию провели по соображениям безопасности после тревоги. " * 30
        ))
        self.assertTrue(looks_like_action_required("Я не могу выполнить вашу просьбу по соображениям безопасности."))
        self.assertTrue(looks_like_action_required("Пояснение. " * 80 + "Этот запрос нарушает правила, поэтому я не могу продолжить выполнение."))

    async def test_claude_request_is_visible_as_needs_action(self):
        class AskingClient:
            async def generate(self, prompt, on_progress=None):
                return "К сожалению, я не могу написать такой сценарий. Измените тему."

        jobs = await ParallelRunner(AskingClient(), 1).run([ScenarioRequest(0, "S", "P")])
        self.assertEqual(jobs[0].state, RunState.PAUSED)
        self.assertIn("Измените тему", jobs[0].result)


    async def test_writer_refusal_pauses_without_regeneration(self):
        class RetryClient:
            fresh_calls = 0
            async def generate(self, prompt, on_progress=None):
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(1)
                return "К сожалению, я не могу написать такой сценарий. Измените тему."
            async def generate_fresh(self, *_args, **_kwargs):
                self.fresh_calls += 1
                raise AssertionError("Writer refusal must not trigger regeneration")

        client = RetryClient()
        jobs = await ParallelRunner(client, 1).run([ScenarioRequest(0, "S", "P")])
        self.assertEqual(client.fresh_calls, 0)
        self.assertEqual(jobs[0].state, RunState.PAUSED)
        self.assertEqual(jobs[0].accepted_story_parts, [])
    async def test_single_part_targets_use_one_planner_and_one_complete_writer(self):
        for target_chars in (5000, 6000, 7000):
            with self.subTest(target_chars=target_chars):
                class SinglePartClient:
                    def __init__(self):
                        self.prompts = []

                    async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                        self.prompts.append(prompt)
                        if "NewsFlow Story Planner" in prompt:
                            return ParallelRunnerTests._story_plan_json(1)
                        if "CURRENT PART: P1" not in prompt or "CURRENT ROLE: COMPLETE" not in prompt:
                            raise AssertionError("single writer must receive the persisted COMPLETE part")
                        target = int(__import__("re").search(
                            r"CURRENT TARGET: approximately (\d+) characters", prompt,
                        ).group(1))
                        return "а" * target

                client = SinglePartClient()
                jobs = await ParallelRunner(client, 1).run([
                    ScenarioRequest(0, "S", "ORIGINAL WRITING CONTRACT", target_chars=target_chars,
                                    allowed_min=target_chars - 100, allowed_max=target_chars + 100),
                ])
                self.assertEqual(len(client.prompts), 2)
                self.assertIn("NewsFlow Story Planner", client.prompts[0])
                self.assertEqual(jobs[0].state, RunState.DONE)
                self.assertEqual(len(jobs[0].accepted_story_parts), 1)

    async def test_single_part_without_length_contract_keeps_natural_writer_length(self):
        class UnboundedClient:
            def __init__(self):
                self.prompts = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(1)
                if "CURRENT TARGET: no explicit character target" not in prompt:
                    raise AssertionError("unbounded writer must not receive a fake one-character target")
                if "approximately 1 characters" in prompt:
                    raise AssertionError("unbounded writer received a one-character target")
                return "Готовый цельный сценарий естественной длины. " * 20

        client = UnboundedClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "S", "ORIGINAL WRITING CONTRACT"),
        ])

        self.assertEqual(len(client.prompts), 2)
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertEqual(jobs[0].length_status, "")
        self.assertGreater(jobs[0].actual_chars, 100)
        self.assertEqual(len(jobs[0].accepted_story_parts), 1)

    async def test_single_part_plan_is_persisted_before_the_writer_starts(self):
        changes = []

        class SingleWriterClient:
            def __init__(self):
                self.prompts = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(1)
                if not changes[-1].story_plan:
                    raise AssertionError("writer started before the story map was persisted")
                return "а" * 5000

        client = SingleWriterClient()
        jobs = await ParallelRunner(client, 1, on_change=changes.append).run([
            ScenarioRequest(0, "S", "ORIGINAL WRITING CONTRACT", target_chars=5000,
                            allowed_min=4500, allowed_max=5500),
        ])
        self.assertEqual(len(client.prompts), 2)
        self.assertTrue(jobs[0].story_plan)
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertEqual(jobs[0].actual_chars, 5000)

    async def test_headline_only_single_complete_writer_uses_dramatized_disclosure(self):
        class SingleWriterClient:
            def __init__(self):
                self.prompts = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    if "Even if only a headline is available" not in prompt:
                        raise AssertionError("headline-only planner rule is missing")
                    return ParallelRunnerTests._story_plan_json(1).replace("\"SUPPORTED\"", "\"DRAMATIZED\"")
                if "CURRENT ROLE: COMPLETE" not in prompt:
                    raise AssertionError("single writer must use COMPLETE role")
                if "DRAMATIZED OPENING DISCLOSURE" not in prompt:
                    raise AssertionError("single-part disclosure rule is missing")
                return "Первое событие произошло. Это драматизированная реконструкция. " + "а" * 6000

        client = SingleWriterClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "Headline only", "", target_chars=6000,
                            allowed_min=5000, allowed_max=7000),
        ])

        self.assertEqual(len(client.prompts), 2)
        self.assertEqual(jobs[0].state, RunState.DONE)


    async def test_dramatized_complete_missing_disclosure_does_not_regenerate_writer(self):
        class MissingDisclosureClient:
            def __init__(self):
                self.planner_calls = 0
                self.writer_calls = 0
                self.fresh_calls = 0

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "NewsFlow Story Planner" in prompt:
                    self.planner_calls += 1
                    return ParallelRunnerTests._story_plan_json(1).replace(
                        '"SUPPORTED"', '"DRAMATIZED"',
                    )
                self.writer_calls += 1
                self.assertIn("DRAMATIZED OPENING DISCLOSURE", prompt)
                return "Первое событие произошло. Службы начали работу. Последствия уточняются."

            async def generate_fresh(self, *_args, **_kwargs):
                self.fresh_calls += 1
                raise AssertionError("Writer disclosure defects must not trigger regeneration")

            @staticmethod
            def assertIn(member, container):
                if member not in container:
                    raise AssertionError(f"{member!r} is missing")

        client = MissingDisclosureClient()
        job = (await ParallelRunner(client, 1).run([ScenarioRequest(
            0, "Headline only", "", target_chars=2000, allowed_min=1600, allowed_max=2400,
        )]))[0]

        self.assertEqual(client.planner_calls, 1)
        self.assertEqual(client.writer_calls, 1)
        self.assertEqual(client.fresh_calls, 0)
        self.assertEqual(job.state, RunState.DONE)
        self.assertEqual(len(job.accepted_story_parts), 1)

    async def test_dramatized_opening_missing_disclosure_still_uses_one_writer_call_per_part(self):
        class MissingOpeningDisclosureClient:
            def __init__(self):
                self.prompts = []
                self.fresh_calls = 0

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(2).replace(
                        '"SUPPORTED"', '"DRAMATIZED"',
                    )
                if "CURRENT PART: P1" in prompt:
                    self.assertIn("DRAMATIZED OPENING DISCLOSURE", prompt)
                    return "Событие началось. Службы начали работу. Последствия уточняются."
                if "CURRENT PART: P2" in prompt:
                    return "Ответ последовал. Стороны приняли новые решения."
                raise AssertionError("unexpected prompt")

            async def generate_fresh(self, *_args, **_kwargs):
                self.fresh_calls += 1
                raise AssertionError("Writer prose must never be regenerated")

            @staticmethod
            def assertIn(member, container):
                if member not in container:
                    raise AssertionError(f"{member!r} is missing")

        client = MissingOpeningDisclosureClient()
        job = (await ParallelRunner(client, 1).run([ScenarioRequest(
            0, "Headline only", "", target_chars=10000, allowed_min=9000, allowed_max=11000,
        )]))[0]

        self.assertEqual(client.fresh_calls, 0)
        self.assertEqual(job.state, RunState.DONE)
        self.assertEqual([row["part_id"] for row in job.accepted_story_parts], ["P1", "P2"])

    async def test_dramatized_disclosure_position_is_prompt_owned_not_runtime_regenerated(self):
        cases = (
            "Событие началось. Это драматизированная реконструкция. Службы включились.",
            "Событие началось. Службы включились. Это драматизированная реконструкция.",
            "Это драматизированная реконструкция. Событие началось. Службы включились.",
            "Событие началось. Службы включились. Город меняет режим. Это драматизированная реконструкция.",
        )
        for response in cases:
            with self.subTest(response=response):
                class PositionClient:
                    def __init__(self, planned_response):
                        self.fresh_calls = 0
                        self.planned_response = planned_response

                    async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                        if "NewsFlow Story Planner" in prompt:
                            return ParallelRunnerTests._story_plan_json(1).replace(
                                '"SUPPORTED"', '"DRAMATIZED"',
                            )
                        if "DRAMATIZED OPENING DISCLOSURE" not in prompt:
                            raise AssertionError("disclosure contract must be present before generation")
                        return self.planned_response

                    async def generate_fresh(self, *_args, **_kwargs):
                        self.fresh_calls += 1
                        raise AssertionError("Writer prose must never be regenerated")

                client = PositionClient(response)
                job = (await ParallelRunner(client, 1).run([ScenarioRequest(
                    0, "Headline only", "", target_chars=2000, allowed_min=1600, allowed_max=2400,
                )]))[0]
                self.assertEqual(job.state, RunState.DONE)
                self.assertEqual(client.fresh_calls, 0)
    async def test_supported_single_complete_writer_has_no_dramatized_disclosure(self):
        class SupportedClient:
            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(1)
                if "TECHNICAL OWNERSHIP INDEX (navigation only; not prose material):\n- C001 [SUPPORTED]" not in prompt:
                    raise AssertionError("single Writer must receive SUPPORTED content kind")
                if "DRAMATIZED OPENING DISCLOSURE" in prompt:
                    raise AssertionError("supported-only story must not disclose dramatization")
                return "а" * 5000

        jobs = await ParallelRunner(SupportedClient(), 1).run([
            ScenarioRequest(0, "Supported", "CONTRACT", target_chars=5000,
                            allowed_min=4500, allowed_max=5500),
        ])
        self.assertEqual(jobs[0].state, RunState.DONE)

    async def test_single_part_resume_uses_persisted_complete_plan_without_regeneration(self):
        from scriptor.runner import Job
        from scriptor.story_planner import (
            calculate_story_part_targets,
            parse_story_plan_response,
        )

        request = ScenarioRequest(0, "Resume", "CONTRACT", target_chars=5000,
                                  allowed_min=4500, allowed_max=5500)
        plan = parse_story_plan_response(
            ParallelRunnerTests._story_plan_json(1), calculate_story_part_targets(5000),
        )

        class ResumeClient:
            def __init__(self):
                self.prompts = []

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.prompts.append(prompt)
                if "NewsFlow Story Planner" in prompt:
                    raise AssertionError("single-part resume must not regenerate a persisted plan")
                if "CURRENT PART: P1" not in prompt:
                    raise AssertionError("single-part resume must use the persisted COMPLETE map")
                return "а" * 5000

        client = ResumeClient()
        jobs = await ParallelRunner(client, 1).run(
            [request], resume_jobs={0: Job(request=request, story_plan=plan.to_dict())},
        )
        self.assertEqual(len(client.prompts), 1)
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertEqual(len(jobs[0].accepted_story_parts), 1)

    async def test_short_single_complete_writer_is_accepted_without_extra_request(self):
        class ShortClient:
            def __init__(self):
                self.calls = 0
                self.fresh_calls = 0

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                self.calls += 1
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(1)
                return "мало"

            async def generate_fresh(self, *_args, **_kwargs):
                self.fresh_calls += 1
                raise AssertionError("SHORT result must not trigger another request")

        client = ShortClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "S", "P", target_chars=120, allowed_min=100, allowed_max=140),
        ])
        self.assertEqual(client.calls, 2)
        self.assertEqual(client.fresh_calls, 0)
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertEqual(jobs[0].result, "мало")
        self.assertEqual(jobs[0].length_status, "SHORT")
        self.assertEqual(len(jobs[0].accepted_story_parts), 1)

    async def test_long_single_complete_writer_is_accepted_without_trim_or_retry(self):
        class LongClient:
            def __init__(self):
                self.planner_calls = 0
                self.writer_calls = 0
                self.fresh_calls = 0

            async def generate(self, prompt, on_progress=None, max_output_tokens=None):
                if "NewsFlow Story Planner" in prompt:
                    self.planner_calls += 1
                    return ParallelRunnerTests._story_plan_json(1)
                self.writer_calls += 1
                return "а" * 200

            async def generate_fresh(self, *_args, **_kwargs):
                self.fresh_calls += 1
                raise AssertionError("LONG result must not trigger another request")

        client = LongClient()
        request = ScenarioRequest(
            0, "S", "P", target_chars=120, allowed_min=100, allowed_max=140,
        )
        result = (await ParallelRunner(client, 1).run([request]))[0]

        self.assertEqual(client.planner_calls, 1)
        self.assertEqual(client.writer_calls, 1)
        self.assertEqual(client.fresh_calls, 0)
        self.assertEqual(result.state, RunState.DONE)
        self.assertEqual(result.length_status, "LONG")
        self.assertEqual(result.actual_chars, 200)
        self.assertEqual(len(result.accepted_story_parts), 1)

    async def test_one_sided_maximum_is_advisory_and_keeps_long_result(self):
        class MaximumClient:
            def __init__(self):
                self.fresh_calls = 0

            async def generate(self, prompt, on_progress=None):
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(1)
                return "а" * 12000

            async def generate_fresh(self, *_args, **_kwargs):
                self.fresh_calls += 1
                raise AssertionError("length alone must not trigger another provider request")

        client = MaximumClient()
        jobs = await ParallelRunner(client, 1).run([
            ScenarioRequest(0, "S", "P", allowed_max=10000),
        ])
        self.assertEqual(client.fresh_calls, 0)
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertEqual(jobs[0].length_status, "LONG")
        self.assertEqual(jobs[0].actual_chars, 12000)
        self.assertEqual(len(jobs[0].accepted_story_parts), 1)
        self.assertEqual(jobs[0].accepted_story_parts[0]["text"], jobs[0].result)
        self.assertEqual(len(jobs[0].accepted_story_parts[0]["text"]), 12000)

    async def test_in_range_script_finishes_after_one_provider_response(self):
        class LengthClient:
            fresh_calls = 0

            async def generate(self, prompt, on_progress=None):
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(1)
                return "готовый текст"

            async def generate_fresh(self, prompt, on_progress=None):
                self.fresh_calls += 1
                raise AssertionError("in-range result must not need a rewrite")

        client = LengthClient()
        request = ScenarioRequest(
            0, "S", "P", target_chars=12, allowed_min=10, allowed_max=14,
        )
        jobs = await ParallelRunner(client, 1).run([request])

        self.assertEqual(client.fresh_calls, 0)
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertEqual(jobs[0].length_status, "READY")
        self.assertEqual(jobs[0].actual_chars, 13)
        self.assertEqual(jobs[0].length_repair_attempts, 0)


    async def test_writer_refusal_does_not_get_fresh_chat_retries(self):
        class RetryTwiceClient:
            fresh_calls = 0
            async def generate(self, prompt, on_progress=None):
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(1)
                return "Я не могу выполнить этот запрос."
            async def generate_fresh(self, *_args, **_kwargs):
                self.fresh_calls += 1
                raise AssertionError("Writer refusal must not trigger fresh regeneration")

        client = RetryTwiceClient()
        job = (await ParallelRunner(client, 1).run([ScenarioRequest(0, "S", "P")]))[0]
        self.assertEqual(client.fresh_calls, 0)
        self.assertEqual(job.state, RunState.PAUSED)
        self.assertEqual(job.accepted_story_parts, [])

    async def test_writer_refusal_does_not_fall_back_to_another_provider(self):
        class ClaudeThenOpenAIClient:
            fresh_calls = 0
            openai_calls = 0
            async def generate(self, prompt, on_progress=None):
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(1)
                return "Я не могу выполнить этот запрос."
            async def generate_fresh(self, *_args, **_kwargs):
                self.fresh_calls += 1
                raise AssertionError("Writer refusal must not trigger fresh regeneration")
            async def generate_openai(self, *_args, **_kwargs):
                self.openai_calls += 1
                raise AssertionError("Writer refusal must not fall back to another provider")

        client = ClaudeThenOpenAIClient()
        job = (await ParallelRunner(client, 1).run([ScenarioRequest(0, "S", "P")]))[0]
        self.assertEqual(client.fresh_calls, 0)
        self.assertEqual(client.openai_calls, 0)
        self.assertEqual(job.state, RunState.PAUSED)
    async def test_runs_multiple_scenarios_concurrently(self):
        client = FakeClient()
        runner = ParallelRunner(client, max_concurrency=4)
        jobs = await runner.run([ScenarioRequest(i, f"S{i}", f"P{i}") for i in range(8)])
        self.assertGreater(client.peak, 1)
        self.assertLessEqual(client.peak, 4)
        self.assertTrue(all(job.state == RunState.DONE for job in jobs))

    async def test_retry_only_failed_job(self):
        class FlakyClient:
            calls = 0
            async def generate(self, prompt, on_progress=None):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("temporary")
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(1)
                return "ok"

        runner = ParallelRunner(FlakyClient(), max_concurrency=1)
        jobs = await runner.run([ScenarioRequest(0, "S", "P")])
        self.assertEqual(jobs[0].state, RunState.ERROR)
        retried = await runner.retry(jobs[0])
        self.assertEqual(retried.state, RunState.DONE)

    async def test_large_run_uses_bounded_worker_pool(self):
        client = FakeClient()
        runner = ParallelRunner(client, max_concurrency=12)
        jobs = await runner.run([ScenarioRequest(i, f"S{i}", f"P{i}") for i in range(500)])
        self.assertEqual(len(jobs), 500)
        self.assertLessEqual(client.peak, 12)
        self.assertTrue(all(job.state == RunState.DONE for job in jobs))

    async def test_cancel_marks_jobs_that_have_not_started(self):
        class BlockingClient:
            started = threading.Event()
            release = threading.Event()

            async def generate(self, prompt, on_progress=None):
                self.started.set()
                await asyncio.to_thread(self.release.wait)
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(1)
                return "ok"

        client = BlockingClient()
        runner = ParallelRunner(client, max_concurrency=1)
        task = asyncio.create_task(runner.run([ScenarioRequest(i, f"S{i}", f"P{i}") for i in range(4)]))
        await asyncio.to_thread(client.started.wait)
        runner.cancel()
        client.release.set()
        jobs = await task
        self.assertEqual(jobs[0].state, RunState.DONE)
        self.assertTrue(all(job.state == RunState.CANCELLED for job in jobs[1:]))

    async def test_pause_blocks_new_jobs_until_resume(self):
        class GateClient:
            calls = 0
            first_started = threading.Event()
            release_first = threading.Event()

            async def generate(self, prompt, on_progress=None):
                self.calls += 1
                if self.calls == 1:
                    self.first_started.set()
                    await asyncio.to_thread(self.release_first.wait)
                if "NewsFlow Story Planner" in prompt:
                    return ParallelRunnerTests._story_plan_json(1)
                return "ok"

        client = GateClient()
        runner = ParallelRunner(client, max_concurrency=1)
        task = asyncio.create_task(runner.run([ScenarioRequest(i, f"S{i}", f"P{i}") for i in range(2)]))
        await asyncio.to_thread(client.first_started.wait)
        runner.pause()
        client.release_first.set()
        await asyncio.sleep(0.05)
        self.assertEqual(client.calls, 2)
        runner.resume()
        jobs = await task
        self.assertTrue(all(job.state == RunState.DONE for job in jobs))


if __name__ == "__main__":
    unittest.main()
