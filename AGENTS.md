# Repository Guidance

- Never add `Codex`, `Co-authored-by`, or any other AI co-author trailer to commits.
- Follow secure-by-default development practices for Python, CLI, download, checksum, subprocess, and GitHub Actions changes.
- Keep every source, test, workflow, and documentation file under 1000 lines. Split files before they exceed that limit.
- Add concise comments for non-obvious security, network, checksum, retry, or platform-specific logic. Avoid comments that restate the code.
- Update `README.md` with every user-facing, operational, setup, security, or workflow change.
- Update `HANDOFF.md` with each change so the next maintainer can see what changed, how it was verified, and what remains.
- Before committing, run the relevant tests, builds, audits, and `git diff --check`.
