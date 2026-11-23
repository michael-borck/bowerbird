"""Model IDs. Each can be overridden with an environment variable."""

from __future__ import annotations

import os

TAXONOMY_DEFAULT = "claude-opus-5"
ASSIGN_DEFAULT = "claude-haiku-4-5"


def taxonomy_model(override: str | None = None) -> str:
    """derive_taxonomy(), and Ask unless BOWERBIRD_CHAT_MODEL says otherwise."""
    return override or os.environ.get("BOWERBIRD_TAXONOMY_MODEL") or TAXONOMY_DEFAULT


def assign_model(override: str | None = None) -> str:
    return override or os.environ.get("BOWERBIRD_ASSIGN_MODEL") or ASSIGN_DEFAULT


def chat_model() -> str:
    return os.environ.get("BOWERBIRD_CHAT_MODEL") or taxonomy_model()
