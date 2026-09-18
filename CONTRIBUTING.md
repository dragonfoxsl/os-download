# Contributing to os-download

Thanks for helping improve os-download.

## Set up the project

Requirements: Python 3.10 or newer and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/dragonfoxsl/os-download.git
cd os-download
uv sync --locked
```

Run the local commands with `uv run os-finder` and `uv run os-download`.

## Make a change

1. Create a focused branch from the latest `main`.
2. Keep changes small and include tests for changed behaviour.
3. Update `README.md` for user-facing or operational changes.
4. Update `HANDOFF.md` with the change, verification, and anything left unresolved.

When adding or changing a finder, use official distribution sources where practical, set network timeouts, preserve useful failure diagnostics, and test with mocked responses. Do not weaken checksum, signature, path, or subprocess validation to make a source work.

## Verify

```bash
uv sync --locked
uv run ruff check
uv run pytest -q
uv build
```

If JavaScript development dependencies changed, also run:

```bash
pnpm install --frozen-lockfile
pnpm audit --audit-level high
```

Run `git diff --check` before committing. Never commit credentials, downloaded images, build output, caches, or local environment files.

## Open a pull request

Explain why the change is needed, what changed, and which checks you ran. Keep unrelated changes in separate pull requests and ensure CI passes.

For vulnerabilities, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.
