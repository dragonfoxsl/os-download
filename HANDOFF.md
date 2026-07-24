# os-download Handoff

## Current State

- Working branch: `docs/maintenance-cleanup` (the repository default is `main`)
- Remote: `git@github.com:dragonfoxsl/os-download.git`
- Current package version: `0.1.3`
- CI runs on push, pull request, manual dispatch, and Fridays at `03:00 UTC`.
- Dependabot checks `uv` and GitHub Actions weekly on Friday.

## Maintainer Rules

- Never add AI co-author trailers to commits.
- Keep `README.md` and this `HANDOFF.md` updated with each change.
- Preserve this repository's README style for future README creation or major rewrites.
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

- Dependabot audit (2026-07-24): no open security alerts. Two update PRs
  remain open: #3 (five grouped GitHub Actions updates) and #8 (`ruff`
  0.15.18 → 0.16.0). Both PRs currently have green Python 3.10 and 3.13 CI.
- `uv.lock` was refreshed on 2026-07-23 for patched `idna`, `requests`, and
  `urllib3`; release `v0.1.3` includes that lock update.
- Keep README screenshots/help output aligned before release tags.
- Recheck finder modules when upstream distro download pages change.
