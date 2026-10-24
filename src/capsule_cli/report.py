"""Compare capsule snapshots and render human-readable requirement reports."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from capsule_cli.capsule_file import CapsuleFileError


@dataclass(frozen=True)
class CapsuleDiff:
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[str, ...]
    node_before: str | None
    node_after: str | None

    @property
    def is_empty(self) -> bool:
        has_env_changes = self.added or self.removed or self.changed
        return not (has_env_changes or self.node_before != self.node_after)


def compare(before: dict | None, after: dict) -> CapsuleDiff:
    before = before or {"env": {}, "node": None}
    old_env = before.get("env", {})
    new_env = after.get("env", {})
    shared = set(old_env) & set(new_env)
    # used_in is intentionally excluded: moving code should not read as a new setup requirement.
    changed = tuple(
        sorted(
            name for name in shared if _human_fields(old_env[name]) != _human_fields(new_env[name])
        )
    )
    return CapsuleDiff(
        added=tuple(sorted(set(new_env) - set(old_env))),
        removed=tuple(sorted(set(old_env) - set(new_env))),
        changed=changed,
        node_before=_node_value(before),
        node_after=_node_value(after),
    )


def load_from_git(root: Path, ref: str) -> dict | None:
    """Load capsule.json from a Git revision; None means it did not exist at that revision."""
    completed = subprocess.run(
        ["git", "show", f"{ref}:capsule.json"], cwd=root, capture_output=True, text=True
    )
    if completed.returncode:
        missing = subprocess.run(
            ["git", "cat-file", "-e", f"{ref}^{{commit}}"], cwd=root, capture_output=True
        )
        if missing.returncode:
            raise CapsuleFileError(f"Git revision {ref!r} does not exist.")
        return None
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise CapsuleFileError(f"capsule.json at {ref!r} is not valid JSON.") from error
    if not isinstance(data, dict) or not isinstance(data.get("env", {}), dict):
        raise CapsuleFileError(f"capsule.json at {ref!r} has an unsupported shape.")
    return data


def render(diff: CapsuleDiff, *, markdown: bool, base: str) -> str:
    if markdown:
        lines = ["## Capsule environment report", "", f"Compared with `{base}`.", ""]
        if diff.is_empty:
            return "\n".join([*lines, "No setup requirements changed."])
        if diff.node_before != diff.node_after:
            old_node = diff.node_before or "not declared"
            new_node = diff.node_after or "not declared"
            lines.extend(["### Node", "", f"`{old_node}` → `{new_node}`", ""])
        _markdown_section(lines, "Added environment variables", diff.added)
        _markdown_section(lines, "Removed environment variables", diff.removed)
        _markdown_section(lines, "Updated annotations", diff.changed)
        return "\n".join(lines).rstrip()

    if diff.is_empty:
        return f"No setup requirements changed compared with {base}."
    lines = [f"Environment requirement changes compared with {base}:"]
    if diff.node_before != diff.node_after:
        old_node = diff.node_before or "not declared"
        new_node = diff.node_after or "not declared"
        lines.append(f"  Node: {old_node} -> {new_node}")
    lines.extend(f"  + {name}" for name in diff.added)
    lines.extend(f"  - {name}" for name in diff.removed)
    lines.extend(f"  ~ {name} (annotations changed)" for name in diff.changed)
    return "\n".join(lines)


def _human_fields(entry: dict) -> dict:
    return {key: value for key, value in entry.items() if key != "used_in"}


def _node_value(data: dict) -> str | None:
    node = data.get("node")
    return node.get("version") if isinstance(node, dict) else None


def _markdown_section(lines: list[str], title: str, names: tuple[str, ...]) -> None:
    if names:
        lines.extend([f"### {title}", "", *(f"- `{name}`" for name in names), ""])
