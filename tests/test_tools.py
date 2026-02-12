"""Tests for the Copilot SDK tools."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codecompass.agent.tools import build_tools
from codecompass.github.git import GitOps
from codecompass.indexer.knowledge_graph import KnowledgeGraph


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def git_ops() -> GitOps:
    return GitOps(REPO_ROOT)


@pytest.fixture()
def knowledge_graph() -> KnowledgeGraph:
    kg = KnowledgeGraph()
    kg.build(REPO_ROOT)
    return kg


@pytest.fixture()
def tools(git_ops: GitOps, knowledge_graph: KnowledgeGraph) -> list:
    return build_tools(REPO_ROOT, git_ops=git_ops, knowledge_graph=knowledge_graph)


class TestTools:
    """Tests for the custom tools exposed to the Copilot SDK."""

    def test_build_tools_returns_list(self, tools: list) -> None:
        assert isinstance(tools, list)
        assert len(tools) >= 9  # We defined 9+ tools

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
        }
        assert expected.issubset(names), f"Missing tools: {expected - names}"
