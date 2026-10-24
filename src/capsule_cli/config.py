"""Load optional Capsule settings from a project's pyproject.toml."""

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CapsuleConfig:
    exclude: tuple[str, ...] = ()
    ignore_env: frozenset[str] = frozenset()
    env_files: tuple[str, ...] = (".env", ".env.local")


class ConfigError(Exception):
    """The project's Capsule configuration is invalid."""


def load_config(root: Path) -> CapsuleConfig:
    """Load ``[tool.capsule]`` or return zero-config defaults."""
    path = root / "pyproject.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return CapsuleConfig()
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Could not read {path.name}: {error}") from error

    section = data.get("tool", {}).get("capsule", {})
    if not isinstance(section, dict):
        raise ConfigError("[tool.capsule] must be a TOML table.")
    allowed = {"exclude", "ignore-env", "env-files"}
    unknown = sorted(set(section) - allowed)
    if unknown:
        raise ConfigError(f"Unknown [tool.capsule] setting(s): {', '.join(unknown)}.")

    exclude = _string_list(section, "exclude", ())
    ignore_env = _string_list(section, "ignore-env", ())
    env_files = _string_list(section, "env-files", (".env", ".env.local"))
    for name in ignore_env:
        if not name or not name.replace("_", "a").isalnum() or name[0].isdigit():
            raise ConfigError(f"Invalid environment variable name in ignore-env: {name!r}.")
    return CapsuleConfig(exclude, frozenset(ignore_env), env_files)


def _string_list(section: dict, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = section.get(key, default)
    if not isinstance(value, list | tuple) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ConfigError(f"tool.capsule.{key} must be an array of non-empty strings.")
    return tuple(dict.fromkeys(value))
