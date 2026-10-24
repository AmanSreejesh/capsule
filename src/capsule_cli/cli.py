"""Command-line interface: defines every capsule command and its options."""

import os
from pathlib import Path
from typing import Annotated

import typer

from capsule_cli import __version__, capsule_file, hooks, node_runtime, report
from capsule_cli.config import CapsuleConfig, ConfigError, load_config
from capsule_cli.env_files import DEFAULT_ENV_FILES, read_env_files
from capsule_cli.node_version import NodeVersion, find_node_version
from capsule_cli.scanner import ScanResult, scan_project

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
    root = capsule_file.find_project_root(Path.cwd())
    config = _load_config(root)
    path = root / capsule_file.FILE_NAME
    try:
        existing = capsule_file.load(path)
    except capsule_file.CapsuleFileError as error:
        typer.echo(
            f"Error: {error} Fix it and run `capsule capture` again; the file was not changed.",
            err=True,
        )
        raise typer.Exit(code=1) from None

    scan = scan_project(root, exclude_patterns=config.exclude, ignored_env=config.ignore_env)
    node = find_node_version(root)
    data = capsule_file.build(scan, node, existing)
    if check:
        if existing == data:
            typer.echo(f"{capsule_file.FILE_NAME} is up to date.")
            _print_scan_warnings(scan)
            return
        typer.echo(
            f"Error: {capsule_file.FILE_NAME} is missing or out of date. "
            "Run `capsule capture` and commit the result.",
            err=True,
        )
        _print_scan_warnings(scan)
        raise typer.Exit(code=1)
    changed = capsule_file.write_if_changed(path, data)
    _print_capture_summary(existing, data, changed, scan, node)


def _print_capture_summary(
    existing: dict | None, data: dict, changed: bool, scan: ScanResult, node: NodeVersion | None
) -> None:
    name = capsule_file.FILE_NAME
    old_names = set((existing or {}).get("env", {}))
    new_names = set(data["env"])
    added = sorted(new_names - old_names)
    removed = sorted(old_names - new_names)

    count = _plural(len(new_names), "env var")
    node_text = f"Node {node.value} from {node.source}." if node else "No Node version declared."
    if existing is None:
        typer.echo(f"Created {name}: {count}. {node_text}")
    elif changed:
        changes = f" (+{len(added)} new, -{len(removed)} removed)" if added or removed else ""
        typer.echo(f"Updated {name}: {count}{changes}. {node_text}")
        for var in added:
            typer.echo(f"  + {var}")
        for var in removed:
            typer.echo(f"  - {var}")
    else:
        typer.echo(f"{name} is up to date: {count}. {node_text}")

    _print_scan_warnings(scan)
    if node is None:
        typer.echo(
            "Tip: add a .nvmrc file containing your Node version (for example 20) "
            "so teammates know which version to install.",
            err=True,
        )


def _print_scan_warnings(scan: ScanResult) -> None:
    if scan.dynamic:
        typer.echo(
            f"Warning: {_plural(len(scan.dynamic), 'env read')} whose name capsule can't work out:",
            err=True,
        )
        for loc in scan.dynamic:
            typer.echo(f"  {loc.path}:{loc.line}", err=True)
        typer.echo(
            f"  Add any variables the project needs from these to {capsule_file.FILE_NAME} "
            'with "manual": true.',
            err=True,
        )


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


@app.command()
def doctor(
    env_file: Annotated[
        list[Path] | None,
        typer.Option(
            "--env-file",
            help="Dotenv file to check (repeatable). Defaults to existing .env and .env.local.",
        ),
    ] = None,
) -> None:
    """Compare this machine against the capsule file."""
    root = capsule_file.find_project_root(Path.cwd())
    config = _load_config(root)
    data = _load_capsule(root)
    configured_files = [Path(name) for name in config.env_files]
    default_files = config.env_files == DEFAULT_ENV_FILES
    local = read_env_files(root, env_file or (None if default_files else configured_files))
    shell_names = set(os.environ)
    available = shell_names | set(local.names)
    required = {
        name for name, entry in data.get("env", {}).items() if not entry.get("optional", False)
    }
    optional = set(data.get("env", {})) - required
    missing = sorted(required - available)
    optional_missing = sorted(optional - available)
    unused = sorted(set(local.names) - set(data.get("env", {})))

    typer.echo(f"Checking {root.name} against {capsule_file.FILE_NAME}...")
    if required:
        found_count = len(required) - len(missing)
        typer.echo(f"  Environment: {found_count}/{len(required)} required variables available")
    else:
        typer.echo("  Environment: no required variables")
    for name in missing:
        entry = data["env"][name]
        note = f" - {entry['note']}" if entry.get("note") else ""
        typer.echo(f"    missing {name}{note}", err=True)
    for name in optional_missing:
        typer.echo(f"    optional {name} is not set")

    node_failed = False
    declared_node = data.get("node")
    if isinstance(declared_node, dict):
        node_check = node_runtime.check_node(str(declared_node.get("version", "")))
        if node_check.compatible is True:
            typer.echo(f"  Node: {node_check.installed} is compatible ({node_check.explanation})")
        elif node_check.compatible is False:
            typer.echo(
                f"  Node: incompatible - {node_check.installed or 'not installed'}; "
                f"{node_check.explanation}",
                err=True,
            )
            node_failed = True
        else:
            typer.echo(
                f"  Node: {node_check.installed}; warning: {node_check.explanation}", err=True
            )
    else:
        typer.echo("  Node: no version declared in the project")

    if unused:
        typer.echo(f"  Unused dotenv entries ({len(unused)}):")
        for name in unused:
            typer.echo(f"    {name} ({', '.join(local.sources[name])})")
    if not local.files:
        typer.echo(
            "  Dotenv: no .env or .env.local file found (shell variables were still checked)"
        )

    if missing or node_failed:
        typer.echo(
            f"Doctor found {len(missing) + int(node_failed)} blocking setup issue(s).", err=True
        )
        raise typer.Exit(code=1) from None
    typer.echo("Ready to develop.")


