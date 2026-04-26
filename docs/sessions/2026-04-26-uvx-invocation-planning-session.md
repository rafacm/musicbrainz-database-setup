# Planning session — Document `uvx`-from-GitHub as the no-clone install path

**Date:** 2026-04-26

**Session ID:** 8cbc72f3-23f7-4ab5-a9bd-38e0baa67534

## Summary

The user opened the session by asking to "get this project to work with `uvx musicbrainz-database-setup`". The assistant explored the package and confirmed it was already correctly shaped for `uvx` invocation — `[project.scripts]` declared the console script, hatchling built from `src/`, and no runtime code depended on a checkout. The actual gap was documentation, not packaging. Three clarifying questions were asked via `AskUserQuestion` (distribution target, release flow, doc strategy) and the user picked: **run from GitHub** (no PyPI publish), **skip release pipeline**, and **show both forms** in the docs. Plan written to `docs/plans/2026-04-26-uvx-invocation.md` and approved via `ExitPlanMode`.

## Detailed conversation

### User

> Let's work now on getting this project to work with "uvx musicbrainz-database-setup".

### Assistant

Read `pyproject.toml`, the package `__init__` / `__main__`, `cli.py` head, the README, AGENTS.md, the `.github/workflows/ci.yml`, and `mise.toml` to ground the work. Verified that the package is already shaped for `uvx`:

- `[project.scripts] musicbrainz-database-setup = "musicbrainz_database_setup.cli:app"` is declared (line 28-29).
- Hatchling builds from `src/musicbrainz_database_setup` (line 35-36).
- `requires-python = ">=3.11"` (uvx auto-fetches a compatible interpreter).
- A grep over `Path(__file__)` / `importlib.resources` / `package_data` came back empty — runtime SQL is fetched from GitHub, dump archives come from CLI flags, so the package has no dependence on being run from a checkout.

Concluded the gap was documentation: the README routes everyone (end-users and contributors alike) through `uv sync` + `uv run`. The `uvx` form would work today; users just don't know about it.

### Assistant

Asked three `AskUserQuestion` questions to scope the change:

1. **Distribution target** — PyPI publish vs. run-from-GitHub vs. local-only vs. PyPI + GitHub fallback.
2. **Release flow** — GitHub Actions trusted publishing vs. manual `uv build`/`uv publish` vs. skip.
3. **Docs update** — replace `uv run` with `uvx`, show both, or don't touch docs.

### User

Picked: **Run from GitHub**, **Skip — not publishing yet**, **Show both** in docs.

### Assistant

With the scope clarified, confirmed the GitHub URL (`github.com/rafacm/musicbrainz-database-setup` — matches the CI badge in the README and the `git remote -v` output: `git@github.com:rafacm/musicbrainz-database-setup.git`) and identified the doc surface to update:

- `README.md` Quick start §2 (`uv sync`) and §3 (`uv run … run --latest`) — collapse into a single uvx-led section.
- `README.md:128` — the "Supported commands" intro line that hard-codes `uv run musicbrainz-database-setup --help`.
- `docs/README.md:116` — the `PGPASSWORD="$(op read …)" uv run musicbrainz-database-setup run --latest` split-credentials example.

Decided **not** to touch `pyproject.toml` (already correct; adding `[project.urls]` is a PyPI nice-to-have not required for `uvx --from git+`), `AGENTS.md` (its `uv run` examples are contributor-focused), or `.github/workflows/ci.yml` (existing build/test coverage is sufficient).

Wrote the plan to `/Users/rafa/.claude/plans/let-s-work-now-on-robust-beaver.md` (the plan-mode draft path) covering: context, recommended approach (verify via `uv build` + `uvx --from .`, then docs edits, then the AGENTS.md-mandated plan/feature/session quartet + CHANGELOG entry), files modified vs. NOT modified, and verification commands. Called `ExitPlanMode`.

### User

Plan approved.
