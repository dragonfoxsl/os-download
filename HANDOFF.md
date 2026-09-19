# os-download Handoff

## Current State

- Package version: `0.1.5` (release candidate; not tagged or published).
- CI tests Python 3.10 and 3.13, lints, builds the package, checks source-distribution boundaries, and smoke-tests both CLIs on Linux, macOS, and Windows.
- Release builds repeat locked lint/tests and smoke-test the built wheel before OIDC publication.
- The mirror canary retries transient failures, preserves diagnostics, and closes stale alerts after recovery.
- Dependabot checks Python, npm, and GitHub Actions dependencies weekly.
- External GitHub Actions are pinned to full commit SHAs; default workflow permissions are read-only, with issue and OIDC writes scoped to the jobs that need them.
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

The `fix/v0.1.5-hardening` branch binds verification markers to the stable requested source URL, resolves checksums against the effective mirror and published filename when `--output` renames a file, terminates curl/aria2 options before URLs, makes file logging non-fatal, isolates rotating Fedora keys, closes streaming responses on every path, and corrects curl identity and resume totals.

Repository maintenance removes generated finder output from Git, pins workflow actions and permissions, narrows source-distribution contents, adds npm Dependabot coverage, moves package metadata to one version source, updates Ruff to 0.16.7, and uses installed command names in user-facing hints.

Verified locally on Python 3.10 and 3.13: Ruff passed; each interpreter passed 106 tests with 2 optional-backend skips; wheel and source archives built; an unrelated untracked file was excluded from the sdist; both archives installed into clean environments and both CLIs reported 0.1.5; all workflow YAML parsed; all 15 live finders resolved; and Python plus pnpm audits reported no known dependency vulnerabilities.

## Durable Notes

- Follow `AGENTS.md`; keep user-facing setup and release instructions in `README.md`.
- Keep README screenshots aligned with CLI help and dashboard behavior before release tags.
- Recheck finder modules when upstream distribution pages change.
- README image rendering uses the locked Playwright development dependency. Run `pnpm install --frozen-lockfile`, `pnpm exec playwright install chromium`, then `pnpm render-images`.
