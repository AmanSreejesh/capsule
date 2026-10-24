"""Inspect the local Node runtime and compare it with a project's declaration."""

import re
import subprocess
from dataclasses import dataclass

_VERSION = re.compile(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")
_COMPARATOR = re.compile(r"(>=|<=|>|<|=|~\s*|\^\s*)?v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")


@dataclass(frozen=True)
class NodeCheck:
    installed: str | None
    compatible: bool | None
    explanation: str


def installed_node_version() -> str | None:
    """Return ``node --version`` without its leading v, or None when Node is unavailable."""
    try:
        completed = subprocess.run(
            ["node", "--version"], capture_output=True, text=True, check=True, timeout=5
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    value = completed.stdout.strip()
    match = _VERSION.fullmatch(value)
    return ".".join(part for part in match.groups() if part is not None) if match else value or None


def check_node(declared: str, installed: str | None = None) -> NodeCheck:
    """Compare an installed version with common Node version-file and engines syntax.

    Exact versions and bare majors require the same major. Common npm comparator ranges,
    caret ranges and tilde ranges are evaluated. Named releases such as ``lts/iron`` are
    reported as unverifiable rather than incorrectly rejected.
    """
    installed = installed if installed is not None else installed_node_version()
    if installed is None:
        return NodeCheck(None, False, "Node is not installed or is not on PATH")
    actual = _parse_version(installed)
    if actual is None:
        return NodeCheck(installed, None, "the installed Node version could not be parsed")

    wanted = declared.strip()
    if wanted.startswith("lts/") or wanted in {"node", "stable", "latest", "lts/*"}:
        return NodeCheck(
            installed, None, f"{wanted!r} is a named release and cannot be checked offline"
        )

    # A version manager's exact or partial value is intentionally major-compatible: teammates
    # can receive compatible patch updates without making doctor noisy.
    if _VERSION.fullmatch(wanted):
        expected = _parse_version(wanted)
        ok = expected is not None and actual[0] == expected[0]
        return NodeCheck(installed, ok, f"expected Node major {expected[0]}")

    comparators = list(_COMPARATOR.finditer(wanted))
    if not comparators or not _range_is_fully_understood(wanted, comparators):
        return NodeCheck(installed, None, f"the declared range {wanted!r} is not understood")
    ok = all(_satisfies(actual, match) for match in comparators)
    return NodeCheck(installed, ok, f"expected {wanted}")


def _range_is_fully_understood(wanted: str, comparators: list[re.Match[str]]) -> bool:
    """Reject partially parsed ranges instead of returning a misleading compatibility result."""
    cursor = 0
    for match in comparators:
        if wanted[cursor : match.start()].strip():
            return False
        cursor = match.end()
    return not wanted[cursor:].strip()


def _parse_version(value: str) -> tuple[int, int, int] | None:
    match = _VERSION.fullmatch(value.strip())
    if not match:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor or 0), int(patch or 0)


def _satisfies(actual: tuple[int, int, int], match: re.Match[str]) -> bool:
    operator, major, minor, patch = match.groups()
    expected = (int(major), int(minor or 0), int(patch or 0))
    if operator is None or operator == "=":
        return actual[0] == expected[0] if minor is None else actual == expected
    if operator == ">=":
        return actual >= expected
    if operator == "<=":
        return actual <= expected
    if operator == ">":
        return actual > expected
    if operator == "<":
        return actual < expected
    if operator.strip() == "^":
        upper = (expected[0] + 1, 0, 0) if expected[0] else (0, expected[1] + 1, 0)
        return expected <= actual < upper
    if operator.strip() == "~":
        upper = (expected[0], expected[1] + 1, 0)
        return expected <= actual < upper
    return False
