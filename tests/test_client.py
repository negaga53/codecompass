"""Tests for CompassClient session/event handling."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from codecompass.agent.client import CompassClient


class _FakeSession:
    def __init__(self, sequences: list[list[object]]) -> None:
        self._handler = None
        self._sequences = sequences

    def on(self, handler) -> None:
        self._handler = handler

    async def send(self, _payload) -> None:
        events = self._sequences.pop(0)
        for event in events:
            self._handler(event)


class _Event:
    def __init__(self, event_type: str, **data) -> None:
        self.type = SimpleNamespace(value=event_type)
        self.data = SimpleNamespace(**data)


def _build_client_with_session(session: _FakeSession) -> CompassClient:
    client = object.__new__(CompassClient)
    client._session = session
    client._active_request = None
    client._request_lock = asyncio.Lock()
    session.on(client._on_event)
    return client


def test_send_and_collect_reuses_single_handler_without_duplication() -> None:
    session = _FakeSession(
        [
            [
                _Event("assistant.message_delta", delta_content="hello "),
                _Event("assistant.message", content="hello world"),
                _Event("session.idle"),
            ],
            [
                _Event("assistant.message_delta", delta_content="second "),
                _Event("assistant.message", content="second reply"),
                _Event("session.idle"),
            ],
        ]
    )
    client = _build_client_with_session(session)

    deltas: list[str] = []

    first = asyncio.run(client.send_and_collect("q1", on_delta=deltas.append))
    second = asyncio.run(client.send_and_collect("q2", on_delta=deltas.append))

    assert first == "hello world"
    assert second == "second reply"
    assert deltas == ["hello ", "second "]


def test_send_and_collect_raises_on_session_error() -> None:
    session = _FakeSession(
        [[_Event("session.error", message="boom"), _Event("session.idle")]]
    )
    client = _build_client_with_session(session)

    try:
        asyncio.run(client.send_and_collect("q"))
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "session error" in str(exc).lower()
        assert "boom" in str(exc)


def test_send_streaming_calls_on_done() -> None:
    session = _FakeSession(
        [[
            _Event("assistant.message_delta", delta_content="A"),
            _Event("assistant.message_delta", delta_content="B"),
            _Event("assistant.message", content="AB"),
            _Event("session.idle"),
        ]]
    )
    client = _build_client_with_session(session)

    seen: list[str] = []
    done: list[str] = []

    asyncio.run(client.send_streaming("q", on_delta=seen.append, on_done=done.append))

    assert seen == ["A", "B"]
    assert done == ["AB"]


def test_has_session_property_reflects_state() -> None:
    client = object.__new__(CompassClient)
    client._session = None
    assert client.has_session is False

    client._session = object()
    assert client.has_session is True


def test_send_and_collect_raises_without_session() -> None:
    client = object.__new__(CompassClient)
    client._session = None
    client._active_request = None
    client._request_lock = asyncio.Lock()

    try:
        asyncio.run(client.send_and_collect("q"))
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "no active session" in str(exc).lower()


def test_send_and_collect_timeout_path() -> None:
    session = _FakeSession([[ ]])
    client = _build_client_with_session(session)

    async def _raise_timeout(_awaitable, timeout):
        _awaitable.close()
        raise asyncio.TimeoutError()

    with patch("codecompass.agent.client.asyncio.wait_for", side_effect=_raise_timeout):
        try:
            asyncio.run(client.send_and_collect("q"))
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "timed out" in str(exc).lower()
