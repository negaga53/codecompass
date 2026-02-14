"""Repository scanner — detects languages, frameworks, and structure."""

from __future__ import annotations

import logging
from pathlib import Path

from codecompass.models import FileInfo, FrameworkInfo, Language, RepoSummary

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extension → Language mapping
# ---------------------------------------------------------------------------

_EXT_MAP: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".pyi": Language.PYTHON,
    ".js": Language.JAVASCRIPT,
    ".jsx": Language.JAVASCRIPT,
    ".mjs": Language.JAVASCRIPT,
    ".cjs": Language.JAVASCRIPT,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TYPESCRIPT,
    ".java": Language.JAVA,
    ".go": Language.GO,
    ".rs": Language.RUST,
    ".c": Language.C,
    ".h": Language.C,
    ".cpp": Language.CPP,
    ".cxx": Language.CPP,
    ".hpp": Language.CPP,
    ".cc": Language.CPP,
    ".cs": Language.CSHARP,
    ".rb": Language.RUBY,
    ".php": Language.PHP,
    ".swift": Language.SWIFT,
    ".kt": Language.KOTLIN,
    ".kts": Language.KOTLIN,
    ".sh": Language.SHELL,
    ".bash": Language.SHELL,
    ".zsh": Language.SHELL,
}

# Files that indicate an entry point
_ENTRY_POINT_NAMES: set[str] = {
    "main.py",
    "__main__.py",
    "app.py",
    "server.py",
    "manage.py",
    "index.js",
    "index.ts",
    "main.go",
    "main.rs",
    "Program.cs",
    "Main.java",
    "main.kt",
}

# Config file basenames (case-insensitive match attempted)
_CONFIG_BASENAMES: set[str] = {
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "package.json",
    "tsconfig.json",
    "cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "gemfile",
    "composer.json",
    "makefile",
    "cmakelists.txt",
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".env",
    ".env.example",
}

# CI config globs
_CI_INDICATORS: dict[str, str] = {
    ".github/workflows": "GitHub Actions",
    ".gitlab-ci.yml": "GitLab CI",
    "Jenkinsfile": "Jenkins",
    ".circleci": "CircleCI",
    ".travis.yml": "Travis CI",
    "azure-pipelines.yml": "Azure Pipelines",
    "bitbucket-pipelines.yml": "Bitbucket Pipelines",
}

# Directories considered as test roots
_TEST_DIR_NAMES: set[str] = {"tests", "test", "spec", "__tests__", "testing"}

# Directories to skip entirely
_SKIP_DIRS: set[str] = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".eggs",
    "*.egg-info",
    ".next",
    "target",
}


