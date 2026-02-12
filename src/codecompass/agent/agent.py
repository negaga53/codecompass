"""Core CodeCompass agent — bridges the Copilot SDK with local analysis."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from codecompass.agent.prompts import (
    ARCHITECTURE_PROMPT,
    CONTRIBUTOR_PROMPT,
    ONBOARDING_SYSTEM_PROMPT,
    STALE_DOCS_PROMPT,
    WHY_QUERY_PROMPT,
    get_onboarding_prompt,
)
from codecompass.indexer.knowledge_graph import KnowledgeGraph
from codecompass.indexer.scanner import RepoScanner
from codecompass.models import RepoSummary
from codecompass.utils.config import Settings

logger = logging.getLogger(__name__)


class AgentMode:
    """Constants for the different operating modes of the agent."""

    ONBOARDING = "onboarding"
    ASK = "ask"
    WHY = "why"
    ARCHITECTURE = "architecture"
    CONTRIBUTOR = "contributor"
    STALE_DOCS = "stale_docs"


_MODE_PROMPTS: dict[str, str] = {
    AgentMode.ONBOARDING: ONBOARDING_SYSTEM_PROMPT,
    AgentMode.ASK: ONBOARDING_SYSTEM_PROMPT,
    AgentMode.WHY: WHY_QUERY_PROMPT,
    AgentMode.ARCHITECTURE: ARCHITECTURE_PROMPT,
    AgentMode.CONTRIBUTOR: CONTRIBUTOR_PROMPT,
    AgentMode.STALE_DOCS: STALE_DOCS_PROMPT,
}


class CodeCompassAgent:
    """Orchestrates the CodeCompass intelligence pipeline.

    Responsibilities:
    - Scans a repository and builds context (summary + knowledge graph)
    - Selects the appropriate system prompt based on the requested mode
    - Provides helper methods for each CLI command

    Args:
        repo_path: Path to the repository to analyze.
        settings: Optional pre-loaded settings.
    """

    def __init__(
        self,
        repo_path: str | Path,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.settings = settings or Settings.load()
        self._summary: RepoSummary | None = None
        self._graph: KnowledgeGraph | None = None

    # ── lazy initializers ────────────────────────────────────────────

    def _ensure_scanned(self) -> RepoSummary:
        if self._summary is None:
            scanner = RepoScanner(
                self.repo_path,
                max_file_size_kb=self.settings.max_file_size_kb,
                tree_depth=self.settings.tree_depth,
            )
            self._summary = scanner.scan()
            logger.info("Repo scanned: %s", self._summary.name)
        return self._summary

    def _ensure_graph(self) -> KnowledgeGraph:
        if self._graph is None:
            self._graph = KnowledgeGraph()
            self._graph.build(self.repo_path)
        return self._graph

    # ── public API ───────────────────────────────────────────────────

    @property
    def summary(self) -> RepoSummary:
        """Scanned ``RepoSummary`` (triggers scan on first access)."""
        return self._ensure_scanned()

    @property
    def graph(self) -> KnowledgeGraph:
        """``KnowledgeGraph`` (built on first access)."""
        return self._ensure_graph()

    def system_message(self, mode: str = AgentMode.ONBOARDING) -> dict[str, str]:
        """Build the system message dict for a given *mode*.

        For ``ONBOARDING`` mode the repo summary is injected.
        """
        if mode == AgentMode.ONBOARDING:
            summary = self._ensure_scanned()
            return get_onboarding_prompt(summary.to_text())

        prompt = _MODE_PROMPTS.get(mode, ONBOARDING_SYSTEM_PROMPT)
        return {"content": prompt}

    async def onboard(self) -> RepoSummary:
        """Run the onboarding pipeline: scan + build graph.

        Returns:
            The ``RepoSummary`` for the repository.
        """
        summary = self._ensure_scanned()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._ensure_graph)
        return summary

    async def ask(self, question: str) -> dict[str, Any]:
        """Prepare a payload for a free-form question.

        Automatically selects WHY mode if the question starts with "why".
        """
        mode = AgentMode.ASK
        lower_q = question.lower().strip()
        if lower_q.startswith("why ") or lower_q.startswith("why?"):
            mode = AgentMode.WHY

        sys_msg = self.system_message(mode)
        return {
            "system_message": sys_msg,
            "user_message": {"content": question},
        }

    async def explore_architecture(self) -> dict[str, Any]:
        """Prepare a payload for architecture exploration."""
        self._ensure_scanned()
        self._ensure_graph()
        sys_msg = self.system_message(AgentMode.ARCHITECTURE)

        modules = self.graph.all_modules()
        module_list = "\n".join(f"- {m}" for m in modules[:50])
        context = (
            f"## Indexed Modules\n\n{module_list}\n\n"
            f"Total import edges: {len(self.graph.imports)}"
        )

        return {
            "system_message": sys_msg,
            "user_message": {
                "content": (
                    "Please analyze the architecture of this repository.\n\n"
                    + context
                )
            },
        }

    async def audit_docs(self) -> dict[str, Any]:
        """Prepare a payload for documentation-freshness auditing."""
        summary = self._ensure_scanned()
        sys_msg = self.system_message(AgentMode.STALE_DOCS)

        doc_files: list[str] = []
        for p in self.repo_path.iterdir():
            if p.suffix.lower() in {".md", ".rst"} and p.is_file():
                doc_files.append(p.name)

        docs_dir = self.repo_path / "docs"
        if docs_dir.is_dir():
            for p in docs_dir.rglob("*.md"):
                rel = p.relative_to(self.repo_path).as_posix()
                if rel not in doc_files:
                    doc_files.append(rel)

        file_list = "\n".join(f"- {f}" for f in doc_files) or "- (no documentation files found)"

        return {
            "system_message": sys_msg,
            "user_message": {
                "content": (
                    "Please audit the documentation freshness for this repo.\n\n"
                    f"## Documentation Files\n\n{file_list}\n\n"
                    f"## Repo Summary\n\n{summary.to_text()}"
                )
            },
        }
