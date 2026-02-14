"""CLI entry point for CodeCompass (Click-based).

Commands:
    onboard       Scan a repo and display an AI-powered onboarding summary
    ask           Ask a natural-language question about the codebase
    why           Ask WHY something exists in the codebase
    architecture  Explore the repo's architecture
    contributors  Show contributor intelligence
    audit         Audit documentation freshness
    chat          Interactive multi-turn chat
    tui           Launch the interactive terminal UI
    config        Manage CodeCompass configuration (incl. set-model)
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from codecompass import __version__
from codecompass.utils.config import Settings

console = Console()


_FALLBACK_MODELS: list[tuple[str, str]] = [
    ("claude-sonnet-4", "1x"),
    ("claude-haiku-4.5", "0.33x"),
    ("gpt-4.1", "0x"),
    ("gpt-5-mini", "0x"),
    ("gpt-5.1", "1x"),
    ("gpt-5.1-codex", "1x"),
    ("gpt-5.2-codex", "1x"),
    ("o4-mini", "0.33x"),
]


_PREMIUM_USAGE: dict[str, tuple[str, str]] = {
    "ask": ("yes", "Sends prompt to Copilot model via SDK session"),
    "why": ("yes", "Sends prompt to Copilot model via SDK session"),
    "architecture": ("yes", "Runs architecture prompt through Copilot model"),
    "audit": ("yes", "Runs docs-audit prompt through Copilot model"),
    "chat": ("yes", "Interactive multi-turn model conversation"),
    "diff-explain": ("yes", "Analyzes commit diffs with Copilot model"),
    "tui": ("yes", "Chat interactions in TUI use Copilot model"),
    "onboard --interactive": ("conditional", "Onboarding scan is local; interactive chat uses Copilot model"),
    "onboard (AI summary)": ("yes", "Streams an AI-generated narrative onboarding summary"),
}


def _confirm_ai_action(settings: Settings, command_name: str, *, skip_confirm: bool = False) -> bool:
    """Show model/cost info and ask the user to confirm before an AI call.

    Returns ``True`` if the user confirms (or the model is free / ``skip_confirm``).
    Returns ``False`` to abort.
    """
    rate = _get_model_rate(settings.model)
    entry = _PREMIUM_USAGE.get(command_name)
    detail = entry[1] if entry else ""

    if rate == "0x":
        console.print(
            f"[dim]Model:[/] [cyan]{settings.model}[/] (free) — {detail}"
        )
        return True

    console.print(
        f"[yellow]💎 Premium request:[/] [cyan]{settings.model}[/] "
        f"({rate} per request) — {detail}"
    )

    if skip_confirm:
        return True

    return click.confirm("Continue?", default=True)


# Cached model list to avoid redundant SDK calls within a single CLI invocation
_MODEL_CACHE: list[tuple[str, str]] | None = None


def _get_model_rate(model: str) -> str:
    """Return the premium rate string for a model (e.g. ``\"0x\"``, ``\"1x\"``)."""
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        _MODEL_CACHE = _available_models_with_premium()
    for name, rate in _MODEL_CACHE:
        if name == model:
            return rate
    return "unknown"


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.WARNING),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _format_premium_rate(raw: object) -> str:
    """Format a premium request multiplier from the SDK into a display string.

    Handles numeric multipliers (0, 0.33, 1, …), booleans, and strings.
    Returns a string like ``"0x"``, ``"1x"``, ``"0.33x"``.
    """
    if isinstance(raw, (int, float)):
        if raw == 0:
            return "0x"
        if raw == int(raw):
            return f"{int(raw)}x"
        return f"{raw:g}x"
    if raw is True:
        return "1x"
    if raw is False:
        return "0x"
    if isinstance(raw, str):
        val = raw.strip().lower()
        # Try parsing as a number (e.g. "0.33")
        try:
            num = float(val.rstrip("x"))
            if num == 0:
                return "0x"
            if num == int(num):
                return f"{int(num)}x"
            return f"{num:g}x"
        except ValueError:
            pass
        if val in {"yes", "true", "premium", "paid"}:
            return "1x"
        if val in {"no", "false", "free"}:
            return "0x"
    return "unknown"


def _extract_premium_multiplier(item: object) -> object:
    """Walk an SDK model object to find the premium request multiplier.

    The Copilot SDK returns ``ModelInfo`` objects with a ``billing``
    attribute that contains the ``multiplier`` (e.g. 0.0, 0.33, 1.0).

    Checks common attribute/key paths (in priority order):
    - ``item.billing.multiplier``
    - ``item["billing"]["multiplier"]``
    - ``item.policy.premium_request_multiplier``
    - Legacy: ``item.premium``, ``item.is_premium``, etc.
    """
    # ── billing.multiplier (current SDK) ─────────────────────────────
    if isinstance(item, dict):
        billing = item.get("billing")
        if isinstance(billing, dict):
            val = billing.get("multiplier")
            if val is not None:
                return val
        policy = item.get("policy")
        if isinstance(policy, dict):
            val = policy.get("premium_request_multiplier") or policy.get("premiumRequestMultiplier")
            if val is not None:
                return val
        for key in ("premium_request_multiplier", "premiumRequestMultiplier",
                    "multiplier", "premium", "is_premium",
                    "uses_premium_requests", "premium_usage"):
            val = item.get(key)
            if val is not None:
                return val
    else:
        billing = getattr(item, "billing", None)
        if billing is not None:
            val = getattr(billing, "multiplier", None)
            if val is not None:
                return val
        policy = getattr(item, "policy", None)
        if policy is not None:
            val = getattr(policy, "premium_request_multiplier", None) or getattr(
                policy, "premiumRequestMultiplier", None
            )
            if val is not None:
                return val
        for attr in ("premium_request_multiplier", "premiumRequestMultiplier",
                     "multiplier", "premium", "is_premium",
                     "uses_premium_requests", "premium_usage"):
            val = getattr(item, attr, None)
            if val is not None:
                return val
    return None


