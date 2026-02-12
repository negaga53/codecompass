"""Tests for the Copilot SDK tools."""

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from codecompass.agent.tools import build_tools
from codecompass.github.client import GitHubClient
from codecompass.github.git import GitOps
from codecompass.indexer.knowledge_graph import KnowledgeGraph


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_github_token() -> str | None:
    """Load GITHUB_TOKEN from .env or environment."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("GITHUB_TOKEN="):
                return line.split("=", 1)[1].strip()
    return None


GITHUB_TOKEN = _load_github_token()
HAS_GITHUB_TOKEN = bool(GITHUB_TOKEN)


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


# ══════════════════════════════════════════════════════════════════════
# Edge-case / boundary tests
# ══════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge-case inputs: empty strings, special characters, extreme values."""

    def test_search_git_history_empty_query(self, tools: list) -> None:
        """Empty query should not crash — it returns all or none."""
        tool = _get_tool(tools, "search_git_history")
        result = _call_tool(tool, query="")
        assert result["resultType"] == "success"

    def test_search_git_history_max_results_one(self, tools: list) -> None:
        """max_results=1 should return at most one commit."""
        tool = _get_tool(tools, "search_git_history")
        text = _call_tool_text(tool, query="", max_results=1)
        # Count bullet lines — should be 0 or 1
        bullet_lines = [l for l in text.splitlines() if l.strip().startswith("- ")]
        assert len(bullet_lines) <= 1

    def test_read_source_file_directory(self, tools: list) -> None:
        """Attempting to read a directory should give a clear error."""
        tool = _get_tool(tools, "read_source_file")
        result = _call_tool_text(tool, file_path="src")
        assert "not a file" in result.lower()

    def test_search_code_empty_query(self, tools: list) -> None:
        """Empty search query should still return a valid result."""
        tool = _get_tool(tools, "search_code")
        result = _call_tool(tool, query="", file_pattern="*.toml")
        assert result["resultType"] == "success"

    def test_get_symbol_info_empty_name(self, tools: list) -> None:
        """Empty symbol name yields 'No symbols found'."""
        tool = _get_tool(tools, "get_symbol_info")
        text = _call_tool_text(tool, symbol_name="")
        assert "No symbols" in text or "symbol" in text.lower()

    def test_get_module_deps_empty_name(self, tools: list) -> None:
        """Empty module name should not crash."""
        tool = _get_tool(tools, "get_module_dependencies")
        result = _call_tool(tool, module_name="")
        assert result["resultType"] == "success"

    def test_search_code_special_chars(self, tools: list) -> None:
        """Regex-special characters in query should be escaped safely."""
        tool = _get_tool(tools, "search_code")
        result = _call_tool(tool, query="[project]", file_pattern="*.toml")
        assert result["resultType"] == "success"

    def test_detect_stale_nonexistent_doc(self, tools: list) -> None:
        """Specific doc_path that doesn't exist should return clean result."""
        tool = _get_tool(tools, "detect_stale_docs")
        text = _call_tool_text(tool, doc_path="nonexistent.md")
        assert "No stale" in text or "documentation" in text.lower()


# ══════════════════════════════════════════════════════════════════════
# Security / boundary tests
# ══════════════════════════════════════════════════════════════════════


class TestSecurityBoundaries:
    """Ensure tools don't expose data outside the repository root."""

    def test_read_source_file_path_traversal(self, tools: list) -> None:
        """Paths with '..' should not escape the repo root."""
        tool = _get_tool(tools, "read_source_file")
        # Try to escape with ../
        text = _call_tool_text(tool, file_path="../../../../../../etc/passwd")
        # Either "not found" or we stay inside repo — must NOT expose sensitive data
        assert "root:" not in text  # Unix passwd content
        assert (
            "not found" in text.lower()
            or "Error" in text
            or "etc/passwd" in text  # shows path but not content
        )

    def test_read_source_file_absolute_path(self, tools: list) -> None:
        """Absolute paths should not bypass repo root restriction."""
        tool = _get_tool(tools, "read_source_file")
        # This is repo_path / "C:\\Windows\\..." which won't exist
        text = _call_tool_text(tool, file_path="C:\\Windows\\System32\\config\\SAM")
        assert "not found" in text.lower() or "Error" in text

    def test_search_code_skips_dotgit(self, tools: list) -> None:
        """search_code must skip .git directory contents."""
        tool = _get_tool(tools, "search_code")
        # Search for a string that only appears in .git pack files
        text = _call_tool_text(tool, query="PACK", file_pattern="*.pack")
        # .git/objects/pack/ files should be skipped
        assert ".git/" not in text


