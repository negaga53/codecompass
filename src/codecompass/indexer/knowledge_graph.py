"""In-memory knowledge graph of modules, imports, and symbols."""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from codecompass.models import ImportEdge, SymbolNode

logger = logging.getLogger(__name__)


class KnowledgeGraph:
    """Builds and queries an in-memory graph of Python source symbols and
    import relationships.

    Currently supports Python only.  Other languages can be added behind the
    same interface by introducing language-specific parsers.
    """

    def __init__(self) -> None:
        self.symbols: dict[str, SymbolNode] = {}
        self.imports: list[ImportEdge] = []
        # Adjacency lists for quick traversal
        self._deps: dict[str, set[str]] = {}       # module → modules it imports
        self._rdeps: dict[str, set[str]] = {}       # module → modules that import it

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------

    def build(self, repo_root: str | Path) -> None:
        """Scan all Python files under *repo_root* and populate the graph.

        Args:
            repo_root: The repository root directory.
        """
        root = Path(repo_root).resolve()
        for py_file in root.rglob("*.py"):
            # Skip hidden and venv directories
            parts = py_file.relative_to(root).parts
            if any(p.startswith(".") or p in {"node_modules", "__pycache__", "venv", ".venv"} for p in parts):
                continue
            self._index_file(py_file, root)

        logger.info(
            "Knowledge graph built: %d symbols, %d import edges",
            len(self.symbols),
            len(self.imports),
        )

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def query(self, symbol_name: str) -> list[SymbolNode]:
        """Find symbols whose name contains *symbol_name* (case-insensitive).

        Returns:
            Matching ``SymbolNode`` objects.
        """
        needle = symbol_name.lower()
        return [s for s in self.symbols.values() if needle in s.name.lower()]

    def dependencies(self, module: str) -> set[str]:
        """Return the set of modules that *module* imports."""
        return self._deps.get(module, set())

    def dependents(self, module: str) -> set[str]:
        """Return the set of modules that import *module*."""
        return self._rdeps.get(module, set())

    def all_modules(self) -> list[str]:
        """Return a sorted list of all indexed module names."""
        modules: set[str] = set()
        for edge in self.imports:
            modules.add(edge.source_module)
            modules.add(edge.target_module)
        return sorted(modules)

    # ------------------------------------------------------------------
    # Internal: file indexing
    # ------------------------------------------------------------------

    def _index_file(self, path: Path, root: Path) -> None:
        """Parse a single Python file and extract symbols + imports."""
        try:
            source = path.read_text(errors="replace")
            tree = ast.parse(source, filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            logger.debug("Skipping unparseable file: %s", path)
            return

        module_name = self._path_to_module(path, root)

        for node in ast.walk(tree):
            # --- Symbols ---
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                key = f"{module_name}.{node.name}"
                self.symbols[key] = SymbolNode(
                    name=node.name,
                    kind="function",
                    file=str(path.relative_to(root)),
                    line=node.lineno,
                    docstring=ast.get_docstring(node) or "",
                )
            elif isinstance(node, ast.ClassDef):
                key = f"{module_name}.{node.name}"
                self.symbols[key] = SymbolNode(
                    name=node.name,
                    kind="class",
                    file=str(path.relative_to(root)),
                    line=node.lineno,
                    docstring=ast.get_docstring(node) or "",
                )
            # --- Imports ---
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self._add_import(module_name, alias.name, [alias.asname or alias.name])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    names = [a.name for a in node.names]
                    self._add_import(module_name, node.module, names)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_import(self, source: str, target: str, names: list[str]) -> None:
        edge = ImportEdge(
            source_module=source,
            target_module=target,
            imported_names=names,
        )
        self.imports.append(edge)
        self._deps.setdefault(source, set()).add(target)
        self._rdeps.setdefault(target, set()).add(source)

    @staticmethod
    def _path_to_module(path: Path, root: Path) -> str:
        """Convert a file path to a dotted Python module name.

        Strips a leading ``src`` directory when it is used as a layout
        directory (i.e. ``src/package/…``) so that the resulting module
        name matches actual Python import paths.
        """
        rel = path.relative_to(root).with_suffix("")
        parts = list(rel.parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        # Strip src layout prefix
        if parts and parts[0] == "src":
            parts = parts[1:]
        return ".".join(parts)
