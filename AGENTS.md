# Repository Guidance

- Never add `Codex`, `Co-authored-by`, or any other AI co-author trailer to commits.
- Follow secure-by-default development practices for Python, CLI, download, checksum, subprocess, and GitHub Actions changes.
- Keep code, tests, workflows, and configuration files under 1000 lines. Normal documentation files may grow to 2000 lines; split documentation before it exceeds that limit.
- Add concise comments for non-obvious security, network, checksum, retry, or platform-specific logic. Avoid comments that restate the code.
- Update `README.md` with every user-facing, operational, setup, security, or workflow change.
- For future README creation or major rewrites, follow this repository's public README style: visual header/badges when relevant, concise product summary, clear command blocks, practical tables, and license at the end.
- Keep agent instructions, branch state, dated PR lists, and operational handoff notes out of `README.md`; put them in `HANDOFF.md` or `AGENTS.md`.
- Ko-fi/support sections are optional. Preserve existing ones, but do not add new Ko-fi or donation content unless the user explicitly requests it.
- Update `HANDOFF.md` with each change so the next maintainer can see what changed, how it was verified, and what remains.
- Before committing, run the relevant tests, builds, audits, and `git diff --check`. Before pushing, if GitHub Actions or Dependabot are configured, check for CI failures and open Dependabot alerts or failing dependency PRs.
