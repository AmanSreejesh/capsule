# Project Map

## Purpose
"capsule": a Python CLI that captures a developer's current working environment and makes it shareable, so resuming or handing off work is easier. Portfolio project for a program application, framed around web development.

## Positioning (confirmed, Claude-proposed at learner's request)
For developers and small teams running projects natively (not in containers). Capsule derives what a project needs from the repo and code, records it in a file committed with the code, and flags changes to those requirements in pull requests, so whoever pulls learns about new requirements before things break. Works alongside `.env.example` / `.nvmrc` (can generate/update them) rather than replacing them.
Known weaknesses: code scanning misses indirectly read env vars (needs a manual way to add them); less value for teams already on Dev Containers; narrower pitch.

## Requirements
From the learner's description (requirements, not technical decisions):
- Capture working-environment details that aren't easily found elsewhere: Node environment, environment variables, tool/runtime versions not recorded in files like a package lock, etc.
- The captured result can be shared.
- A command (e.g. when restarting or picking up shared work) presents the captured info to make setup easier.
- GitHub integration, e.g. automatically embedding required env variables (and similar hard-to-find info) in a PR description.
- Should be genuinely useful and not made obsolete by existing tools or features.
- Implemented in Python.
- Deadline: showable in ~2 weeks from 2026-10-04 (~2026-10-18).
- Everything must be free (no paid services/APIs).
- Claude works on local files only; the learner makes all git commits.

## v1 Scope (confirmed by learner; nothing implemented)
Data captured: env var names only (never values), with file path(s) where each is referenced; Node version. Package manager detection cut by learner (too niche). Deferred to v2: global CLIs, local services. OS/architecture not stored in the committed file.
Features (learner chose all seven): PR report; CI guard (fails if code uses an env var missing from the committed file); check command; git hook running check after pull; annotations (per-var notes + manual declaration of vars the scan misses); unused var detection; generate `.env.example`.
Still proposed, not confirmed: JS/TS projects first.
Open: how precisely to record the Node version (avoid churn between developers).

## Components
- CLI (implemented as placeholders): `src/capsule_cli/cli.py`, a Typer app with subcommands `capture` (`--check` = CI guard), `doctor`, `diff`, `hook install|uninstall`, `export env-example`; each currently exits 1 with "not implemented yet". `--version` works. Entry points: `capsule` console script, `python -m capsule_cli` (`__main__.py`). Version lives in `src/capsule_cli/__init__.py`.
- Tests: `tests/test_cli.py` (pytest + Typer CliRunner).
Confirmed design (not implemented):
- Scanner: finds env var references in JS/TS code (approach not designed).
- Committed file: source of truth; env var names + where used + annotations; Node version (format not designed).
- GitHub Action: thin wrapper that runs `capsule diff` and posts the output to the PR (mechanism not designed).
Build order (proposed): skeleton → scanner + Node version → committed file + capture → doctor → CI guard → PR report → git hook → export → unused vars.
Existing in repo: empty `src/capsule_cli/` directory, empty `tests/` directory, `.venv/` (Python 3.12.0), `.vscode/settings.json`.

## Main Flow
Confirmed at the level of the positioning (details not designed; nothing implemented):
dev finishes work --runs capsule--> project requirements derived from repo/code (+ ? machine versions) --> committed snapshot file
PR opened --> changes to requirements shown in PR description (? mechanism)
PR merged --> other dev pulls (file arrives via git) --runs capsule check command--> local machine compared against file
Unresolved: env var value handling, first-version scope, exact source-of-truth wording (implied: committed file is source, PR shows a view).

## Data and Trust Boundaries
Unknown. Env variables may contain secrets; how captured data is stored and shared has not been decided.

## Build and Deployment
- Packaging: `pyproject.toml` (hatchling; distribution name `capsule-cli`; requires Python >=3.11; dependency `typer`; dev extra `pytest`). PyPI name availability not checked yet.
- Virtual environment: `.venv/` (Python 3.12.0). Install: `.venv\Scripts\python.exe -m pip install -e ".[dev]"`.
- Tests: `.venv\Scripts\python.exe -m pytest`.
- `.gitignore`: Python cache/build files, `.venv/`.

## Unknowns
- What exactly gets captured, and how it's collected
- Snapshot format and where it's stored
- How snapshots are shared
- What the "restore/show" command does with a snapshot
- How GitHub integration works (API, gh CLI, Actions, etc.)
- CLI framework and packaging
- How to differentiate from existing tools
