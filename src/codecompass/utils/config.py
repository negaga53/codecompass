"""Configuration management for CodeCompass."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


_DEFAULT_MODEL = "gpt-4.1"
_CONFIG_FILENAME = ".codecompass.toml"


class Settings(BaseModel):
    """Application-wide settings loaded from environment and/or config file.

    Resolution order (highest priority first):
    1. Explicit constructor kwargs
    2. Environment variables
    3. ``.codecompass.toml`` in the repo/base path (or working directory)
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
    premium_usage_warnings: bool = Field(
        default=True,
        description="Whether to print premium-request usage warnings in AI commands",
    )

    # ----- class methods ----

    @classmethod
    def load(
        cls,
        overrides: dict[str, Any] | None = None,
        *,
        base_path: str | Path | None = None,
    ) -> "Settings":
        """Build a ``Settings`` instance honouring env vars and config files.

        Args:
            overrides: Explicit key-value overrides (e.g. from CLI flags).
            base_path: Repository path to use when resolving ``.codecompass.toml``.

        Returns:
            A fully resolved ``Settings`` object.
        """
        values: dict[str, Any] = {}

        effective_base = base_path
        if overrides and overrides.get("repo_path"):
            effective_base = str(overrides["repo_path"])

        # 1 — Try reading a local config file
        cfg_path = config_path(effective_base)
        if cfg_path.is_file():
            values.update(_parse_toml(cfg_path))

        # 2 — Environment variables (prefixed CODECOMPASS_)
        env_map: dict[str, str] = {
            "GITHUB_TOKEN": "github_token",
            "CODECOMPASS_MODEL": "model",
            "CODECOMPASS_REPO_PATH": "repo_path",
            "CODECOMPASS_MAX_FILE_SIZE_KB": "max_file_size_kb",
            "CODECOMPASS_TREE_DEPTH": "tree_depth",
            "CODECOMPASS_LOG_LEVEL": "log_level",
            "CODECOMPASS_PREMIUM_USAGE_WARNINGS": "premium_usage_warnings",
        }
        for env_key, field_name in env_map.items():
            env_val = os.environ.get(env_key)
            if env_val is not None:
                values[field_name] = env_val

        # 3 — Explicit overrides win
        if overrides:
            values.update(overrides)

        return cls(**values)


def config_path(repo_path: str | Path | None = None) -> Path:
    """Return the path to the config file for the given repo (or cwd)."""
    base = Path(repo_path).resolve() if repo_path else Path.cwd()
    return base / _CONFIG_FILENAME


def write_config(
    settings: "Settings",
    path: str | Path | None = None,
    *,
    keys: list[str] | None = None,
) -> Path:
    """Write settings to a ``.codecompass.toml`` file.

    Args:
        settings: The Settings object to save.
        path: Target file path. Defaults to ``.codecompass.toml`` in cwd.
        keys: If given, only write these keys. Otherwise write all non-default.

    Returns:
        The path that was written.
    """
    target = Path(path) if path else config_path()

    all_fields = {
        "model": settings.model,
        "log_level": settings.log_level,
        "tree_depth": settings.tree_depth,
        "max_file_size_kb": settings.max_file_size_kb,
        "premium_usage_warnings": settings.premium_usage_warnings,
    }

    if keys:
        values = {k: v for k, v in all_fields.items() if k in keys}
    else:
        values = all_fields

    # Build TOML by hand to avoid extra deps (no tomli_w in stdlib)
    lines = ["[codecompass]"]
    for k, v in sorted(values.items()):
        if isinstance(v, str):
            lines.append(f'{k} = "{v}"')
        elif isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        else:
            lines.append(f"{k} = {v}")
    lines.append("")

    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def update_config_key(key: str, value: str, path: str | Path | None = None) -> Path:
    """Set a single key in the config file, preserving other values.

    If the file doesn't exist it's created. If the key already exists
    it's updated in-place.

    Args:
        key: Setting name (e.g. ``model``, ``log_level``).
        value: New value as a string.
        path: Config file path. Defaults to ``.codecompass.toml`` in cwd.

    Returns:
        The path that was written.
    """
    target = Path(path) if path else config_path()

    existing: dict[str, Any] = {}
    if target.is_file():
        existing = _parse_toml(target)

    # Coerce numeric values
    if key in ("tree_depth", "max_file_size_kb"):
        try:
            existing[key] = int(value)
        except ValueError:
            existing[key] = value
    elif key == "premium_usage_warnings":
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            existing[key] = True
        elif normalized in {"0", "false", "no", "n", "off"}:
            existing[key] = False
        else:
            existing[key] = value
    else:
        existing[key] = value

    # Write back
    lines = ["[codecompass]"]
    for k, v in sorted(existing.items()):
        if isinstance(v, str):
            lines.append(f'{k} = "{v}"')
        elif isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        else:
            lines.append(f"{k} = {v}")
    lines.append("")

    target.write_text("\n".join(lines), encoding="utf-8")
    return target


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
