import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from capsule_cli import __version__, node_runtime
from capsule_cli.cli import app
from capsule_cli.node_runtime import NodeCheck

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_help_lists_every_command():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("capture", "doctor", "diff", "hook", "export"):
        assert command in result.output


# --- capture ---


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A small JS project; the test runs from inside its src/ folder."""
    (tmp_path / "package.json").write_text('{"engines": {"node": ">=20"}}')
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text("const { API_KEY } = process.env;\n")
    monkeypatch.chdir(tmp_path / "src")
    return tmp_path


def read_capsule(project: Path) -> dict:
    return json.loads((project / "capsule.json").read_text())


def test_capture_creates_file_at_project_root(project):
    result = runner.invoke(app, ["capture"])

    assert result.exit_code == 0
    assert "Created capsule.json: 1 env var. Node >=20 from package.json (engines.node)." in (
        result.output
    )
    assert read_capsule(project) == {
        "format": 1,
        "node": {"version": ">=20", "source": "package.json (engines.node)"},
        "env": {"API_KEY": {"used_in": ["src/app.ts"]}},
    }


def test_second_capture_is_up_to_date(project):
    runner.invoke(app, ["capture"])
    before = (project / "capsule.json").read_text()

    result = runner.invoke(app, ["capture"])

    assert result.exit_code == 0
    assert "capsule.json is up to date: 1 env var." in result.output
    assert (project / "capsule.json").read_text() == before


def test_capture_keeps_notes_and_reports_changes(project):
    (project / "capsule.json").write_text(
        json.dumps(
            {
                "env": {
                    "API_KEY": {"note": "from the dashboard", "used_in": []},
                    "OLD_URL": {"used_in": ["src/old.ts"]},
                    "FLAG_X": {"manual": True},
                }
            }
        )
    )
    (project / "src" / "db.ts").write_text("process.env.DATABASE_URL;\n")

    result = runner.invoke(app, ["capture"])

    assert result.exit_code == 0
    assert "Updated capsule.json: 3 env vars (+1 new, -1 removed)." in result.output
    assert "  + DATABASE_URL" in result.output
    assert "  - OLD_URL" in result.output
    env = read_capsule(project)["env"]
    assert env["API_KEY"] == {"note": "from the dashboard", "used_in": ["src/app.ts"]}
    assert env["FLAG_X"] == {"manual": True, "used_in": []}
    assert "OLD_URL" not in env


def test_capture_refuses_to_overwrite_broken_file(project):
    broken = '{"env": {"API_KEY": {"note": "keep me",}}}'
    (project / "capsule.json").write_text(broken)

    result = runner.invoke(app, ["capture"])

    assert result.exit_code == 1
    assert "capsule.json is not valid JSON (line 1, column 40" in result.output
    assert "the file was not changed" in result.output
    assert (project / "capsule.json").read_text() == broken


def test_capture_warns_about_dynamic_reads(project):
    (project / "src" / "flags.ts").write_text("\nconst on = process.env[`FEATURE_${name}`];\n")

    result = runner.invoke(app, ["capture"])

    assert result.exit_code == 0
    assert "Warning: 1 env read whose name capsule can't work out:" in result.output
    assert "  src/flags.ts:2" in result.output


def test_capture_suggests_declaring_node_version(project):
    (project / "package.json").write_text("{}")

    result = runner.invoke(app, ["capture"])

    assert "No Node version declared." in result.output
    assert "Tip: add a .nvmrc file" in result.output


def test_capture_check_passes_when_current_and_fails_without_writing_when_stale(project):
    runner.invoke(app, ["capture"])
    assert runner.invoke(app, ["capture", "--check"]).exit_code == 0
    before = (project / "capsule.json").read_text()
    (project / "src" / "new.ts").write_text("process.env.NEW_REQUIREMENT;\n")

    result = runner.invoke(app, ["capture", "--check"])

    assert result.exit_code == 1
    assert "missing or out of date" in result.output
    assert (project / "capsule.json").read_text() == before


def test_capture_applies_pyproject_configuration(project):
    (project / "src" / "fixture.ts").write_text("process.env.FAKE_FIXTURE;\n")
    (project / "src" / "app.ts").write_text("process.env.API_KEY; process.env.PLATFORM_PROVIDED;\n")
    (project / "pyproject.toml").write_text(
        """
