# Document `uvx`-from-GitHub as the no-clone install path

**Date:** 2026-04-26

## Context

End-users currently have to clone the repo and run `uv sync` + `uv run musicbrainz-database-setup …` to invoke the CLI. We want one-shot invocation without a local checkout, via:

```bash
uvx --from git+https://github.com/rafacm/musicbrainz-database-setup \
  musicbrainz-database-setup run --db … --modules core --latest
```

The package is already structured correctly for this — `[project.scripts]` declares the `musicbrainz-database-setup` console script (`pyproject.toml:28-29`), hatchling builds from `src/musicbrainz_database_setup` (line 35-36), and no runtime code reads files from the repo checkout: `admin/sql/*.sql` is fetched from GitHub, dump archives come from CLI flags / configured workdir, and there is no `__file__`-relative resource lookup. So `uvx` works as soon as the wheel builds, which it does today.

This plan is therefore a **docs-only change** plus a verification step, not a code or packaging change. PyPI publishing is explicitly out of scope (deferred to a future plan).

## Approach

1. **Verify the invocation works against a local source tree** — `uv build` + `uvx --from . musicbrainz-database-setup --help` is a strong proxy for `uvx --from git+…` because both go through the same hatchling build pipeline.

2. **README.md — Quick start.** Collapse the old "§2 Install the CLI" + "§3 Import the database" two-step (`uv sync` then `uv run …`) into a single §2 "Import the database" that leads with the `uvx --from git+…` form. Keep the `uv sync` + `uv run` flow as a 💡 callout pointing at the Development section, for users who already have a checkout. Renumber "§4 Explore the data" → "§3".

3. **README.md — "Supported commands" intro.** Show both `uvx --from git+… --help` (no clone) and `uv run … --help` (from a checkout) on the same line.

4. **docs/README.md — split-credentials example.** The `PGPASSWORD="$(op read …)" uv run …` snippet currently shows only the checkout form; add the `uvx --from git+…` variant above it so users arriving via `uvx` see the same env-var pattern.

5. **AGENTS.md.** Leave as-is. Its `uv run` examples are contributor-focused and remain correct.

6. **CHANGELOG.md.** Add an entry under `## 2026-04-26` documenting the no-clone install path, with links to this plan, the feature doc, and both session transcripts.

## Files modified

- `README.md` — Quick start restructure + Supported-commands one-liner.
- `docs/README.md` — split-credentials section gains a `uvx` example.
- `CHANGELOG.md` — entry under `## 2026-04-26`.
- `docs/plans/2026-04-26-uvx-invocation.md` (this file).
- `docs/features/2026-04-26-uvx-invocation.md`.
- `docs/sessions/2026-04-26-uvx-invocation-planning-session.md`.
- `docs/sessions/2026-04-26-uvx-invocation-implementation-session.md`.

## Files NOT modified

- `pyproject.toml` — `[project.scripts]`, build backend, package layout, and `requires-python` are already correct. Adding `[project.urls]` (Homepage / Repository / Issues) is a nice-to-have for PyPI metadata but is not required for `uvx --from git+…` and is therefore out of scope.
- `src/**` — no code changes.
- `.github/workflows/ci.yml` — existing build/test on 3.11 / 3.12 / 3.13 already covers the package-builds-and-runs invariant.

## Verification

From a shell with no project venv activated:

```bash
uv build                                                                # wheel builds clean
uvx --from . musicbrainz-database-setup --help                          # uvx happy path on local source
uvx --from . musicbrainz-database-setup list-dumps --help               # subcommand smoke
uvx --from "git+https://github.com/rafacm/musicbrainz-database-setup@docs/uvx-from-github" \
  musicbrainz-database-setup --help                                     # canonical end-user form, after branch is pushed
```

Steps 1-3 are runnable before the branch is pushed; step 4 is the proof that the README-recommended invocation works for a fresh user with no checkout.