def _available_models_with_premium() -> list[tuple[str, str]]:
    """Best-effort model list from Copilot SDK with premium metadata.

    Returns a list of ``(model_id, premium_rate)`` tuples where
    *premium_rate* is a display string like ``"0x"``, ``"1x"``, etc.

    Falls back to hardcoded data if SDK model listing is unavailable.
    """

    async def _fetch() -> list[tuple[str, str]]:
        from copilot import CopilotClient  # type: ignore[import-untyped]

        client = CopilotClient()
        await client.start()
        try:
            list_fn = getattr(client, "list_models", None) or getattr(client, "listModels", None)
            if not callable(list_fn):
                return _FALLBACK_MODELS

            raw_models = await list_fn()
        finally:
            await client.stop()

        parsed: list[tuple[str, str]] = []
        for item in raw_models or []:
            if isinstance(item, dict):
                model_id = item.get("id") or item.get("model") or item.get("name")
            else:
                model_id = (
                    getattr(item, "id", None)
                    or getattr(item, "model", None)
                    or getattr(item, "name", None)
                )

            premium_raw = _extract_premium_multiplier(item)

            if model_id:
                parsed.append((str(model_id), _format_premium_rate(premium_raw)))

        return parsed or _FALLBACK_MODELS

    try:
        return asyncio.run(_fetch())
    except Exception:
        return _FALLBACK_MODELS


def _github_token_status(settings: Settings) -> tuple[bool, str]:
    """Return ``(is_set, description)`` for the GitHub token status."""
    token = settings.github_token
    if token:
        masked = token[:4] + "…" + token[-4:] if len(token) > 8 else "****"
        return True, f"configured ({masked})"
    # Check environment variable directly as a hint
    import os
    if os.environ.get("GITHUB_TOKEN"):
        return True, "set via GITHUB_TOKEN env var"
    return False, "not set"


def _init_git(repo_path: Path):
    """Create a GitOps instance (returns None if not a git repo)."""
    from codecompass.github.git import GitOps, GitOpsError

    try:
        return GitOps(repo_path)
    except GitOpsError:
        return None


def _init_github_client(git_ops, settings: Settings):
    """Create a GitHubClient from the repo remote URL, if possible."""
    if git_ops is None:
        return None
    try:
        import re
        from codecompass.github.client import GitHubClient

        url = git_ops.remote_url()
        if not url:
            return None
        m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url)
        if not m:
            return None
        return GitHubClient(m.group(1), m.group(2), token=settings.github_token)
    except Exception:
        return None


async def _run_with_sdk(
    repo_path: Path,
    settings: Settings,
    system_message: dict[str, str],
    prompt: str,
    *,
    status_msg: str = "Thinking…",
) -> None:
    """Send a prompt to the Copilot SDK and stream the response.

    Shows a Rich spinner while waiting for the first token, then
    streams output to stdout.  Catches timeouts gracefully.
    """
    from codecompass.agent.client import CompassClient
    from codecompass.indexer.knowledge_graph import KnowledgeGraph

    git_ops = _init_git(repo_path)

    kg = KnowledgeGraph()
    try:
        kg.build(repo_path)
    except Exception:
        kg = None

    gh_client = _init_github_client(git_ops, settings)

    async with CompassClient(
        repo_path,
        model=settings.model,
        git_ops=git_ops,
        knowledge_graph=kg,
        github_client=gh_client,
    ) as client:
        await client.create_session(
            system_message=system_message,
            streaming=True,
        )

        first_token = True
        status = console.status(f"[bold cyan]{status_msg}[/]")
        status.start()

        def on_delta(delta: str) -> None:
            nonlocal first_token
            if first_token:
                status.stop()
                console.print()
                first_token = False
            sys.stdout.write(delta)
            sys.stdout.flush()

        try:
            await client.send_and_collect(prompt, on_delta=on_delta)
        except RuntimeError as exc:
            status.stop()
            if "timed out" in str(exc).lower() or "timeout" in str(exc).lower():
                console.print(
                    "\n[yellow]⚠ The Copilot model timed out.[/] "
                    "Try again or use a different model."
                )
                return
            raise
        finally:
            if first_token:
                status.stop()

        console.print("\n")


