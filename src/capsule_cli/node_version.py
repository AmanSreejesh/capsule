"""Read the Node version a project declares, never the one installed on this machine."""

import json
from dataclasses import dataclass
from pathlib import Path

# Checked in order; the first file that declares a version wins. Version-manager files say which
# version to install, so they come before engines.node, which is often a broad range like ">=18".
_SOURCES = [
    (".nvmrc", lambda root: _first_line(root / ".nvmrc")),
    (".node-version", lambda root: _first_line(root / ".node-version")),
    (".tool-versions", lambda root: _tool_versions_node(root / ".tool-versions")),
    ("package.json (volta.node)", lambda root: _package_json_field(root, "volta", "node")),
    ("package.json (engines.node)", lambda root: _package_json_field(root, "engines", "node")),
]


@dataclass(frozen=True)
class NodeVersion:
    """A Node version exactly as declared (such as "20.11.1", "lts/iron", or ">=18")."""

    value: str
    source: str


def find_node_version(root: Path) -> NodeVersion | None:
    """The Node version the project at `root` declares, or None if no file declares one."""
    for source, read in _SOURCES:
        value = read(root)
        if value:
            return NodeVersion(value, source)
    return None


def _first_line(path: Path) -> str | None:
    lines = _lines(path)
    return lines[0] if lines else None


def _tool_versions_node(path: Path) -> str | None:
    # Lines look like "nodejs 20.11.1". asdf names the tool `nodejs`; mise also accepts `node`.
    # Extra versions after the first are fallbacks, so the first is the one to install.
    for line in _lines(path):
        tool, *versions = line.split()
        if tool in ("nodejs", "node") and versions:
            return versions[0]
    return None


def _package_json_field(root: Path, *keys: str) -> str | None:
    """A nested string field such as `engines.node`; None if missing, not a string, or bad JSON."""
    try:
        data = json.loads((root / "package.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data.strip() if isinstance(data, str) else None


def _lines(path: Path) -> list[str]:
    """Non-empty lines with `#` comments removed; empty if the file is missing or unreadable."""
    try:
        # utf-8-sig also accepts files that some Windows editors save with a byte-order mark.
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, ValueError):
        return []
    stripped = (line.split("#", 1)[0].strip() for line in text.splitlines())
    return [line for line in stripped if line]
