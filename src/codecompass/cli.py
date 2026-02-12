"""CLI entry point for CodeCompass (Click-based).

Commands:
    onboard       Scan a repo and display an interactive onboarding summary
    ask           Ask a natural-language question about the codebase
    why           Ask WHY something exists in the codebase
    architecture  Explore the repo's architecture
    contributors  Show contributor intelligence
    audit         Audit documentation freshness
    chat          Interactive multi-turn chat
    tui           Launch the interactive terminal UI
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click
from rich.console import Console

from codecompass import __version__
from codecompass.utils.config import Settings

console = Console()


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.WARNING),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _init_git(repo_path: Path):
    """Create a GitOps instance (returns None if not a git repo)."""
    from codecompass.github.git import GitOps, GitOpsError

    try:
        return GitOps(repo_path)
    except GitOpsError:
        return None


async def _run_with_sdk(
    repo_path: Path,
    settings: Settings,
    system_message: dict[str, str],
    prompt: str,
) -> None:
    """Send a prompt to the Copilot SDK and stream the response."""
    from codecompass.agent.client import CompassClient
    from codecompass.indexer.knowledge_graph import KnowledgeGraph

    git_ops = _init_git(repo_path)

    kg = KnowledgeGraph()
    try:
        kg.build(repo_path)
    except Exception:
        kg = None

    async with CompassClient(
        repo_path,
        model=settings.model,
        git_ops=git_ops,
        knowledge_graph=kg,
    ) as client:
        await client.create_session(
            system_message=system_message,
            streaming=True,
        )

        def on_delta(delta: str) -> None:
            sys.stdout.write(delta)
            sys.stdout.flush()

        console.print()
        await client.send_and_collect(prompt, on_delta=on_delta)
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

    async with CompassClient(
        repo_path,
        model=settings.model,
        git_ops=git_ops,
        knowledge_graph=kg,
    ) as client:
        await client.create_session(
            system_message=system_message,
            streaming=True,
        )

        console.print(
            "\n[bold cyan]🧭 CodeCompass[/] — Interactive mode "
            "(type [bold]exit[/] or [bold]quit[/] to leave)\n"
        )

        while True:
            try:
                question = console.input("[bold green]You:[/] ")
            except (EOFError, KeyboardInterrupt):
                break

            if question.strip().lower() in ("exit", "quit", "q"):
                break
            if not question.strip():
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

    settings = Settings.load(overrides)
    _configure_logging(settings.log_level)

    ctx.ensure_object(dict)
    ctx.obj["settings"] = settings
    ctx.obj["repo_path"] = Path(repo).resolve()

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ── onboard ──────────────────────────────────────────────────────────


@main.command()
@click.option(
    "--interactive", "-i", is_flag=True,
    help="Start an interactive Q&A session after displaying the summary.",
)
@click.pass_context
def onboard(ctx: click.Context, interactive: bool) -> None:
    """Scan a repository and display an AI-powered onboarding summary."""
    from codecompass.agent.agent import CodeCompassAgent
    from codecompass.utils.formatting import print_onboarding_summary

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]

    agent = CodeCompassAgent(repo_path, settings=settings)
    summary = asyncio.run(agent.onboard())
    print_onboarding_summary(summary)

    if interactive:
        sys_msg = agent.system_message("onboarding")
        asyncio.run(_interactive_session(repo_path, settings, sys_msg))


# ── ask ──────────────────────────────────────────────────────────────


@main.command()
@click.argument("question")
@click.pass_context
def ask(ctx: click.Context, question: str) -> None:
    """Ask a natural-language question about the codebase."""
    from codecompass.agent.agent import CodeCompassAgent

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]

    agent = CodeCompassAgent(repo_path, settings=settings)
    payload = asyncio.run(agent.ask(question))

    asyncio.run(
        _run_with_sdk(repo_path, settings, payload["system_message"], question)
    )


# ── why ──────────────────────────────────────────────────────────────


@main.command()
@click.argument("question")
@click.pass_context
def why(ctx: click.Context, question: str) -> None:
    """Ask WHY a decision was made or why something exists in the codebase."""
    from codecompass.agent.agent import CodeCompassAgent, AgentMode

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]

    agent = CodeCompassAgent(repo_path, settings=settings)
    sys_msg = agent.system_message(AgentMode.WHY)

    asyncio.run(_run_with_sdk(repo_path, settings, sys_msg, question))


# ── architecture ─────────────────────────────────────────────────────


@main.command()
@click.pass_context
def architecture(ctx: click.Context) -> None:
    """Explore the architecture of the repository with AI analysis."""
    from codecompass.agent.agent import CodeCompassAgent

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]

    agent = CodeCompassAgent(repo_path, settings=settings)
    payload = asyncio.run(agent.explore_architecture())

    asyncio.run(
        _run_with_sdk(
            repo_path,
            settings,
            payload["system_message"],
            payload["user_message"]["content"],
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
@click.pass_context
def audit(ctx: click.Context) -> None:
    """Audit repository documentation for staleness using AI."""
    from codecompass.agent.agent import CodeCompassAgent

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]

    agent = CodeCompassAgent(repo_path, settings=settings)
    payload = asyncio.run(agent.audit_docs())

    asyncio.run(
        _run_with_sdk(
            repo_path,
            settings,
            payload["system_message"],
            payload["user_message"]["content"],
        )
    )


# ── chat ─────────────────────────────────────────────────────────────


@main.command()
@click.pass_context
def chat(ctx: click.Context) -> None:
    """Start an interactive multi-turn chat about the codebase."""
    from codecompass.agent.agent import CodeCompassAgent
    from codecompass.utils.formatting import print_onboarding_summary

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]

    agent = CodeCompassAgent(repo_path, settings=settings)
    summary = asyncio.run(agent.onboard())
    print_onboarding_summary(summary)

    sys_msg = agent.system_message("onboarding")
    asyncio.run(_interactive_session(repo_path, settings, sys_msg))


# ── tui ──────────────────────────────────────────────────────────────


@main.command()
@click.pass_context
def tui(ctx: click.Context) -> None:
    """Launch the interactive Textual TUI."""
    from codecompass.ui.app import CodeCompassApp

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]

    app = CodeCompassApp(repo_path=repo_path, settings=settings)
    app.run()


# ── export ───────────────────────────────────────────────────────────


@main.command()
@click.option(
    "--format", "-f", "fmt",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
    help="Export format.",
)
@click.option(
    "--output", "-o", "output_path",
    default=None,
    help="Output file path (default: stdout).",
)
@click.pass_context
def export(ctx: click.Context, fmt: str, output_path: str | None) -> None:
    """Export the onboarding summary and knowledge graph.

    Generates a portable onboarding document or structured JSON.
    """
    import json as json_mod

    from codecompass.agent.agent import CodeCompassAgent

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]

    agent = CodeCompassAgent(repo_path, settings=settings)
    summary = asyncio.run(agent.onboard())
    kg = agent.graph

    if fmt == "json":
        data = {
            "name": summary.name,
            "root": summary.root,
            "languages": [lang.value for lang in summary.languages],
            "frameworks": [{"name": f.name, "version": f.version, "category": f.category} for f in summary.frameworks],
            "total_files": summary.total_files,
            "total_lines": summary.total_lines,
            "entry_points": summary.entry_points,
            "config_files": summary.config_files,
            "test_directories": summary.test_directories,
            "has_ci": summary.has_ci,
            "has_readme": summary.has_readme,
            "has_contributing": summary.has_contributing,
            "modules": sorted(kg.all_modules()),
            "symbols": [
                {"name": s.name, "kind": s.kind, "file": s.file, "line": s.line}
                for s in kg.symbols.values()
            ],
            "imports": [
                {"source": e.source_module, "target": e.target_module, "names": e.imported_names}
                for e in kg.imports
            ],
        }
        output = json_mod.dumps(data, indent=2)
    else:
        # Markdown export
        lines = [
            f"# {summary.name} - Onboarding Guide",
            "",
            "*Generated by [CodeCompass](https://github.com/codecompass)*",
            "",
            "## Overview",
            "",
            summary.to_text(),
            "",
            "## Modules",
            "",
        ]
        for mod in sorted(kg.all_modules()):
            if mod.startswith(summary.name.lower().replace("-", "_").replace(" ", "_")):
                lines.append(f"- `{mod}`")

        lines += [
            "",
            "## Key Symbols",
            "",
            "| Symbol | Kind | File | Line |",
            "|--------|------|------|------|",
        ]
        for s in sorted(kg.symbols.values(), key=lambda x: x.file)[:50]:
            lines.append(f"| `{s.name}` | {s.kind} | `{s.file}` | {s.line or '-'} |")

        lines += [
            "",
            "## Dependencies",
            "",
        ]
        for edge in kg.imports[:30]:
            lines.append(f"- `{edge.source_module}` -> `{edge.target_module}`")

        output = "\n".join(lines)

    if output_path:
        Path(output_path).write_text(output, encoding="utf-8")
        console.print(f"[green]Exported to {output_path}[/]")
    else:
        click.echo(output)
