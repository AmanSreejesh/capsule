"""Scanner: finds the env vars a JS/TS project reads, using tree-sitter syntax trees."""

import os
import subprocess
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path

import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Node, Parser

_JAVASCRIPT = Language(tree_sitter_javascript.language())
_TYPESCRIPT = Language(tree_sitter_typescript.language_typescript())
_TSX = Language(tree_sitter_typescript.language_tsx())

# File extension -> grammar. The JavaScript grammar also understands JSX.
_LANGUAGES = {
    ".js": _JAVASCRIPT,
    ".jsx": _JAVASCRIPT,
    ".mjs": _JAVASCRIPT,
    ".cjs": _JAVASCRIPT,
    ".ts": _TYPESCRIPT,
    ".mts": _TYPESCRIPT,
    ".cts": _TYPESCRIPT,
    ".tsx": _TSX,
}

# Dependency and build-output folders. Also applied to git's file list, in case one is committed.
SKIP_DIRS = frozenset({".git", "node_modules", "dist", "build", ".next", "out", "coverage"})

# Variables that Node tooling and Vite set themselves, so they aren't project requirements.
_BUILT_INS = {
    "process.env": frozenset({"NODE_ENV"}),
    "import.meta.env": frozenset({"MODE", "BASE_URL", "PROD", "DEV", "SSR"}),
}

# TypeScript/grouping wrappers that don't change which object is being read: `(process.env as Env)`.
_WRAPPERS = frozenset(
    {"parenthesized_expression", "as_expression", "satisfies_expression", "non_null_expression"}
)


@dataclass(frozen=True, order=True)
class Location:
    """A place in the project: path relative to the project root (always `/`), 1-based line."""

    path: str
    line: int


@dataclass
class ScanResult:
    # Each env var name the code reads -> every place it's read.
    env_vars: dict[str, list[Location]] = field(default_factory=dict)
    # Reads whose name isn't known until the code runs, e.g. `process.env[name]` or `...rest`.
    dynamic: list[Location] = field(default_factory=list)


def scan_project(
    root: Path,
    *,
    exclude_patterns: tuple[str, ...] = (),
    ignored_env: frozenset[str] = frozenset(),
) -> ScanResult:
    """Scan every JS/TS source file in the project at `root`."""
    result = ScanResult()
    for path in list_source_files(root, exclude_patterns=exclude_patterns):
        _scan_into(result, (root / path).read_bytes(), path)
    for name in ignored_env:
        result.env_vars.pop(name, None)
    return _sorted(result)


def scan_source(source: bytes, path: str) -> ScanResult:
    """Scan one file's contents. `path` picks the grammar and appears in the reported locations."""
    result = ScanResult()
    _scan_into(result, source, path)
    return _sorted(result)


def list_source_files(root: Path, *, exclude_patterns: tuple[str, ...] = ()) -> list[str]:
    """Paths (relative to `root`, with `/`) of the JS/TS files to scan, sorted."""
    candidates = _git_files(root)
    if candidates is None:
        candidates = _walk_files(root)
    # is_file() drops files git still tracks but that were deleted from disk.
    return sorted(
        p
        for p in candidates
        if _is_source_file(p)
        and not any(fnmatchcase(p, pattern) for pattern in exclude_patterns)
        and (root / p).is_file()
    )


def _git_files(root: Path) -> list[str] | None:
    """Files git tracks plus untracked files that aren't gitignored; None if git can't answer."""
    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    # -z separates paths with NUL so names with spaces or non-ASCII characters come through as-is.
    return [p for p in completed.stdout.decode("utf-8").split("\0") if p]


def _walk_files(root: Path) -> list[str]:
    """Fallback for folders that aren't git repos: every file, skipping SKIP_DIRS."""
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            files.append((Path(dirpath) / name).relative_to(root).as_posix())
    return files


def _is_source_file(path: str) -> bool:
    *folders, name = path.split("/")
    return Path(name).suffix in _LANGUAGES and ".min." not in name and SKIP_DIRS.isdisjoint(folders)


