import pytest

from capsule_cli.config import CapsuleConfig, ConfigError, load_config


def test_defaults_without_pyproject(tmp_path):
    assert load_config(tmp_path) == CapsuleConfig()


def test_loads_project_settings(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.capsule]
exclude = ["fixtures/**", "generated/*.js"]
ignore-env = ["CI", "VERCEL"]
env-files = [".env.development", ".env.local"]
"""
    )
    config = load_config(tmp_path)
    assert config.exclude == ("fixtures/**", "generated/*.js")
    assert config.ignore_env == {"CI", "VERCEL"}
    assert config.env_files == (".env.development", ".env.local")


@pytest.mark.parametrize(
    "body, message",
    [
        ('exclude = "dist/**"', "must be an array"),
        ('ignore-env = ["BAD-NAME"]', "Invalid environment variable"),
        ("unknown = []", "Unknown"),
    ],
)
def test_invalid_settings_fail_loudly(tmp_path, body, message):
    (tmp_path / "pyproject.toml").write_text(f"[tool.capsule]\n{body}\n")
    with pytest.raises(ConfigError, match=message):
        load_config(tmp_path)
