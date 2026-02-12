"""Tests for the CLI entry point."""

from click.testing import CliRunner
from codecompass.cli import main


runner = CliRunner()


class TestCLI:
    """Tests for the Click CLI commands."""

    def test_version(self) -> None:
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_help(self) -> None:
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "CodeCompass" in result.output
        assert "onboard" in result.output
        assert "ask" in result.output
        assert "tui" in result.output

    def test_onboard(self) -> None:
        result = runner.invoke(main, ["--repo", ".", "onboard"])
        assert result.exit_code == 0
        # Should print the summary panel
        assert "CodeCompass" in result.output or "python" in result.output.lower()

    def test_contributors(self) -> None:
        result = runner.invoke(main, ["--repo", ".", "contributors"])
        assert result.exit_code == 0
        assert "Contributors" in result.output or "contributor" in result.output.lower() or "commits" in result.output.lower()

    def test_no_command_shows_help(self) -> None:
        result = runner.invoke(main, [])
        assert result.exit_code == 0
        assert "Commands:" in result.output or "onboard" in result.output

    def test_export_json(self) -> None:
        result = runner.invoke(main, ["--repo", ".", "export", "--format", "json"])
        assert result.exit_code == 0
        assert '"name"' in result.output
        assert '"languages"' in result.output

    def test_export_help(self) -> None:
        result = runner.invoke(main, ["export", "--help"])
        assert result.exit_code == 0
        assert "markdown" in result.output
        assert "json" in result.output
