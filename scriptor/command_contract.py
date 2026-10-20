"""Checked contracts for the active NewsFlow production commands.

The Electron transport remains intentionally generic for older, unmodified
screens.  New Light-path work must register here first: this is the place
that names the only canonical handler and explicitly rejects a non-object
payload before it reaches a provider or worker.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class CommandContractError(ValueError):
    """A renderer payload or response does not match an active command path."""


@dataclass(frozen=True)
class CommandRegistration:
    handler: str
    service: str
    forbidden_legacy_modules: tuple[str, ...]
    requires_snapshot: bool = True


_NO_LEGACY = ("scriptor.app", "scriptor.legacy_bridge")

# Every entry below is a user-facing production boundary.  The mapping is
# deliberately small and explicit: registering a command is a design choice,
# not a side effect of adding another string to the generic IPC channel.
COMMAND_CONTRACT: dict[str, CommandRegistration] = {
    "save-settings": CommandRegistration("save_settings_patch", "scriptor.config.Settings", _NO_LEGACY),
    "save-browser-topic-scenario-settings": CommandRegistration(
        "save_browser_topic_scenario_settings", "scriptor.browser_topic_scenarios", _NO_LEGACY,
    ),
    "generate-browser-topic-scenarios": CommandRegistration(
        "generate_browser_topic_scenarios", "scriptor.browser_topic_scenarios", _NO_LEGACY,
    ),
    "add-topic": CommandRegistration("add_topic", "scriptor.bridge topic service", _NO_LEGACY),
    "reject-suggested-topics": CommandRegistration(
        "reject_suggested_topics", "scriptor.bridge idea proposal service", _NO_LEGACY,
    ),
    "generate-ideas": CommandRegistration("generate_ideas", "scriptor.idea_engine", _NO_LEGACY),
    "generate-scenarios": CommandRegistration("generate_scenarios", "scriptor.bridge scenario worker", _NO_LEGACY),
    "import-manual-scenario": CommandRegistration("import_manual_scenario", "scriptor.bridge import service", _NO_LEGACY),
    "remove-scenarios": CommandRegistration("remove_scenarios_command", "scriptor.session", _NO_LEGACY),
    "generate-voice-queue": CommandRegistration("generate_voice_queue", "scriptor.bridge current voice worker", _NO_LEGACY),
    "generate-voice-range": CommandRegistration("generate_voice_range", "scriptor.tts_ranges", _NO_LEGACY),
    "rebuild-voice-map": CommandRegistration("rebuild_voice_map", "scriptor.voice_map", _NO_LEGACY),
    "reconcile-voice-queue": CommandRegistration(
        "reconcile_voice_queue", "scriptor.bridge completed-MP3 recovery", _NO_LEGACY,
    ),
    "generate-covers": CommandRegistration("generate_covers", "scriptor.thumbnail_prompt_v2", _NO_LEGACY),
    "import-cover-text-triples": CommandRegistration(
        "import_cover_text_triples", "scriptor.bridge manual cover-text import", _NO_LEGACY,
    ),
    "import-cover-prompt-pairs": CommandRegistration(
        "import_cover_prompt_pairs", "scriptor.bridge manual cover-prompt import", _NO_LEGACY,
    ),
    "save-cover-manual-prompt": CommandRegistration(
        "save_cover_manual_prompt", "scriptor.bridge manual cover-prompt editor", _NO_LEGACY,
    ),
    "save-footage-block": CommandRegistration("save_footage_block", "scriptor.footage_block_bridge", _NO_LEGACY),
    "delete-footage-block": CommandRegistration("delete_footage_block", "scriptor.footage_block_bridge", _NO_LEGACY),
    "preview-footage-block-import": CommandRegistration("preview_footage_block_import", "scriptor.footage_block_bridge", _NO_LEGACY),
    "import-footage-block-pairs": CommandRegistration("import_footage_block_pairs", "scriptor.footage_block_bridge", _NO_LEGACY),
    "assign-footage-block": CommandRegistration("assign_footage_block", "scriptor.footage_block_bridge", _NO_LEGACY),
    "run-montage-queue": CommandRegistration("run_montage_queue", "scriptor.timeline canonical montage path", _NO_LEGACY),
    "save-montage-stock-keys": CommandRegistration(
        "save_montage_stock_keys", "scriptor.bridge montage stock credentials", _NO_LEGACY,
    ),
    "run-proxy-cache-warmup": CommandRegistration(
        "warm_proxy_cache", "scriptor.timeline source-proxy warm-up", _NO_LEGACY,
    ),
    "set-proxy-cache-paused": CommandRegistration(
        "set_proxy_cache_paused", "scriptor.bridge proxy-cache control", _NO_LEGACY,
    ),
    "package-outputs": CommandRegistration("package_outputs", "scriptor.bridge output packager", _NO_LEGACY),
    "export-results-batch": CommandRegistration("export_results_batch", "scriptor.bridge batch results exporter", _NO_LEGACY),
    "generate-seo": CommandRegistration("generate_seo", "scriptor.bridge SEO service", _NO_LEGACY),
    "generate-tags": CommandRegistration("generate_tags", "scriptor.bridge tags service", _NO_LEGACY),
    "upload-publication-jobs": CommandRegistration("upload_publication_jobs", "scriptor.youtube_studio", _NO_LEGACY),
    "confirm-publication-v2-distribution": CommandRegistration(
        "confirm_publication_v2_distribution", "scriptor.publication_v2", _NO_LEGACY,
    ),
    "preview-publication-v2-distribution": CommandRegistration(
        "preview_publication_v2_distribution", "scriptor.publication_v2", _NO_LEGACY,
    ),
    "set-publication-v2-item-priority": CommandRegistration("set_publication_v2_item_priority", "scriptor.publication_v2", _NO_LEGACY),
    "migrate-publication-v2": CommandRegistration("migrate_publication_v2", "scriptor.publication_v2", _NO_LEGACY),
    "save-publication-v2-rule-preset": CommandRegistration("save_publication_v2_rule_preset", "scriptor.publication_v2", _NO_LEGACY),
    "save-publication-v2-plan-version": CommandRegistration("save_publication_v2_plan_version", "scriptor.publication_v2", _NO_LEGACY),
    "restore-publication-v2-plan-version": CommandRegistration("restore_publication_v2_plan_version", "scriptor.publication_v2", _NO_LEGACY),
    "delete-publication-v2-plan-version": CommandRegistration("delete_publication_v2_plan_version", "scriptor.publication_v2", _NO_LEGACY),
    "apply-publication-v2-rule-preset": CommandRegistration("apply_publication_v2_rule_preset", "scriptor.publication_v2", _NO_LEGACY),
    "delete-publication-v2-rule-preset": CommandRegistration("delete_publication_v2_rule_preset", "scriptor.publication_v2", _NO_LEGACY),
    "run-publication-v2-studio": CommandRegistration("run_publication_v2_studio", "scriptor.youtube_studio + scriptor.publication_v2", _NO_LEGACY),
    "resolve-publication-v2-uncertain-upload": CommandRegistration(
        "resolve_publication_v2_uncertain_upload", "scriptor.publication_v2 + scriptor.youtube_api", _NO_LEGACY,
    ),
    "open-publication-v2-identity-verification": CommandRegistration(
        "open_publication_v2_identity_verification", "scriptor.youtube_studio", _NO_LEGACY,
    ),
    "queue-publication-v2-reupload": CommandRegistration(
        "queue_publication_v2_reuploads", "scriptor.publication_v2 + scriptor.youtube_api", _NO_LEGACY,
    ),
}


def registration_for(command: str) -> CommandRegistration:
    registration = COMMAND_CONTRACT.get(str(command))
    if registration is None:
        raise CommandContractError(f"Команда не зарегистрирована в active contract: {command}")
    return registration


def validate_command_request(command: str, payload: Any) -> None:
    """Validate an active command at the process boundary without coercion."""
    registration_for(command)
    if not isinstance(payload, dict):
        raise CommandContractError(f"Payload команды {command} должен быть объектом")


def validate_command_result(command: str, result: Any) -> None:
    """Critical command handlers always project a structured renderer state."""
    registration = registration_for(command)
    if registration.requires_snapshot and not isinstance(result, dict):
        raise CommandContractError(f"Команда {command} не вернула структурированное состояние")
