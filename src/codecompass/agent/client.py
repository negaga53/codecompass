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
        model: LLM model identifier (e.g., ``"gpt-4o"``, ``"gpt-4.1"``).
        git_ops: Optional ``GitOps`` instance for git-based tools.
        knowledge_graph: Optional ``KnowledgeGraph`` instance.
    """

    def __init__(
        self,
        repo_path: Path,
        *,
        model: str = "gpt-4o",
        git_ops: Any = None,
        knowledge_graph: Any = None,
    ) -> None:
        self._repo_path = repo_path
        self._model = model
        self._git_ops = git_ops
        self._knowledge_graph = knowledge_graph
        self._client: CopilotClient | None = None
        self._session: Any = None
        self._tools = build_tools(
            repo_path,
            git_ops=git_ops,
            knowledge_graph=knowledge_graph,
        )

    # ── lifecycle ────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the Copilot SDK client."""
        self._client = CopilotClient()
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

        config: dict[str, Any] = {
            "model": self._model,
            "streaming": streaming,
            "tools": self._tools,
        }
        if system_message:
            config["system_message"] = system_message

        self._session = await self._client.create_session(config)
        logger.info("Session created with model=%s, streaming=%s", self._model, streaming)
        return self._session

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

        done = asyncio.Event()
        response_parts: list[str] = []
        full_response: list[str] = []

        def on_event(event: Any) -> None:
            event_type = event.type.value if hasattr(event.type, "value") else str(event.type)

            if event_type == "assistant.message_delta":
                delta = event.data.delta_content or ""
                response_parts.append(delta)
                if on_delta and delta:
                    on_delta(delta)
            elif event_type == "assistant.message":
                full_response.append(event.data.content or "")
            elif event_type == "session.idle":
                done.set()

        self._session.on(on_event)

        await self._session.send({"prompt": prompt})
        await done.wait()

        # Prefer the full response if available, otherwise join deltas
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

        done = asyncio.Event()
        final_content: list[str] = []

        def on_event(event: Any) -> None:
            event_type = event.type.value if hasattr(event.type, "value") else str(event.type)

            if event_type == "assistant.message_delta":
                delta = event.data.delta_content or ""
                if delta:
                    on_delta(delta)
            elif event_type == "assistant.message":
                final_content.append(event.data.content or "")
            elif event_type == "session.idle":
                done.set()

        self._session.on(on_event)
        await self._session.send({"prompt": prompt})
        await done.wait()

        if on_done and final_content:
            on_done(final_content[-1])

    @property
    def has_session(self) -> bool:
        """Whether an active session exists."""
        return self._session is not None
