"""Textual TUI application for CodeCompass.

Provides a split-pane terminal UI with:
- Left sidebar: repository summary + file tree
- Right panel: interactive chat with the Copilot SDK agent (streaming)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Footer, Header, Input, Static, Markdown, Button

from codecompass.agent.agent import CodeCompassAgent
from codecompass.ui.widgets import ChatMessage, SummaryPanel, SettingsPanel
from codecompass.utils.config import Settings


class CodeCompassApp(App[None]):
    """Interactive TUI for CodeCompass codebase intelligence.

    Launch with::

        codecompass tui [--repo PATH]
    """

    TITLE = "🧭 CodeCompass"
    SUB_TITLE = "Codebase Intelligence Assistant"

    CSS = """
    Screen {
        layout: vertical;
    }

    #main {
        layout: horizontal;
        height: 1fr;
    }

    #sidebar {
        width: 35;
        min-width: 25;
        max-width: 50;
        border-right: tall $primary;
        background: $surface;
    }

    #sidebar-content {
        padding: 1 1;
        height: 1fr;
        overflow-y: auto;
    }

    #chat-area {
        width: 1fr;
    }

    #messages {
        height: 1fr;
        padding: 0 1;
    }

    #input-bar {
        dock: bottom;
        height: 3;
        margin: 0 1;
        border: tall $primary;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        background: $primary-darken-3;
        color: $text;
        padding: 0 1;
    }

    ChatMessage {
        margin: 1 0;
        padding: 1 2;
    }
    ChatMessage.user {
        background: $primary-darken-2;
        border-left: thick $primary;
    }
    ChatMessage.assistant {
        background: $surface;
        border-left: thick $accent;
    }
    ChatMessage.system {
        background: $surface-darken-1;
        border-left: thick $warning;
        color: $text-muted;
    }

    SummaryPanel {
        height: 1fr;
        padding: 1 1;
    }

    #settings-panel {
        display: none;
    }
    #settings-panel.visible {
        display: block;
    }

    #thinking-indicator {
        display: none;
        color: $warning;
        padding: 0 2;
    }
    #thinking-indicator.visible {
        display: block;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+l", "clear_chat", "Clear"),
        Binding("ctrl+n", "new_session", "New session"),
        Binding("ctrl+s", "toggle_settings", "Settings"),
    ]

    def __init__(
        self,
        repo_path: str | Path = ".",
        settings: Settings | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._repo_path = Path(repo_path).resolve()
        self._settings = settings or Settings.load()
        self._agent: CodeCompassAgent | None = None
        self._compass_client: Any = None  # CompassClient
        self._is_processing = False
        self._settings_visible = False

    # ── Compose ──────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with Vertical(id="sidebar"):
                yield SummaryPanel(id="sidebar-content")
                yield SettingsPanel(
                    model=self._settings.model,
                    log_level=self._settings.log_level,
                    tree_depth=self._settings.tree_depth,
                    max_file_size_kb=self._settings.max_file_size_kb,
                    id="settings-panel",
                )
            with Vertical(id="chat-area"):
                yield VerticalScroll(id="messages")
                yield Static("", id="thinking-indicator")
                yield Input(
                    placeholder="Ask about the codebase… (Ctrl+Q to quit)",
                    id="input-bar",
                )
        yield Static("🧭 Scanning repository…", id="status-bar")
        yield Footer()

    # ── Lifecycle ────────────────────────────────────────────────────

    async def on_mount(self) -> None:
        """Initialize the agent and start onboarding scan."""
        self.run_worker(self._initialize(), name="init", exclusive=True)

    async def _initialize(self) -> None:
        """Run the full init pipeline: scan → build graph → connect SDK."""
        status = self.query_one("#status-bar", Static)
        summary_panel = self.query_one("#sidebar-content", SummaryPanel)
        messages = self.query_one("#messages", VerticalScroll)

        # 1. Scan the repo
        status.update("🧭 Scanning repository…")
        self._agent = CodeCompassAgent(self._repo_path, settings=self._settings)
        summary = await self._agent.onboard()

        # 2. Update sidebar
        summary_panel.summary_text = summary.to_text()

        # 3. Welcome message
        welcome = (
            f"👋 Welcome! I've scanned **{summary.name}**.\n\n"
            f"- **Languages:** {', '.join(lang.value for lang in summary.languages)}\n"
            f"- **Files:** {summary.total_files} ({summary.total_lines:,} lines)\n"
            f"- **Frameworks:** {', '.join(f.name for f in summary.frameworks) or 'none detected'}\n\n"
            "Ask me anything about this codebase — architecture, \"why\" questions, "
            "contributor info, or help finding code."
        )
        await messages.mount(ChatMessage(welcome, role="system"))

        # 4. Connect to Copilot SDK
        status.update("🔌 Connecting to Copilot SDK…")
        try:
            await self._connect_sdk()
            status.update(f"🧭 {summary.name} — Connected (model: {self._settings.model})")
        except Exception as exc:
            status.update(f"⚠️ SDK not connected: {exc}")
            await messages.mount(
                ChatMessage(
                    f"⚠️ Could not connect to Copilot SDK: `{exc}`\n\n"
                    "Make sure the Copilot CLI is installed and you are authenticated. "
                    "You can still browse the repo summary in the sidebar.",
                    role="system",
                )
            )

    async def _connect_sdk(self) -> None:
        """Initialize the CompassClient and create a session."""
        from codecompass.agent.client import CompassClient
        from codecompass.github.git import GitOps, GitOpsError

        # Git ops
        try:
            git_ops = GitOps(self._repo_path)
        except GitOpsError:
            git_ops = None

        # Knowledge graph
        kg = self._agent.graph if self._agent else None

        self._compass_client = CompassClient(
            self._repo_path,
            model=self._settings.model,
            git_ops=git_ops,
            knowledge_graph=kg,
        )
        await self._compass_client.start()

        sys_msg = self._agent.system_message("onboarding") if self._agent else None
        await self._compass_client.create_session(
            system_message=sys_msg,
            streaming=True,
        )

    # ── Input handling ───────────────────────────────────────────────

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user submitting a question."""
        question = event.value.strip()
        if not question or self._is_processing:
            return

        input_widget = self.query_one("#input-bar", Input)
        input_widget.value = ""
        input_widget.disabled = True

        messages = self.query_one("#messages", VerticalScroll)

        # Add user message
        await messages.mount(ChatMessage(question, role="user"))
        messages.scroll_end()

        # Show thinking indicator
        self._is_processing = True
        thinking = self.query_one("#thinking-indicator", Static)
        thinking.update("💭 Thinking…")
        thinking.add_class("visible")

        # Process with SDK
        self.run_worker(
            self._process_question(question),
            name="chat",
            exclusive=True,
        )

    async def _process_question(self, question: str) -> None:
        """Send question to SDK and stream the response."""
        messages = self.query_one("#messages", VerticalScroll)
        thinking = self.query_one("#thinking-indicator", Static)
        input_widget = self.query_one("#input-bar", Input)

        if self._compass_client is None or not self._compass_client.has_session:
            # SDK not connected — show fallback
            await messages.mount(
                ChatMessage(
                    "I'm not connected to the Copilot SDK. "
                    "Please ensure the Copilot CLI is installed and authenticated.",
                    role="assistant",
                )
            )
        else:
            # Create a streaming message
            response_msg = ChatMessage("", role="assistant")
            await messages.mount(response_msg)

            accumulated: list[str] = []

            def on_delta(delta: str) -> None:
                accumulated.append(delta)
                # Update the message content on the main thread
                self.call_from_thread(
                    self._update_streaming_message,
                    response_msg,
                    "".join(accumulated),
                )

            try:
                thinking.update("💭 Agent is working…")
                response = await self._compass_client.send_and_collect(
                    question, on_delta=on_delta
                )
                # Final update with complete response
                self._update_streaming_message(response_msg, response)
            except Exception as exc:
                self._update_streaming_message(
                    response_msg,
                    f"⚠️ Error: {exc}",
                )

        # Clean up
        thinking.remove_class("visible")
        self._is_processing = False
        input_widget.disabled = False
        input_widget.focus()
        messages.scroll_end()

    def _update_streaming_message(self, msg: ChatMessage, content: str) -> None:
        """Update a ChatMessage widget's content (called from event loop)."""
        try:
            md_widget = msg.query_one(Markdown)
            md_widget.update("**CodeCompass:** " + content)
        except Exception:
            pass

    # ── Actions ──────────────────────────────────────────────────────

    def action_clear_chat(self) -> None:
        """Remove all chat messages."""
        messages = self.query_one("#messages", VerticalScroll)
        messages.remove_children()

    async def action_new_session(self) -> None:
        """Create a new chat session."""
        self.action_clear_chat()
        if self._compass_client:
            try:
                sys_msg = (
                    self._agent.system_message("onboarding")
                    if self._agent
                    else None
                )
                await self._compass_client.create_session(
                    system_message=sys_msg,
                    streaming=True,
                )
                messages = self.query_one("#messages", VerticalScroll)
                await messages.mount(
                    ChatMessage("🔄 New session started. Ask me anything!", role="system")
                )
            except Exception as exc:
                messages = self.query_one("#messages", VerticalScroll)
                await messages.mount(
                    ChatMessage(f"⚠️ Could not create new session: {exc}", role="system")
                )

    def action_toggle_settings(self) -> None:
        """Show or hide the settings panel in the sidebar."""
        panel = self.query_one("#settings-panel", SettingsPanel)
        self._settings_visible = not self._settings_visible
        if self._settings_visible:
            panel.add_class("visible")
        else:
            panel.remove_class("visible")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle settings panel save/cancel buttons."""
        if event.button.id == "settings-save":
            await self._save_settings()
        elif event.button.id == "settings-cancel":
            self._settings_visible = False
            self.query_one("#settings-panel", SettingsPanel).remove_class("visible")

    async def _save_settings(self) -> None:
        """Read values from settings inputs and write to .codecompass.toml.

        If the model changed, reconnects the SDK client with the new model.
        """
        from codecompass.utils.config import write_config, config_path

        try:
            model = self.query_one("#settings-model", Input).value.strip()
            log_level = self.query_one("#settings-log-level", Input).value.strip().upper()
            tree_depth_str = self.query_one("#settings-tree-depth", Input).value.strip()
            max_size_str = self.query_one("#settings-max-file-size", Input).value.strip()

            tree_depth = int(tree_depth_str) if tree_depth_str else 4
            max_file_size_kb = int(max_size_str) if max_size_str else 512

            old_model = self._settings.model
            new_settings = Settings(
                model=model or "gpt-4.1",
                log_level=log_level or "WARNING",
                tree_depth=tree_depth,
                max_file_size_kb=max_file_size_kb,
            )
            target = config_path(self._repo_path)
            write_config(new_settings, target)

            # Update running settings
            self._settings = new_settings

            # Hide panel and confirm
            self._settings_visible = False
            self.query_one("#settings-panel", SettingsPanel).remove_class("visible")

            status = self.query_one("#status-bar", Static)
            messages = self.query_one("#messages", VerticalScroll)

            # Reconnect SDK if model changed
            model_changed = model and model != old_model
            if model_changed and self._compass_client:
                status.update(f"🔄 Switching model to {model}…")
                try:
                    await self._compass_client.stop()
                    self._compass_client._model = model
                    await self._compass_client.start()
                    sys_msg = (
                        self._agent.system_message("onboarding")
                        if self._agent
                        else None
                    )
                    await self._compass_client.create_session(
                        system_message=sys_msg,
                        streaming=True,
                    )
                    status.update(f"🧭 Connected (model: {model})")
                    await messages.mount(
                        ChatMessage(
                            f"🔄 Model switched to **{model}**. "
                            "Previous conversation context was reset.",
                            role="system",
                        )
                    )
                except Exception as exc:
                    status.update(f"⚠️ Model switch failed: {exc}")
                    await messages.mount(
                        ChatMessage(f"⚠️ Could not switch model: {exc}", role="system")
                    )
            else:
                status.update(f"✓ Settings saved to {target.name} (model: {model})")
                await messages.mount(
                    ChatMessage(
                        f"⚙️ Settings saved: model={model}, log_level={log_level}, "
                        f"tree_depth={tree_depth}, max_file_size_kb={max_file_size_kb}",
                        role="system",
                    )
                )

        except Exception as exc:
            status = self.query_one("#status-bar", Static)
            status.update(f"⚠️ Error saving settings: {exc}")

    # ── Cleanup ──────────────────────────────────────────────────────

    async def on_unmount(self) -> None:
        """Clean up SDK client on exit."""
        if self._compass_client:
            try:
                await self._compass_client.stop()
            except Exception:
                pass