async def _interactive_session(
    repo_path: Path,
    settings: Settings,
    system_message: dict[str, str],
) -> None:
    """Run an interactive multi-turn chat session with the Copilot SDK."""
    from codecompass.agent.client import CompassClient
    from codecompass.indexer.knowledge_graph import KnowledgeGraph

    git_ops = _init_git(repo_path)

    kg = KnowledgeGraph()
    try:
        kg.build(repo_path)
    except Exception:
        kg = None

    gh_client = _init_github_client(git_ops, settings)

    async with CompassClient(
        repo_path,
        model=settings.model,
        git_ops=git_ops,
        knowledge_graph=kg,
        github_client=gh_client,
    ) as client:
        await client.create_session(
            system_message=system_message,
            streaming=True,
        )

        console.print(
            "\n[bold cyan]🧭 CodeCompass[/] — Interactive mode "
            f"[dim](model: {settings.model})[/]\n"
            "[dim]Commands: /model <name> to switch model, "
            "/models to list, exit to quit[/]\n"
        )

        # Show GitHub token status
        token_ok, token_desc = _github_token_status(settings)
        token_style = "green" if token_ok else "red"
        token_icon = "✓" if token_ok else "✗"
        console.print(
            f"  GitHub token: [{token_style}]{token_icon} {token_desc}[/]\n"
        )

        current_model = settings.model

        while True:
            try:
                question = console.input("[bold green]You:[/] ")
            except (EOFError, KeyboardInterrupt):
                break

            stripped = question.strip()
            if stripped.lower() in ("exit", "quit", "q"):
                break
            if not stripped:
                continue

            # Slash commands
            if stripped.lower() == "/models":
                models = _available_models_with_premium()
                model_text = ", ".join(
                    f"{name} ({rate})" if rate != "0x" else f"{name} (free)"
                    for name, rate in models
                )
                console.print(f"\n[bold]Available models:[/] {model_text}")
                console.print(f"[dim]Current: {current_model}[/]\n")
                continue

            if stripped.lower().startswith("/model "):
                new_model = stripped[7:].strip()
                if not new_model:
                    console.print(f"[dim]Current model: {current_model}[/]")
                    continue
                # Recreate the client with the new model
                console.print(f"[dim]Switching to {new_model}…[/]")
                await client.stop()
                client._model = new_model
                current_model = new_model
                await client.start()
                await client.create_session(
                    system_message=system_message,
                    streaming=True,
                )
                console.print(f"[green]✓ Now using {new_model}[/]\n")
                continue

            console.print("[bold blue]CodeCompass:[/] ", end="")

            def on_delta(delta: str) -> None:
                sys.stdout.write(delta)
                sys.stdout.flush()

            await client.send_and_collect(question, on_delta=on_delta)
            console.print("\n")

        console.print("\n[dim]Goodbye![/]\n")


# ── Main CLI group ───────────────────────────────────────────────────


@click.group(invoke_without_command=True)
@click.option("--repo", "-r", default=".", help="Path to the repository to analyze.")
@click.option("--log-level", "-l", default=None, help="Logging level.")
@click.option("--model", "-m", default=None, help="LLM model to use (e.g., gpt-4o, gpt-4.1).")
@click.version_option(__version__, prog_name="codecompass")
@click.pass_context
def main(ctx: click.Context, repo: str, log_level: str | None, model: str | None) -> None:
    """🧭 CodeCompass — AI-powered codebase intelligence and onboarding assistant."""
    overrides: dict[str, str] = {}
    if log_level:
        overrides["log_level"] = log_level
    if model:
        overrides["model"] = model
    overrides["repo_path"] = repo

    settings = Settings.load(overrides, base_path=repo)
    _configure_logging(settings.log_level)

    ctx.ensure_object(dict)
    ctx.obj["settings"] = settings
    ctx.obj["repo_path"] = Path(repo).resolve()

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        # Show quick status summary
        token_ok, token_desc = _github_token_status(settings)
        token_icon = "✓" if token_ok else "✗"
        console.print(
            f"\n  GitHub token: [{('green' if token_ok else 'red')}]{token_icon} {token_desc}[/]"
            f"  |  Model: [cyan]{settings.model}[/]"
        )


# ── onboard ──────────────────────────────────────────────────────────


@main.command()
@click.option(
    "--interactive", "-i", is_flag=True,
    help="Start an interactive Q&A session after displaying the summary.",
)
@click.option(
    "--output", "-o", "output_path",
    default=None,
    help="Export the onboarding summary to a file (default: stdout only).",
)
@click.option(
    "--format", "-f", "fmt",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    help="Export format when using --output.",
)
@click.option("--ai/--no-ai", "run_ai", default=None,
              help="Generate (or skip) an AI narrative summary. Prompts if omitted.")
@click.option("--yes", "-y", "skip_confirm", is_flag=True,
              help="Skip confirmation prompts.")
@click.pass_context
def onboard(
    ctx: click.Context,
    interactive: bool,
    output_path: str | None,
    fmt: str,
    run_ai: bool | None,
    skip_confirm: bool,
) -> None:
    """Scan a repository and display an AI-powered onboarding summary.

    The repo is scanned locally (no premium requests consumed) and the
    results are displayed as a rich panel.  Optionally, an AI-generated
    narrative is streamed from the Copilot model.

    Use --output to export the summary to a file (markdown or JSON).

    \b
    💎 The AI summary and --interactive mode may consume Copilot
       premium requests depending on the selected model.
    """
    from codecompass.agent.agent import CodeCompassAgent
    from codecompass.utils.formatting import print_onboarding_summary

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]

    with console.status("[bold cyan]Scanning repository…[/]"):
        agent = CodeCompassAgent(repo_path, settings=settings)
        summary = asyncio.run(agent.onboard())
    print_onboarding_summary(summary)

    # --- AI-generated narrative summary --------------------------------
    want_ai = run_ai  # True, False, or None (ask)
    if want_ai is None:
        want_ai = click.confirm(
            "\nGenerate an AI-powered onboarding summary?", default=True
        )

    if want_ai:
        if not _confirm_ai_action(settings, "onboard (AI summary)", skip_confirm=skip_confirm):
            console.print("[dim]Skipped.[/]")
        else:
            ai_prompt = (
                "Based on the repository context you have, write a concise "
                "but insightful onboarding summary for a new developer joining "
                "this project. Cover: purpose, architecture highlights, key "
                "entry points, how to get started, and anything surprising or "
                "noteworthy. Be specific — reference actual file names and modules."
            )
            sys_msg = agent.system_message("onboarding")
            try:
                asyncio.run(
                    _run_with_sdk(
                        repo_path, settings, sys_msg, ai_prompt,
                        status_msg="Generating AI summary…",
                    )
                )
            except Exception as exc:
                console.print(f"[yellow]⚠ AI summary unavailable:[/] {exc}")

    # --- Export --------------------------------------------------------
    if output_path:
        _export_onboarding(agent, summary, output_path, fmt)

    # --- Interactive mode ----------------------------------------------
    if interactive:
        if not _confirm_ai_action(settings, "onboard --interactive", skip_confirm=skip_confirm):
            return
        sys_msg = agent.system_message("onboarding")
        asyncio.run(_interactive_session(repo_path, settings, sys_msg))


