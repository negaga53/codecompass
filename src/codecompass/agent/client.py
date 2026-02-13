"""Copilot SDK client wrapper for CodeCompass.

This module manages the lifecycle of the Copilot SDK client and sessions,
integrating custom tools and system prompts for codebase intelligence.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

from copilot import CopilotClient  # type: ignore[import-untyped]

from codecompass.agent.tools import build_tools

logger = logging.getLogger(__name__)


class CompassClient:
    """High-level wrapper around the Copilot SDK client.

    Manages client lifecycle, session creation, and message streaming.

    Args:
        repo_path: Absolute path to the repository root.
        model: LLM model identifier (e.g., ``"gpt-4.1"``).
        git_ops: Optional ``GitOps`` instance for git-based tools.
        knowledge_graph: Optional ``KnowledgeGraph`` instance.
        github_client: Optional ``GitHubClient`` for PR/issue lookup.
        github_token: Optional GitHub token. If not provided, uses
            stored OAuth credentials from ``copilot login``.
    """

    def __init__(
        self,
        repo_path: Path,
        *,
        model: str = "gpt-4.1",
        git_ops: Any = None,
        knowledge_graph: Any = None,
        github_client: Any = None,
        github_token: str | None = None,
    ) -> None:
        self._repo_path = repo_path
        self._model = model
        self._git_ops = git_ops
        self._knowledge_graph = knowledge_graph
        self._github_client = github_client
        self._github_token = github_token
        self._client: CopilotClient | None = None
        self._session: Any = None
        self._active_request: dict[str, Any] | None = None
        self._request_lock = asyncio.Lock()
        self._tools = build_tools(
            repo_path,
            git_ops=git_ops,
            knowledge_graph=knowledge_graph,
            github_client=github_client,
        )

    # ── lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the Copilot SDK client.

        Uses the stored OAuth credentials from ``copilot login`` by default.
        If a *github_token* was provided via constructor, passes it to the
        CLI instead (note: PATs may not work with the Copilot API — device
        flow OAuth tokens are recommended).
        """
        opts: dict[str, Any] = {}
        if self._github_token:
            opts["github_token"] = self._github_token
            opts["use_logged_in_user"] = False
        else:
            opts["use_logged_in_user"] = True

        self._client = CopilotClient(opts if opts else None)
        await self._client.start()
        logger.info("Copilot SDK client started")

    async def stop(self) -> None:
        """Stop the Copilot SDK client and clean up."""
        if self._session is not None:
            try:
                await self._session.destroy()
            except Exception:
                pass
            self._session = None
        if self._client is not None:
            await self._client.stop()
            self._client = None
        logger.info("Copilot SDK client stopped")

    async def __aenter__(self) -> "CompassClient":
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    # ── session management ───────────────────────────────────────────

    async def create_session(
        self,
        *,
        system_message: dict[str, str] | None = None,
        streaming: bool = True,
    ) -> Any:
        """Create a new Copilot SDK session with CodeCompass tools.

        Args:
            system_message: Optional system message for the session.
            streaming: Whether to enable streaming responses.

        Returns:
            The SDK session object.
        """
        if self._client is None:
            raise RuntimeError("Client not started. Call start() first.")

        # Destroy existing session if any
        if self._session is not None:
            try:
                await self._session.destroy()
            except Exception:
                pass
            self._active_request = None

        config: dict[str, Any] = {
            "model": self._model,
            "streaming": streaming,
            "tools": self._tools,
        }
        if system_message:
            config["system_message"] = system_message

        self._session = await self._client.create_session(config)
        self._session.on(self._on_event)
        logger.info("Session created with model=%s, streaming=%s", self._model, streaming)
        return self._session

    def _on_event(self, event: Any) -> None:
        """Dispatch SDK events to the current in-flight request collector."""
        active = self._active_request
        if active is None:
            return

        event_type = event.type.value if hasattr(event.type, "value") else str(event.type)
        event_data = getattr(event, "data", None)

        if event_type == "assistant.message_delta":
            delta = getattr(event_data, "delta_content", "") or ""
            if delta:
                active["response_parts"].append(delta)
                cb = active.get("on_delta")
                if cb:
                    cb(delta)
            return

        if event_type == "assistant.message":
            content = getattr(event_data, "content", "") or ""
            active["full_response"].append(content)
            return

        if event_type == "session.error":
            error_msg = (
                getattr(event_data, "message", None)
                or getattr(event_data, "error", None)
                or "Unknown SDK session error"
            )
            active["error"] = str(error_msg)
            active["done"].set()
            return

        if event_type == "session.idle":
            active["done"].set()
            return

    # ── messaging ────────────────────────────────────────────────────

    async def send_and_collect(
        self,
        prompt: str,
        *,
        on_delta: Callable[[str], None] | None = None,
    ) -> str:
        """Send a message and collect the full response.

        Args:
            prompt: The user prompt to send.
            on_delta: Optional callback invoked with each streaming chunk.

        Returns:
            The complete assistant response text.
        """
        if self._session is None:
            raise RuntimeError("No active session. Call create_session() first.")
        async with self._request_lock:
            collector = {
                "done": asyncio.Event(),
                "response_parts": [],
                "full_response": [],
                "error": None,
                "on_delta": on_delta,
            }
            self._active_request = collector
            try:
                await self._session.send({"prompt": prompt})
                await asyncio.wait_for(collector["done"].wait(), timeout=60)
            except asyncio.TimeoutError as exc:
                raise RuntimeError("Timed out waiting for Copilot SDK response") from exc
            finally:
                self._active_request = None

            if collector["error"]:
                raise RuntimeError(f"Copilot SDK session error: {collector['error']}")

            full_response: list[str] = collector["full_response"]
            response_parts: list[str] = collector["response_parts"]
            if full_response:
                return full_response[-1]
            return "".join(response_parts)

    async def send_streaming(
        self,
        prompt: str,
        *,
        on_delta: Callable[[str], None],
        on_done: Callable[[str], None] | None = None,
    ) -> None:
        """Send a message and stream the response via callbacks.

        Args:
            prompt: The user prompt to send.
            on_delta: Callback for each streaming text chunk.
            on_done: Optional callback with the final complete response.
        """
        if self._session is None:
            raise RuntimeError("No active session. Call create_session() first.")
        async with self._request_lock:
            collector = {
                "done": asyncio.Event(),
                "response_parts": [],
                "full_response": [],
                "error": None,
                "on_delta": on_delta,
            }
            self._active_request = collector
            try:
                await self._session.send({"prompt": prompt})
                await asyncio.wait_for(collector["done"].wait(), timeout=60)
            except asyncio.TimeoutError as exc:
                raise RuntimeError("Timed out waiting for Copilot SDK response") from exc
            finally:
                self._active_request = None

            if collector["error"]:
                raise RuntimeError(f"Copilot SDK session error: {collector['error']}")

            final_content: list[str] = collector["full_response"]
            if on_done and final_content:
                on_done(final_content[-1])

    @property
    def has_session(self) -> bool:
        """Whether an active session exists."""
        return self._session is not None
