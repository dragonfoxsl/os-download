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
uv run os-finder --os ubuntu debian

# Run the download manager (from default URL file)
uv run os-download

# Download a single URL
uv run os-download --url "https://example.com/file.iso"

# Run either script directly (during development)
uv run python os_download_finder.py --os ubuntu
uv run python download_manager.py --url "https://example.com/file.iso"
```

There are no tests or linters configured in this project.

## Architecture

Two independent scripts wired up as `uv` entry points via `pyproject.toml`:

**`os_download_finder.py`** — finds ISO download URLs and writes them to `./os-links/all_os.txt`.
- `BaseOSFinder` is the abstract base class; all per-OS finders subclass it and implement `find_download_links() -> Dict[str, str]`.
- A module-level `_session` (shared `requests.Session` with retry logic and browser User-Agent) is used by all finders via `self.session`.
- `MultiOSDownloadFinder` holds the registry mapping CLI keys (`ubuntu`, `opensense`, etc.) to finder instances. Adding a new OS means: create a subclass, register it here, and add it to the argparse choices.
- URL scraping strategy: each finder tries live web scraping/APIs first, falls back to a hardcoded version pattern, and optionally prompts the user for a manual override URL at runtime (suppressed with `--no-interactive`).
- Output: `./os-links/all_os.txt` contains one ISO URL per line (no comments); `all_os_links.txt` is a verbose annotated version.

**`download_manager.py`** — reads `./os-links/all_os.txt` and downloads each ISO with progress and resume support.
- `DownloadManager` handles all download logic. Resume works via HTTP `Range` headers; if the server returns anything other than 206/416 for a range request, it falls back to a full download.
- Default download directory is OS-aware: `~/Downloads/os-isos` on all platforms (respects `XDG_DOWNLOAD_DIR` on Linux).
- Progress is printed every 2 seconds; the final line is printed after the download completes.

The two scripts are designed to be run sequentially: finder first to populate `./os-links/all_os.txt`, then downloader to fetch the ISOs.

## OS-specific Notes

- **pfSense / Windows 11**: No direct ISO links available; finder returns a download page URL instead.
- **TrueNAS Scale**: Version-to-codename mapping is hardcoded in `TrueNASFinder.codenames`; update this dict when new major releases ship.
- **OPNsense**: ISO filename is `.iso.bz2` on some mirror versions — the regex in `OpenSenseFinder` handles both.