# ── ask ──────────────────────────────────────────────────────────────


@main.command()
@click.argument("question", required=False, default=None)
@click.option("--yes", "-y", "skip_confirm", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def ask(ctx: click.Context, question: str | None, skip_confirm: bool) -> None:
    """Ask a natural-language question about the codebase.

    If QUESTION is omitted you will be prompted for it interactively.

    \b
    💎 This command sends a prompt to the Copilot model and may
       consume premium requests depending on the selected model.
    """
    from codecompass.agent.agent import CodeCompassAgent

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]

    if not question:
        question = click.prompt("Your question")
        if not question.strip():
            console.print("[yellow]No question provided.[/]")
            return

    if not _confirm_ai_action(settings, "ask", skip_confirm=skip_confirm):
        return

    with console.status("[bold cyan]Analyzing codebase…[/]"):
        agent = CodeCompassAgent(repo_path, settings=settings)
        payload = asyncio.run(agent.ask(question))

    asyncio.run(
        _run_with_sdk(repo_path, settings, payload["system_message"], question,
                      status_msg="Thinking…")
    )


# ── why ──────────────────────────────────────────────────────────────


@main.command()
@click.argument("question", required=False, default=None)
@click.option("--yes", "-y", "skip_confirm", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def why(ctx: click.Context, question: str | None, skip_confirm: bool) -> None:
    """Ask WHY a decision was made or why something exists in the codebase.

    If QUESTION is omitted you will be prompted for it interactively.

    \b
    💎 This command sends a prompt to the Copilot model and may
       consume premium requests depending on the selected model.
    """
    from codecompass.agent.agent import CodeCompassAgent, AgentMode

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]

    if not question:
        question = click.prompt("Your question")
        if not question.strip():
            console.print("[yellow]No question provided.[/]")
            return

    if not _confirm_ai_action(settings, "why", skip_confirm=skip_confirm):
        return

    with console.status("[bold cyan]Analyzing codebase…[/]"):
        agent = CodeCompassAgent(repo_path, settings=settings)
        sys_msg = agent.system_message(AgentMode.WHY)

    asyncio.run(_run_with_sdk(repo_path, settings, sys_msg, question,
                              status_msg="Thinking…"))


# ── architecture ─────────────────────────────────────────────────────


@main.command()
@click.option("--yes", "-y", "skip_confirm", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def architecture(ctx: click.Context, skip_confirm: bool) -> None:
    """Explore the architecture of the repository with AI analysis.

    Scans the codebase and asks the Copilot model to reason about
    the project's architecture, patterns, and design decisions.

    \b
    💎 This command sends a prompt to the Copilot model and may
       consume premium requests depending on the selected model.
    """
    from codecompass.agent.agent import CodeCompassAgent

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]

    if not _confirm_ai_action(settings, "architecture", skip_confirm=skip_confirm):
        return

    with console.status("[bold cyan]Scanning repository architecture…[/]"):
        agent = CodeCompassAgent(repo_path, settings=settings)
        payload = asyncio.run(agent.explore_architecture())

    asyncio.run(
        _run_with_sdk(
            repo_path,
            settings,
            payload["system_message"],
            payload["user_message"]["content"],
            status_msg="Analyzing architecture…",
        )
    )


# ── contributors ─────────────────────────────────────────────────────


@main.command()
@click.pass_context
def contributors(ctx: click.Context) -> None:
    """Show contributor intelligence for the repository."""
    from codecompass.github.git import GitOps, GitOpsError
    from codecompass.utils.formatting import print_markdown

    repo_path: Path = ctx.obj["repo_path"]

    try:
        git = GitOps(repo_path)
    except GitOpsError as exc:
        console.print(f"[red]Error:[/] {exc}")
        return

    contributor_list = git.contributors()
    if not contributor_list:
        console.print("[yellow]No contributors found.[/]")
        return

    lines = ["# Contributors\n", "| Name | Commits | Email |", "|------|---------|-------|"]
    for c in contributor_list:
        lines.append(f"| {c['name']} | {c['commits']} | {c.get('email', '')} |")

    console.print()
    print_markdown("\n".join(lines))
    console.print()


# ── audit ────────────────────────────────────────────────────────────


