# Package Cleanup Design

## Goal

Convert the two-script CLI into a maintainable Python package while preserving the existing user-facing commands and flags. The cleanup also fixes the reliability issues found in review and adds a small automated test suite so future scraper and downloader changes are safer.

## Public Compatibility

The installed commands remain unchanged:

- `os-finder`
- `os-download`

Existing flags stay compatible unless a flag is explicitly documented as new. Default paths remain:

- finder output: `./os-links/all_os.txt`
- finder log: `./logs/os-finder.log`
- downloader URL file: `./os-links/all_os.txt`
- downloader log: `./logs/os-download.log`
- download directory: platform download directory plus `os-isos`

The old top-level scripts will be removed after entry points are updated, because package entry points become the supported execution path. During development, users can run `uv run os-finder` and `uv run os-download` exactly as before.

## Package Layout

```text
src/os_download/
  __init__.py
  cli/
    __init__.py
    finder.py
    downloader.py
  finders/
    __init__.py
    base.py
    ubuntu.py
    opnsense.py
    pfsense.py
    debian.py
    truenas.py
    windows.py
    manjaro.py
    mxlinux.py
    puppy.py
    cachyos.py
    registry.py
  downloader/
    __init__.py
    manager.py
    checksums.py
    compression.py
    mido.py
    curl.py
    paths.py
  http.py
  logging.py
```

The package boundaries are:

- `cli/`: argument parsing, exit codes, user-facing console messages.
- `finders/`: one module per OS, plus registry and shared base behavior.
- `downloader/manager.py`: batch orchestration, progress display, resume logic.
- `downloader/checksums.py`: SHA256 lookup and hash comparison.
- `downloader/compression.py`: `.bz2` and `.gz` extraction.
- `downloader/mido.py`: Mido install and invocation.
- `downloader/curl.py`: curl fallback for hosts blocked by `requests`.
- `http.py`: shared `requests.Session` construction.
- `logging.py`: logger setup helpers.

## Behavior Fixes

### Checksum And Decompression

For compressed URLs, verification happens before decompression. This matches checksum sidecar files that refer to the downloaded archive, such as `.iso.gz.sha256` or `.iso.bz2.sha256`.

Post-download flow:

1. Download archive or ISO.
2. If `--verify` is enabled, verify the downloaded file at its current path.
3. If verification fails, keep the downloaded file and report failure.
4. If verification passes or no checksum is available, decompress when enabled.

### OPNsense Verification

Remove the unconditional `or True`. OPNsense should return a direct ISO only when the resolved URL verifies successfully. If verification fails, return no direct ISO so the normal unresolved/manual override flow can run.

### TrueNAS Unknown Codenames

Do not guess a codename for unknown TrueNAS major/minor releases. If GitHub reports a version whose major/minor is not mapped, return the official download page rather than constructing a stale or likely wrong URL.

Known mappings stay explicit and easy to update.

### Mido Isolation

Move Mido cloning and invocation into `downloader/mido.py`. Keep current behavior for this pass: Windows 11 still resolves to a `mido://win11x64` pseudo-URL and `os-download` still installs Mido automatically when needed.

The isolation keeps a later pinning or `--mido-path` feature straightforward, but this pass does not add new Mido flags.

### Git Hygiene

Fix `.gitignore` so runtime logs are ignored. Remove accidental Node package files from the package design unless the user intentionally adds a Node toolchain later.

## Testing

Add `pytest` as a development dependency and create tests under `tests/`.

Initial unit tests:

- `test_checksums.py`: checksum sidecar matching, `SHA256SUMS` matching, missing checksum returns `None`.
- `test_compression.py`: `.gz` and `.bz2` extraction returns the decompressed path and removes the archive.
- `test_downloader_post_download.py`: compressed downloads verify before decompression.
- `test_opnsense_finder.py`: failed URL verification prevents returning the direct ISO.
- `test_truenas_finder.py`: unknown codename returns the download page instead of a guessed URL.
- `test_gitignore.py`: `logs/` is ignored.

Tests use fake sessions and local temp files. The default suite must not hit live network services.

Add `ruff` as a development dependency and configure basic linting in `pyproject.toml`.

## README Updates

Update the "Built with" section to use GitHub-style shields badges for:

- Python
- uv
- requests
- Rich
- pytest
- Ruff

Keep the README's command examples compatible with the preserved CLI commands.

## Implementation Order

1. Add test tooling and the first failing tests for the behavior fixes.
2. Create the package skeleton.
3. Move finder code module by module, preserving behavior.
4. Move downloader helpers into focused modules.
5. Update entry points and build configuration.
6. Fix `.gitignore` and README badges.
7. Run compile, unit tests, CLI help, and a no-network JSON smoke path.

## Acceptance Criteria

- `uv run pytest` passes.
- `uv run ruff check .` passes.
- `uv run python -m py_compile` or equivalent package compile passes.
- `uv run os-finder --help` works.
- `uv run os-download --help` works.
- `uv run os-finder --os windows11 --json` returns the same `mido://win11x64` result.
- The package builds from `src/os_download`.
- No live network access is required for the test suite.
