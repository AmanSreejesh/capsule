"""Read environment variable names from dotenv files without exposing their values."""

import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ENV_FILES = (".env", ".env.local")
_ASSIGNMENT = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


@dataclass(frozen=True)
class EnvFileResult:
    """Names found in local dotenv files and the file each name came from."""

    names: frozenset[str]
    sources: dict[str, tuple[str, ...]]
    files: tuple[str, ...]


def read_env_files(root: Path, paths: list[Path] | None = None) -> EnvFileResult:
    """Read names only from existing dotenv files.

    Explicit relative paths are resolved from the project root. Missing explicit files are
    represented in ``files`` so callers can explain what was checked.
    """
    candidates = paths or [Path(name) for name in DEFAULT_ENV_FILES]
    sources: dict[str, list[str]] = {}
    files: list[str] = []
    for candidate in candidates:
        path = candidate if candidate.is_absolute() else root / candidate
        display = _display_path(root, path)
        if paths is not None or path.is_file():
            files.append(display)
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError):
            continue
        for line in lines:
            match = _ASSIGNMENT.match(line.strip())
            if match:
                sources.setdefault(match.group(1), []).append(display)
    return EnvFileResult(
        names=frozenset(sources),
        sources={name: tuple(dict.fromkeys(found)) for name, found in sorted(sources.items())},
        files=tuple(files),
    )


def _display_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())
