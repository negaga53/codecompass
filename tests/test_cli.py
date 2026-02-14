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
        assert "tui" in result.output

    def test_onboard(self) -> None:
        result = runner.invoke(main, ["--repo", ".", "onboard", "--no-ai"])
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


class TestConfigCommands:
    """Tests for the config subcommands."""

    def test_config_help(self) -> None:
        result = runner.invoke(main, ["config", "--help"])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "show" in result.output
        assert "set" in result.output
        assert "path" in result.output
        assert "set-model" in result.output

    def test_config_path(self) -> None:
        result = runner.invoke(main, ["config", "path"])
        assert result.exit_code == 0
        assert ".codecompass.toml" in result.output

    def test_config_path_global(self) -> None:
        result = runner.invoke(main, ["config", "path", "--global"])
        assert result.exit_code == 0
        assert "config.toml" in result.output

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

    def test_config_set_global_writes_global_file(self, tmp_path, monkeypatch) -> None:
        if os.name == "nt":
            monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
            global_cfg = tmp_path / "appdata" / "codecompass" / "config.toml"
        else:
            monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
            global_cfg = tmp_path / "xdg" / "codecompass" / "config.toml"

        result = runner.invoke(
            main,
            ["config", "set", "--global", "model", "gpt-4.1"],
        )
        assert result.exit_code == 0
        assert global_cfg.is_file()
        assert 'model = "gpt-4.1"' in global_cfg.read_text()

    def test_config_set_numeric(self) -> None:
        """Test that numeric keys are coerced to integers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(main, ["--repo", tmpdir, "config", "set", "tree_depth", "8"])
            assert result.exit_code == 0
            cfg = Path(tmpdir) / ".codecompass.toml"
            content = cfg.read_text()
            assert "tree_depth = 8" in content

    def test_config_set_log_level(self) -> None:
        """Test that log_level can be set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = runner.invoke(main, ["--repo", tmpdir, "config", "set", "log_level", "DEBUG"])
            assert result.exit_code == 0
            cfg = Path(tmpdir) / ".codecompass.toml"
            content = cfg.read_text()
            assert 'log_level = "DEBUG"' in content

    def test_config_set_model_without_value_uses_selector(self, monkeypatch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr(
                "codecompass.cli._available_models_with_premium",
                lambda: [("gpt-4.1", "0x"), ("gpt-5.1", "1x")],
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

    def test_config_set_model_shortcut(self, monkeypatch) -> None:
        """Test that 'config set-model' works as a shortcut for 'config set model'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr(
                "codecompass.cli._available_models_with_premium",
                lambda: [("gpt-4.1", "0x"), ("gpt-5.1", "1x")],
            )

            # Direct value
            result = runner.invoke(
                main,
                ["--repo", tmpdir, "config", "set-model", "gpt-4.1"],
            )
            assert result.exit_code == 0
            cfg = Path(tmpdir) / ".codecompass.toml"
            content = cfg.read_text()
            assert 'model = "gpt-4.1"' in content

    def test_config_set_model_shortcut_interactive(self, monkeypatch) -> None:
        """Test that 'config set-model' without a value shows the picker."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr(
                "codecompass.cli._available_models_with_premium",
                lambda: [("gpt-4.1", "0x"), ("gpt-5.1", "1x")],
            )

            result = runner.invoke(
                main,
                ["--repo", tmpdir, "config", "set-model"],
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
                input="gpt-4.1\nWARNING\n4\n512\n",
            )
            assert result.exit_code == 0
            cfg = Path(tmpdir) / ".codecompass.toml"
            assert cfg.is_file()
            content = cfg.read_text()
            assert "gpt-4.1" in content
            assert "WARNING" in content

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
                input="new-model\nDEBUG\n6\n1024\n",
            )
            assert result.exit_code == 0
            content = cfg.read_text()
            assert "new-model" in content
            assert "old" not in content
