"""capsule.json: finding, loading, building and writing the committed capsule file."""

import json
import os
import tempfile
from pathlib import Path

from capsule_cli.node_version import NodeVersion
from capsule_cli.scanner import ScanResult

FILE_NAME = "capsule.json"
FORMAT = 1


class CapsuleFileError(Exception):
    """capsule.json exists but can't be used. It must be left untouched so no notes are lost."""


def find_project_root(start: Path) -> Path:
    """Find the nearest parent with capsule.json or package.json, falling back to `start`."""
    start = start.resolve()
    for folder in (start, *start.parents):
        if (folder / FILE_NAME).is_file() or (folder / "package.json").is_file():
            return folder
    return start


def load(path: Path) -> dict | None:
    """The parsed file, or None if it doesn't exist yet."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise CapsuleFileError(
            f"{path.name} is not valid JSON "
            f"(line {error.lineno}, column {error.colno}: {error.msg})."
        ) from error
    _check_shape(data, path.name)
    return data


def build(scan: ScanResult, node: NodeVersion | None, existing: dict | None) -> dict:
    """New file contents: fresh scan results plus every human-written field from `existing`.

    Capsule owns `node` and each entry's `used_in`; every other field is kept as written.
    A variable the code no longer reads is dropped unless it's marked `"manual": true`.
    """
    existing = existing or {}
    old_env = existing.get("env", {})
    manual = {name for name, entry in old_env.items() if entry.get("manual")}

    env = {}
    for name in sorted(set(scan.env_vars) | manual):
        entry = {key: value for key, value in old_env.get(name, {}).items() if key != "used_in"}
        entry["used_in"] = sorted({loc.path for loc in scan.env_vars.get(name, [])})
        env[name] = dict(sorted(entry.items()))

    data = {
        "format": FORMAT,
        "node": {"version": node.value, "source": node.source} if node else None,
        "env": env,
    }
    # Keep any other top-level fields people added, after capsule's own.
    for key, value in sorted(existing.items()):
        data.setdefault(key, value)
    return data


def dumps(data: dict) -> str:
    """The standard text for `data`, so the same contents always produce the same file."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_if_changed(path: Path, data: dict) -> bool:
    """Write in the standard format, returning False when the text is already current."""
    text = dumps(data)
    try:
        # read_text normalizes Windows line endings, so CRLF checkouts still compare equal.
        if path.read_text(encoding="utf-8-sig") == text:
            return False
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        mode = path.stat().st_mode if path.exists() else 0o644
        temp_path.chmod(mode)
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    return True


def _check_shape(data: object, name: str) -> None:
    if not isinstance(data, dict):
        raise CapsuleFileError(f"{name} must contain a JSON object.")
    if data.get("format", FORMAT) != FORMAT:
        raise CapsuleFileError(
            f"{name} uses format {data['format']!r}, "
            f"but this version of capsule reads format {FORMAT}."
        )
    env = data.get("env", {})
    if not isinstance(env, dict):
        raise CapsuleFileError(
            f'"env" in {name} must be an object mapping variable names to entries.'
        )
    for var_name, entry in env.items():
        if not isinstance(entry, dict):
            raise CapsuleFileError(
                f'"env.{var_name}" in {name} must be an object, e.g. {{"note": "..."}}.'
            )
