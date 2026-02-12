"""Tests for models and config."""

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
        assert settings.model == "gpt-4o"
        assert settings.max_file_size_kb > 0

    def test_overrides(self) -> None:
        settings = Settings.load({"model": "gpt-4.1"})
        assert settings.model == "gpt-4.1"

    def test_repo_path_default(self) -> None:
        settings = Settings.load()
        assert settings.repo_path == "."
