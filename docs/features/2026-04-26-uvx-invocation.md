# Document `uvx`-from-GitHub as the no-clone install path

**Date:** 2026-04-26

## Problem

The README's Quick start told every user — including drive-by, one-shot users with no interest in hacking on the tool — to clone the repo, run `uv sync`, then `uv run musicbrainz-database-setup …`. The package was already shaped correctly for `uvx`-from-source invocation (a `[project.scripts]` console script, hatchling src-layout, no runtime dependence on the checked-out tree), but nothing in the docs surfaced it. End-users had no way to know they could skip the checkout entirely.

## Changes

| Change | File | Effect |
|---|---|---|
| Quick start lead with `uvx --from git+…` | `README.md` | Old `§2 Install the CLI` (`uv sync`) and `§3 Import the database` (`uv run …`) collapsed into one `§2 Import the database` section that leads with the no-clone `uvx --from git+https://github.com/rafacm/musicbrainz-database-setup musicbrainz-database-setup run …` form. The `uv sync` + `uv run` flow moves to a 💡 callout pointing at the Development section, for users who already have (or want) a checkout. `§4 Explore the data` renumbered to `§3`. |
| Both invocation forms on the `--help` hint | `README.md` | The "Supported commands" intro (`Run … --help to see the available commands and options at any time`) shows `uvx --from git+…` first and `uv run … --help` second. |
| Split-credentials example shows `uvx` | `docs/README.md` | The `PGPASSWORD="$(op read …)" uv run … --latest` example now shows the `uvx --from git+…` variant above the `uv run` form, so the env-var-secret pattern is visible to users who arrive via `uvx`. |

## Verification

Run from a clean shell with no project venv activated:

```bash
uv build                                                               # wheel + sdist build clean
uvx --from . musicbrainz-database-setup --help                         # full --help renders
uvx --from . musicbrainz-database-setup list-dumps --help              # subcommand renders
```

Plus, after pushing the docs branch:

```bash
uvx --from "git+https://github.com/rafacm/musicbrainz-database-setup@docs/uvx-from-github" \
  musicbrainz-database-setup --help
```

All four print Typer help without error. Existing CI (`.github/workflows/ci.yml`) covers the package-builds-and-runs invariant on Python 3.11 / 3.12 / 3.13.

## Files modified

- `README.md` — Quick start restructure (`§2`/`§3`/`§4` → `§2`/`§3`); both forms on the Supported-commands `--help` line.
- `docs/README.md` — split-credentials snippet gains the `uvx --from git+…` form.
- `CHANGELOG.md` — entry under `## 2026-04-26`.
- `docs/plans/2026-04-26-uvx-invocation.md`, `docs/features/2026-04-26-uvx-invocation.md`, `docs/sessions/2026-04-26-uvx-invocation-{planning,implementation}-session.md` — the standard plan / feature / session quartet.
