"""Local git operations using subprocess (no native dependencies).

Uses the system ``git`` binary for maximum portability — no need for
``pygit2`` or other compiled libraries.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class GitOpsError(Exception):
    """Raised when a git command fails."""


class GitOps:
    """High-level wrapper for local git operations via subprocess.

    Args:
        repo_path: Path to the repository root.
    """

    def __init__(self, repo_path: str | Path) -> None:
        self.repo_path = Path(repo_path).resolve()
        # Verify this is a git repo
        if not (self.repo_path / ".git").exists():
            # Try git rev-parse to handle worktrees etc.
            try:
                self._run(["git", "rev-parse", "--git-dir"])
            except GitOpsError:
                raise GitOpsError(f"Not a git repository: {self.repo_path}")

    # ── internal ─────────────────────────────────────────────────────

    def _run(
        self,
        cmd: list[str],
        *,
        check: bool = True,
        timeout: int = 30,
    ) -> str:
        """Run a git command and return stdout."""
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=check,
            )
            return result.stdout
        except subprocess.CalledProcessError as exc:
            raise GitOpsError(
                f"git command failed: {' '.join(cmd)}\n{exc.stderr}"
            ) from exc
        except FileNotFoundError:
            raise GitOpsError("git is not installed or not in PATH")

    # ── commit log ───────────────────────────────────────────────────

    def log(
        self,
        max_count: int = 50,
        path: str | None = None,
    ) -> list[dict[str, str]]:
        """Get recent commits as a list of dicts.

        Returns:
            List of dicts with keys: hash, short_hash, author, email,
            date, message.
        """
        fmt = "%H%x00%h%x00%an%x00%ae%x00%aI%x00%s"
        cmd = ["git", "log", f"--max-count={max_count}", f"--format={fmt}"]
        if path:
            cmd += ["--", path]

        output = self._run(cmd)
        commits = []
        for line in output.strip().splitlines():
            parts = line.split("\x00")
            if len(parts) >= 6:
                commits.append({
                    "hash": parts[0],
                    "short_hash": parts[1],
                    "author": parts[2],
                    "email": parts[3],
                    "date": parts[4],
                    "message": parts[5],
                })
        return commits

    def search_log(
        self,
        query: str,
        path: str | None = None,
        max_count: int = 20,
    ) -> list[dict[str, str]]:
        """Search commit messages for a query string.

        Args:
            query: Text to search for in commit messages.
            path: Optional file path filter.
            max_count: Maximum results.

        Returns:
            List of matching commit dicts.
        """
        fmt = "%H%x00%h%x00%an%x00%ae%x00%aI%x00%s"
        cmd = [
            "git", "log",
            f"--max-count={max_count}",
            f"--format={fmt}",
            f"--grep={query}",
            "--regexp-ignore-case",
        ]
        if path:
            cmd += ["--", path]

        output = self._run(cmd, check=False)
        commits = []
        for line in output.strip().splitlines():
            if not line:
                continue
            parts = line.split("\x00")
            if len(parts) >= 6:
                commits.append({
                    "hash": parts[0],
                    "short_hash": parts[1],
                    "author": parts[2],
                    "email": parts[3],
                    "date": parts[4],
                    "message": parts[5],
                })
        return commits

    # ── blame ────────────────────────────────────────────────────────

    def blame(self, path: str) -> list[dict[str, Any]]:
        """Run git blame on a file.

        Returns:
            List of dicts with: hash, author, date, line_start, content.
        """
        cmd = ["git", "blame", "--porcelain", path]
        output = self._run(cmd, check=False)

        entries: list[dict[str, Any]] = []
        current: dict[str, Any] = {}

        for line in output.splitlines():
            if line and line[0] not in ("\t", " ") and len(line.split()) >= 3:
                parts = line.split()
                if len(parts[0]) == 40:  # SHA
                    if current:
                        entries.append(current)
                    current = {
                        "hash": parts[0][:7],
                        "line_start": int(parts[2]) if len(parts) > 2 else 0,
                    }
            elif line.startswith("author "):
                current["author"] = line[7:]
            elif line.startswith("author-time "):
                try:
                    ts = int(line[12:])
                    current["date"] = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                except (ValueError, OSError):
                    pass
            elif line.startswith("summary "):
                current["message"] = line[8:]
            elif line.startswith("\t"):
                current["content"] = line[1:]

        if current:
            entries.append(current)
        return entries

    # ── contributors ─────────────────────────────────────────────────

    def contributors(self, max_commits: int = 500) -> list[dict[str, Any]]:
        """Get contributor statistics.

        Returns:
            Sorted list of contributor dicts (most commits first).
        """
        cmd = [
            "git", "shortlog", "-sne",
            f"--max-count={max_commits}",
            "HEAD",
        ]
        output = self._run(cmd, check=False)

        contributors = []
        for line in output.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            # Format: "   123\tName <email>"
            parts = line.split("\t", 1)
            if len(parts) == 2:
                count = int(parts[0].strip())
                name_email = parts[1].strip()
                name = name_email.split("<")[0].strip()
                email = ""
                if "<" in name_email and ">" in name_email:
                    email = name_email.split("<")[1].rstrip(">")
                contributors.append({
                    "name": name,
                    "email": email,
                    "commits": count,
                })
        return contributors

    def file_contributors(self, path: str) -> list[dict[str, Any]]:
        """Get contributors for a specific file.

        Returns:
            List of contributor dicts with commit count and last date.
        """
        fmt = "%an%x00%aI"
        cmd = ["git", "log", f"--format={fmt}", "--", path]
        output = self._run(cmd, check=False)

        stats: dict[str, dict[str, Any]] = {}
        for line in output.strip().splitlines():
            if not line:
                continue
            parts = line.split("\x00")
            if len(parts) >= 2:
                name = parts[0]
                date = parts[1]
                if name not in stats:
                    stats[name] = {"name": name, "commits": 0, "last_date": date}
                stats[name]["commits"] += 1
                if date > stats[name]["last_date"]:
                    stats[name]["last_date"] = date

        return sorted(stats.values(), key=lambda x: x["commits"], reverse=True)

    # ── diff ─────────────────────────────────────────────────────────

    def diff(self, staged: bool = False) -> str:
        """Get the current diff (working tree or staged).

        Args:
            staged: If True, show staged changes instead of unstaged.

        Returns:
            Unified diff string.
        """
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--staged")
        return self._run(cmd, check=False)

    # ── status ───────────────────────────────────────────────────────

    def status(self) -> str:
        """Get a short status summary."""
        return self._run(["git", "status", "--short"], check=False)

    # ── branch info ──────────────────────────────────────────────────

    def current_branch(self) -> str:
        """Get the current branch name."""
        output = self._run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            check=False,
        )
        return output.strip()

    def remote_url(self) -> str | None:
        """Get the origin remote URL, if any."""
        output = self._run(
            ["git", "remote", "get-url", "origin"],
            check=False,
        )
        url = output.strip()
        return url if url else None
