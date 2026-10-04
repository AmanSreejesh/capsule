"""Command-line interface: defines every capsule command and its options."""

from typing import Annotated

import typer

from capsule_cli import __version__

app = typer.Typer(
    help="Track the environment your project needs and flag changes to it in pull requests.",
    no_args_is_help=True,
)
hook_app = typer.Typer(
    help="Manage the git hook that runs `capsule doctor` after pulls and checkouts.",
    no_args_is_help=True,
)
export_app = typer.Typer(
    help="Generate standard project files from the capsule file.",
    no_args_is_help=True,
)
app.add_typer(hook_app, name="hook")
app.add_typer(export_app, name="export")


def _not_implemented(command: str) -> None:
    typer.echo(f"`capsule {command}` is not implemented yet.", err=True)
    raise typer.Exit(code=1)


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"capsule {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_show_version,
            is_eager=True,
            help="Show the version and exit.",
        ),
    ] = False,
) -> None:
    pass


@app.command()
def capture(
    check: Annotated[
        bool,
        typer.Option(
            "--check",
            help="Write nothing; exit with an error if the capsule file is out of date (for CI).",
        ),
    ] = False,
) -> None:
    """Scan the project and write or update the capsule file."""
    _not_implemented("capture --check" if check else "capture")


@app.command()
def doctor() -> None:
    """Compare this machine against the capsule file."""
    _not_implemented("doctor")


@app.command()
def diff() -> None:
    """Report requirement changes compared with the base branch."""
    _not_implemented("diff")


@hook_app.command("install")
def hook_install() -> None:
    """Install a git hook that runs `capsule doctor` after pulls and checkouts."""
    _not_implemented("hook install")


@hook_app.command("uninstall")
def hook_uninstall() -> None:
    """Remove the capsule git hook."""
    _not_implemented("hook uninstall")


@export_app.command("env-example")
def export_env_example() -> None:
    """Write a .env.example file listing every required env var."""
    _not_implemented("export env-example")