@app.command()
def diff(
    base: Annotated[
        str,
        typer.Option("--base", help="Git revision whose capsule.json should be the baseline."),
    ] = "HEAD",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text or markdown."),
    ] = "text",
) -> None:
    """Report requirement changes compared with the base branch."""
    if output_format not in {"text", "markdown"}:
        typer.echo("Error: --format must be `text` or `markdown`.", err=True)
        raise typer.Exit(code=2)
    root = capsule_file.find_project_root(Path.cwd())
    current = _load_capsule(root)
    try:
        before = report.load_from_git(root, base)
    except capsule_file.CapsuleFileError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from None
    changes = report.compare(before, current)
    typer.echo(report.render(changes, markdown=output_format == "markdown", base=base))


@hook_app.command("install")
def hook_install() -> None:
    """Install a git hook that runs `capsule doctor` after pulls and checkouts."""
    root = capsule_file.find_project_root(Path.cwd())
    try:
        changed = hooks.install(root)
    except hooks.HookError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from None
    if changed:
        typer.echo(f"Installed Capsule in Git hooks: {', '.join(changed)}.")
    else:
        typer.echo("Capsule Git hooks are already installed.")


@hook_app.command("uninstall")
def hook_uninstall() -> None:
    """Remove the capsule git hook."""
    root = capsule_file.find_project_root(Path.cwd())
    try:
        changed = hooks.uninstall(root)
    except hooks.HookError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from None
    if changed:
        typer.echo(f"Removed Capsule from Git hooks: {', '.join(changed)}.")
    else:
        typer.echo("No Capsule Git hooks were installed.")


@export_app.command("env-example")
def export_env_example(
    check: Annotated[
        bool,
        typer.Option("--check", help="Write nothing; fail if .env.example is out of date."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", help="Replace an existing .env.example not managed by Capsule."),
    ] = False,
) -> None:
    """Write a .env.example file listing every required env var."""
    root = capsule_file.find_project_root(Path.cwd())
    data = _load_capsule(root)
    path = root / ".env.example"
    text = _env_example(data)
    old = path.read_text(encoding="utf-8-sig") if path.exists() else None
    managed = old is None or old.startswith("# Generated by Capsule")
    if not managed and not force:
        typer.echo(
            "Error: .env.example was not generated by Capsule. "
            "Use --force to replace it, or keep managing it by hand.",
            err=True,
        )
        raise typer.Exit(code=1)
    if check:
        if old == text:
            typer.echo(".env.example is up to date.")
            return
        typer.echo(
            "Error: .env.example is out of date. Run `capsule export env-example`.",
            err=True,
        )
        raise typer.Exit(code=1)
    if old == text:
        typer.echo(".env.example is up to date.")
        return
    path.write_text(text, encoding="utf-8", newline="\n")
    action = "Created" if old is None else "Updated"
    typer.echo(f"{action} .env.example with {len(data.get('env', {}))} variables.")


def _load_capsule(root: Path) -> dict:
    path = root / capsule_file.FILE_NAME
    try:
        data = capsule_file.load(path)
    except capsule_file.CapsuleFileError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from None
    if data is None:
        typer.echo(
            f"Error: {capsule_file.FILE_NAME} does not exist. Run `capsule capture` first.",
            err=True,
        )
        raise typer.Exit(code=1)
    return data


def _load_config(root: Path) -> CapsuleConfig:
    try:
        return load_config(root)
    except ConfigError as error:
        typer.echo(f"Error: {error}", err=True)
        raise typer.Exit(code=1) from None


def _env_example(data: dict) -> str:
    lines = [
        "# Generated by Capsule. Values intentionally left blank.",
        "# Run `capsule export env-example` after changing capsule.json.",
        "",
    ]
    for name, entry in sorted(data.get("env", {}).items()):
        if entry.get("note"):
            lines.append(f"# {entry['note']}")
        if entry.get("optional"):
            lines.append("# Optional")
        lines.extend([f"{name}=", ""])
    return "\n".join(lines).rstrip() + "\n"
