import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import redirect_stdout
from typing import Dict, List, Optional

from rich.console import Console

from os_download.finders.base import BaseOSFinder, has_iso_link
from os_download.finders.cachyos import CachyOSFinder
from os_download.finders.debian import DebianFinder
from os_download.finders.manjaro import ManjaroKDEFinder
from os_download.finders.mxlinux import MXLinuxFinder
from os_download.finders.opnsense import OPNsenseFinder
from os_download.finders.pfsense import PfSenseFinder
from os_download.finders.puppy import PuppyLinuxFinder
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
    "all",
]


def prompt_override_url(os_name: str, session) -> Optional[str]:
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
        }

    def find_all_links(
        self,
        os_list: Optional[List[str]] = None,
        interactive: bool = True,
        quiet: bool = False,
    ) -> Dict[str, Dict[str, str]]:
        valid = [name for name in (os_list or list(self.finders)) if name in self.finders]
        for name in os_list or []:
            if name not in self.finders:
                console.print(f"[yellow]Unknown OS: {name}[/]")

        results: Dict[str, Dict[str, str]] = {}
        with ThreadPoolExecutor(max_workers=len(valid)) as executor:
            futures = {executor.submit(run_finder, self.finders[name]): name for name in valid}
            for future in as_completed(futures):
                name = futures[future]
                links, _ = future.result()
                results[name] = links
                logger.info("FINDER  %-14s  links=%d  %s", name, len(links), list(links.keys()))

        all_links: Dict[str, Dict[str, str]] = {}
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
        all_links: Dict[str, Dict[str, str]],
        output_path: str = "./os-links/all_os.txt",
    ) -> None:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as output:
            for links in all_links.values():
                for url in links.values():
                    if url.lower().endswith((".iso", ".iso.bz2", ".iso.gz")) or url.startswith(
                        "mido://"
                    ):
                        output.write(f"{url}\n")
        console.print(f"[green]ISO links saved to:[/] {output_path}")