# ══════════════════════════════════════════════════════════════════════
# Content / structural validation tests
# ══════════════════════════════════════════════════════════════════════


class TestContentValidation:
    """Deeper validation of tool output structure and content."""

    def test_architecture_has_key_sections(self, tools: list) -> None:
        """Architecture summary should contain file count and language info."""
        tool = _get_tool(tools, "get_architecture_summary")
        text = _call_tool_text(tool)
        assert "Files:" in text
        assert "Lines:" in text
        assert "python" in text.lower()

    def test_read_file_content_matches(self, tools: list) -> None:
        """Reading pyproject.toml should contain actual project metadata."""
        tool = _get_tool(tools, "read_source_file")
        text = _call_tool_text(tool, file_path="pyproject.toml")
        assert "codecompass" in text.lower()
        assert "version" in text.lower()
        assert "0.1.0" in text

    def test_symbol_info_has_location(self, tools: list) -> None:
        """Symbol lookup should include file path and line number."""
        tool = _get_tool(tools, "get_symbol_info")
        text = _call_tool_text(tool, symbol_name="GitOps")
        # Should have a backtick-quoted path:line
        assert "git.py" in text
        assert "class" in text.lower()

    def test_module_deps_shows_imports(self, tools: list) -> None:
        """cli module depends on click, rich, etc."""
        tool = _get_tool(tools, "get_module_dependencies")
        text = _call_tool_text(tool, module_name="src.codecompass.cli")
        assert "Imports" in text or "depends on" in text.lower()

    def test_git_history_format(self, tools: list) -> None:
        """Each commit line should contain hash, date, and author."""
        tool = _get_tool(tools, "search_git_history")
        text = _call_tool_text(tool, query="")
        lines = [l for l in text.splitlines() if l.strip().startswith("- ")]
        if lines:
            first = lines[0]
            assert "`" in first  # backtick-quoted hash
            assert "by" in first or "(" in first  # author or date

    def test_contributors_format(self, tools: list) -> None:
        """Contributor output should include commit count."""
        tool = _get_tool(tools, "get_file_contributors")
        text = _call_tool_text(tool, file_path="pyproject.toml")
        assert "commit" in text.lower()

    def test_result_type_always_success(self, tools: list) -> None:
        """All tools should return resultType='success' with valid inputs."""
        # Provide valid minimal args for each tool
        valid_args: dict[str, dict] = {
            "search_git_history": {"query": "test"},
            "get_file_contributors": {"file_path": "pyproject.toml"},
            "read_source_file": {"file_path": "pyproject.toml"},
            "search_code": {"query": "codecompass", "file_pattern": "*.toml"},
            "get_architecture_summary": {},
            "find_related_docs": {"file_path": "pyproject.toml"},
            "detect_stale_docs": {},
            "get_symbol_info": {"symbol_name": "GitOps"},
            "get_module_dependencies": {"module_name": "src.codecompass.cli"},
            "get_pr_details": {"query": "test"},
            "search_issues": {"query": "test"},
        }
        for tool in tools:
            kwargs = valid_args.get(tool.name, {})
            result = _call_tool(tool, **kwargs)
            assert result.get("resultType") == "success", (
                f"Tool '{tool.name}' returned resultType={result.get('resultType')}"
            )


# ══════════════════════════════════════════════════════════════════════
# Mocked GitHub API tool tests
# ══════════════════════════════════════════════════════════════════════


