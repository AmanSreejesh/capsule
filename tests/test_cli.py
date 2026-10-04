import pytest
from typer.testing import CliRunner

from capsule_cli import __version__
from capsule_cli.cli import app

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


# Placeholders until each command is built; remove a case as its command is implemented.
@pytest.mark.parametrize(
    "args",
    [
        ["capture"],
        ["capture", "--check"],
        ["doctor"],
        ["diff"],
        ["hook", "install"],
        ["hook", "uninstall"],
        ["export", "env-example"],
    ],
)
def test_placeholder_commands_exit_with_error(args):
    result = runner.invoke(app, args)
    assert result.exit_code == 1
    assert "not implemented yet" in result.output