def _scan_into(result: ScanResult, source: bytes, path: str) -> None:
    tree = Parser(_LANGUAGES[Path(path).suffix]).parse(source)
    # Walk every node with an explicit stack instead of recursion, so deep nesting can't overflow.
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        _visit(node, path, result)
        stack.extend(node.children)


def _visit(node: Node, path: str, result: ScanResult) -> None:
    if node.type == "member_expression":
        # process.env.API_KEY
        source = _env_source(node.child_by_field_name("object"))
        if source and not _is_write_target(node):
            _record(result, source, _text(node.child_by_field_name("property")), path, node)

    elif node.type == "subscript_expression":
        # process.env["API_KEY"] or process.env[name]
        source = _env_source(node.child_by_field_name("object"))
        if source and not _is_write_target(node):
            name = _literal_string(node.child_by_field_name("index"))
            if name is None:
                result.dynamic.append(_location(path, node))
            else:
                _record(result, source, name, path, node)

    elif node.type == "variable_declarator":
        # const { API_KEY, PORT = 3000 } = process.env
        pattern = node.child_by_field_name("name")
        source = _env_source(_unwrap(node.child_by_field_name("value")))
        if source and pattern is not None and pattern.type == "object_pattern":
            _record_pattern(result, source, pattern, path)


def _record_pattern(result: ScanResult, source: str, pattern: Node, path: str) -> None:
    for child in pattern.named_children:
        if child.type == "shorthand_property_identifier_pattern":  # { A }
            key = child
        elif child.type == "object_assignment_pattern":  # { A = "default" }
            key = child.child_by_field_name("left")
        elif child.type == "pair_pattern":  # { A: renamed }
            key = child.child_by_field_name("key")
        elif child.type == "rest_pattern":  # { ...rest }
            result.dynamic.append(_location(path, child))
            continue
        else:  # comments
            continue

        if key.type in ("property_identifier", "shorthand_property_identifier_pattern"):
            name = _text(key)
        else:
            name = _literal_string(key)  # { "A": renamed }; None for { [name]: value }
        if name is None:
            result.dynamic.append(_location(path, child))
        else:
            _record(result, source, name, path, child)


def _env_source(node: Node | None) -> str | None:
    """Return "process.env" or "import.meta.env" if `node` is that object, else None."""
    if node is None or node.type != "member_expression":
        return None
    owner = node.child_by_field_name("object")
    prop = node.child_by_field_name("property")
    if owner is None or prop is None or _text(prop) != "env":
        return None
    if _text(owner) in ("process", "import.meta"):
        return f"{_text(owner)}.env"
    return None


def _is_write_target(node: Node) -> bool:
    """Return whether code sets or deletes the variable instead of reading it."""
    parent = node.parent
    if parent is None:
        return False
    if parent.type in ("assignment_expression", "augmented_assignment_expression"):
        return parent.child_by_field_name("left") == node
    if parent.type == "unary_expression":
        return _text(parent.child_by_field_name("operator")) == "delete"
    return False


def _literal_string(node: Node | None) -> str | None:
    """The text of a plain string like "X", 'X' or `X`; None for anything computed at runtime."""
    if node is None:
        return None
    is_plain_template = node.type == "template_string" and not any(
        c.type == "template_substitution" for c in node.children
    )
    if node.type == "string" or is_plain_template:
        return _text(node)[1:-1]
    return None


def _unwrap(node: Node | None) -> Node | None:
    while node is not None and node.type in _WRAPPERS and node.named_children:
        node = node.named_children[0]
    return node


def _record(result: ScanResult, source: str, name: str, path: str, node: Node) -> None:
    if name not in _BUILT_INS[source]:
        result.env_vars.setdefault(name, []).append(_location(path, node))


def _location(path: str, node: Node) -> Location:
    return Location(path, node.start_point.row + 1)


def _text(node: Node | None) -> str:
    return node.text.decode("utf-8", errors="replace") if node is not None else ""


def _sorted(result: ScanResult) -> ScanResult:
    """Deterministic output: names alphabetical, locations by path then line, duplicates dropped."""
    return ScanResult(
        env_vars={name: sorted(set(locs)) for name, locs in sorted(result.env_vars.items())},
        dynamic=sorted(set(result.dynamic)),
    )