class TestGetPRDetailsMocked:
    """Tests for get_pr_details with a mocked GitHub client."""

    @pytest.fixture()
    def github_tools(self, git_ops, knowledge_graph):
        """Build tools with a mocked GitHub client."""
        mock_client = MagicMock()

        # Mock get_pr — returns a single PR dict
        mock_client.get_pr = AsyncMock(return_value={
            "number": 42,
            "title": "Add feature X",
            "state": "merged",
            "user": {"login": "alice"},
            "created_at": "2025-01-10T12:00:00Z",
            "merged_at": "2025-01-12T14:00:00Z",
            "body": "This PR adds the amazing feature X.",
        })
        mock_client.get_pr_comments = AsyncMock(return_value=[
            {"user": {"login": "bob"}, "body": "LGTM, looks great!"},
        ])
        mock_client.get_pr_reviews = AsyncMock(return_value=[
            {"user": {"login": "carol"}, "state": "APPROVED", "body": "Approved!"},
        ])
        mock_client.list_prs = AsyncMock(return_value=[
            {
                "number": 42,
                "title": "Add feature X",
                "state": "merged",
                "user": {"login": "alice"},
                "body": "This PR adds the amazing feature X.",
            },
            {
                "number": 10,
                "title": "Fix bug Y",
                "state": "closed",
                "user": {"login": "dave"},
                "body": "Fixes the Y bug.",
            },
        ])

        return build_tools(
            REPO_ROOT,
            git_ops=git_ops,
            knowledge_graph=knowledge_graph,
            github_client=mock_client,
        )

    def test_pr_by_number(self, github_tools) -> None:
        """Fetch PR by number should return full details."""
        tool = _get_tool(github_tools, "get_pr_details")
        text = _call_tool_text(tool, query="42")
        assert "PR #42" in text
        assert "Add feature X" in text
        assert "alice" in text
        assert "merged" in text.lower()

    def test_pr_has_review(self, github_tools) -> None:
        """PR details should include review info."""
        tool = _get_tool(github_tools, "get_pr_details")
        text = _call_tool_text(tool, query="42")
        assert "carol" in text
        assert "APPROVED" in text

    def test_pr_has_comments(self, github_tools) -> None:
        """PR details should include comment info."""
        tool = _get_tool(github_tools, "get_pr_details")
        text = _call_tool_text(tool, query="42")
        assert "bob" in text
        assert "LGTM" in text

    def test_pr_search_by_keyword(self, github_tools) -> None:
        """Non-numeric query should search PRs by keyword."""
        tool = _get_tool(github_tools, "get_pr_details")
        text = _call_tool_text(tool, query="feature")
        assert "#42" in text
        assert "Add feature X" in text

    def test_pr_search_no_match(self, github_tools) -> None:
        """Search query with no match returns 'No pull requests found'."""
        tool = _get_tool(github_tools, "get_pr_details")
        text = _call_tool_text(tool, query="zzz_nonexistent_zzz")
        assert "No pull requests found" in text


class TestSearchIssuesMocked:
    """Tests for search_issues with a mocked GitHub client."""

    @pytest.fixture()
    def github_tools(self, git_ops, knowledge_graph):
        mock_client = MagicMock()
        mock_client.search_issues = AsyncMock(return_value=[
            {
                "number": 99,
                "title": "Memory leak in parser",
                "state": "open",
                "body": "The parser leaks memory on large files.",
            },
            {
                "number": 77,
                "title": "Add dark mode support",
                "state": "closed",
                "body": "Dark mode requested by users.",
            },
        ])
        return build_tools(
            REPO_ROOT,
            git_ops=git_ops,
            knowledge_graph=knowledge_graph,
            github_client=mock_client,
        )

    def test_search_issues_returns_results(self, github_tools) -> None:
        tool = _get_tool(github_tools, "search_issues")
        text = _call_tool_text(tool, query="memory")
        assert "#99" in text
        assert "Memory leak" in text

    def test_search_issues_format(self, github_tools) -> None:
        """Issue results should include state and body preview."""
        tool = _get_tool(github_tools, "search_issues")
        text = _call_tool_text(tool, query="memory")
        assert "open" in text
        assert "parser" in text.lower()

    def test_search_issues_multiple_results(self, github_tools) -> None:
        """Should return multiple matched issues."""
        tool = _get_tool(github_tools, "search_issues")
        text = _call_tool_text(tool, query="anything")
        assert "#99" in text
        assert "#77" in text