@main.command()
@click.option("--yes", "-y", "skip_confirm", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def audit(ctx: click.Context, skip_confirm: bool) -> None:
    """Audit repository documentation for staleness using AI.

    Scans docs and source files, then uses the Copilot model to
    identify stale, missing, or inconsistent documentation.

    \b
    💎 This command sends a prompt to the Copilot model and may
       consume premium requests depending on the selected model.
    """
    from codecompass.agent.agent import CodeCompassAgent

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]

    if not _confirm_ai_action(settings, "audit", skip_confirm=skip_confirm):
        return

    with console.status("[bold cyan]Scanning documentation…[/]"):
        agent = CodeCompassAgent(repo_path, settings=settings)
        payload = asyncio.run(agent.audit_docs())

    asyncio.run(
        _run_with_sdk(
            repo_path,
            settings,
            payload["system_message"],
            payload["user_message"]["content"],
            status_msg="Auditing docs…",
        )
    )


# ── chat ─────────────────────────────────────────────────────────────


@main.command()
@click.option("--yes", "-y", "skip_confirm", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def chat(ctx: click.Context, skip_confirm: bool) -> None:
    """Start an interactive multi-turn chat about the codebase.

    Scans the repo first, then enters a continuous conversation loop
    with the Copilot model.

    \b
    💎 Each message in the chat consumes Copilot premium requests
       depending on the selected model.
    """
    from codecompass.agent.agent import CodeCompassAgent
    from codecompass.utils.formatting import print_onboarding_summary

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]

    if not _confirm_ai_action(settings, "chat", skip_confirm=skip_confirm):
        return

    with console.status("[bold cyan]Scanning repository…[/]"):
        agent = CodeCompassAgent(repo_path, settings=settings)
        summary = asyncio.run(agent.onboard())
    print_onboarding_summary(summary)

    sys_msg = agent.system_message("onboarding")
    asyncio.run(_interactive_session(repo_path, settings, sys_msg))


# ── graph ────────────────────────────────────────────────────────────


@main.command()
@click.option(
    "--output", "-o", "output_path",
    default=None,
    help="Output file path for the Mermaid diagram (default: stdout).",
)
@click.option(
    "--format", "-f", "fmt",
    type=click.Choice(["mermaid", "text"]),
    default="mermaid",
    help="Output format (mermaid or plain text).",
)
@click.pass_context
def graph(ctx: click.Context, output_path: str | None, fmt: str) -> None:
    """Generate a visual dependency graph of the codebase.

    Outputs a Mermaid flowchart diagram showing module dependencies,
    import relationships, and architectural layers using AST analysis
    of the indexed codebase.

    Example:
        codecompass graph -o deps.md
        codecompass graph -f text
    """
    from codecompass.indexer.knowledge_graph import KnowledgeGraph

    repo_path: Path = ctx.obj["repo_path"]

    kg = KnowledgeGraph()
    kg.build(repo_path)

    # Identify project modules (exclude stdlib, third-party, tests)
    all_mods = kg.all_modules()

    # Detect the project package name from the repo
    # (first dotted module that has sub-modules)
    project_root_pkg = None
    for m in all_mods:
        parts = m.split(".")
        if len(parts) >= 2:
            candidate = parts[0]
            # Check if multiple modules share this prefix
            count = sum(1 for x in all_mods if x.startswith(candidate + "."))
            if count >= 3:
                project_root_pkg = candidate
                break

    if not project_root_pkg:
        console.print("[yellow]Could not detect project package. Showing all modules.[/]")
        project_root_pkg = ""

    project_mods = sorted(set(
        m for m in all_mods
        if m.startswith(project_root_pkg) and not m.startswith(("tests.", "e2e_"))
    ))

    if fmt == "text":
        lines = ["# Module Dependency Graph", ""]
        project_mod_set = set(project_mods)
        for mod in project_mods:
            deps = kg.dependencies(mod)
            internal_deps = sorted(d for d in deps if d in project_mod_set)
            if internal_deps:
                lines.append(f"{mod}:")
                for d in internal_deps:
                    lines.append(f"  → {d}")
                lines.append("")
        output = "\n".join(lines)
    else:
        # Mermaid flowchart
        lines = ["```mermaid", "flowchart TD"]

        # Create sanitized IDs for Mermaid
        def _mid(m: str) -> str:
            return m.replace(".", "_")

        # Detect layers by package
        layers: dict[str, list[str]] = {}
        for mod in project_mods:
            parts = mod.split(".")
            if len(parts) >= 2:
                layer = ".".join(parts[:2])
            else:
                layer = parts[0]
            layers.setdefault(layer, []).append(mod)

        # Add subgraphs for each layer
        for layer, mods in sorted(layers.items()):
            label = layer.split(".")[-1].title()
            lines.append(f"    subgraph {label}")
            for mod in mods:
                short = mod.split(".")[-1]
                lines.append(f"        {_mid(mod)}[{short}]")
            lines.append("    end")

        # Add edges (only internal project deps)
        project_mod_set = set(project_mods)
        for mod in project_mods:
            deps = kg.dependencies(mod)
            for dep in sorted(deps):
                if dep in project_mod_set:
                    lines.append(f"    {_mid(mod)} --> {_mid(dep)}")

        lines.append("```")
        output = "\n".join(lines)

    if output_path:
        Path(output_path).write_text(output, encoding="utf-8")
        console.print(f"[green]Dependency graph written to {output_path}[/]")
    else:
        click.echo(output)


# ── diff-explain ─────────────────────────────────────────────────────


