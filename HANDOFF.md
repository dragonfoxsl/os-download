# os-download Handoff

## Current State

- Package version: `0.1.4`.
- CI tests Python 3.10 and 3.13, lints, builds the package, and smoke-tests both CLIs on Linux, macOS, and Windows.
- Release builds repeat locked lint/tests and smoke-test the built wheel before OIDC publication.
- The mirror canary retries transient failures, preserves diagnostics, and closes stale alerts after recovery.
- Dependabot checks Python and GitHub Actions dependencies weekly.
- Contributor and security-reporting guidance lives in `CONTRIBUTING.md` and `SECURITY.md`; GitHub private vulnerability reporting is enabled.

## Verification Baseline

```bash
UV_CACHE_DIR=/tmp/uv-cache uv sync --locked
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/uv-cache uv build
pnpm audit --audit-level high
```

## Current Maintenance

The hardening branch closes the integrity and release gaps found in the audit: trusted-cache enforcement, validated resume ranges, atomic decompression, curl HTTP failure handling, safe output names, batch collision checks, deterministic finder diagnostics, official TrueNAS discovery, positive CLI numeric arguments, locked CI/release installs, cross-platform CLI smoke coverage, contributor and security guidance, and Ruff 0.16.3.

Verified locally: Ruff passed; Python 3.10 and 3.13 each passed 95 tests with 2 optional-backend skips; locked source and wheel builds succeeded; both CLIs ran from an isolated wheel install; all workflow YAML parsed; all 15 live finders resolved; and Python plus pnpm audits reported no known dependency vulnerabilities.

## Durable Notes

- Follow `AGENTS.md`; keep user-facing setup and release instructions in `README.md`.
- Keep README screenshots aligned with CLI help and dashboard behavior before release tags.
- Recheck finder modules when upstream distribution pages change.
- README image rendering uses the locked Playwright development dependency. Run `pnpm install --frozen-lockfile`, `pnpm exec playwright install chromium`, then `pnpm render-images`.
