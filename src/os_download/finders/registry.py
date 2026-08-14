import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext, redirect_stdout

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from os_download.finders.arch import ArchLinuxFinder
from os_download.finders.base import ISO_EXTS, BaseOSFinder, has_iso_link
from os_download.finders.cachyos import CachyOSFinder
from os_download.finders.debian import DebianFinder
from os_download.finders.fedora import FedoraFinder
from os_download.finders.linuxmint import LinuxMintFinder
from os_download.finders.manjaro import ManjaroKDEFinder
from os_download.finders.mxlinux import MXLinuxFinder
from os_download.finders.opensuse import OpenSUSETumbleweedFinder
from os_download.finders.opnsense import OPNsenseFinder
from os_download.finders.pfsense import PfSenseFinder
from os_download.finders.puppy import PuppyLinuxFinder
from os_download.finders.rocky import RockyLinuxFinder
from os_download.finders.truenas import TrueNASFinder
from os_download.finders.ubuntu import UbuntuFinder
from os_download.finders.windows import Windows11Finder

console = Console()
logger = logging.getLogger("os_finder")

OS_CHOICES = [
    "ubuntu",
    "opnsense",
    "pfsense",
    "debian",
    "truenas",
    "windows11",
    "manjaro",
    "mxlinux",
    "puppy",
    "cachyos",
    "fedora",
    "opensuse",
    "arch",
    "linuxmint",
    "rocky",
    "all",
]


def prompt_override_url(os_name: str, session) -> str | None:
    console.print(f"\n[yellow]No direct ISO found for {os_name}.[/]")
    try:
        url = input("   Enter an override URL (or press Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        console.print("   [red]URL must start with http:// or https://, skipping.[/]")
        return None

    try:
        response = session.head(url, timeout=10, allow_redirects=True)
        if response.status_code == 200:
            console.print("   [green]URL verified.[/]")
        else:
            console.print(f"   [yellow]Server returned {response.status_code}, may still work.[/]")
    except Exception as exc:
        console.print(f"   [yellow]Could not verify: {exc}[/]")
    return url


def run_finder(finder: BaseOSFinder):
    buffer = io.StringIO()
    try:
        with redirect_stdout(buffer):
            links = finder.find_download_links()
    except Exception as exc:
        buffer.write(f"Error: {exc}\n")
        links = {}
    return links, buffer.getvalue()


class MultiOSDownloadFinder:
    def __init__(self, timeout: int = 15):
        self.finders = {
            "ubuntu": UbuntuFinder(timeout),
            "opnsense": OPNsenseFinder(timeout),
            "pfsense": PfSenseFinder(timeout),
            "debian": DebianFinder(timeout),
            "truenas": TrueNASFinder(timeout),
            "windows11": Windows11Finder(timeout),
            "manjaro": ManjaroKDEFinder(timeout),
            "mxlinux": MXLinuxFinder(timeout),
            "puppy": PuppyLinuxFinder(timeout),
            "cachyos": CachyOSFinder(timeout),
            "fedora": FedoraFinder(timeout),
            "opensuse": OpenSUSETumbleweedFinder(timeout),
            "arch": ArchLinuxFinder(timeout),
            "linuxmint": LinuxMintFinder(timeout),
            "rocky": RockyLinuxFinder(timeout),
        }

    def find_all_links(
        self,
        os_list: list[str] | None = None,
        interactive: bool = True,
        quiet: bool = False,
    ) -> dict[str, dict[str, str]]:
        valid = [name for name in (os_list or list(self.finders)) if name in self.finders]
        for name in os_list or []:
            if name not in self.finders:
                console.print(f"[yellow]Unknown OS: {name}[/]")

        results: dict[str, dict[str, str]] = {}
        if not valid:
            return {}

        progress_context = nullcontext(None) if quiet else Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description:<20}"),
            TextColumn("{task.fields[status]}"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        )
        with progress_context as progress:
            task_ids = (
                {
                    name: progress.add_task(
                        self.finders[name].name,
                        status="[dim]searching...[/dim]",
                        total=None,
                    )
                    for name in valid
                }
                if progress
                else {}
            )

            try:
                with ThreadPoolExecutor(max_workers=len(valid)) as executor:
                    futures = {
                        executor.submit(run_finder, self.finders[name]): name for name in valid
                    }
                    for future in as_completed(futures):
                        name = futures[future]
                        links, _ = future.result()
                        results[name] = links
                        logger.info(
                            "FINDER  %-14s  links=%d  %s", name, len(links), list(links.keys())
                        )

                        if progress:
                            status = (
                                f"[green]✓ {', '.join(links)}[/green]"
                                if links
                                else "[red]✗ not found[/red]"
                            )
                            progress.update(task_ids[name], status=status, completed=1, total=1)
            except KeyboardInterrupt:
                if quiet:
                    raise
                console.print("\n[yellow]⏸  Interrupted — returning partial results.[/]")
                logger.warning("FINDER INTERRUPTED by user")

        all_links: dict[str, dict[str, str]] = {}
        for name in valid:
            links = results.get(name, {})
            if interactive and not has_iso_link(links):
                override = prompt_override_url(self.finders[name].name, self.finders[name].session)
                if override:
                    links["override"] = override
            if links:
                all_links[name] = links
        return all_links

    def save_links_to_file(
        self,
        all_links: dict[str, dict[str, str]],
        output_path: str = "./os-links/all_os.txt",
    ) -> None:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        written: set[str] = set()
        count = 0
        with open(output_path, "w", encoding="utf-8") as output:
            for os_name, links in all_links.items():
                downloadable = [
                    url
                    for url in links.values()
                    if (url.lower().endswith(ISO_EXTS) or url.startswith("mido://"))
                    and url not in written
                ]
                if not downloadable:
                    continue
                display_name = self.finders[os_name].name if os_name in self.finders else os_name
                output.write(f"# {display_name}\n")
                for url in downloadable:
                    written.add(url)
                    count += 1
                    output.write(f"{url}\n")
                output.write("\n")
        console.print(f"[green]{count} ISO links saved to:[/] {output_path}")
