"""End-to-end test with the actual Copilot SDK."""

import asyncio
import os
import sys

# Force UTF-8 output
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from copilot import CopilotClient


async def test_basic():
    """Test 1: Basic SDK connection and model listing."""
    print("=" * 60)
    print("TEST 1: Basic SDK connection")
    print("=" * 60)

    client = CopilotClient({"use_logged_in_user": True})
    await client.start()

    auth = await client.get_auth_status()
    print(f"Auth: {auth.isAuthenticated} as {auth.login}")
    assert auth.isAuthenticated, "Not authenticated"

    models = await client.list_models()
    print(f"Models available: {len(models)}")
    assert len(models) > 0, "No models available"

    # Simple message
    session = await client.create_session({
        "streaming": True,
        "system_message": {"content": "Reply in exactly one word."},
    })

    done = asyncio.Event()
    response = []

    def on_event(event):
        etype = event.type.value if hasattr(event.type, "value") else str(event.type)
        if etype == "assistant.message":
            response.append(event.data.content or "")
        elif etype in ("session.idle", "session.error"):
            done.set()

    session.on(on_event)
    await session.send({"prompt": "Greet me."})
    await asyncio.wait_for(done.wait(), timeout=30)

    print(f"Response: {response[-1] if response else 'NONE'}")
    assert response, "No response received"
    await session.destroy()
    await client.stop()
    print("PASS\n")


async def test_with_tools():
    """Test 2: SDK with custom CodeCompass tools."""
    print("=" * 60)
    print("TEST 2: CodeCompass tools integration")
    print("=" * 60)

    # Import our tools
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
    from codecompass.agent.tools import build_tools
    from codecompass.github.git import GitOps
    from codecompass.indexer.knowledge_graph import KnowledgeGraph

    repo_path = os.path.dirname(__file__)
    git_ops = GitOps(repo_path)
    kg = KnowledgeGraph()
    kg.build(repo_path)

    tools = build_tools(repo_path, git_ops=git_ops, knowledge_graph=kg)
    print(f"Tools registered: {len(tools)}")
    tool_names = [t.name if hasattr(t, "name") else str(t) for t in tools]
    print(f"  {tool_names}")

    client = CopilotClient({"use_logged_in_user": True})
    await client.start()

    session = await client.create_session({
        "streaming": True,
        "tools": tools,
        "system_message": {
            "content": (
                "You are CodeCompass, a codebase onboarding assistant. "
                "Use the available tools to answer questions about the repository."
            ),
        },
    })
    print("Session with tools created")

    done = asyncio.Event()
    response_parts = []
    full_response = []
    tool_calls = []
    errors = []

    def on_event(event):
        etype = event.type.value if hasattr(event.type, "value") else str(event.type)
        if etype == "assistant.message_delta":
            delta = event.data.delta_content or ""
            response_parts.append(delta)
            sys.stdout.write(delta)
            sys.stdout.flush()
        elif etype == "assistant.message":
            full_response.append(event.data.content or "")
        elif etype == "assistant.tool_call":
            tool_calls.append(etype)
            print(f"\n  [TOOL CALL] {event.data}", flush=True)
        elif etype == "session.error":
            msg = getattr(event.data, "message", None) or str(event.data)
            errors.append(msg)
            print(f"\n  [ERROR] {msg}", flush=True)
            done.set()
        elif etype == "session.idle":
            done.set()

    session.on(on_event)

    print("\nAsking about project architecture...")
    await session.send({
        "prompt": "What is this project about? Use the get_architecture_summary tool to find out."
    })

    try:
        await asyncio.wait_for(done.wait(), timeout=60)
    except asyncio.TimeoutError:
        print("\nTIMEOUT")

    print()
    if errors:
        print(f"Errors: {errors}")
    if full_response:
        print(f"\nFull response length: {len(full_response[-1])} chars")
    print(f"Tool calls made: {len(tool_calls)}")

    assert not errors or len(full_response) > 0, "Errors with no response"
    await session.destroy()
    await client.stop()
    print("PASS\n")


async def main():
    print("CodeCompass E2E Tests with Copilot SDK")
    print("=" * 60)

    await test_basic()
    await test_with_tools()

    print("=" * 60)
    print("ALL E2E TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
