STATUS: DONE

Files changed:
- `src/os_download/cli/__init__.py`
- `src/os_download/cli/finder.py`
- `src/os_download/cli/downloader.py`
- `pyproject.toml`

Commands run and outcomes:
- `UV_CACHE_DIR=/tmp/uv-cache uv run os-finder --help`
  - Before implementation: failed with `ModuleNotFoundError: No module named 'os_download_finder'`
  - After implementation: passed, package rebuilt and help output rendered
- `UV_CACHE_DIR=/tmp/uv-cache uv run os-download --help`
  - Before implementation: failed with `ModuleNotFoundError: No module named 'download_manager'`
  - After implementation: passed and help output rendered
- `UV_CACHE_DIR=/tmp/uv-cache uv run os-finder --os windows11 --json`
  - Before implementation: failed with `ModuleNotFoundError: No module named 'os_download_finder'`
  - After implementation: passed and returned:
    ```json
    {
      "windows11": {
        "win11x64": "mido://win11x64"
      }
    }
    ```
- `PYTHONPATH=src .venv/bin/python -m os_download.cli.finder --help`
  - Passed; used as a local package import sanity check while `uv run` was blocked by sandboxed network resolution
- `PYTHONPATH=src .venv/bin/python -m os_download.cli.downloader --help`
  - Passed; used as a local package import sanity check while `uv run` was blocked by sandboxed network resolution
- `PYTHONPATH=src .venv/bin/python -m os_download.cli.finder --os windows11 --json`
  - Passed; matched the expected Windows 11 JSON payload
- `git diff -- src/os_download/cli/__init__.py src/os_download/cli/finder.py src/os_download/cli/downloader.py pyproject.toml`
  - Reviewed targeted Task 5 changes only
- `git status --short`
  - Confirmed unrelated untracked files existed and were left untouched

Commits made:
- `refactor: add package cli entry points`

Self-review notes:
- Kept write scope to the Task 5 files plus this report.
- Moved finder/downloader CLI behavior into package modules without editing legacy top-level scripts.
- Updated `[project.scripts]` to package entry points so the packaged CLI matches the wheel layout introduced earlier.
- Verification needed temporary unsandboxed network because `uv run` had to fetch `hatchling` from PyPI before rebuilding the package metadata.
