"""Shared Pydantic data models for CodeCompass."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    """Severity level for documentation staleness findings."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Language(str, Enum):
    """Programming languages that the scanner can detect."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    GO = "go"
    RUST = "rust"
    C = "c"
    CPP = "cpp"
    CSHARP = "csharp"
    RUBY = "ruby"
    PHP = "php"
    SWIFT = "swift"
    KOTLIN = "kotlin"
    SHELL = "shell"
    OTHER = "other"


# ---------------------------------------------------------------------------
# File-related models
# ---------------------------------------------------------------------------


class FileInfo(BaseModel):
    """Metadata about a single file in the repository."""

    path: str = Field(description="Repo-relative file path")
    language: Language | None = Field(default=None, description="Detected language")
    size_bytes: int = Field(default=0, description="File size in bytes")
    line_count: int = Field(default=0, description="Number of lines")
    is_entry_point: bool = Field(default=False, description="Whether this is an app entry point")
    is_config: bool = Field(default=False, description="Whether this is a config file")
    is_test: bool = Field(default=False, description="Whether this is a test file")


# ---------------------------------------------------------------------------
# Git-related models
# ---------------------------------------------------------------------------


class CommitInfo(BaseModel):
    """Summary of a single git commit."""

    hash: str = Field(description="Full commit SHA")
    short_hash: str = Field(description="Short (7-char) commit SHA")
    author_name: str = Field(description="Author display name")
    author_email: str = Field(default="", description="Author email")
    authored_at: datetime = Field(description="Author timestamp")
    message: str = Field(description="Full commit message")
    files_changed: int = Field(default=0, description="Number of files changed")


class BlameEntry(BaseModel):
    """A single blame hunk for a file."""

    start_line: int
    end_line: int
    commit_hash: str
    author_name: str
    authored_at: datetime
    message: str = ""


class ContributorInfo(BaseModel):
    """Aggregated information about a single contributor."""

    name: str
    email: str = ""
    commit_count: int = 0
    first_commit: datetime | None = None
    last_commit: datetime | None = None
    files_touched: list[str] = Field(default_factory=list)
    top_directories: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Repo summary
# ---------------------------------------------------------------------------


class FrameworkInfo(BaseModel):
    """A detected framework or notable library."""

    name: str
    version: str | None = None
    category: str = ""  # e.g. "web", "testing", "orm"


class RepoSummary(BaseModel):
    """Comprehensive summary of a scanned repository."""

    name: str = Field(description="Repository / project name")
    root: str = Field(description="Absolute path to the repo root")
    languages: list[Language] = Field(default_factory=list)
    frameworks: list[FrameworkInfo] = Field(default_factory=list)
    total_files: int = 0
    total_lines: int = 0
    entry_points: list[str] = Field(default_factory=list)
    config_files: list[str] = Field(default_factory=list)
    test_directories: list[str] = Field(default_factory=list)
    has_ci: bool = False
    ci_system: str | None = None
    has_readme: bool = False
    has_contributing: bool = False
    has_license: bool = False
    directory_tree: str = Field(default="", description="ASCII directory tree")

    def to_text(self) -> str:
        """Render the summary as a human-readable text block."""
        lines: list[str] = [
            f"**{self.name}**",
            "",
            f"- Root: `{self.root}`",
            f"- Languages: {', '.join(lang.value for lang in self.languages) or 'unknown'}",
            f"- Frameworks: {', '.join(f.name for f in self.frameworks) or 'none detected'}",
            f"- Files: {self.total_files}  |  Lines: {self.total_lines}",
        ]
        if self.entry_points:
            lines.append(f"- Entry points: {', '.join(self.entry_points)}")
        if self.test_directories:
            lines.append(f"- Test dirs: {', '.join(self.test_directories)}")
        if self.has_ci:
            lines.append(f"- CI: {self.ci_system or 'detected'}")
        lines.append(f"- README: {'yes' if self.has_readme else 'no'}")
        lines.append(f"- CONTRIBUTING: {'yes' if self.has_contributing else 'no'}")
        if self.directory_tree:
            lines += ["", "```", self.directory_tree, "```"]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Documentation staleness
# ---------------------------------------------------------------------------


class StalenessFinding(BaseModel):
    """A single documentation-staleness finding."""

    file: str
    line: int | None = None
    issue: str
    evidence: str = ""
    severity: Severity = Severity.MEDIUM
    suggested_fix: str = ""


class StalenessReport(BaseModel):
    """Aggregated documentation-staleness audit report."""

    repo_name: str
    findings: list[StalenessFinding] = Field(default_factory=list)
    scanned_files: int = 0
    scanned_at: datetime = Field(default_factory=datetime.now)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.HIGH)

    @property
    def medium_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.MEDIUM)

    @property
    def low_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.LOW)


# ---------------------------------------------------------------------------
# Knowledge-graph primitives
# ---------------------------------------------------------------------------


class SymbolNode(BaseModel):
    """A node in the knowledge graph representing a code symbol."""

    name: str
    kind: str = ""  # "class", "function", "module", etc.
    file: str = ""
    line: int | None = None
    docstring: str = ""


class ImportEdge(BaseModel):
    """An edge in the knowledge graph representing an import relationship."""

    source_module: str
    target_module: str
    imported_names: list[str] = Field(default_factory=list)
