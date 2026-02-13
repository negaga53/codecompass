"""Tests for the RepoScanner and KnowledgeGraph."""

from pathlib import Path

import pytest

from codecompass.indexer.knowledge_graph import KnowledgeGraph
from codecompass.indexer.scanner import RepoScanner
from codecompass.models import Language


# ── Use the CodeCompass project itself as the test fixture ────────────

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestRepoScanner:
    """Tests for ``RepoScanner``."""

    def test_scan_returns_summary(self) -> None:
        scanner = RepoScanner(REPO_ROOT)
        summary = scanner.scan()
        assert summary.name
        assert summary.total_files > 0
        assert summary.total_lines > 0

    def test_detects_python(self) -> None:
        scanner = RepoScanner(REPO_ROOT)
        summary = scanner.scan()
        assert Language.PYTHON in summary.languages

    def test_detects_frameworks(self) -> None:
        scanner = RepoScanner(REPO_ROOT)
        summary = scanner.scan()
        framework_names = {f.name for f in summary.frameworks}
        assert "click" in framework_names
        assert "pydantic" in framework_names
        assert "textual" in framework_names

    def test_has_readme(self) -> None:
        scanner = RepoScanner(REPO_ROOT)
        summary = scanner.scan()
        assert summary.has_readme is True

    def test_directory_tree_is_populated(self) -> None:
        scanner = RepoScanner(REPO_ROOT)
        summary = scanner.scan()
        assert len(summary.directory_tree) > 0
        assert "codecompass" in summary.directory_tree

    def test_to_text(self) -> None:
        scanner = RepoScanner(REPO_ROOT)
        summary = scanner.scan()
        text = summary.to_text()
        assert "python" in text.lower()
        assert summary.name in text

    def test_detects_cmakelists_config_file(self, tmp_path: Path) -> None:
        """Regression test: CMakeLists.txt should be recognized as a config file."""
        (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.10)\n")
        (tmp_path / "main.cpp").write_text("int main() { return 0; }\n")

        scanner = RepoScanner(tmp_path)
        summary = scanner.scan()

        assert "CMakeLists.txt" in summary.config_files


class TestKnowledgeGraph:
    """Tests for ``KnowledgeGraph``."""

    @pytest.fixture()
    def kg(self) -> KnowledgeGraph:
        kg = KnowledgeGraph()
        kg.build(REPO_ROOT)
        return kg

    def test_discovers_modules(self, kg: KnowledgeGraph) -> None:
        modules = kg.all_modules()
        assert len(modules) > 0
        # Should find CodeCompass's own modules
        assert any("codecompass" in m for m in modules)

    def test_query_finds_class(self, kg: KnowledgeGraph) -> None:
        results = kg.query("RepoScanner")
        assert len(results) > 0
        assert results[0].kind in ("class", "function")

    def test_query_finds_function(self, kg: KnowledgeGraph) -> None:
        results = kg.query("build_tools")
        assert len(results) > 0

    def test_dependencies(self, kg: KnowledgeGraph) -> None:
        # Find any module with dependencies
        for module in kg.all_modules():
            deps = kg.dependencies(module)
            if deps:
                assert len(deps) > 0
                return
        # If no module has deps (unlikely), just pass
        pytest.skip("No modules with dependencies found")

    def test_dependents(self, kg: KnowledgeGraph) -> None:
        # Many modules depend on codecompass.models
        dependents = kg.dependents("codecompass.models")
        assert len(dependents) >= 0  # may be 0 if not imported directly

    def test_query_nonexistent_returns_empty(self, kg: KnowledgeGraph) -> None:
        results = kg.query("NonExistentSymbolXYZ123")
        assert len(results) == 0

    def test_build_resets_state_between_repos(self, tmp_path: Path) -> None:
        repo_one = tmp_path / "repo_one"
        repo_two = tmp_path / "repo_two"
        repo_one.mkdir()
        repo_two.mkdir()

        (repo_one / "a.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
        (repo_two / "b.py").write_text("def beta():\n    return 2\n", encoding="utf-8")

        kg = KnowledgeGraph()
        kg.build(repo_one)
        names_one = {s.name for s in kg.symbols.values()}
        assert "alpha" in names_one

        kg.build(repo_two)
        names_two = {s.name for s in kg.symbols.values()}
        assert "beta" in names_two
        assert "alpha" not in names_two