class RepoScanner:
    """Walks a repository tree and produces a ``RepoSummary``.

    Args:
        root: Absolute path to the repository root.
        max_file_size_kb: Skip files larger than this (in KB).
        tree_depth: Maximum depth for the directory-tree rendering.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        max_file_size_kb: int = 512,
        tree_depth: int = 4,
    ) -> None:
        self.root = Path(root).resolve()
        self.max_file_size_kb = max_file_size_kb
        self.tree_depth = tree_depth

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def scan(self) -> RepoSummary:
        """Perform a full scan and return a ``RepoSummary``."""
        files: list[FileInfo] = []
        languages: set[Language] = set()
        entry_points: list[str] = []
        config_files: list[str] = []
        test_dirs: set[str] = set()
        total_lines = 0

        for path in self._walk():
            rel = path.relative_to(self.root).as_posix()
            info = self._analyze_file(path, rel)
            files.append(info)

            if info.language:
                languages.add(info.language)
            if info.is_entry_point:
                entry_points.append(rel)
            if info.is_config:
                config_files.append(rel)
            if info.is_test:
                # Record the top-level test directory
                parts = Path(rel).parts
                if parts:
                    test_dirs.add(parts[0])
            total_lines += info.line_count

        has_ci, ci_system = self._detect_ci()
        frameworks = self._detect_frameworks(config_files)

        return RepoSummary(
            name=self.root.name,
            root=str(self.root),
            languages=sorted(languages, key=lambda lang: lang.value),
            frameworks=frameworks,
            total_files=len(files),
            total_lines=total_lines,
            entry_points=entry_points,
            config_files=config_files,
            test_directories=sorted(test_dirs),
            has_ci=has_ci,
            ci_system=ci_system,
            has_readme=(self.root / "README.md").exists()
            or (self.root / "readme.md").exists(),
            has_contributing=(self.root / "CONTRIBUTING.md").exists(),
            has_license=(self.root / "LICENSE").exists()
            or (self.root / "LICENSE.md").exists(),
            directory_tree=self._build_tree(),
        )

    # ------------------------------------------------------------------
    # Walking
    # ------------------------------------------------------------------

    def _walk(self) -> list[Path]:
        """Recursively collect all non-skipped files under ``self.root``."""
        result: list[Path] = []
        self._walk_dir(self.root, result)
        return result

    def _walk_dir(self, directory: Path, acc: list[Path]) -> None:
        try:
            entries = sorted(directory.iterdir())
        except PermissionError:
            return

        for entry in entries:
            if entry.name.startswith(".") and entry.is_dir():
                # Allow .github but skip other hidden dirs
                if entry.name != ".github":
                    continue
            if entry.is_dir():
                if entry.name in _SKIP_DIRS:
                    continue
                self._walk_dir(entry, acc)
            elif entry.is_file():
                if entry.stat().st_size > self.max_file_size_kb * 1024:
                    continue
                acc.append(entry)

    # ------------------------------------------------------------------
    # File analysis
    # ------------------------------------------------------------------

    def _analyze_file(self, path: Path, rel: str) -> FileInfo:
        lang = _EXT_MAP.get(path.suffix.lower())
        is_entry = path.name in _ENTRY_POINT_NAMES
        is_config = path.name.lower() in _CONFIG_BASENAMES
        is_test = any(part in _TEST_DIR_NAMES for part in Path(rel).parts)

        line_count = 0
        try:
            line_count = sum(1 for _ in path.open("r", errors="replace"))
        except OSError:
            pass

        return FileInfo(
            path=rel,
            language=lang,
            size_bytes=path.stat().st_size,
            line_count=line_count,
            is_entry_point=is_entry,
            is_config=is_config,
            is_test=is_test,
        )

    # ------------------------------------------------------------------
    # CI detection
    # ------------------------------------------------------------------

    def _detect_ci(self) -> tuple[bool, str | None]:
        for indicator, name in _CI_INDICATORS.items():
            if (self.root / indicator).exists():
                return True, name
        return False, None

    # ------------------------------------------------------------------
    # Framework detection (heuristic)
    # ------------------------------------------------------------------

    def _detect_frameworks(self, config_files: list[str]) -> list[FrameworkInfo]:
        frameworks: list[FrameworkInfo] = []
        config_set = {c.lower() for c in config_files}

        # Python
        if "pyproject.toml" in config_set or "setup.cfg" in config_set:
            frameworks.extend(self._detect_python_frameworks())

        # Node / JS / TS
        if "package.json" in config_set:
            frameworks.extend(self._detect_node_frameworks())

        return frameworks

    def _detect_python_frameworks(self) -> list[FrameworkInfo]:
        found: list[FrameworkInfo] = []
        pyproject = self.root / "pyproject.toml"
        if not pyproject.exists():
            return found

        try:
            content = pyproject.read_text(errors="replace").lower()
        except OSError:
            return found

        detections: list[tuple[str, str]] = [
            ("django", "web"),
            ("flask", "web"),
            ("fastapi", "web"),
            ("starlette", "web"),
            ("pytest", "testing"),
            ("textual", "tui"),
            ("click", "cli"),
            ("pydantic", "validation"),
            ("sqlalchemy", "orm"),
            ("celery", "task-queue"),
        ]
        for name, category in detections:
            if name in content:
                found.append(FrameworkInfo(name=name, category=category))
        return found

    def _detect_node_frameworks(self) -> list[FrameworkInfo]:
        found: list[FrameworkInfo] = []
        pkg = self.root / "package.json"
        if not pkg.exists():
            return found

        try:
            content = pkg.read_text(errors="replace").lower()
        except OSError:
            return found

        detections: list[tuple[str, str]] = [
            ("react", "ui"),
            ("next", "web"),
            ("vue", "ui"),
            ("angular", "ui"),
            ("express", "web"),
            ("fastify", "web"),
            ("jest", "testing"),
            ("mocha", "testing"),
            ("vitest", "testing"),
        ]
        for name, category in detections:
            if f'"{name}"' in content:
                found.append(FrameworkInfo(name=name, category=category))
        return found

    # ------------------------------------------------------------------
    # Directory tree
    # ------------------------------------------------------------------

    def _build_tree(self) -> str:
        """Build an ASCII directory tree up to ``self.tree_depth`` levels."""
        lines: list[str] = [self.root.name + "/"]
        self._tree_recurse(self.root, "", 0, lines)
        return "\n".join(lines)

    def _tree_recurse(
        self,
        directory: Path,
        prefix: str,
        depth: int,
        acc: list[str],
    ) -> None:
        if depth >= self.tree_depth:
            return
        try:
            entries = sorted(directory.iterdir(), key=lambda e: (e.is_file(), e.name))
        except PermissionError:
            return

        # Filter out skipped dirs
        entries = [
            e
            for e in entries
            if not (e.is_dir() and (e.name in _SKIP_DIRS or (e.name.startswith(".") and e.name != ".github")))
        ]

        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            display = entry.name + ("/" if entry.is_dir() else "")
            acc.append(f"{prefix}{connector}{display}")
            if entry.is_dir():
                extension = "    " if is_last else "│   "
                self._tree_recurse(entry, prefix + extension, depth + 1, acc)
