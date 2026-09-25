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
    "generate-covers": CommandRegistration("generate_covers", "scriptor.thumbnail_prompt_v2", _NO_LEGACY),
    "run-montage-queue": CommandRegistration("run_montage_queue", "scriptor.timeline canonical montage path", _NO_LEGACY),
    "package-outputs": CommandRegistration("package_outputs", "scriptor.bridge output packager", _NO_LEGACY),
    "generate-seo": CommandRegistration("generate_seo", "scriptor.bridge SEO service", _NO_LEGACY),
    "generate-tags": CommandRegistration("generate_tags", "scriptor.bridge tags service", _NO_LEGACY),
    "upload-publication-jobs": CommandRegistration("upload_publication_jobs", "scriptor.youtube_studio", _NO_LEGACY),
    "confirm-publication-v2-distribution": CommandRegistration(
        "confirm_publication_v2_distribution", "scriptor.publication_v2", _NO_LEGACY,
    ),
    "preview-publication-v2-distribution": CommandRegistration(
        "preview_publication_v2_distribution", "scriptor.publication_v2", _NO_LEGACY,
    ),
    "migrate-publication-v2": CommandRegistration("migrate_publication_v2", "scriptor.publication_v2", _NO_LEGACY),
    "open-publication-v2-identity-verification": CommandRegistration(
        "open_publication_v2_identity_verification", "scriptor.bridge visible Studio handoff", _NO_LEGACY,
    ),
    "queue-publication-v2-reuploads": CommandRegistration(
        "queue_publication_v2_reuploads", "scriptor.publication_v2", _NO_LEGACY,
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
