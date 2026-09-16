"""Explicit, default-off flags for future risky NewsFlow workflows.

Flags are intentionally process-local environment input. They are not stored
in user settings, transferred by migrations, or enabled by an old session.
"""

from __future__ import annotations

import os

FEATURE_FLAGS_ENV = "NEWSFLOW_FEATURE_FLAGS"
KNOWN_FEATURE_FLAGS = frozenset({
    "montage_v3",
    "new_cover_workflow",
    "new_publication_scheduler",
})


class FeatureFlagError(ValueError):
    """An explicit feature flag is unknown or malformed."""


def enabled_flags() -> frozenset[str]:
    """Return explicitly enabled known flags; absence means stable behavior."""
    requested = frozenset(
        value.strip()
        for value in os.environ.get(FEATURE_FLAGS_ENV, "").split(",")
        if value.strip()
    )
    unknown = requested - KNOWN_FEATURE_FLAGS
    if unknown:
        raise FeatureFlagError(f"Unknown NewsFlow feature flag(s): {', '.join(sorted(unknown))}")
    return requested


def is_enabled(name: str) -> bool:
    """Return whether one registered future workflow is explicitly enabled."""
    if name not in KNOWN_FEATURE_FLAGS:
        raise FeatureFlagError(f"Unknown NewsFlow feature flag: {name}")
    return name in enabled_flags()
