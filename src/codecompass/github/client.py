"""GitHub REST API client for CodeCompass."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from codecompass.utils.config import Settings

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


class GitHubClientError(Exception):
    """Raised when a GitHub API request fails."""


class GitHubClient:
    """Async wrapper around the GitHub REST API.

    Args:
        token: GitHub personal access token.  If omitted the value from
            ``Settings`` is used.
        owner: Repository owner (user or org).
        repo: Repository name.
    """

    def __init__(
        self,
        owner: str,
        repo: str,
        *,
        token: str | None = None,
    ) -> None:
        self.owner = owner
        self.repo = repo
        resolved_token = token or Settings.load().github_token
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if resolved_token:
            headers["Authorization"] = f"Bearer {resolved_token}"
        self._client = httpx.AsyncClient(
            base_url=_GITHUB_API,
            headers=headers,
            timeout=30.0,
        )

    # -- lifecycle -----------------------------------------------------------

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # -- helpers -------------------------------------------------------------

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Issue a GET request and return parsed JSON."""
        url = f"/repos/{self.owner}/{self.repo}{path}"
        resp = await self._client.get(url, params=params)
        if resp.status_code >= 400:
            raise GitHubClientError(
                f"GitHub API error {resp.status_code}: {resp.text[:300]}"
            )
        return resp.json()

    # -- public API ----------------------------------------------------------

    async def get_repo_info(self) -> dict[str, Any]:
        """Fetch general repository metadata."""
        return await self._get("")

    async def list_prs(
        self,
        state: str = "all",
        per_page: int = 30,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """List pull requests."""
        return await self._get(
            "/pulls",
            params={"state": state, "per_page": per_page, "page": page},
        )

    async def get_pr(self, number: int) -> dict[str, Any]:
        """Get a single pull request by number."""
        return await self._get(f"/pulls/{number}")

    async def get_pr_comments(self, number: int) -> list[dict[str, Any]]:
        """Get review comments on a pull request."""
        return await self._get(f"/pulls/{number}/comments")

    async def get_pr_reviews(self, number: int) -> list[dict[str, Any]]:
        """Get reviews on a pull request."""
        return await self._get(f"/pulls/{number}/reviews")

    async def search_issues(
        self,
        query: str,
        per_page: int = 10,
    ) -> list[dict[str, Any]]:
        """Search issues and PRs in this repo.

        ``query`` is appended to a repo-scoped qualifier automatically.
        """
        full_query = f"repo:{self.owner}/{self.repo} {query}"
        resp = await self._client.get(
            "/search/issues",
            params={"q": full_query, "per_page": per_page},
        )
        if resp.status_code >= 400:
            raise GitHubClientError(
                f"GitHub search error {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()
        return data.get("items", [])

    async def get_commits(
        self,
        path: str | None = None,
        per_page: int = 30,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """List commits, optionally filtered to a specific file path."""
        params: dict[str, Any] = {"per_page": per_page, "page": page}
        if path:
            params["path"] = path
        return await self._get("/commits", params=params)

    async def get_commit(self, sha: str) -> dict[str, Any]:
        """Fetch a single commit by SHA."""
        return await self._get(f"/commits/{sha}")
