# Capsule

**Make a web project's invisible setup requirements visible before they break someone else's machine.**

Capsule is a small Python CLI for JavaScript and TypeScript projects. It discovers the environment
variables a codebase reads, records the project's declared Node version, checks a developer's local
setup, and turns requirement changes into a pull-request-ready report.

It is designed for developers and small teams who work directly on their machines and want useful
environment checks without adopting Docker, Dev Containers, or a hosted secrets service.

## Why it exists

A lockfile can reproduce npm dependencies, but it does not tell a new contributor that the app needs
`DATABASE_URL`, that `STRIPE_SECRET_KEY` comes from a team dashboard, or that the project expects Node
20. Those details often live in chat messages, stale onboarding docs, or one developer's memory.

Capsule keeps the requirement **names and instructions** beside the code while keeping all values and
secrets local.

## Quick start

Install Capsule from this checkout:

```console
python -m pip install -e .
```

Run it in a JavaScript or TypeScript project:

```console
$ capsule capture
Created capsule.json: 3 env vars. Node 20 from .nvmrc.

$ capsule doctor
Checking storefront against capsule.json...
  Environment: 2/3 required variables available
    missing STRIPE_SECRET_KEY — Create a restricted key in the Stripe dashboard
  Node: 20.11.1 is compatible (expected Node major 20)
Doctor found 1 blocking setup issue.
```

After setting the missing variable:

```console
$ capsule doctor
Checking storefront against capsule.json...
  Environment: 3/3 required variables available
  Node: 20.11.1 is compatible (expected Node major 20)
Ready to develop.
```

When a pull request adds a requirement:

```console
$ capsule diff --base main --format markdown
## Capsule environment report

Compared with `main`.

### Added environment variables

- `STRIPE_WEBHOOK_SECRET`
```

## Commands

| Command | Purpose |
| --- | --- |
| `capsule capture` | Scan the project and create or update `capsule.json`. |
| `capsule capture --check` | CI guard: fail without writing when the committed snapshot is stale. |
| `capsule doctor` | Check local dotenv/shell variables and the installed Node version. |
| `capsule doctor --env-file PATH` | Check one or more explicit dotenv files. |
| `capsule diff --base REF` | Show setup requirement changes from a Git revision. |
| `capsule diff --base REF --format markdown` | Produce a PR-ready Markdown report. |
| `capsule export env-example` | Safely generate a value-free `.env.example`. |
| `capsule export env-example --check` | Fail when the generated example is stale. |
| `capsule hook install` | Run `doctor` after Git pulls and checkouts. |
| `capsule hook uninstall` | Remove only Capsule's blocks from those hooks. |

## The committed file

`capsule capture` creates a deterministic file that is easy to review:

```json
{
  "format": 1,
  "node": {
    "version": "20",
    "source": ".nvmrc"
  },
  "env": {
    "DATABASE_URL": {
      "note": "Ask the backend lead for a local database URL",
      "used_in": [
        "src/db.ts"
      ]
    },
    "SENTRY_DSN": {
      "optional": true,
      "used_in": [
        "src/observability.ts"
      ]
    }
  }
}
```

Capsule owns `node` and `used_in`. You can add annotations directly:

- `note`: onboarding instructions shown by `doctor` and exported as a comment.
- `optional`: documents a variable without making it block local setup.
- `manual`: preserves a variable that is read indirectly and cannot be found statically.

Unknown human-authored fields are preserved. Invalid JSON is never overwritten.

## Detection

Capsule parses `.js`, `.jsx`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.mts`, and `.cts` with tree-sitter.
Unlike a regular-expression search, this ignores comments, strings, assignments, generated output,
dependencies, `NODE_ENV`, and Vite's built-in variables. It understands:

```js
process.env.API_KEY
process.env["DATABASE_URL"]
const { REDIS_URL, PORT = 3000 } = process.env
import.meta.env.VITE_API_URL
```

Computed reads such as `process.env[name]` cannot be resolved safely, so Capsule reports their file
and line and asks you to add any requirement with `"manual": true`.

Node declarations are read in this order: `.nvmrc`, `.node-version`, `.tool-versions`,
`package.json#volta.node`, then `package.json#engines.node`. Capsule records the declaration, never
the current developer's machine version, which keeps the committed file deterministic.

## Project configuration

Capsule needs no configuration for a typical app. Larger repositories can add settings to their
existing `pyproject.toml`:

```toml
[tool.capsule]
exclude = ["fixtures/**", "generated/*.js"]
ignore-env = ["CI", "VERCEL"]
env-files = [".env.development", ".env.local"]
```

- `exclude` accepts `/`-separated glob patterns for source files Capsule should not scan.
- `ignore-env` removes platform-provided or intentionally irrelevant names from capture results.
- `env-files` defines the dotenv files `doctor` checks when `--env-file` is not supplied.

Invalid or misspelled settings fail loudly instead of being silently ignored.

## GitHub pull-request integration

This repository is also a composite GitHub Action. A consumer workflow can check the committed file,
add a Markdown summary, and maintain one Capsule comment on the pull request:

```yaml
name: Capsule
on: pull_request

permissions:
  contents: read
  pull-requests: write

jobs:
  environment:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - uses: AmanSreejesh/capsule@main
        with:
          base: ${{ github.event.pull_request.base.sha }}
          comment: "true"
```

For production use, pin the action to a release tag or commit SHA instead of `main`.

## Safety and privacy

- Capsule records variable **names**, never values.
- `doctor` reads only names from dotenv files and never prints their contents.
- Local machine state is checked but never written to `capsule.json`.
- Generated `.env.example` files contain blank values.
- Capsule refuses to replace a hand-written `.env.example` unless `--force` is explicit.
- Hook installation preserves existing hook contents; uninstall removes only Capsule's marked block.

Variable names and free-text notes can still reveal sensitive architecture. Review `capsule.json` as
you would any other committed configuration file, and never place credentials in a `note`.

## Development

```console
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"  # Windows
.venv\Scripts\python -m ruff check src tests
.venv\Scripts\python -m pytest
```

On macOS or Linux, use `.venv/bin/python` instead. The suite covers parsing, file safety, version
comparison, local checks, generated output, Git diffs, and hook preservation.

## Current scope

Capsule intentionally starts with the web-development setup problems it can detect reliably and
without a hosted service: JS/TS environment variables and Node versions. It does not store secret
values, provision services, or try to replace a reproducible container. Aliases such as
`const env = process.env` and libraries that consume the entire environment require manual entries.

## License

MIT
