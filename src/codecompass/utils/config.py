"""Configuration management for CodeCompass."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


_DEFAULT_MODEL = "gpt-4o"
_CONFIG_FILENAME = ".codecompass.toml"


class Settings(BaseModel):
    """Application-wide settings loaded from environment and/or config file.

    Resolution order (highest priority first):
    1. Explicit constructor kwargs
    2. Environment variables
    3. ``.codecompass.toml`` in the working directory
    4. Defaults defined here
    """

    github_token: str = Field(default="", description="GitHub personal access token")
    model: str = Field(default=_DEFAULT_MODEL, description="LLM model identifier to use")
    repo_path: str = Field(
        default=".",
        description="Default repository path when none is provided on the CLI",
    )
    max_file_size_kb: int = Field(
        default=512,
        description="Skip files larger than this (in KB) during scanning",
    )
    tree_depth: int = Field(
        default=4,
        description="Max depth for the generated directory-tree view",
    )
    log_level: str = Field(default="WARNING", description="Logging level")

    # ----- class methods ----

    @classmethod
    def load(cls, overrides: dict[str, Any] | None = None) -> "Settings":
        """Build a ``Settings`` instance honouring env vars and config files.

        Args:
            overrides: Explicit key-value overrides (e.g. from CLI flags).

        Returns:
            A fully resolved ``Settings`` object.
        """
        values: dict[str, Any] = {}

        # 1 — Try reading a local config file
        config_path = Path.cwd() / _CONFIG_FILENAME
        if config_path.is_file():
            values.update(_parse_toml(config_path))

        # 2 — Environment variables (prefixed CODECOMPASS_)
        env_map: dict[str, str] = {
            "GITHUB_TOKEN": "github_token",
            "CODECOMPASS_MODEL": "model",
            "CODECOMPASS_REPO_PATH": "repo_path",
            "CODECOMPASS_MAX_FILE_SIZE_KB": "max_file_size_kb",
            "CODECOMPASS_TREE_DEPTH": "tree_depth",
            "CODECOMPASS_LOG_LEVEL": "log_level",
        }
        for env_key, field_name in env_map.items():
            env_val = os.environ.get(env_key)
            if env_val is not None:
                values[field_name] = env_val

        # 3 — Explicit overrides win
        if overrides:
            values.update(overrides)

        return cls(**values)


def _parse_toml(path: Path) -> dict[str, Any]:
    """Parse a TOML config file and return a flat dict of settings.

    Uses the stdlib ``tomllib`` (Python ≥ 3.11) with a fallback to
    ``tomli`` for 3.10.
    """
    try:
        import tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError:  # Python 3.10
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError:
            return {}

    with open(path, "rb") as fh:
        data = tomllib.load(fh)

    # Support a top-level [codecompass] table or flat keys
    return dict(data.get("codecompass", data))
