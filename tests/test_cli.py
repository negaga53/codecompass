"""Tests for the CLI entry point."""

import os
import tempfile
from pathlib import Path

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
        assert "demo" in result.output
        assert "premium-usage" in result.output
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

    def test_demo_script(self) -> None:
        result = runner.invoke(main, ["--repo", ".", "demo"])
        assert result.exit_code == 0
        assert "Judge Demo Script" in result.output
        assert "diff-explain" in result.output
        assert "pytest -q" in result.output

    def test_premium_usage_command(self) -> None:
        result = runner.invoke(main, ["premium-usage"])
        assert result.exit_code == 0
        assert "Premium" in result.output
        assert "ask" in result.output
        assert "diff-explain" in result.output
        assert "onboard --interactive" in result.output


class TestConfigCommands:
    """Tests for the config subcommands."""

    def test_config_help(self) -> None:
        result = runner.invoke(main, ["config", "--help"])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "show" in result.output
        assert "set" in result.output
        assert "path" in result.output

    def test_config_path(self) -> None:
        result = runner.invoke(main, ["config", "path"])
        assert result.exit_code == 0
        assert ".codecompass.toml" in result.output

    def test_config_show(self) -> None:
        result = runner.invoke(main, ["config", "show"])
        assert result.exit_code == 0
        assert "model" in result.output
        assert "log_level" in result.output

    def test_config_set_and_show(self) -> None:
        """Test config set creates/updates the file and config show reflects it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Set in a temp directory to avoid polluting the project
            result = runner.invoke(main, ["--repo", tmpdir, "config", "set", "model", "test-model"])
            assert result.exit_code == 0
            assert "test-model" in result.output

            # Check the file was created
            cfg = Path(tmpdir) / ".codecompass.toml"
            assert cfg.is_file()
            content = cfg.read_text()
            assert "test-model" in content

    def test_config_set_invalid_key(self) -> None:
        result = runner.invoke(main, ["config", "set", "invalid_key", "value"])
        assert result.exit_code == 0
        assert "Invalid key" in result.output

    def test_config_set_github_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(main, ["--repo", tmpdir, "config", "set", "github_token", "ghp_testtoken"])
            assert result.exit_code == 0
            cfg = Path(tmpdir) / ".codecompass.toml"
            content = cfg.read_text()
            assert 'github_token = "ghp_testtoken"' in content

    def test_config_set_numeric(self) -> None:
        """Test that numeric keys are coerced to integers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(main, ["--repo", tmpdir, "config", "set", "tree_depth", "8"])
            assert result.exit_code == 0
            cfg = Path(tmpdir) / ".codecompass.toml"
            content = cfg.read_text()
            assert "tree_depth = 8" in content

    def test_config_set_bool(self) -> None:
        """Test that boolean keys are coerced to booleans."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(main, ["--repo", tmpdir, "config", "set", "premium_usage_warnings", "false"])
            assert result.exit_code == 0
            cfg = Path(tmpdir) / ".codecompass.toml"
            content = cfg.read_text().lower()
            assert "premium_usage_warnings = false" in content

    def test_config_set_model_without_value_uses_selector(self, monkeypatch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr(
                "codecompass.cli._available_models_with_premium",
                lambda: [("gpt-4.1", "yes"), ("gpt-5.1", "yes")],
            )

            result = runner.invoke(
                main,
                ["--repo", tmpdir, "config", "set", "model"],
                input="gpt-5.1\n",
            )
            assert result.exit_code == 0
            cfg = Path(tmpdir) / ".codecompass.toml"
            content = cfg.read_text()
            assert 'model = "gpt-5.1"' in content

    def test_config_init_creates_file(self) -> None:
        """Test config init with default values (piped via input)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(
                main,
                ["--repo", tmpdir, "config", "init"],
                input="gpt-4.1\nWARNING\n4\n512\ny\n",
            )
            assert result.exit_code == 0
            cfg = Path(tmpdir) / ".codecompass.toml"
            assert cfg.is_file()
            content = cfg.read_text()
            assert "gpt-4.1" in content
            assert "WARNING" in content
            assert "premium_usage_warnings = true" in content.lower()

    def test_config_init_no_overwrite(self) -> None:
        """Test that config init refuses to overwrite without --force."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Path(tmpdir) / ".codecompass.toml"
            cfg.write_text("[codecompass]\nmodel = \"existing\"\n")
            result = runner.invoke(main, ["--repo", tmpdir, "config", "init"])
            assert result.exit_code == 0
            assert "already exists" in result.output
            # Original file unchanged
            assert "existing" in cfg.read_text()

    def test_config_init_force_overwrite(self) -> None:
        """Test config init --force overwrites existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Path(tmpdir) / ".codecompass.toml"
            cfg.write_text("[codecompass]\nmodel = \"old\"\n")
            result = runner.invoke(
                main,
                ["--repo", tmpdir, "config", "init", "--force"],
                input="new-model\nDEBUG\n6\n1024\nn\n",
            )
            assert result.exit_code == 0
            content = cfg.read_text()
            assert "new-model" in content
            assert "old" not in content
            assert "premium_usage_warnings = false" in content.lower()
