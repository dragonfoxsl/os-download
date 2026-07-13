import argparse
import json
import logging
import sys

from rich import box as rich_box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from os_download import __version__
from os_download.finders.base import ISO_EXTS, has_iso_link, url_kind
from os_download.finders.registry import OS_CHOICES, MultiOSDownloadFinder
from os_download.logging import setup_file_logger

logger = logging.getLogger("os_finder")
console = Console()


def _print_summary(finder: MultiOSDownloadFinder, all_links: dict[str, dict[str, str]]) -> None:
    table = Table(
        title="[bold]Resolved Links[/]",
        box=rich_box.ROUNDED,
        show_lines=True,
        title_justify="left",
        header_style="bold dim",
        border_style="dim",
    )
    table.add_column("OS", style="bold cyan", no_wrap=True, min_width=14)
    table.add_column("Variant", style="dim", no_wrap=True)
    table.add_column("Type", no_wrap=True, min_width=6)
    table.add_column("URL")

    iso_count = 0
    for os_name, links in all_links.items():
        display_name = finder.finders[os_name].name
        for index, (variant, url) in enumerate(links.items()):
            kind, color = url_kind(url)
            if kind == "ISO":
                iso_count += 1
            table.add_row(
                display_name if index == 0 else "",
                variant,
                f"[{color}]{kind}[/]",
                f"[{color}]{url}[/]",
            )

    console.print(table)
    os_count = len(all_links)
    console.print(
        f"  [dim]{os_count} OS{'es' if os_count != 1 else ''} resolved  ·  "
        f"[green]{iso_count} ISO link{'s' if iso_count != 1 else ''} ready to download[/dim]"
    )


def _run_check(finder: MultiOSDownloadFinder, os_list: list[str]) -> int:
    """Report which finders still resolve an ISO. Exit code is the number that no longer do.

    A finder that quietly stops resolving is this project's real failure mode: mirrors
    reorganise, and nothing tells you until you go to download. Run this on a schedule.
    """
    all_links = finder.find_all_links(os_list, interactive=False, quiet=True)

    broken = []
    for name in os_list:
        links = all_links.get(name, {})
        display_name = finder.finders[name].name
        if has_iso_link(links):
            iso_count = sum(1 for url in links.values() if url.lower().endswith(ISO_EXTS))
            detail = f"{iso_count} ISO{'s' if iso_count != 1 else ''}" if iso_count else "Mido"
            console.print(f"  [green]✓[/] {display_name:<20} [dim]{detail}[/]")
        else:
            broken.append(display_name)
            reason = "no ISO link (only a download page)" if links else "nothing resolved"
            console.print(f"  [red]✗[/] {display_name:<20} [red]{reason}[/]")
            logger.error("CHECK FAILED  %-14s  %s", name, reason)

    console.print()
    if broken:
        console.print(
            f"[red]✗ {len(broken)} of {len(os_list)} finders no longer resolve an ISO:[/] "
            f"{', '.join(broken)}"
        )
        return 1

    console.print(f"[green]✓ All {len(os_list)} finders resolve an ISO.[/]")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-OS Download Link Finder")
    parser.add_argument("--version", action="version", version=f"os-finder {__version__}")
    parser.add_argument(
        "--os",
        nargs="+",
        choices=OS_CHOICES,
        default=["all"],
        help="Operating systems to find download links for",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Disable the override URL prompt when a link cannot be found",
    )
    parser.add_argument(
        "--output",
        default="./os-links/all_os.txt",
        help="Output file for ISO URLs (default: ./os-links/all_os.txt)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="HTTP request timeout in seconds (default: 15)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON and suppress progress messages",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report which OSes still resolve to an ISO and exit non-zero if any do not",
    )
    parser.add_argument(
        "--log",
        metavar="FILE",
        default="./logs/os-finder.log",
        help="Write log to FILE (default: ./logs/os-finder.log)",
    )
    args = parser.parse_args()

    setup_file_logger(logger, args.log)

    finder = MultiOSDownloadFinder(timeout=args.timeout)
    os_list = list(finder.finders.keys()) if "all" in args.os else args.os

    if args.check:
        sys.exit(_run_check(finder, os_list))

    if args.json:
        all_links = finder.find_all_links(os_list, interactive=False, quiet=True)
        print(json.dumps(all_links, indent=2))
        return

    os_display = "  ·  ".join(finder.finders[name].name for name in os_list)
    console.print(
        Panel(
            f"[bold]Multi-OS Download Link Finder[/]\n[dim]{os_display}[/]",
            expand=False,
        )
    )

    all_links = finder.find_all_links(os_list, interactive=not args.no_interactive)

    if not all_links:
        console.print("[red]✗ No download links found for any operating system[/]")
        sys.exit(1)

    console.print()
    _print_summary(finder, all_links)
    console.print()
    finder.save_links_to_file(all_links, output_path=args.output)

    iso_count = sum(
        1
        for links in all_links.values()
        for url in links.values()
        if url.lower().endswith(ISO_EXTS)
    )
    console.print(
        Panel(
            f"  [green]✓[/]  [bold]{iso_count} ISO URL{'s' if iso_count != 1 else ''}[/] "
            f"saved to [cyan]{args.output}[/]\n"
            f"  Run [bold cyan]uv run os-download[/] to start downloading",
            title="[bold green]Ready[/]",
            border_style="green",
            expand=False,
        )
    )


if __name__ == "__main__":
    main()
