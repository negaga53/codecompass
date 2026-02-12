"""Rich formatting helpers for CLI output."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from codecompass.models import ContributorInfo, RepoSummary, StalenessReport

console = Console()


# ---------------------------------------------------------------------------
# Onboarding summary
# ---------------------------------------------------------------------------


def format_onboarding_summary(summary: "RepoSummary") -> Panel:
    """Render a ``RepoSummary`` as a Rich panel for the terminal."""
    md = Markdown(summary.to_text())
    return Panel(md, title="[bold cyan]CodeCompass — Onboarding Summary[/]", border_style="cyan")


def print_onboarding_summary(summary: "RepoSummary") -> None:
    """Print the onboarding summary panel to the console."""
    console.print()
    console.print(format_onboarding_summary(summary))
    console.print()


# ---------------------------------------------------------------------------
# Contributor table
# ---------------------------------------------------------------------------


def format_contributor_table(contributors: list["ContributorInfo"]) -> Table:
    """Build a Rich table summarizing contributors."""
    table = Table(title="Contributor Overview", show_lines=True)
    table.add_column("Name", style="bold")
    table.add_column("Commits", justify="right")
    table.add_column("Last Active")
    table.add_column("Top Directories")

    for c in contributors:
        last_active = c.last_commit.strftime("%Y-%m-%d") if c.last_commit else "—"
        dirs = ", ".join(c.top_directories[:3]) or "—"
        table.add_row(c.name, str(c.commit_count), last_active, dirs)

    return table


def print_contributor_table(contributors: list["ContributorInfo"]) -> None:
    """Print contributor table to the console."""
    console.print()
    console.print(format_contributor_table(contributors))
    console.print()


# ---------------------------------------------------------------------------
# Stale-docs report
# ---------------------------------------------------------------------------


def format_stale_docs_report(report: "StalenessReport") -> Panel:
    """Render a staleness report as a Rich panel."""
    parts: list[str] = [
        f"**Repo:** {report.repo_name}  ",
        f"**Scanned files:** {report.scanned_files}  ",
        f"**Findings:** {len(report.findings)} "
        f"(High: {report.high_count}, Medium: {report.medium_count}, Low: {report.low_count})",
        "",
    ]
    for i, f in enumerate(report.findings, 1):
        loc = f"{f.file}:{f.line}" if f.line else f.file
        parts.append(f"{i}. **[{f.severity.value.upper()}]** `{loc}` — {f.issue}")
        if f.evidence:
            parts.append(f"   Evidence: {f.evidence}")
        if f.suggested_fix:
            parts.append(f"   Suggested fix: {f.suggested_fix}")
        parts.append("")

    md = Markdown("\n".join(parts))
    return Panel(md, title="[bold yellow]Documentation Freshness Audit[/]", border_style="yellow")


def print_stale_docs_report(report: "StalenessReport") -> None:
    """Print a staleness report to the console."""
    console.print()
    console.print(format_stale_docs_report(report))
    console.print()


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def print_code(code: str, language: str = "python", *, title: str = "") -> None:
    """Pretty-print a code snippet with syntax highlighting."""
    syntax = Syntax(code, language, theme="monokai", line_numbers=True)
    if title:
        console.print(Panel(syntax, title=title, border_style="green"))
    else:
        console.print(syntax)


def print_markdown(text: str) -> None:
    """Render a Markdown string to the console via Rich."""
    console.print(Markdown(text))


def print_error(message: str) -> None:
    """Print a styled error message."""
    console.print(Text(f"✖ {message}", style="bold red"))


def print_success(message: str) -> None:
    """Print a styled success message."""
    console.print(Text(f"✔ {message}", style="bold green"))


def print_info(message: str) -> None:
    """Print a styled informational message."""
    console.print(Text(f"ℹ {message}", style="bold blue"))