@main.command(name="diff-explain")
@click.option("--commits", "-n", default=None, type=int, help="Number of recent commits to analyze (prompts if omitted).")
@click.option("--yes", "-y", "skip_confirm", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def diff_explain(ctx: click.Context, commits: int | None, skip_confirm: bool) -> None:
    """AI-powered explanation of recent changes.

    Analyzes the last N commits using git diff, then uses the Copilot
    SDK to generate a human-readable summary explaining WHAT changed,
    WHY (based on commit messages and code context), and what a new
    developer should know about these changes.

    \b
    💎 This command sends a prompt to the Copilot model and may
       consume premium requests depending on the selected model.
    """
    from codecompass.agent.agent import CodeCompassAgent
    from codecompass.github.git import GitOps, GitOpsError

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]

    if commits is None:
        commits = click.prompt("How many recent commits to analyze?", default=5, type=int)

    if not _confirm_ai_action(settings, "diff-explain", skip_confirm=skip_confirm):
        return

    try:
        git = GitOps(repo_path)
    except GitOpsError as exc:
        console.print(f"[red]Error:[/] {exc}")
        return

    # Gather recent commits
    with console.status(f"[bold cyan]Gathering last {commits} commits…[/]"):
        log = git.log(max_count=commits)
    if not log:
        console.print("[yellow]No commits found.[/]")
        return

    # Build context from commits + diffs
    context_parts = ["## Recent Changes\n"]
    for entry in log:
        context_parts.append(
            f"### Commit `{entry['short_hash']}` — {entry['message']}\n"
            f"- **Author:** {entry['author']}\n"
            f"- **Date:** {entry['date']}\n"
        )
        try:
            diff = git.diff(f"{entry['hash']}~1", entry['hash'])
            if diff:
                # Truncate very long diffs
                if len(diff) > 2000:
                    diff = diff[:2000] + "\n... (truncated)"
                context_parts.append(f"```diff\n{diff}\n```\n")
        except Exception:
            context_parts.append("_(diff not available)_\n")

    diff_context = "\n".join(context_parts)

    prompt = (
        "Analyze these recent code changes and provide:\n"
        "1. A high-level summary of what changed\n"
        "2. WHY these changes were likely made (based on commit messages and code)\n"
        "3. Impact assessment — what parts of the system were affected\n"
        "4. What a new developer should understand about these changes\n\n"
        f"{diff_context}"
    )

    agent = CodeCompassAgent(repo_path, settings=settings)
    sys_msg = agent.system_message("onboarding")

    asyncio.run(_run_with_sdk(repo_path, settings, sys_msg, prompt,
                              status_msg="Analyzing changes…"))


# ── tui ──────────────────────────────────────────────────────────────


@main.command()
@click.option("--yes", "-y", "skip_confirm", is_flag=True, help="Skip confirmation prompt.")
@click.pass_context
def tui(ctx: click.Context, skip_confirm: bool) -> None:
    """Launch the interactive Textual TUI.

    Opens a full-screen terminal interface for browsing the codebase,
    chatting with the AI, and exploring architecture.

    \b
    💎 Chat interactions in the TUI use the Copilot model and may
       consume premium requests depending on the selected model.
    """
    from codecompass.ui.app import CodeCompassApp

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]

    if not _confirm_ai_action(settings, "tui", skip_confirm=skip_confirm):
        return

    app = CodeCompassApp(repo_path=repo_path, settings=settings)
    app.run()


# ── config ───────────────────────────────────────────────────────────


@main.group()
@click.pass_context
def config(ctx: click.Context) -> None:
    """Manage CodeCompass configuration.

    View, create, and edit `.codecompass.toml` settings files.
    """
    pass


@config.command(name="init")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing config file.")
@click.option("--global", "global_scope", is_flag=True, help="Write to global user config instead of repo config.")
@click.pass_context
def config_init(ctx: click.Context, force: bool, global_scope: bool) -> None:
    """Generate a .codecompass.toml configuration file with sensible defaults.

    Interactively prompts for key settings (model, log level, etc.)
    and writes them to .codecompass.toml in the current directory.
    """
    from codecompass.utils.config import config_path, global_config_path, write_config

    repo_path: Path = ctx.obj["repo_path"]
    target = global_config_path() if global_scope else config_path(repo_path)

    if target.is_file() and not force:
        console.print(
            f"[yellow]Config already exists:[/] {target}\n"
            "Use [bold]--force[/] to overwrite."
        )
        return

    # Interactive prompts with defaults
    model = click.prompt("LLM model", default="gpt-4.1")
    log_level = click.prompt(
        "Log level",
        default="WARNING",
        type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    )
    tree_depth = click.prompt("Directory tree depth", default=4, type=int)
    max_file_size_kb = click.prompt("Max file size (KB)", default=512, type=int)

    settings = Settings(
        model=model,
        log_level=log_level.upper(),
        tree_depth=tree_depth,
        max_file_size_kb=max_file_size_kb,
    )
    write_config(settings, target)
    console.print(f"\n[green]✓[/] Config written to [bold]{target}[/]")


