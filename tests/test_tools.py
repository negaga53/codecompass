"""Tests for the Copilot SDK tools."""

import asyncio
from pathlib import Path

import pytest

from codecompass.agent.tools import build_tools
from codecompass.github.git import GitOps
from codecompass.indexer.knowledge_graph import KnowledgeGraph


REPO_ROOT = Path(__file__).resolve().parents[1]


def _call_tool(tool, **kwargs) -> dict:
    """Helper to invoke a tool handler with arguments and return the result dict."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(tool.handler({"arguments": kwargs}))
    finally:
        loop.close()


def _call_tool_text(tool, **kwargs) -> str:
    """Call a tool and return the text result for the LLM."""
    result = _call_tool(tool, **kwargs)
    return result.get("textResultForLlm", "")


@pytest.fixture(scope="module")
def git_ops() -> GitOps:
    return GitOps(REPO_ROOT)


@pytest.fixture(scope="module")
def knowledge_graph() -> KnowledgeGraph:
    kg = KnowledgeGraph()
    kg.build(REPO_ROOT)
    return kg


@pytest.fixture(scope="module")
def tools(git_ops: GitOps, knowledge_graph: KnowledgeGraph) -> list:
    return build_tools(REPO_ROOT, git_ops=git_ops, knowledge_graph=knowledge_graph)


def _get_tool(tools, name):
    """Find a tool by name from the tools list."""
    for t in tools:
        if t.name == name:
            return t
    raise ValueError(f"Tool '{name}' not found in {[t.name for t in tools]}")


class TestToolsMeta:
    """Tests for tool registration and metadata."""

    def test_build_tools_returns_list(self, tools: list) -> None:
        assert isinstance(tools, list)
        assert len(tools) >= 11

    def test_tools_have_names(self, tools: list) -> None:
        for tool in tools:
            assert hasattr(tool, "name")
            assert isinstance(tool.name, str)
            assert len(tool.name) > 0

    def test_tool_names(self, tools: list) -> None:
        names = {t.name for t in tools}
        expected = {
            "search_git_history",
            "get_file_contributors",
            "read_source_file",
            "search_code",
            "get_architecture_summary",
            "find_related_docs",
            "detect_stale_docs",
            "get_symbol_info",
            "get_module_dependencies",
            "get_pr_details",
            "search_issues",
        }
        assert expected.issubset(names), f"Missing tools: {expected - names}"

    def test_tools_have_descriptions(self, tools: list) -> None:
        for tool in tools:
            assert hasattr(tool, "description")
            assert len(tool.description) > 10

    def test_tools_have_handlers(self, tools: list) -> None:
        for tool in tools:
            assert hasattr(tool, "handler")
            assert callable(tool.handler)


class TestSearchGitHistory:
    """Integration tests for the search_git_history tool."""

    def test_search_existing_commits(self, tools: list) -> None:
        tool = _get_tool(tools, "search_git_history")
        result = _call_tool_text(tool, query="Initial")
        assert "Initial" in result or "commit" in result.lower() or "No commits" in result

    def test_search_no_match(self, tools: list) -> None:
        tool = _get_tool(tools, "search_git_history")
        result = _call_tool_text(tool, query="xyznonexistent999")
        assert "No commits found" in result


class TestGetFileContributors:
    """Integration tests for the get_file_contributors tool."""

    def test_contributors_existing_file(self, tools: list) -> None:
        tool = _get_tool(tools, "get_file_contributors")
        result = _call_tool_text(tool, file_path="pyproject.toml")
        assert "Contributors" in result or "contributor" in result.lower()

    def test_contributors_nonexistent_file(self, tools: list) -> None:
        tool = _get_tool(tools, "get_file_contributors")
        result = _call_tool_text(tool, file_path="nonexistent_file.xyz")
        # Should handle gracefully (error message or empty list)
        assert isinstance(result, str)


class TestReadSourceFile:
    """Integration tests for the read_source_file tool."""

    def test_read_existing_file(self, tools: list) -> None:
        tool = _get_tool(tools, "read_source_file")
        result = _call_tool_text(tool, file_path="pyproject.toml")
        assert "pyproject.toml" in result
        assert "codecompass" in result

    def test_read_with_line_range(self, tools: list) -> None:
        tool = _get_tool(tools, "read_source_file")
        result = _call_tool_text(tool, file_path="pyproject.toml", start_line=1, end_line=5)
        assert "lines 1-5" in result

    def test_read_nonexistent_file(self, tools: list) -> None:
        tool = _get_tool(tools, "read_source_file")
        result = _call_tool_text(tool, file_path="does_not_exist.py")
        assert "not found" in result.lower()


class TestSearchCode:
    """Integration tests for the search_code tool."""

    def test_search_existing_pattern(self, tools: list) -> None:
        tool = _get_tool(tools, "search_code")
        result = _call_tool_text(tool, query="def build_tools")
        assert "build_tools" in result
        assert "tools.py" in result

    def test_search_no_match(self, tools: list) -> None:
        tool = _get_tool(tools, "search_code")
        # Search only in .toml files where this string won't appear
        result = _call_tool_text(tool, query="QWRTY_ASDFGH_ZXCVB", file_pattern="*.toml")
        assert "No matches" in result

    def test_search_with_pattern(self, tools: list) -> None:
        tool = _get_tool(tools, "search_code")
        result = _call_tool_text(tool, query="class GitOps", file_pattern="*.py")
        assert "GitOps" in result


class TestGetArchitectureSummary:
    """Integration tests for the get_architecture_summary tool."""

    def test_architecture_summary(self, tools: list) -> None:
        tool = _get_tool(tools, "get_architecture_summary")
        result = _call_tool_text(tool)
        assert "python" in result.lower()
        assert "Files:" in result or "Lines:" in result


class TestFindRelatedDocs:
    """Integration tests for the find_related_docs tool."""

    def test_find_docs_for_source(self, tools: list) -> None:
        tool = _get_tool(tools, "find_related_docs")
        # README.md is at repo root, which is checked for files near the root
        result = _call_tool_text(tool, file_path="pyproject.toml")
        assert "README" in result or "Documentation" in result or ".md" in result

    def test_find_docs_nonexistent(self, tools: list) -> None:
        tool = _get_tool(tools, "find_related_docs")
        result = _call_tool_text(tool, file_path="nonexistent_file.py")
        assert "not found" in result.lower()


class TestDetectStaleDocs:
    """Integration tests for the detect_stale_docs tool."""

    def test_detect_stale_all(self, tools: list) -> None:
        tool = _get_tool(tools, "detect_stale_docs")
        result = _call_tool_text(tool)
        # Should return either findings or "no stale" message
        assert "stale" in result.lower() or "issue" in result.lower() or "current" in result.lower()

    def test_detect_stale_specific(self, tools: list) -> None:
        tool = _get_tool(tools, "detect_stale_docs")
        result = _call_tool_text(tool, doc_path="README.md")
        assert isinstance(result, str)
        assert len(result) > 0


class TestGetSymbolInfo:
    """Integration tests for the get_symbol_info tool."""

    def test_find_class(self, tools: list) -> None:
        tool = _get_tool(tools, "get_symbol_info")
        result = _call_tool_text(tool, symbol_name="GitOps")
        assert "GitOps" in result
        assert "class" in result.lower()

    def test_find_function(self, tools: list) -> None:
        tool = _get_tool(tools, "get_symbol_info")
        result = _call_tool_text(tool, symbol_name="build_tools")
        assert "build_tools" in result
        assert "function" in result.lower()

    def test_find_nonexistent(self, tools: list) -> None:
        tool = _get_tool(tools, "get_symbol_info")
        result = _call_tool_text(tool, symbol_name="NonexistentClass999")
        assert "No symbols" in result


class TestGetModuleDependencies:
    """Integration tests for the get_module_dependencies tool."""

    def test_module_deps(self, tools: list) -> None:
        tool = _get_tool(tools, "get_module_dependencies")
        result = _call_tool_text(tool, module_name="src.codecompass.cli")
        assert "Dependencies" in result
        # cli.py imports many modules
        assert "codecompass" in result

    def test_module_no_deps(self, tools: list) -> None:
        tool = _get_tool(tools, "get_module_dependencies")
        result = _call_tool_text(tool, module_name="nonexistent.module.xyz")
        assert "No outgoing" in result or "not found" in result.lower()


class TestGetPRDetails:
    """Integration tests for the get_pr_details tool."""

    def test_no_github_client(self, tools: list) -> None:
        tool = _get_tool(tools, "get_pr_details")
        result = _call_tool_text(tool, query="test")
        assert "GitHub API not available" in result


class TestSearchIssues:
    """Integration tests for the search_issues tool."""

    def test_no_github_client(self, tools: list) -> None:
        tool = _get_tool(tools, "search_issues")
        result = _call_tool_text(tool, query="bug")
        assert "GitHub API not available" in result
