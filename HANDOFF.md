# os-download Handoff

## Current State

- Working branch: `docs/public-readme-cleanup` (the repository default is `main`)
- Remote: `git@github.com:dragonfoxsl/os-download.git`
- Current package version: `0.1.4`
- CI runs lint, tests, and a package build on push, pull request, manual dispatch,
  and Fridays at `03:00 UTC`.
- Dependabot checks `uv` and GitHub Actions weekly on Friday.

## Maintainer Rules

- Never add AI co-author trailers to commits.
- Keep `README.md` and this `HANDOFF.md` updated with each change.
- Keep public README content focused on users and contributors. Put agent instructions,
  branch state, dated PR lists, and operational handoff notes in `HANDOFF.md` or `AGENTS.md`.
- Preserve this repository's public README style for future README creation or major rewrites.
- Preserve existing support links, but do not add new Ko-fi/donation content unless explicitly requested.
- Follow secure development practices for download URLs, checksum verification, subprocess use, and GitHub Actions.
- Keep code and configuration files under 1000 lines, and normal documentation under 2000 lines.
- Add concise comments only for non-obvious network, checksum, retry, or platform-specific behavior.
- Before pushing, check configured GitHub Actions and Dependabot status for failures or open alerts.

## Verification Baseline

- Lint: `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check`
- Tests: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q`
- Build: `UV_CACHE_DIR=/tmp/uv-cache uv build`
- Node metadata audit: `pnpm audit --audit-level high`

## Open Items

- Dependabot audit (2026-07-25): no open version-update PRs.
- `uv.lock` was refreshed on 2026-07-23 for patched `idna`, `requests`, and
  `urllib3`; release `v0.1.3` includes that lock update.
- The upcoming `v0.1.4` release will republish the corrected README metadata to PyPI.
- Keep README screenshots/help output aligned before release tags.
- Recheck finder modules when upstream distro download pages change.