@config.command(name="show")
@click.option("--global", "global_scope", is_flag=True, help="Show only the global user config file values.")
@click.pass_context
def config_show(ctx: click.Context, global_scope: bool) -> None:
    """Display the current resolved configuration.

    Shows all settings with their values and sources (default, env, file, CLI).
    """
    from codecompass.utils.config import config_path, global_config_path

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]
    repo_cfg_file = config_path(repo_path)
    global_cfg_file = global_config_path()

    from rich.table import Table

    table = Table(title="CodeCompass Configuration", show_lines=True)
    table.add_column("Setting", style="bold cyan")
    table.add_column("Value")
    table.add_column("Source", style="dim")

    # Determine sources
    repo_vals: dict = {}
    global_vals: dict = {}
    if repo_cfg_file.is_file():
        from codecompass.utils.config import _parse_toml
        repo_vals = _parse_toml(repo_cfg_file)
    if global_cfg_file.is_file():
        from codecompass.utils.config import _parse_toml
        global_vals = _parse_toml(global_cfg_file)

    import os

    env_map = {
        "model": "CODECOMPASS_MODEL",
        "log_level": "CODECOMPASS_LOG_LEVEL",
        "tree_depth": "CODECOMPASS_TREE_DEPTH",
        "max_file_size_kb": "CODECOMPASS_MAX_FILE_SIZE_KB",
        "github_token": "GITHUB_TOKEN",
    }

    defaults = Settings()

    display_settings = settings
    if global_scope:
        global_only_vals = dict(global_vals)
        if "repo_path" not in global_only_vals:
            global_only_vals["repo_path"] = settings.repo_path
        display_settings = Settings(**global_only_vals)

    for field_name in ["model", "log_level", "tree_depth", "max_file_size_kb", "repo_path", "github_token"]:
        val = getattr(display_settings, field_name)
        # Determine source
        env_key = env_map.get(field_name)
        if not global_scope and env_key and os.environ.get(env_key):
            source = f"env ({env_key})"
        elif global_scope and field_name in global_vals:
            source = f"file ({global_cfg_file.name})"
        elif not global_scope and field_name in repo_vals:
            source = f"file ({repo_cfg_file.name})"
        elif not global_scope and field_name in global_vals:
            source = f"file ({global_cfg_file.name})"
        elif val == getattr(defaults, field_name):
            source = "default"
        else:
            source = "CLI flag"

        # Mask token
        display_val = str(val)
        if field_name == "github_token" and val:
            display_val = val[:4] + "…" + val[-4:] if len(val) > 8 else "****"

        table.add_row(field_name, display_val, source)

    console.print()
    console.print(table)
    if global_scope:
        console.print(f"\n[dim]Global config file: {global_cfg_file}{'  ✓ exists' if global_cfg_file.is_file() else '  (not found)'}[/]")
    else:
        console.print(f"\n[dim]Repo config file: {repo_cfg_file}{'  ✓ exists' if repo_cfg_file.is_file() else '  (not found)'}[/]")
        console.print(f"[dim]Global config file: {global_cfg_file}{'  ✓ exists' if global_cfg_file.is_file() else '  (not found)'}[/]")
    console.print()


@config.command(name="set")
@click.option("--global", "global_scope", is_flag=True, help="Write key to global user config instead of repo config.")
@click.argument("key")
@click.argument("value", required=False)
@click.pass_context
def config_set(ctx: click.Context, global_scope: bool, key: str, value: str | None) -> None:
    """Set a single configuration value.

    Updates (or creates) .codecompass.toml with the given key-value pair.

    Example:
        codecompass config set model gpt-4.1
        codecompass config set log_level DEBUG
        codecompass config set tree_depth 6
    """
    from codecompass.utils.config import update_config_key, config_path, global_config_path

    valid_keys = {"model", "log_level", "tree_depth", "max_file_size_kb", "github_token"}
    if key not in valid_keys:
        console.print(
            f"[red]Invalid key:[/] {key}\n"
            f"Valid keys: {', '.join(sorted(valid_keys))}"
        )
        return

    settings: Settings = ctx.obj["settings"]

    if key == "model" and (value is None or not str(value).strip()):
        models = _available_models_with_premium()
        model_choices = [name for name, _ in models]

        table = Table(title="Available Copilot Models")
        table.add_column("Model", style="bold cyan")
        table.add_column("Premium Rate", style="dim")
        for name, premium in models:
            rate_display = "free" if premium == "0x" else premium
            table.add_row(name, rate_display)
        console.print()
        console.print(table)
        console.print()

        default_model = settings.model if settings.model in model_choices else model_choices[0]
        value = click.prompt(
            "Select model",
            type=click.Choice(model_choices, case_sensitive=False),
            default=default_model,
            show_choices=False,
        )

    if value is None or not str(value).strip():
        if key == "github_token":
            value = click.prompt("GitHub token", hide_input=True)
        else:
            value = click.prompt(f"Value for {key}")

    repo_path: Path = ctx.obj["repo_path"]
    target = global_config_path() if global_scope else config_path(repo_path)
    update_config_key(key, value, target)
    console.print(f"[green]✓[/] Set [bold]{key}[/] = [cyan]{value}[/] in {target}")


@config.command(name="path")
@click.option("--global", "global_scope", is_flag=True, help="Show global user config path.")
@click.pass_context
def config_path_cmd(ctx: click.Context, global_scope: bool) -> None:
    """Print the path to the configuration file."""
    from codecompass.utils.config import config_path, global_config_path

    repo_path: Path = ctx.obj["repo_path"]
    p = global_config_path() if global_scope else config_path(repo_path)
    exists = "✓ exists" if p.is_file() else "not found"
    click.echo(f"{p}  ({exists})")


