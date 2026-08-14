# CLAUDE.md

Follow `AGENTS.md`. User-facing commands, setup, and release steps live in `README.md`; current maintenance state lives in `HANDOFF.md`.

## Verification

```bash
uv sync --locked
uv run ruff check
uv run pytest -q
uv build
pnpm audit --audit-level high
```

## Invariants

- Keep `pyproject.toml` and `src/os_download/__init__.py` versions aligned before tagging.
- README image URLs must be absolute so they render on PyPI. Regenerate images from the real CLIs and `SessionDashboard`; do not hand-edit screenshots.
- Finder and downloader sessions are thread-local because `requests.Session` is not thread-safe.
- Keep `Accept-Encoding: identity`: content encoding can make nginx ignore range requests and silently turn resumes into full downloads.
- Finder failures must call `self.log_failure(exc)`; mirror failures should not become unexplained “not found” results.
- Verification is signature-then-hash. Trust only pinned fingerprints or keys served over HTTPS by the distribution itself.
- Invalid signatures are fatal. Unsigned checksums warn unless `--require-signature` is set.
- Quarantine failed downloads instead of leaving corrupt bytes available for resume.
- Never append to an incomplete aria2 file; segmented files may contain holes.
- Keep Rich display logic in `downloader/ui.py`; `DownloadManager` owns orchestration.
- Mido is executed from the pinned `MIDO_COMMIT`. Change that reference deliberately.

## Adding an OS

Create a `BaseOSFinder` subclass, register it in `MultiOSDownloadFinder.finders`, add its key to `OS_CHOICES`, and cover its parsing or fallback behavior with the smallest useful test.