[tool.capsule]
exclude = ["src/fixture.ts"]
ignore-env = ["PLATFORM_PROVIDED"]
"""
    )

    result = runner.invoke(app, ["capture"])

    assert result.exit_code == 0
    assert set(read_capsule(project)["env"]) == {"API_KEY"}


def test_capture_reports_invalid_configuration(project):
    (project / "pyproject.toml").write_text('[tool.capsule]\nexclude = "src/**"\n')
    result = runner.invoke(app, ["capture"])
    assert result.exit_code == 1
    assert "tool.capsule.exclude must be an array" in result.output


# --- doctor ---


def test_doctor_checks_dotenv_and_reports_unused(project, monkeypatch):
    runner.invoke(app, ["capture"])
    (project / ".env").write_text("API_KEY=secret\nOLD_SETTING=unused\n")
    monkeypatch.setattr(
        node_runtime,
        "check_node",
        lambda declared: NodeCheck("20.11.1", True, "expected >=20"),
    )

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "1/1 required variables available" in result.output
    assert "OLD_SETTING (.env)" in result.output
    assert "Ready to develop" in result.output
    assert "secret" not in result.output


def test_doctor_fails_for_missing_required_var_and_bad_node(project, monkeypatch):
    runner.invoke(app, ["capture"])
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setattr(
        node_runtime,
        "check_node",
        lambda declared: NodeCheck("18.0.0", False, "expected >=20"),
    )

    result = runner.invoke(app, ["doctor", "--env-file", "missing.env"])

    assert result.exit_code == 1
    assert "missing API_KEY" in result.output
    assert "incompatible" in result.output
    assert "2 blocking setup issue" in result.output


def test_doctor_does_not_fail_for_missing_optional_var(project, monkeypatch):
    runner.invoke(app, ["capture"])
    data = read_capsule(project)
    data["env"]["API_KEY"]["optional"] = True
    (project / "capsule.json").write_text(json.dumps(data))
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setattr(
        node_runtime,
        "check_node",
        lambda declared: NodeCheck("20.0.0", True, "expected >=20"),
    )
    result = runner.invoke(app, ["doctor", "--env-file", "missing.env"])
    assert result.exit_code == 0
    assert "optional API_KEY is not set" in result.output


def test_doctor_uses_configured_env_files(project, monkeypatch):
    runner.invoke(app, ["capture"])
    (project / "pyproject.toml").write_text('[tool.capsule]\nenv-files = [".env.development"]\n')
    (project / ".env.development").write_text("API_KEY=local-only\n")
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setattr(
        node_runtime,
        "check_node",
        lambda declared: NodeCheck("20.0.0", True, "expected >=20"),
    )

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "1/1 required variables available" in result.output
    assert "local-only" not in result.output


# --- generated env example ---


def test_export_env_example_includes_notes_and_optional_marker(project):
    runner.invoke(app, ["capture"])
    data = read_capsule(project)
    data["env"]["API_KEY"].update({"note": "Create one in the dashboard", "optional": True})
    (project / "capsule.json").write_text(json.dumps(data))

    result = runner.invoke(app, ["export", "env-example"])

    assert result.exit_code == 0
    text = (project / ".env.example").read_text()
    assert "# Create one in the dashboard\n# Optional\nAPI_KEY=" in text
    assert runner.invoke(app, ["export", "env-example", "--check"]).exit_code == 0


def test_export_refuses_to_replace_human_file_without_force(project):
    runner.invoke(app, ["capture"])
    (project / ".env.example").write_text("HAND_WRITTEN=\n")
    result = runner.invoke(app, ["export", "env-example"])
    assert result.exit_code == 1
    assert "--force" in result.output
    assert (project / ".env.example").read_text() == "HAND_WRITTEN=\n"


# --- diff and hooks ---


def _git_commit(project: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=project, check=True)
    subprocess.run(["git", "add", "capsule.json"], cwd=project, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=project, check=True)


def test_diff_renders_worktree_changes_as_markdown(project):
    runner.invoke(app, ["capture"])
    _git_commit(project)
    data = read_capsule(project)
    data["env"]["NEW_VAR"] = {"manual": True, "used_in": []}
    (project / "capsule.json").write_text(json.dumps(data))

    result = runner.invoke(app, ["diff", "--base", "HEAD", "--format", "markdown"])

    assert result.exit_code == 0
    assert "## Capsule environment report" in result.output
    assert "- `NEW_VAR`" in result.output


def test_hook_install_and_uninstall(project):
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    installed = runner.invoke(app, ["hook", "install"])
    assert installed.exit_code == 0
    assert "post-merge" in installed.output
    assert "capsule doctor" in (project / ".git" / "hooks" / "post-merge").read_text()
    removed = runner.invoke(app, ["hook", "uninstall"])
    assert removed.exit_code == 0
    assert not (project / ".git" / "hooks" / "post-merge").exists()
