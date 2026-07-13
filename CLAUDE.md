# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Git Commits

Do not mention Claude or add any `Co-Authored-By: Claude` lines in commit messages.

## Commands

```bash
# Install dependencies
uv sync

# Run the OS link finder (all OSes)
uv run os-finder

# Run the OS link finder (specific OSes)
uv run os-finder --os ubuntu fedora opensuse arch linuxmint rocky

# Check every finder still resolves an ISO (what the scheduled mirror canary runs)
uv run os-finder --check

# Run the download manager (from default URL file)
uv run os-download

# Download a single URL
uv run os-download --url "https://example.com/file.iso"

# Run tests and lint
uv run pytest -q
uv run ruff check

# Regenerate the README images after changing flags or the dashboard
uv run python scripts/render_help_svg.py        # both --help screenshots
uv run python scripts/render_dashboard_svg.py   # the download dashboard
```

The README screenshots are generated from the real CLIs and the real `SessionDashboard`, never hand-edited — a hand-edited one silently advertised a `--verify` flag that had been removed. Note that `rsvg-convert` renders Rich's SVG export badly (it collapses the spacing); check them in a browser, which is what GitHub uses.

Tests and linting are configured through `pyproject.toml`.

## Architecture

Two package entry points wired through `pyproject.toml`:

**`src/os_download/cli/finder.py`** — finds ISO download URLs and writes them to `./os-links/all_os.txt`.
- `BaseOSFinder` is the abstract base class; all per-OS finders subclass it and implement `find_download_links() -> dict[str, str]`.
- `self.session` is a thread-local `requests.Session` (`http.get_session()`) with retry logic and a browser User-Agent. `requests.Session` is not thread-safe and finders run concurrently, so never share one across threads.
- **The session sends `Accept-Encoding: identity` on purpose — do not remove it.** requests defaults to `gzip, deflate`, and nginx ignores `Range` whenever a content-coding is negotiated: it answers `200` with the whole file instead of `206`/`416`, which silently turns every resume into a full re-download. `test_download_file_resumes_a_partial_file_without_refetching_it` guards this by counting bytes served.
- Mirror lookups fail routinely, so finders swallow exceptions — but every handler must call `self.log_failure(exc)` so a mirror layout change is diagnosable from the log instead of silently reporting "not found".
- `MultiOSDownloadFinder` holds the registry mapping CLI keys (`ubuntu`, `opnsense`, `fedora`, etc.) to finder instances. Adding a new OS means: create a subclass, register it here, and add it to `OS_CHOICES`.
- URL scraping strategy: each finder tries live web scraping/APIs first, falls back to a hardcoded version pattern, and optionally prompts the user for a manual override URL at runtime (suppressed with `--no-interactive`).
- Output: `./os-links/all_os.txt` contains one ISO URL per line, grouped under `# <OS name>` comments.

**`src/os_download/cli/downloader.py`** — reads `./os-links/all_os.txt` and downloads each ISO with progress and resume support.
- `DownloadManager` (`downloader/manager.py`) owns orchestration only. Resume works via HTTP `Range` headers; if the server returns anything other than 206/416 for a range request, it falls back to a full download. A 403 falls back to `curl`.
- `downloader/ui.py` owns everything Rich: `SessionDashboard` (layout, header, completion panel) and `SessionState`. Keep display logic out of `manager.py`.
- `SessionState` counts a file only once its future reports back, so interrupting a session leaves never-started files out of both the success and failure tallies. Don't reintroduce `success = total - failed`.
- Verification is **on by default** (`--no-verify` to skip) and runs signature-then-hash through `downloader/verification.py`:
  - `checksums.py` finds the published hash *and the document it came from*, handling the conventions mirrors use: sidecars, `SHA256SUMS` / `sha256sum.txt` / `CHECKSUM`, GNU and BSD (`SHA256 (name) = hash`) formats, and scraping the directory index for release-named files (Fedora).
  - `signatures.py` verifies the signature over that document. **Keys are only ever imported by pinned fingerprint, or from a keyring served over HTTPS by the distro itself** — never from the mirror. A valid signature by an unpinned key is treated as an attack, not a pass. Changing a pinned fingerprint is a security decision: corroborate it against the distribution's own published key.
  - An invalid signature is fatal even when the hash matches; an unsigned checksum only warns unless `--require-signature`.
- A file that fails verification is renamed to `<name>.corrupt`, never left in place — a later resume would otherwise append to corrupt bytes. A verified file gets a `.verified` marker (size + mtime) so multi-GB ISOs are not re-hashed every run.
- Backends: built-in (requests), `curl` on 403, and `aria2c` for segmented downloads (`--backend`, default `auto`). **A partial aria2 download must never be handed to the byte-appending resume path** — segmented files can have holes, so appending from their current length silently corrupts them. `manager._use_aria2` and `_discard_partial` enforce this.
- `download_file` retries transient failures in place with backoff; `Outcome` distinguishes RETRYABLE (dropped connection) from FATAL (404, bad checksum), because retrying a verdict on the bytes just re-fails.
- Default download directory is OS-aware: `~/Downloads/os-isos` on all platforms (respects `XDG_DOWNLOAD_DIR` on Linux).

The two commands are designed to be run sequentially: finder first to populate `./os-links/all_os.txt`, then downloader to fetch the ISOs.

## OS-specific Notes

- **Windows 11**: Uses the `mido://win11x64` pseudo-URL and delegates direct ISO resolution to Mido during download. Mido is fetched at the pinned commit in `downloader/mido.py` (`MIDO_COMMIT`), not from the default branch, because `Mido.sh` is executed locally. Bump that constant deliberately; `OS_DOWNLOAD_MIDO_REF` overrides it.
- **pfSense CE**: Direct ISO is compressed as `.iso.gz`; downloader auto-extracts it unless `--no-decompress` is set.
- **TrueNAS Scale**: Version-to-codename mapping is hardcoded in `TrueNASFinder.codenames`; update this dict when new major releases ship.
- **OPNsense**: ISO filename is `.iso.bz2` on some mirror versions; downloader auto-extracts it unless `--no-decompress` is set.
- **Fedora, openSUSE Tumbleweed, Arch Linux, Linux Mint, Rocky Linux**: Supported through direct mirror directory scraping or stable current/latest ISO aliases.
