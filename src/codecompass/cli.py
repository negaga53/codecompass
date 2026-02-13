"""CLI entry point for CodeCompass (Click-based).

Commands:
    onboard       Scan a repo and display an interactive onboarding summary
    ask           Ask a natural-language question about the codebase
    why           Ask WHY something exists in the codebase
    architecture  Explore the repo's architecture
    contributors  Show contributor intelligence
    audit         Audit documentation freshness
    chat          Interactive multi-turn chat
    demo          Print a deterministic, judge-friendly demo script
    premium-usage Show commands that may consume Copilot premium requests
    tui           Launch the interactive terminal UI
    config        Manage CodeCompass configuration
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


_PREMIUM_USAGE: dict[str, tuple[str, str]] = {
    "ask": ("yes", "Sends prompt to Copilot model via SDK session"),
    "why": ("yes", "Sends prompt to Copilot model via SDK session"),
    "architecture": ("yes", "Runs architecture prompt through Copilot model"),
    "audit": ("yes", "Runs docs-audit prompt through Copilot model"),
    "chat": ("yes", "Interactive multi-turn model conversation"),
    "diff-explain": ("yes", "Analyzes commit diffs with Copilot model"),
    "tui": ("yes", "Chat interactions in TUI use Copilot model"),
    "onboard --interactive": ("conditional", "Onboarding scan is local; interactive chat uses Copilot model"),
}


def _print_premium_notice(settings: Settings, command_name: str, detail: str) -> None:
    if not settings.premium_usage_warnings:
        return
    console.print(
        f"[yellow]⚠ Premium usage:[/] `{command_name}` may consume Copilot premium requests. {detail}"
    )


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
            f"[dim](model: {settings.model})[/]\n"
            "[dim]Commands: /model <name> to switch model, "
            "/models to list, exit to quit[/]\n"
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
                console.print(
                    "\n[bold]Available models:[/] claude-sonnet-4, "
                    "claude-haiku-4.5, gpt-4.1, gpt-5.1, "
                    "gpt-5.2-codex, o4-mini"
                )
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
        _print_premium_notice(settings, "onboard --interactive", _PREMIUM_USAGE["onboard --interactive"][1])
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
    _print_premium_notice(settings, "ask", _PREMIUM_USAGE["ask"][1])

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
    _print_premium_notice(settings, "why", _PREMIUM_USAGE["why"][1])

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
    _print_premium_notice(settings, "architecture", _PREMIUM_USAGE["architecture"][1])

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
    _print_premium_notice(settings, "audit", _PREMIUM_USAGE["audit"][1])

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
    _print_premium_notice(settings, "chat", _PREMIUM_USAGE["chat"][1])

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
@click.option("--commits", "-n", default=5, help="Number of recent commits to analyze.")
@click.pass_context
def diff_explain(ctx: click.Context, commits: int) -> None:
    """AI-powered explanation of recent changes.

    Analyzes the last N commits using git diff, then uses the Copilot
    SDK to generate a human-readable summary explaining WHAT changed,
    WHY (based on commit messages and code context), and what a new
    developer should know about these changes.

    This is a unique CodeCompass feature — it combines git history
    analysis with AI reasoning that the plain Copilot CLI cannot do.
    """
    from codecompass.agent.agent import CodeCompassAgent
    from codecompass.github.git import GitOps, GitOpsError

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]
    _print_premium_notice(settings, "diff-explain", _PREMIUM_USAGE["diff-explain"][1])

    try:
        git = GitOps(repo_path)
    except GitOpsError as exc:
        console.print(f"[red]Error:[/] {exc}")
        return

    # Gather recent commits
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

    asyncio.run(_run_with_sdk(repo_path, settings, sys_msg, prompt))


@main.command(name="premium-usage")
def premium_usage() -> None:
    """Show which commands may consume Copilot premium requests."""
    table = Table(title="Copilot Premium Request Usage")
    table.add_column("Command", style="bold cyan")
    table.add_column("Consumes Premium Requests")
    table.add_column("Notes", style="dim")

    for command_name in sorted(_PREMIUM_USAGE):
        usage, note = _PREMIUM_USAGE[command_name]
        table.add_row(command_name, usage, note)

    console.print()
    console.print(table)
    console.print("\n[dim]Tip: local-only commands like onboard (without --interactive), graph, export, and contributors do not invoke model prompts.[/]")
    console.print()


# ── demo ─────────────────────────────────────────────────────────────


@main.command()
@click.option(
    "--artifact", "artifact_path",
    default="demo-deps.md",
    show_default=True,
    help="Artifact path for generated dependency graph (when --generate-artifact is used).",
)
@click.option(
    "--generate-artifact",
    is_flag=True,
    help="Generate a Mermaid dependency graph artifact for the demo.",
)
@click.pass_context
def demo(ctx: click.Context, artifact_path: str, generate_artifact: bool) -> None:
    """Print a deterministic, judge-oriented demo flow.

    This command is intentionally network-independent and reproducible.
    It prints a concise script judges can follow, and can optionally
    generate a dependency graph artifact for screen-sharing.
    """
    from codecompass.indexer.knowledge_graph import KnowledgeGraph

    repo_path: Path = ctx.obj["repo_path"]
    lines = [
        "# CodeCompass Judge Demo Script (6-8 minutes)",
        "",
        "1) Onboard context",
        f"   codecompass --repo {repo_path} onboard",
        "   Expected: project summary (languages, frameworks, tree, entry points)",
        "",
        "2) Show deterministic architecture artifact",
        f"   codecompass --repo {repo_path} graph -f mermaid -o {artifact_path}",
        "   Expected: Mermaid dependency graph written to disk",
        "",
        "3) Ask a dependency question",
        f"   codecompass --repo {repo_path} ask \"What depends on codecompass.github.git?\"",
        "   Expected: grounded answer referencing module dependencies",
        "",
        "4) Explain recent changes",
        f"   codecompass --repo {repo_path} diff-explain -n 5",
        "   Expected: WHAT changed, WHY, and impact summary",
        "",
        "5) Audit docs freshness",
        f"   codecompass --repo {repo_path} audit",
        "   Expected: stale/inconsistent docs findings or clean audit",
        "",
        "6) Reliability proof",
        "   pytest -q",
        "   Expected: passing suite summary",
    ]

    if generate_artifact:
        kg = KnowledgeGraph()
        kg.build(repo_path)
        all_mods = kg.all_modules()
        project_mods = sorted(m for m in all_mods if m.startswith("codecompass."))

        mermaid = ["```mermaid", "flowchart TD"]

        def _mid(module_name: str) -> str:
            return module_name.replace(".", "_")

        for m in project_mods:
            mermaid.append(f"    {_mid(m)}[{m.split('.')[-1]}]")
        project_set = set(project_mods)
        for m in project_mods:
            for dep in sorted(kg.dependencies(m)):
                if dep in project_set:
                    mermaid.append(f"    {_mid(m)} --> {_mid(dep)}")
        mermaid.append("```")
        Path(artifact_path).write_text("\n".join(mermaid), encoding="utf-8")
        lines += ["", f"Generated artifact: {artifact_path}"]

    click.echo("\n".join(lines))


# ── tui ──────────────────────────────────────────────────────────────


@main.command()
@click.pass_context
def tui(ctx: click.Context) -> None:
    """Launch the interactive Textual TUI."""
    from codecompass.ui.app import CodeCompassApp

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]
    _print_premium_notice(settings, "tui", _PREMIUM_USAGE["tui"][1])

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
@click.pass_context
def config_init(ctx: click.Context, force: bool) -> None:
    """Generate a .codecompass.toml configuration file with sensible defaults.

    Interactively prompts for key settings (model, log level, etc.)
    and writes them to .codecompass.toml in the current directory.
    """
    from codecompass.utils.config import config_path, write_config

    repo_path: Path = ctx.obj["repo_path"]
    target = config_path(repo_path)

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
    premium_usage_warnings = click.confirm(
        "Show premium usage warnings for AI commands",
        default=True,
    )

    settings = Settings(
        model=model,
        log_level=log_level.upper(),
        tree_depth=tree_depth,
        max_file_size_kb=max_file_size_kb,
        premium_usage_warnings=premium_usage_warnings,
    )
    write_config(settings, target)
    console.print(f"\n[green]✓[/] Config written to [bold]{target}[/]")


@config.command(name="show")
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """Display the current resolved configuration.

    Shows all settings with their values and sources (default, env, file, CLI).
    """
    from codecompass.utils.config import config_path

    settings: Settings = ctx.obj["settings"]
    repo_path: Path = ctx.obj["repo_path"]
    cfg_file = config_path(repo_path)

    from rich.table import Table

    table = Table(title="CodeCompass Configuration", show_lines=True)
    table.add_column("Setting", style="bold cyan")
    table.add_column("Value")
    table.add_column("Source", style="dim")

    # Determine sources
    file_vals: dict = {}
    if cfg_file.is_file():
        from codecompass.utils.config import _parse_toml
        file_vals = _parse_toml(cfg_file)

    import os

    env_map = {
        "model": "CODECOMPASS_MODEL",
        "log_level": "CODECOMPASS_LOG_LEVEL",
        "tree_depth": "CODECOMPASS_TREE_DEPTH",
        "max_file_size_kb": "CODECOMPASS_MAX_FILE_SIZE_KB",
        "premium_usage_warnings": "CODECOMPASS_PREMIUM_USAGE_WARNINGS",
        "github_token": "GITHUB_TOKEN",
    }

    defaults = Settings()
    for field_name in ["model", "log_level", "tree_depth", "max_file_size_kb", "premium_usage_warnings", "repo_path", "github_token"]:
        val = getattr(settings, field_name)
        # Determine source
        env_key = env_map.get(field_name)
        if env_key and os.environ.get(env_key):
            source = f"env ({env_key})"
        elif field_name in file_vals:
            source = f"file ({cfg_file.name})"
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
    console.print(f"\n[dim]Config file: {cfg_file}{'  ✓ exists' if cfg_file.is_file() else '  (not found)'}[/]")
    console.print()


@config.command(name="set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set(ctx: click.Context, key: str, value: str) -> None:
    """Set a single configuration value.

    Updates (or creates) .codecompass.toml with the given key-value pair.

    Example:
        codecompass config set model gpt-4.1
        codecompass config set log_level DEBUG
        codecompass config set tree_depth 6
    """
    from codecompass.utils.config import update_config_key, config_path

    valid_keys = {"model", "log_level", "tree_depth", "max_file_size_kb", "premium_usage_warnings"}
    if key not in valid_keys:
        console.print(
            f"[red]Invalid key:[/] {key}\n"
            f"Valid keys: {', '.join(sorted(valid_keys))}"
        )
        return

    repo_path: Path = ctx.obj["repo_path"]
    target = config_path(repo_path)
    update_config_key(key, value, target)
    console.print(f"[green]✓[/] Set [bold]{key}[/] = [cyan]{value}[/] in {target}")


@config.command(name="path")
@click.pass_context
def config_path_cmd(ctx: click.Context) -> None:
    """Print the path to the configuration file."""
    from codecompass.utils.config import config_path

    repo_path: Path = ctx.obj["repo_path"]
    p = config_path(repo_path)
    exists = "✓ exists" if p.is_file() else "not found"
    click.echo(f"{p}  ({exists})")


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
            "imports": list({
                (e.source_module, e.target_module): {"source": e.source_module, "target": e.target_module, "names": e.imported_names}
                for e in kg.imports
            }.values()),
        }
        output = json_mod.dumps(data, indent=2)
    else:
        # Markdown export
        lines = [
            f"# {summary.name} — Onboarding Guide",
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
        # List modules that belong to this project
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
        # Filter out dunder methods and private symbols
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
        # Deduplicate dependencies
        seen_deps: set[tuple[str, str]] = set()
        for edge in kg.imports:
            key = (edge.source_module, edge.target_module)
            if key not in seen_deps:
                seen_deps.add(key)
                # Skip stdlib imports for cleaner output
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

    if output_path:
        Path(output_path).write_text(output, encoding="utf-8")
        console.print(f"[green]Exported to {output_path}[/]")
    else:
        click.echo(output)