@config.command(name="set-model")
@click.option("--global", "global_scope", is_flag=True, help="Write to global user config.")
@click.argument("model_name", required=False, default=None)
@click.pass_context
def config_set_model(ctx: click.Context, global_scope: bool, model_name: str | None) -> None:
    """Shortcut to change the active Copilot model.

    Shows the model picker table and lets you choose interactively,
    or pass the model name directly:

        codecompass config set-model gpt-4.1
        codecompass config set-model          # interactive picker
    """
    from codecompass.utils.config import update_config_key, config_path, global_config_path

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]

    if model_name is None or not model_name.strip():
        models = _available_models_with_premium()
        model_choices = [name for name, _ in models]

        table = Table(title="Available Copilot Models")
        table.add_column("Model", style="bold cyan")
        table.add_column("Premium Rate", style="dim")
        for name, premium in models:
            rate_display = "free" if premium == "0x" else premium
            table.add_row(name, rate_display)
        console.print()
        console.print(table)
        console.print()

        default_model = settings.model if settings.model in model_choices else model_choices[0]
        model_name = click.prompt(
            "Select model",
            type=click.Choice(model_choices, case_sensitive=False),
            default=default_model,
            show_choices=False,
        )

    target = global_config_path() if global_scope else config_path(repo_path)
    update_config_key("model", model_name, target)
    console.print(f"[green]✓[/] Model set to [bold cyan]{model_name}[/] in {target}")


# ── _export_onboarding (helper for onboard --output) ────────────────


def _export_onboarding(
    agent: object,
    summary: object,
    output_path: str,
    fmt: str,
) -> None:
    """Serialise onboarding summary + knowledge graph to a file.

    Called from ``onboard --output``; replaces the old standalone
    ``export`` command.
    """
    import json as json_mod

    kg = agent.graph  # type: ignore[attr-defined]

    if fmt == "json":
        data = {
            "name": summary.name,  # type: ignore[attr-defined]
            "root": summary.root,  # type: ignore[attr-defined]
            "languages": [lang.value for lang in summary.languages],  # type: ignore[attr-defined]
            "frameworks": [{"name": f.name, "version": f.version, "category": f.category} for f in summary.frameworks],  # type: ignore[attr-defined]
            "total_files": summary.total_files,  # type: ignore[attr-defined]
            "total_lines": summary.total_lines,  # type: ignore[attr-defined]
            "entry_points": summary.entry_points,  # type: ignore[attr-defined]
            "config_files": summary.config_files,  # type: ignore[attr-defined]
            "test_directories": summary.test_directories,  # type: ignore[attr-defined]
            "has_ci": summary.has_ci,  # type: ignore[attr-defined]
            "has_readme": summary.has_readme,  # type: ignore[attr-defined]
            "has_contributing": summary.has_contributing,  # type: ignore[attr-defined]
            "modules": sorted(kg.all_modules()),
            "symbols": [
                {"name": s.name, "kind": s.kind, "file": s.file, "line": s.line}
                for s in kg.symbols.values()
            ],
            "imports": list({
                (e.source_module, e.target_module): {"source": e.source_module, "target": e.target_module, "names": e.imported_names}
                for e in kg.imports
            }.values()),
        }
        output = json_mod.dumps(data, indent=2)
    else:
        # Markdown export
        lines = [
            f"# {summary.name} — Onboarding Guide",  # type: ignore[attr-defined]
            "",
            "*Generated by [CodeCompass](https://github.com/codecompass)*",
            "",
            "## Overview",
            "",
            summary.to_text(),  # type: ignore[attr-defined]
            "",
            "## Modules",
            "",
        ]
        all_modules = sorted(kg.all_modules())
        root_counts: dict[str, int] = {}
        for module_name in all_modules:
            root = module_name.split(".")[0]
            if root.startswith(("tests", "e2e_")):
                continue
            root_counts[root] = root_counts.get(root, 0) + 1

        if root_counts:
            project_root = max(root_counts, key=root_counts.get)
            project_modules = [
                m for m in all_modules
                if (m == project_root or m.startswith(project_root + "."))
                and not m.startswith(("tests.", "e2e_"))
            ]
        else:
            project_modules = [
                m for m in all_modules
                if not m.startswith(("tests.", "e2e_"))
            ]
        for mod in project_modules:
            lines.append(f"- `{mod}`")

        lines += [
            "",
            "## Key Symbols",
            "",
            "| Symbol | Kind | File | Line |",
            "|--------|------|------|------|",
        ]
        public_symbols = sorted(
            (s for s in kg.symbols.values()
             if not s.name.startswith("_")),
            key=lambda x: (x.file, x.line or 0),
        )
        for s in public_symbols[:80]:
            lines.append(f"| `{s.name}` | {s.kind} | `{s.file}` | {s.line or '-'} |")

        lines += [
            "",
            "## Dependencies",
            "",
        ]
        seen_deps: set[tuple[str, str]] = set()
        for edge in kg.imports:
            key = (edge.source_module, edge.target_module)
            if key not in seen_deps:
                seen_deps.add(key)
                if edge.target_module.startswith(("__future__", "os", "sys",
                                                   "pathlib", "json", "enum",
                                                   "datetime", "logging",
                                                   "asyncio", "typing",
                                                   "subprocess", "ast",
                                                   "dataclasses", "re",
                                                   "io", "functools",
                                                   "collections", "abc")):
                    continue
                lines.append(f"- `{edge.source_module}` → `{edge.target_module}`")

        output = "\n".join(lines)

    Path(output_path).write_text(output, encoding="utf-8")
    console.print(f"[green]Exported to {output_path}[/]")
