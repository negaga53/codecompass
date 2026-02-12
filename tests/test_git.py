"""Tests for local git operations."""

from pathlib import Path

import pytest

from codecompass.github.git import GitOps, GitOpsError


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestGitOps:
    """Tests for ``GitOps`` — tests run against the CodeCompass repo itself."""

    @pytest.fixture()
    def git(self) -> GitOps:
        return GitOps(REPO_ROOT)

    def test_init_valid_repo(self, git: GitOps) -> None:
        assert git.repo_path == REPO_ROOT

    def test_init_invalid_repo(self, tmp_path: Path) -> None:
        with pytest.raises(GitOpsError, match="Not a git repository"):
            GitOps(tmp_path)

    def test_current_branch(self, git: GitOps) -> None:
        branch = git.current_branch()
        assert isinstance(branch, str)
        assert len(branch) > 0

    def test_log(self, git: GitOps) -> None:
        commits = git.log(max_count=5)
        assert len(commits) >= 1
        commit = commits[0]
        assert "hash" in commit
        assert "short_hash" in commit
        assert "author" in commit
        assert "message" in commit

    def test_status(self, git: GitOps) -> None:
        status = git.status()
        assert isinstance(status, str)

    def test_contributors(self, git: GitOps) -> None:
        contribs = git.contributors()
        assert len(contribs) >= 1
        assert "name" in contribs[0]
        assert "commits" in contribs[0]

    def test_diff(self, git: GitOps) -> None:
        diff = git.diff()
        assert isinstance(diff, str)

    def test_search_log_no_match(self, git: GitOps) -> None:
        results = git.search_log("xyzzy_nonexistent_term_42")
        assert len(results) == 0

    def test_search_log_match(self, git: GitOps) -> None:
        results = git.search_log("Initial")
        # We have at least one commit with "Initial" in message
        assert len(results) >= 1
