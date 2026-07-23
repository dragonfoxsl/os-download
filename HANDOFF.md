# os-download Handoff

## Current State

- Branch: `main`
- Remote: `git@github.com:dragonfoxsl/os-download.git`
- CI runs on push, pull request, manual dispatch, and Fridays at `03:00 UTC`.
- Dependabot checks `uv` and GitHub Actions weekly on Friday.

## Maintainer Rules

- Never add AI co-author trailers to commits.
- Keep `README.md` and this `HANDOFF.md` updated with each change.
- Follow secure development practices for download URLs, checksum verification, subprocess use, and GitHub Actions.
- Keep every file under 1000 lines; split files before they exceed that limit.
- Add concise comments only for non-obvious network, checksum, retry, or platform-specific behavior.

## Verification Baseline

- Lint: `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check`
- Tests: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q`
- Build: `UV_CACHE_DIR=/tmp/uv-cache uv build`
- Node metadata audit: `pnpm audit --audit-level high`

## Open Items

- Keep README screenshots/help output aligned before release tags.
- Recheck finder modules when upstream distro download pages change.
