#!/usr/bin/env python3
"""Render the README's terminal-window screenshots from live --help output.

The help screenshots are easy to forget and go stale silently: the committed one still
advertised --verify long after the flag was replaced. Regenerate them instead of editing
the SVG by hand:

    uv run python scripts/render_help_svg.py
"""

import os
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "screenshots"

# Catppuccin Mocha, matching the existing screenshots.
BG = "#1e1e2e"
TITLE_BAR = "#181825"
TITLE_TEXT = "#7f849c"
PROMPT = "#a6e3a1"
BODY = "#cdd6f4"
DOTS = ("#f38ba8", "#f9e2af", "#a6e3a1")

CHAR_WIDTH = 8.42  # measured for 14px JetBrains Mono
LINE_HEIGHT = 20
TOP = 64
PADDING_X = 24
BOTTOM_PADDING = 20


def help_text(command: str) -> list[str]:
    # The default download directory is derived from the user's home, which would otherwise
    # bake the generating machine's home path into a public README. XDG_DOWNLOAD_DIR takes
    # precedence, so set that rather than HOME, which uv needs for its own cache.
    environment = {
        **os.environ,
        "COLUMNS": "100",
        "XDG_DOWNLOAD_DIR": "/home/user/Downloads",
    }
    result = subprocess.run(
        ["uv", "run", command, "--help"],
        capture_output=True,
        text=True,
        check=True,
        env=environment,
    )
    return result.stdout.rstrip().splitlines()


def render(command: str) -> str:
    lines = help_text(command)
    columns = max(len(line) for line in lines + [f"$ {command} --help"])

    width = int(PADDING_X * 2 + columns * CHAR_WIDTH)
    height = TOP + (len(lines) + 1) * LINE_HEIGHT + BOTTOM_PADDING

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" rx="14" fill="{BG}"/>',
        f'<rect x="0" y="0" width="{width}" height="42" rx="14" fill="{TITLE_BAR}"/>',
        f'<path d="M0 28 Q0 42 14 42 H{width - 14} Q{width} 42 {width} 28 V42 H0 Z" '
        f'fill="{TITLE_BAR}"/>',
    ]
    for index, colour in enumerate(DOTS):
        parts.append(f'<circle cx="{24 + index * 22}" cy="21" r="6" fill="{colour}"/>')

    parts.append(
        f'<text x="{width // 2}" y="26" text-anchor="middle" '
        f'font-family="Inter, Arial, sans-serif" font-size="13" font-weight="600" '
        f'fill="{TITLE_TEXT}">{command} --help</text>'
    )
    parts.append(
        f'<text x="{PADDING_X}" y="{TOP}" font-family="JetBrains Mono, Consolas, monospace" '
        f'font-size="14" fill="{PROMPT}">$ {command} --help</text>'
    )

    for index, line in enumerate(lines):
        y = TOP + (index + 1) * LINE_HEIGHT + 8
        parts.append(
            f'<text x="{PADDING_X}" y="{y}" '
            f'font-family="JetBrains Mono, Consolas, monospace" font-size="14" '
            f'fill="{BODY}" xml:space="preserve">{escape(line)}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    for command in ("os-finder", "os-download"):
        target = OUT_DIR / f"{command}-help.svg"
        target.write_text(render(command), encoding="utf-8")
        print(f"wrote {target.relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
