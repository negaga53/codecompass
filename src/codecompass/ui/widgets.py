"""Custom Textual widgets for the CodeCompass TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Markdown, Static, Tree


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
