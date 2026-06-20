STATUS: done

Files changed:
- `src/os_download/downloader/paths.py`
- `src/os_download/downloader/mido.py`
- `src/os_download/downloader/curl.py`
- `src/os_download/downloader/manager.py`
- `.superpowers/sdd/task-4-report.md`

Commands run and outcomes:
- `sed -n '1,260p' .superpowers/sdd/task-4-brief.md`
  - Reviewed Task 4 requirements and target interfaces.
- `git status --short`
  - Observed unrelated untracked files: `logs/`, `node_modules/`, `package.json`, `pnpm-lock.yaml`.
- `rg --files src/os_download/downloader tests | sort`
  - Confirmed existing package helpers and focused test file.
- `rg -n "class DownloadManager|def _post_download|def _download_with_curl|def _ensure_mido|def _download_with_mido|def _keyboard_listener|filename_from_url|default_download_dir" -S .`
  - Located legacy downloader implementations in `download_manager.py`.
- `sed -n '1,320p' download_manager.py`
  - Read legacy helper and manager implementations to move into package modules.
- `sed -n '1,260p' tests/test_downloader_post_download.py`
  - Reviewed focused regression test for verify-before-decompress behavior.
- `git branch --show-current`
  - Confirmed branch is `package-cleanup`.
- `uv run pytest tests/test_downloader_post_download.py -q`
  - Failed before test execution because `uv` could not write to the home cache in this environment.
- `/usr/bin/zsh -lc 'UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_downloader_post_download.py -q'`
  - Failed red due to missing package module: `ModuleNotFoundError: No module named 'os_download.downloader.manager'`.
- `sed -n '1,240p' src/os_download/downloader/checksums.py`
  - Reviewed shared checksum helper from Task 2.
- `sed -n '1,240p' src/os_download/downloader/compression.py`
  - Reviewed shared decompression helper from Task 2.
- `sed -n '1,220p' src/os_download/http.py`
  - Reviewed shared HTTP session builder from Task 2.
- `sed -n '320,760p' download_manager.py`
  - Read remaining legacy manager methods needed for package move.
- `/usr/bin/zsh -lc 'UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/test_downloader_post_download.py -q'`
  - Passed green: `1 passed in 0.34s`.
- `sed -n '1,260p' .../skills/verification-before-completion/SKILL.md`
  - Reviewed verification requirement before commit/completion.
- `git diff -- src/os_download/downloader/paths.py src/os_download/downloader/mido.py src/os_download/downloader/curl.py src/os_download/downloader/manager.py`
  - Verified package file changes are limited to Task 4 additions.
- `git status --short src/os_download/downloader/paths.py src/os_download/downloader/mido.py src/os_download/downloader/curl.py src/os_download/downloader/manager.py .superpowers/sdd/task-4-report.md`
  - Verified staged scope target files only.

Commits made:
- `refactor: move downloader into package`
- Commit hashes for this task are available in git history and reported in the task handoff response.

Self-review notes:
- Kept write scope limited to the four package downloader files plus this report.
- Implemented `default_download_dir()` and `filename_from_url()` in the package helper module as specified.
- Moved Mido and curl downloader helpers into package modules with the required interfaces.
- Added package `DownloadManager` wrappers around Task 2 helpers for session creation, checksum verification, and decompression.
- Updated `_post_download()` to verify the downloaded archive before decompression, which is the behavior covered by the focused regression test.
- Left legacy top-level downloader script untouched, per task constraints.
