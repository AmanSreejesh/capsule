"""Install and remove Capsule's small, clearly delimited Git hook blocks."""

import stat
import subprocess
from pathlib import Path

START = "# >>> capsule doctor >>>"
END = "# <<< capsule doctor <<<"
BLOCK = f"""{START}
if command -v capsule >/dev/null 2>&1; then
  capsule doctor || true
else
  python -m capsule_cli doctor || true
fi
{END}
"""
HOOKS = ("post-merge", "post-checkout")


class HookError(Exception):
    pass


def hooks_dir(root: Path) -> Path:
    completed = subprocess.run(
        ["git", "rev-parse", "--git-path", "hooks"], cwd=root, capture_output=True, text=True
    )
    if completed.returncode:
        raise HookError("This project is not a Git repository.")
    path = Path(completed.stdout.strip())
    return path if path.is_absolute() else root / path


def install(root: Path) -> list[str]:
    directory = hooks_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    changed = []
    for name in HOOKS:
        path = directory / name
        old = path.read_text(encoding="utf-8") if path.exists() else "#!/bin/sh\n"
        if START in old:
            continue
        separator = "" if old.endswith("\n") else "\n"
        path.write_text(f"{old}{separator}{BLOCK}", encoding="utf-8", newline="\n")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        changed.append(name)
    return changed


def uninstall(root: Path) -> list[str]:
    directory = hooks_dir(root)
    changed = []
    for name in HOOKS:
        path = directory / name
        if not path.exists():
            continue
        old = path.read_text(encoding="utf-8")
        new = _without_block(old)
        if new == old:
            continue
        if new.strip() in {"", "#!/bin/sh"}:
            path.unlink()
        else:
            path.write_text(new, encoding="utf-8", newline="\n")
        changed.append(name)
    return changed


def _without_block(text: str) -> str:
    start = text.find(START)
    if start < 0:
        return text
    end = text.find(END, start)
    if end < 0:
        return text
    end += len(END)
    if end < len(text) and text[end] == "\n":
        end += 1
    return (text[:start] + text[end:]).rstrip() + "\n"
