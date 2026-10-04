# Learning Progress

## Pending decision
- Decision: Step 2 scanner approach (Build checkpoint)
- Stage: awaiting reasoning
- Asked: how the learner would find env var references in a JS/TS codebase (which files, what to skip, how to recognize each form), given the listed forms: `process.env.X`, `process.env["X"]`, destructuring from `process.env` (incl. defaults), `import.meta.env.X`, dynamic `process.env[name]`, and mentions inside comments/strings.
- Still open for step 2: Node version precision (churn between developers).
- Build order (Claude-proposed, learner didn't object): 1 skeleton (done) → 2 scanner + Node version → 3 committed file + capture (annotations) → 4 doctor → 5 CI guard → 6 PR report → 7 git hook → 8 export env-example → 9 unused vars.

## Implemented: Step 1 project skeleton
- Learner approved scope at Implementation checkpoint, including Claude's proposed additions (placeholder commands, Python >=3.11, hatchling + editable install, pytest, `.gitignore` for Python artifacts, package name `capsule-cli`). `.vibe-wise/` not added to `.gitignore` (learner didn't ask).
- Verified: 9 tests pass; `capsule --help`, `--version`, `python -m capsule_cli` work.

## Resolved: command interface and CLI library
- Learner delegated command naming ("trivial naming thing"), asked for subcommands and combining where it fits. Claude chose: `capture`, `capture --check` (CI guard), `doctor` (check + unused vars), `diff` (PR report; GitHub Action is a thin wrapper), `hook install/uninstall`, `export env-example`; annotations edited directly in the committed file.
- Learner chose Typer for the CLI library (reason: easiest, least code). Tradeoff noted by Claude: a few more dependencies than argparse/Click.

## Design decisions so far
- Learner's first workflow proposal: dev runs capsule after finishing changes; info attached to the PR; after merge, a dev who pulls runs a command and gets the info. Claude flagged machine-vs-project noise, secret leakage, and display-vs-check ambiguity.
- Learner first picked "both repo and PR description" for the snapshot ("most effective") and "the person's env" as the env var source; Claude showed the shell has 82 unrelated env vars including a live token.
- Niche: Claude proposed at learner's explicit request; learner confirmed (see project-map Positioning). This settled requirements coming from repo/code and the committed file being the source of truth with the PR showing changes.
- Learner decision: env vars stored by name only ("I think the name is fine"). Claude supplied the justification: names cover both the PR diff and the check command.
- v1 data scope: Claude picked at learner's request (env var names, Node version, package manager), using criteria: does a PR change it; reliable zero-setup detection; project vs. machine (machine data churns in a committed file); build cost. Learner then cut package manager (use cases too niche).
- v1 features: Claude listed ideas mapped to the env requirement lifecycle; learner chose all seven ("I like the table") without per-feature reasons. Claude showed the shared dependency on scanner + committed file.
- Still proposed, not confirmed: JS/TS projects first. Open: Node version precision (churn between developers).

## Core workflow
- Learner proposed: capture at the end of a dev's work, attach to PR, receiving dev runs a command after pulling. Learner asked for pushback and feature suggestions.
- Introduced (Claude explained): `git pull` only brings committed files; PR descriptions live on GitHub and would need the API / `gh` CLI to read.
- Introduced (Claude explained): sources for "what the project needs" (declaration files, code scanning for env var references, local `.env` keys, explicit config) and each one's weakness; tool versions come from running e.g. `node --version`.
- Introduced (Claude explained): env var names vs. values; options from names-only to sharing values, and that secure secret sharing is handled by dedicated secret managers.
- Introduced (Claude explained): source of truth vs. derived view; tradeoffs of a committed snapshot file vs. PR description vs. both.
- Introduced (Claude explained): catalog of environment info that breaks setups and where capsule could get it: runtime versions, package manager + version, global CLIs used by scripts, local services (DB/cache), OS/CPU architecture, required env var names; plus what already covers each.
- Needs reinforcement: learner was initially unsure how to approach relevance detection and snapshot location; first env var answer ("the person's env") didn't account for unrelated vars or secret values.
- Demonstrated understanding: none yet.

## Positioning and obsolescence
- Learner concern: Dev Containers cover most environment info capsule would capture.
- Introduced (Claude explained): a tool is obsolete only if another does the same job for the same people at equal or lower cost; Dev Containers are prescriptive (spec → built environment) and need Docker plus supporting tooling; descriptive tools record what actually worked. Levers: different people, different cost, different job, complement rather than compete.
- Learner explicitly asked Claude to decide the niche. Claude proposed it (see project-map Positioning); learner chose Confirm and continue without discussion. This is a confirmed choice, not demonstrated reasoning.
- Demonstrated understanding: none yet.
- Needs reinforcement: articulating the positioning in their own words (relevant to their goal of defending the design).

## Feature value and scope
- Introduced (Claude explained): what lockfiles record (exact dependency versions; manager implied by file name) and don't (manager version, local machine check).
- Demonstrated understanding: evaluated package manager detection against its use cases and chose to cut it because the cases were too niche.
- Introduced (Claude explained): data captured vs. features built on that data; mapping features to moments in an env requirement's lifecycle.
- Introduced (Claude explained): all v1 features depend on the scanner and committed file, so scanner reliability matters most.

## Existing environment tooling landscape
- Introduced (Claude explained): version-pinning files (`.nvmrc`/`.node-version`, `engines` in package.json, `.python-version`, `.tool-versions` for asdf/mise); `.env.example` convention; full reproducible environments (Dev Containers, Docker, Nix/devbox); lockfiles pin dependencies, not runtimes, global tools or env vars.
- Introduced (Claude explained): env vars often hold secrets, so sharing them (including in PR descriptions) is the project's main trust boundary.
- Demonstrated understanding: none yet.
- Needs reinforcement: none yet.
