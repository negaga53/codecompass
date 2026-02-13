"""Tests for models and config."""

from pathlib import Path

from codecompass.models import (
    Language,
    RepoSummary,
    FrameworkInfo,
    SymbolNode,
    StalenessFinding,
    Severity,
)
from codecompass.utils.config import Settings


class TestModels:
    """Tests for Pydantic data models."""

    def test_language_enum(self) -> None:
        assert Language.PYTHON.value == "python"
        assert Language.TYPESCRIPT.value == "typescript"

    def test_repo_summary_to_text(self) -> None:
        summary = RepoSummary(
            name="test-repo",
            root="/tmp/test",
            languages=[Language.PYTHON],
            frameworks=[FrameworkInfo(name="flask")],
            total_files=10,
            total_lines=500,
            has_readme=True,
            has_contributing=False,
        )
        text = summary.to_text()
        assert "test-repo" in text
        assert "python" in text
        assert "flask" in text
        assert "Files: 10" in text

    def test_symbol_node(self) -> None:
        sym = SymbolNode(
            name="MyClass",
            kind="class",
            file="src/main.py",
            line=42,
            docstring="A test class.",
        )
        assert sym.name == "MyClass"
        assert sym.line == 42

    def test_staleness_finding(self) -> None:
        finding = StalenessFinding(
            file="README.md",
            issue="Outdated command reference",
            severity=Severity.HIGH,
        )
        assert finding.severity == Severity.HIGH

    def test_severity_enum(self) -> None:
        assert Severity.HIGH.value == "high"
        assert Severity.LOW.value == "low"


class TestSettings:
    """Tests for the ``Settings`` loader."""

    def test_defaults(self) -> None:
        settings = Settings.load()
        assert settings.model == "gpt-4.1"
        assert settings.max_file_size_kb > 0

    def test_overrides(self) -> None:
        settings = Settings.load({"model": "gpt-4.1"})
        assert settings.model == "gpt-4.1"

    def test_repo_path_default(self) -> None:
        settings = Settings.load()
        assert settings.repo_path == "."
        assert settings.premium_usage_warnings is True

    def test_load_prefers_repo_config_over_cwd(self, tmp_path: Path) -> None:
        cwd_cfg = tmp_path / ".codecompass.toml"
        cwd_cfg.write_text('[codecompass]\nmodel = "cwd-model"\n', encoding="utf-8")

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo_cfg = repo_dir / ".codecompass.toml"
        repo_cfg.write_text('[codecompass]\nmodel = "repo-model"\n', encoding="utf-8")

        settings = Settings.load({"repo_path": str(repo_dir)}, base_path=repo_dir)
        assert settings.model == "repo-model"

    def test_load_uses_base_path_when_no_overrides(self, tmp_path: Path) -> None:
        repo_cfg = tmp_path / ".codecompass.toml"
        repo_cfg.write_text('[codecompass]\nlog_level = "DEBUG"\n', encoding="utf-8")

        settings = Settings.load(base_path=tmp_path)
        assert settings.log_level == "DEBUG"

    def test_load_reads_premium_warning_toggle(self, tmp_path: Path) -> None:
        cfg = tmp_path / ".codecompass.toml"
        cfg.write_text('[codecompass]\npremium_usage_warnings = false\n', encoding="utf-8")

        settings = Settings.load(base_path=tmp_path)
        assert settings.premium_usage_warnings is False