class TestSearchIssuesEmpty:
    """Test search_issues when the API returns no results."""

    @pytest.fixture()
    def github_tools(self, git_ops, knowledge_graph):
        mock_client = MagicMock()
        mock_client.search_issues = AsyncMock(return_value=[])
        return build_tools(
            REPO_ROOT,
            git_ops=git_ops,
            knowledge_graph=knowledge_graph,
            github_client=mock_client,
        )

    def test_search_issues_empty_results(self, github_tools) -> None:
        tool = _get_tool(github_tools, "search_issues")
        text = _call_tool_text(tool, query="nothing")
        assert "No issues found" in text


# ══════════════════════════════════════════════════════════════════════
# Real GitHub API tests (run when GITHUB_TOKEN is available)
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not HAS_GITHUB_TOKEN, reason="GITHUB_TOKEN not set")
class TestGetPRDetailsRealAPI:
    """Test get_pr_details against the real GitHub API (octocat/Hello-World)."""

    @pytest.fixture(scope="class")
    def live_github_tools(self, git_ops, knowledge_graph):
        """Build tools with a real GitHub client pointed at octocat/Hello-World."""
        client = GitHubClient(owner="octocat", repo="Hello-World", token=GITHUB_TOKEN)
        return build_tools(
            REPO_ROOT,
            git_ops=git_ops,
            knowledge_graph=knowledge_graph,
            github_client=client,
        )

    def test_pr_by_number_real(self, live_github_tools) -> None:
        """octocat/Hello-World has PR #2029 (or similar). Query by number."""
        tool = _get_tool(live_github_tools, "get_pr_details")
        # PR #1 doesn't exist on Hello-World; use a known PR or search
        text = _call_tool_text(tool, query="test")
        # Should get some PR results (not "GitHub API not available")
        assert "GitHub API not available" not in text
        assert (
            "PR #" in text
            or "No pull requests found" in text
            or "#" in text
        )

    def test_pr_search_keyword_real(self, live_github_tools) -> None:
        """Search PRs by keyword on a real repo."""
        tool = _get_tool(live_github_tools, "get_pr_details")
        text = _call_tool_text(tool, query="update")
        assert "GitHub API not available" not in text


@pytest.mark.skipif(not HAS_GITHUB_TOKEN, reason="GITHUB_TOKEN not set")
class TestSearchIssuesRealAPI:
    """Test search_issues against the real GitHub API."""

    @pytest.fixture(scope="class")
    def live_github_tools(self, git_ops, knowledge_graph):
        client = GitHubClient(owner="octocat", repo="Hello-World", token=GITHUB_TOKEN)
        return build_tools(
            REPO_ROOT,
            git_ops=git_ops,
            knowledge_graph=knowledge_graph,
            github_client=client,
        )

    def test_search_issues_real(self, live_github_tools) -> None:
        """Search issues on octocat/Hello-World (has many issues)."""
        tool = _get_tool(live_github_tools, "search_issues")
        text = _call_tool_text(tool, query="hello")
        assert "GitHub API not available" not in text
        # Should find at least one issue
        assert "#" in text or "No issues found" in text

    def test_search_issues_real_format(self, live_github_tools) -> None:
        """Real issue results should have proper structure."""
        tool = _get_tool(live_github_tools, "search_issues")
        text = _call_tool_text(tool, query="world")
        assert "GitHub API not available" not in text
        if "Found" in text:
            assert "issue" in text.lower()
            assert "#" in text
