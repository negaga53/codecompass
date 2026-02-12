"""Custom Textual widgets for the CodeCompass TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Markdown, Static, Tree, Input, Button, Label


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


class ChatMessage(Static):
    """A single message bubble in the chat view.

    Args:
        text: The message content (Markdown supported).
        role: ``"user"`` or ``"assistant"``.
    """

    DEFAULT_CSS = """
    ChatMessage {
        margin: 1 2;
        padding: 1 2;
    }
    ChatMessage.user {
        background: $primary-darken-2;
        border: tall $primary;
    }
    ChatMessage.assistant {
        background: $surface;
        border: tall $accent;
    }
    """

    def __init__(self, text: str, role: str = "assistant", **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._text = text
        self._role = role
        self.add_class(role)

    def compose(self) -> ComposeResult:
        prefix = "**You:** " if self._role == "user" else "**CodeCompass:** "
        yield Markdown(prefix + self._text)


# ---------------------------------------------------------------------------
# File tree
# ---------------------------------------------------------------------------


class FileTree(Widget):
    """Displays the repository directory tree as a Textual ``Tree`` widget.

    Args:
        tree_text: ASCII directory-tree string (as produced by
            ``RepoScanner._build_tree``).
    """

    DEFAULT_CSS = """
    FileTree {
        height: 100%;
    }
    """

    def __init__(self, tree_text: str = "", **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._tree_text = tree_text

    def compose(self) -> ComposeResult:
        tree: Tree[str] = Tree("Repository")
        if self._tree_text:
            lines = self._tree_text.strip().splitlines()
            for line in lines:
                tree.root.add_leaf(line)
        tree.root.expand()
        yield tree


# ---------------------------------------------------------------------------
# Summary panel
# ---------------------------------------------------------------------------


class SummaryPanel(Widget):
    """Right-hand panel showing the onboarding summary.

    Bind the ``summary_text`` reactive to update content dynamically.
    """

    DEFAULT_CSS = """
    SummaryPanel {
        padding: 1 2;
        height: 100%;
        overflow-y: auto;
    }
    """

    summary_text: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        yield Markdown(self.summary_text or "_Scanning repository…_")

    def watch_summary_text(self, value: str) -> None:  # noqa: D401
        """Called when ``summary_text`` changes — re-render the Markdown."""
        try:
            md = self.query_one(Markdown)
            md.update(value)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Settings panel
# ---------------------------------------------------------------------------


class SettingsPanel(Widget):
    """Inline settings editor widget.

    Displays editable settings fields with a save button.
    When saved, writes changes to ``.codecompass.toml``.
    """

    DEFAULT_CSS = """
    SettingsPanel {
        layout: vertical;
        padding: 1 2;
        height: auto;
        max-height: 30;
        background: $surface;
        border: tall $primary;
    }

    SettingsPanel Label {
        margin: 1 0 0 0;
        color: $text-muted;
    }

    SettingsPanel Input {
        margin: 0 0 0 0;
    }

    SettingsPanel .settings-title {
        text-style: bold;
        color: $primary;
        margin: 0 0 1 0;
    }

    SettingsPanel .btn-row {
        layout: horizontal;
        height: 3;
        margin: 1 0 0 0;
    }

    SettingsPanel Button {
        margin: 0 1 0 0;
    }
    """

    def __init__(
        self,
        model: str = "gpt-4.1",
        log_level: str = "WARNING",
        tree_depth: int = 4,
        max_file_size_kb: int = 512,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._model = model
        self._log_level = log_level
        self._tree_depth = tree_depth
        self._max_file_size_kb = max_file_size_kb

    def compose(self) -> ComposeResult:
        yield Static("⚙️ Settings", classes="settings-title")
        yield Label("Model:")
        yield Input(value=self._model, id="settings-model")
        yield Label("Log Level (DEBUG/INFO/WARNING/ERROR):")
        yield Input(value=self._log_level, id="settings-log-level")
        yield Label("Directory Tree Depth:")
        yield Input(value=str(self._tree_depth), id="settings-tree-depth")
        yield Label("Max File Size (KB):")
        yield Input(value=str(self._max_file_size_kb), id="settings-max-file-size")
        with Static(classes="btn-row"):
            yield Button("Save", variant="primary", id="settings-save")
            yield Button("Cancel", variant="default", id="settings-cancel")
