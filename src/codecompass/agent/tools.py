"""Custom tools exposed to the Copilot SDK agent.

These tools give the agent the ability to inspect local git history,
search files, read source code, analyze the knowledge graph, and query
the GitHub API — all from within a conversation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Pydantic param models (used by @define_tool) ─────────────────────


class SearchGitHistoryParams(BaseModel):
    query: str = Field(description="Search term to look for in commit messages")
    path: str = Field(default="", description="Optional file path to filter commits")
    max_results: int = Field(default=20, description="Maximum commits to return")


class GetFileContributorsParams(BaseModel):
    file_path: str = Field(description="Repo-relative file path to analyze")


class ReadFileParams(BaseModel):
    file_path: str = Field(description="Repo-relative file path to read")
    start_line: int = Field(default=0, description="Start line (0 for beginning)")
    end_line: int = Field(default=0, description="End line (0 for end of file)")


class SearchCodeParams(BaseModel):
    query: str = Field(description="Text or pattern to search for in source files")
    file_pattern: str = Field(default="*", description="Glob pattern to filter files (e.g., '*.py')")
    max_results: int = Field(default=10, description="Maximum matching files to return")


class GetArchitectureSummaryParams(BaseModel):
    depth: int = Field(default=3, description="How many directory levels to show")


class FindRelatedDocsParams(BaseModel):
    file_path: str = Field(description="Repo-relative path of the code file")


class DetectStaleDocsParams(BaseModel):
    doc_path: str = Field(default="", description="Specific doc file to audit (empty for all)")


class SearchPRsParams(BaseModel):
    query: str = Field(description="Search query for pull requests and issues")
    max_results: int = Field(default=5, description="Maximum results to return")


class GetSymbolInfoParams(BaseModel):
    symbol_name: str = Field(description="Class, function, or module name to look up")


class GetModuleDepsParams(BaseModel):
    module_name: str = Field(description="Dotted module name to inspect dependencies for")


# ── Tool factory ─────────────────────────────────────────────────────


class GetPRDetailsParams(BaseModel):
    query: str = Field(description="PR number (as string) or search term to find relevant pull requests")
    max_results: int = Field(default=5, description="Maximum pull requests to return")


class SearchIssuesParams(BaseModel):
    query: str = Field(description="Search query for GitHub issues")
    max_results: int = Field(default=5, description="Maximum issues to return")


def build_tools(
    repo_path: Path,
    *,
    git_ops: Any = None,
    knowledge_graph: Any = None,
    github_client: Any = None,
):
    """Build the list of Copilot SDK custom tools.

    This function is imported by the client module and passed into the
    ``create_session`` call.  Each tool is created with the ``@define_tool``
    decorator from the SDK so that schemas are auto-generated from the
    Pydantic models above.

    Args:
        repo_path: Absolute path to the repository root.
        git_ops: An instance of ``GitOps`` for local git operations.
        knowledge_graph: An instance of ``KnowledgeGraph``.
        github_client: An instance of ``GitHubClient`` for PR/issue lookup.

    Returns:
        A list of tool objects ready for ``create_session(tools=[...])``.
    """
    from copilot import define_tool  # type: ignore[import-untyped]

    tools = []

    # ── search_git_history ───────────────────────────────────────────

    @define_tool(description="Search the git commit history for messages matching a query. Returns recent commits whose messages contain the search term, optionally filtered to a file path.")
    async def search_git_history(params: SearchGitHistoryParams) -> str:
        if git_ops is None:
            return "Git operations not available (not a git repository)"
        try:
            commits = git_ops.search_log(
                query=params.query,
                path=params.path or None,
                max_count=params.max_results,
            )
            if not commits:
                return f"No commits found matching '{params.query}'"
            lines = []
            for c in commits:
                lines.append(
                    f"- `{c['short_hash']}` ({c['date']}) by {c['author']}: {c['message']}"
                )
            return "\n".join(lines)
        except Exception as exc:
            return f"Error searching git history: {exc}"

    tools.append(search_git_history)

    # ── get_file_contributors ────────────────────────────────────────

    @define_tool(description="Get the contributors who have worked on a specific file, based on git blame and commit history.")
    async def get_file_contributors(params: GetFileContributorsParams) -> str:
        if git_ops is None:
            return "Git operations not available"
        try:
            contributors = git_ops.file_contributors(params.file_path)
            if not contributors:
                return f"No contributors found for '{params.file_path}'"
            lines = [f"Contributors to `{params.file_path}`:"]
            for c in contributors:
                lines.append(f"- {c['name']}: {c['commits']} commits, last: {c['last_date']}")
            return "\n".join(lines)
        except Exception as exc:
            return f"Error getting contributors: {exc}"

    tools.append(get_file_contributors)

    # ── read_source_file ─────────────────────────────────────────────

    @define_tool(description="Read the contents of a source file from the repository. Can read the entire file or a specific line range.")
    async def read_source_file(params: ReadFileParams) -> str:
        try:
            full_path = repo_path / params.file_path
            if not full_path.exists():
                return f"File not found: {params.file_path}"
            if not full_path.is_file():
                return f"Not a file: {params.file_path}"

            content = full_path.read_text(errors="replace")
            lines = content.splitlines()

            if params.start_line > 0 or params.end_line > 0:
                start = max(0, params.start_line - 1)
                end = params.end_line if params.end_line > 0 else len(lines)
                selected = lines[start:end]
                header = f"File: {params.file_path} (lines {start + 1}-{min(end, len(lines))})"
                return f"{header}\n\n```\n" + "\n".join(selected) + "\n```"

            # Truncate very large files
            if len(lines) > 300:
                truncated = lines[:300]
                header = f"File: {params.file_path} (first 300 of {len(lines)} lines)"
                return f"{header}\n\n```\n" + "\n".join(truncated) + "\n```\n\n... (truncated)"

            return f"File: {params.file_path} ({len(lines)} lines)\n\n```\n{content}\n```"
        except Exception as exc:
            return f"Error reading file: {exc}"

    tools.append(read_source_file)

    # ── search_code ──────────────────────────────────────────────────

    @define_tool(description="Search for text patterns across source files in the repository. Returns matching file paths and line numbers with context.")
    async def search_code(params: SearchCodeParams) -> str:
        try:
            import re

            pattern = re.compile(re.escape(params.query), re.IGNORECASE)
            matches: list[str] = []
            skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build"}

            for file_path in repo_path.rglob(params.file_pattern):
                if any(part in skip_dirs for part in file_path.parts):
                    continue
                if not file_path.is_file():
                    continue
                if file_path.stat().st_size > 512 * 1024:
                    continue

                try:
                    content = file_path.read_text(errors="replace")
                except OSError:
                    continue

                for i, line in enumerate(content.splitlines(), 1):
                    if pattern.search(line):
                        rel = file_path.relative_to(repo_path).as_posix()
                        matches.append(f"- `{rel}:{i}`: {line.strip()[:120]}")
                        if len(matches) >= params.max_results:
                            break

                if len(matches) >= params.max_results:
                    break

            if not matches:
                return f"No matches found for '{params.query}'"
            return f"Found {len(matches)} match(es) for '{params.query}':\n\n" + "\n".join(matches)
        except Exception as exc:
            return f"Error searching code: {exc}"

    tools.append(search_code)

    # ── get_architecture_summary ─────────────────────────────────────

    @define_tool(description="Get a high-level architecture summary of the repository including directory structure, detected languages, and frameworks.")
    async def get_architecture_summary(params: GetArchitectureSummaryParams) -> str:
        try:
            from codecompass.indexer.scanner import RepoScanner
            scanner = RepoScanner(repo_path, tree_depth=params.depth)
            summary = scanner.scan()
            return summary.to_text()
        except Exception as exc:
            return f"Error generating architecture summary: {exc}"

    tools.append(get_architecture_summary)

    # ── find_related_docs ────────────────────────────────────────────

    @define_tool(description="Find documentation files related to a given source file. Looks for README files in the same directory, adjacent markdown files, and doc-strings.")
    async def find_related_docs(params: FindRelatedDocsParams) -> str:
        try:
            source_path = repo_path / params.file_path
            if not source_path.exists():
                return f"File not found: {params.file_path}"

            docs: list[str] = []
            search_dir = source_path.parent

            # Look for markdown files in the same and parent directories
            for d in [search_dir, search_dir.parent]:
                if d < repo_path:
                    continue
                for md in d.glob("*.md"):
                    rel = md.relative_to(repo_path).as_posix()
                    docs.append(f"- `{rel}`")
                for rst in d.glob("*.rst"):
                    rel = rst.relative_to(repo_path).as_posix()
                    docs.append(f"- `{rel}`")

            # Check for a docs/ directory at repo root
            docs_dir = repo_path / "docs"
            if docs_dir.is_dir():
                for md in docs_dir.rglob("*.md"):
                    rel = md.relative_to(repo_path).as_posix()
                    docs.append(f"- `{rel}`")

            if not docs:
                return f"No related documentation found for `{params.file_path}`"
            # Deduplicate
            unique = list(dict.fromkeys(docs))
            return f"Documentation related to `{params.file_path}`:\n\n" + "\n".join(unique[:20])
        except Exception as exc:
            return f"Error finding related docs: {exc}"

    tools.append(find_related_docs)

    # ── detect_stale_docs ────────────────────────────────────────────

    @define_tool(description="Detect potentially stale or outdated documentation by comparing doc content against actual code. Checks for mismatched commands, renamed files, and outdated references.")
    async def detect_stale_docs(params: DetectStaleDocsParams) -> str:
        try:
            findings: list[str] = []
            doc_files: list[Path] = []

            if params.doc_path:
                p = repo_path / params.doc_path
                if p.exists():
                    doc_files.append(p)
            else:
                # Scan common doc locations
                for pattern in ["*.md", "*.rst", "docs/**/*.md", "docs/**/*.rst"]:
                    doc_files.extend(repo_path.glob(pattern))

            for doc in doc_files:
                if not doc.is_file():
                    continue
                rel = doc.relative_to(repo_path).as_posix()
                try:
                    content = doc.read_text(errors="replace")
                except OSError:
                    continue

                # Check for references to files that don't exist
                import re
                # Match backtick-quoted file paths
                refs = re.findall(r'`([a-zA-Z0-9_/\-\.]+\.[a-zA-Z]+)`', content)
                for ref in refs:
                    ref_path = repo_path / ref
                    if ref.startswith(("http", "ftp", "#")):
                        continue
                    if not ref_path.exists() and "/" in ref:
                        findings.append(
                            f"- **{rel}**: References `{ref}` which does not exist"
                        )

                # Check for common stale patterns
                if "npm start" in content and not (repo_path / "package.json").exists():
                    findings.append(f"- **{rel}**: Mentions `npm start` but no package.json found")
                if "pip install" in content and not (repo_path / "pyproject.toml").exists():
                    if not (repo_path / "setup.py").exists() and not (repo_path / "requirements.txt").exists():
                        findings.append(f"- **{rel}**: Mentions `pip install` but no Python packaging found")

            if not findings:
                return "No stale documentation detected. All references appear current."
            return f"Found {len(findings)} potential documentation issue(s):\n\n" + "\n".join(findings)
        except Exception as exc:
            return f"Error detecting stale docs: {exc}"

    tools.append(detect_stale_docs)

    # ── get_symbol_info ──────────────────────────────────────────────

    @define_tool(description="Look up a code symbol (function, class, module) in the knowledge graph. Returns its location, type, and docstring.")
    async def get_symbol_info(params: GetSymbolInfoParams) -> str:
        if knowledge_graph is None:
            return "Knowledge graph not available"
        try:
            results = knowledge_graph.query(params.symbol_name)
            if not results:
                return f"No symbols found matching '{params.symbol_name}'"
            lines = [f"Found {len(results)} symbol(s) matching '{params.symbol_name}':"]
            for sym in results[:15]:
                loc = f"`{sym.file}:{sym.line}`" if sym.line else f"`{sym.file}`"
                doc = f" — {sym.docstring[:100]}..." if sym.docstring else ""
                lines.append(f"- **{sym.kind}** `{sym.name}` at {loc}{doc}")
            return "\n".join(lines)
        except Exception as exc:
            return f"Error looking up symbol: {exc}"

    tools.append(get_symbol_info)

    # ── get_module_dependencies ──────────────────────────────────────

    @define_tool(description="Show what modules a given module imports (dependencies) and what modules import it (dependents).")
    async def get_module_dependencies(params: GetModuleDepsParams) -> str:
        if knowledge_graph is None:
            return "Knowledge graph not available"
        try:
            deps = knowledge_graph.dependencies(params.module_name)
            rdeps = knowledge_graph.dependents(params.module_name)
            lines = [f"Dependencies for `{params.module_name}`:"]
            if deps:
                lines.append("\n**Imports (depends on):**")
                for d in sorted(deps):
                    lines.append(f"  - `{d}`")
            else:
                lines.append("\n*No outgoing dependencies found.*")

            if rdeps:
                lines.append("\n**Imported by (dependents):**")
                for d in sorted(rdeps):
                    lines.append(f"  - `{d}`")
            else:
                lines.append("\n*No incoming dependencies found.*")

            return "\n".join(lines)
        except Exception as exc:
            return f"Error getting module dependencies: {exc}"

    tools.append(get_module_dependencies)

    # ── get_pr_details ───────────────────────────────────────────────

    @define_tool(description="Search for and retrieve pull request details from GitHub. Use this to understand why changes were made, find context from code review discussions, and trace the history of decisions.")
    async def get_pr_details(params: GetPRDetailsParams) -> str:
        if github_client is None:
            return "GitHub API not available. Set GITHUB_TOKEN and ensure this is a GitHub-hosted repo."
        try:
            # Try to interpret query as a PR number
            try:
                pr_num = int(params.query)
                pr = await github_client.get_pr(pr_num)
                if pr:
                    comments = await github_client.get_pr_comments(pr_num)
                    reviews = await github_client.get_pr_reviews(pr_num)
                    lines = [
                        f"## PR #{pr['number']}: {pr['title']}",
                        f"- **State:** {pr['state']}",
                        f"- **Author:** {pr.get('user', {}).get('login', 'unknown')}",
                        f"- **Created:** {pr.get('created_at', 'N/A')}",
                        f"- **Merged:** {pr.get('merged_at', 'N/A')}",
                        "",
                        "### Description",
                        pr.get("body", "_No description_") or "_No description_",
                    ]
                    if reviews:
                        lines.append("\n### Reviews")
                        for r in reviews[:5]:
                            lines.append(
                                f"- **{r.get('user', {}).get('login', '?')}** ({r.get('state', '?')}): "
                                f"{(r.get('body', '') or '')[:200]}"
                            )
                    if comments:
                        lines.append("\n### Comments")
                        for c in comments[:5]:
                            lines.append(
                                f"- **{c.get('user', {}).get('login', '?')}**: "
                                f"{(c.get('body', '') or '')[:200]}"
                            )
                    return "\n".join(lines)
            except ValueError:
                pass  # Not a number, search instead

            # Search PRs by query
            prs = await github_client.list_prs(state="all")
            matching = [
                p for p in prs
                if params.query.lower() in (p.get("title", "") + p.get("body", "")).lower()
            ][:params.max_results]

            if not matching:
                return f"No pull requests found matching '{params.query}'"
            lines = [f"Found {len(matching)} PR(s) matching '{params.query}':"]
            for p in matching:
                lines.append(
                    f"- **#{p['number']}** {p['title']} ({p['state']}) "
                    f"by {p.get('user', {}).get('login', '?')}"
                )
            return "\n".join(lines)
        except Exception as exc:
            return f"Error fetching PR details: {exc}"

    tools.append(get_pr_details)

    # ── search_issues ────────────────────────────────────────────────

    @define_tool(description="Search GitHub Issues for context about decisions, bugs, or feature requests related to the codebase.")
    async def search_issues(params: SearchIssuesParams) -> str:
        if github_client is None:
            return "GitHub API not available. Set GITHUB_TOKEN and ensure this is a GitHub-hosted repo."
        try:
            issues = await github_client.search_issues(params.query)
            if not issues:
                return f"No issues found matching '{params.query}'"
            results = issues[:params.max_results]
            lines = [f"Found {len(results)} issue(s) matching '{params.query}':"]
            for iss in results:
                lines.append(
                    f"- **#{iss.get('number', '?')}** {iss.get('title', 'Untitled')} "
                    f"({iss.get('state', '?')}) — {(iss.get('body', '') or '')[:100]}"
                )
            return "\n".join(lines)
        except Exception as exc:
            return f"Error searching issues: {exc}"

    tools.append(search_issues)

    return tools
