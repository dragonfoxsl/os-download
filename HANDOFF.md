# os-download Handoff

## Current State

- Package version: `0.1.4`.
- CI tests Python 3.10 and 3.13, lints, and builds the package on pushes, pull requests, manual dispatches, and Fridays at `03:00 UTC`.
- Dependabot checks Python and GitHub Actions dependencies weekly.

## Verification Baseline

```bash
UV_CACHE_DIR=/tmp/uv-cache uv sync --locked
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q
UV_CACHE_DIR=/tmp/uv-cache uv build
pnpm audit --audit-level high
```

## Current Maintenance

The Ponytail cleanup consolidates duplicated HTTP 416 tests and finder concurrency, removes Debian's ineffective URL recheck, drops redundant exception-handler `pass` statements, and trims duplicated maintenance guidance.

Verified locally: Ruff passed, 75 tests passed with 2 skipped, source and wheel builds succeeded, both CLI help commands ran, normal/quiet finder modes returned the same results, `pnpm audit` found no known vulnerabilities, and the locked image workflow rendered all four PNGs in a disposable copy.

## Durable Notes

- Follow `AGENTS.md`; keep user-facing setup and release instructions in `README.md`.
- Keep README screenshots aligned with CLI help and dashboard behavior before release tags.
- Recheck finder modules when upstream distribution pages change.
- README image rendering uses the locked Playwright development dependency. Run `pnpm install --frozen-lockfile`, `pnpm exec playwright install chromium`, then `pnpm render-images`.
