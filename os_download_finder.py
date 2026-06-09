#!/usr/bin/env python3
"""
Multi-OS Download Link Finder

Finds download links for:
- Ubuntu (Latest LTS + Latest release, Server & Desktop)
- OPNsense
- pfSense CE
- Debian (Stable)
- TrueNAS Scale
- Windows 11
- Manjaro KDE
- MX Linux
- Puppy Linux
- CachyOS
"""

import io
import json
import logging
import os
import re
import sys
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import redirect_stdout
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.table import Table
from rich import box as rich_box

console = Console()
logger = logging.getLogger("os_finder")


def setup_logging(log_file: str) -> None:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s"))
    logger.setLevel(logging.DEBUG)
    logger.addHandler(fh)


def _build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        )
    })
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


_session = _build_session()


class BaseOSFinder:
    def __init__(self, name: str, timeout: int = 15):
        self.name = name
        self.timeout = timeout
        self.session = _session

    def verify_download_url(self, url: str) -> bool:
        try:
            response = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            return response.status_code == 200
        except Exception:
            return False

    def find_download_links(self) -> Dict[str, str]:
        raise NotImplementedError


class UbuntuFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("Ubuntu", timeout)
        self.base_url = "http://releases.ubuntu.com/"
        self.api_url = "https://api.launchpad.net/1.0/ubuntu/series"

    def _get_versions(self) -> Tuple[Optional[str], Optional[str]]:
        """Returns (latest_version, lts_version). Both may be the same."""
        try:
            response = self.session.get(self.api_url, timeout=self.timeout)
            response.raise_for_status()
            entries = response.json().get('entries', [])
            supported = [e for e in entries if e.get('supported') and e.get('version')]
            supported.sort(key=lambda e: tuple(map(int, e['version'].split('.'))))

            if supported:
                latest = supported[-1]['version']
                lts_entries = [e for e in supported if 'LTS' in e.get('displayname', '')]
                lts = lts_entries[-1]['version'] if lts_entries else latest
                return latest, lts
        except Exception:
            pass

        # Fallback: scrape the releases index
        try:
            response = self.session.get(self.base_url, timeout=self.timeout)
            response.raise_for_status()
            versions = re.findall(r'href="(\d+\.\d+)/"', response.text)
            if versions:
                versions.sort(key=lambda x: tuple(map(int, x.split('.'))))
                latest = versions[-1]
                lts_candidates = [
                    v for v in versions
                    if int(v.split('.')[0]) % 2 == 0 and int(v.split('.')[1]) == 4
                ]
                lts = lts_candidates[-1] if lts_candidates else latest
                return latest, lts
        except Exception:
            pass

        return None, None

    def _links_for_version(self, version: str) -> Dict[str, str]:
        base_url = f"{self.base_url}{version}/"
        links = {
            'desktop': f"{base_url}ubuntu-{version}-desktop-amd64.iso",
            'server': f"{base_url}ubuntu-{version}-live-server-amd64.iso",
        }
        try:
            response = self.session.get(base_url, timeout=self.timeout)
            if response.status_code == 200:
                for key, pattern in [
                    ('desktop', r'href="([^"]*ubuntu[^"]*desktop[^"]*\.iso)"'),
                    ('server', r'href="([^"]*ubuntu[^"]*live-server[^"]*\.iso)"'),
                ]:
                    m = re.search(pattern, response.text, re.IGNORECASE)
                    if m:
                        links[key] = urljoin(base_url, m.group(1))
        except Exception:
            pass
        return links

    def find_download_links(self) -> Dict[str, str]:
        latest_version, lts_version = self._get_versions()
        if not lts_version and not latest_version:
            return {}

        result = {}
        same = latest_version == lts_version

        if lts_version:
            prefix = "" if same else "lts-"
            for variant, url in self._links_for_version(lts_version).items():
                if self.verify_download_url(url):
                    result[f"{prefix}{variant}"] = url

        if latest_version and not same:
            for variant, url in self._links_for_version(latest_version).items():
                if self.verify_download_url(url):
                    result[f"latest-{variant}"] = url

        return result


class OPNsenseFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("OPNsense", timeout)
        self.pkg_index = "https://pkg.opnsense.org/releases/"

    def find_download_links(self) -> Dict[str, str]:
        try:
            r = self.session.get(self.pkg_index, timeout=self.timeout)
            r.raise_for_status()
            versions = re.findall(r'href="(\d+\.\d+)/"', r.text)
            if not versions:
                return {}
            versions.sort(key=lambda v: tuple(map(int, v.split('.'))))
            latest = versions[-1]

            version_url = f"{self.pkg_index}{latest}/"
            r = self.session.get(version_url, timeout=self.timeout)
            r.raise_for_status()
            isos = re.findall(r'href="(OPNsense-[\d.]+-dvd-amd64\.iso(?:\.bz2)?)"', r.text, re.IGNORECASE)
            if not isos:
                return {}
            isos.sort(key=lambda n: tuple(int(x) for x in re.findall(r'\d+', re.search(r'OPNsense-([\d.]+)-', n).group(1))))
            url = version_url + isos[-1]
            return {'amd64': url} if self.verify_download_url(url) or True else {}
        except Exception:
            return {}


class PfSenseFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("pfSense CE", timeout)
        self.cdn_url = "https://atxfiles.netgate.com/mirror/downloads/"

    def find_download_links(self) -> Dict[str, str]:
        try:
            r = self.session.get(self.cdn_url, timeout=self.timeout)
            r.raise_for_status()
            # Find all CE ISO files, pick the latest by version
            isos = re.findall(r'href="(pfSense-CE-([\d.]+)-RELEASE-amd64\.iso\.gz)"', r.text)
            if not isos:
                return {'download_page': 'https://www.pfsense.org/download/'}
            isos.sort(key=lambda t: tuple(map(int, t[1].split('.'))))
            filename = isos[-1][0]
            url = self.cdn_url + filename
            return {'amd64': url}
        except Exception:
            return {'download_page': 'https://www.pfsense.org/download/'}


class DebianFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("Debian", timeout)

    def find_download_links(self) -> Dict[str, str]:
        links = {}

        try:
            r = self.session.get(
                "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/",
                timeout=self.timeout,
            )
            if r.status_code == 200:
                m = re.search(r'href="(debian[^"]*netinst\.iso)"', r.text)
                if m:
                    links['netinst'] = (
                        f"https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/{m.group(1)}"
                    )
        except Exception:
            pass

        try:
            r = self.session.get(
                "https://cdimage.debian.org/debian-cd/current/amd64/iso-dvd/",
                timeout=self.timeout,
            )
            if r.status_code == 200:
                m = re.search(r'href="(debian[^"]*DVD-1\.iso)"', r.text)
                if m:
                    links['dvd'] = (
                        f"https://cdimage.debian.org/debian-cd/current/amd64/iso-dvd/{m.group(1)}"
                    )
        except Exception:
            pass

        verified = {}
        for variant, url in links.items():
            if self.verify_download_url(url):
                verified[variant] = url
            else:
                verified[variant] = url  # include even if HEAD fails
        return verified


class TrueNASFinder(BaseOSFinder):
    codenames = {
        '25.04': 'Fangtooth',
        '24.10': 'Electric-Eel',
        '24.04': 'Dragonfish',
    }

    def __init__(self, timeout: int = 15):
        super().__init__("TrueNAS Scale", timeout)
        self.github_api = "https://api.github.com/repos/truenas/truenas-scale/releases/latest"
        self.download_base = "https://download.sys.truenas.net/TrueNAS-SCALE-"

    def find_download_links(self) -> Dict[str, str]:
        version = None
        try:
            r = self.session.get(self.github_api, timeout=self.timeout)
            r.raise_for_status()
            tag = r.json().get('tag_name', '')
            version = tag.replace('TrueNAS-SCALE-', '').strip() or None
        except Exception:
            pass

        if not version:
            version = "25.04.1"

        major_minor = '.'.join(version.split('.')[:2])
        codename = self.codenames.get(major_minor)
        if codename is None:
            codename = list(self.codenames.values())[-1]

        url = f"{self.download_base}{codename}/{version}/TrueNAS-SCALE-{version}.iso"
        return {'scale': url}


class Windows11Finder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("Windows 11", timeout)

    def find_download_links(self) -> Dict[str, str]:
        # Microsoft's ISO download requires JavaScript session tokens; use Mido.
        return {'win11x64': 'mido://win11x64'}


class ManjaroKDEFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("Manjaro KDE", timeout)
        self.products_url = "https://manjaro.org/products/download/x86"
        self.download_url = "https://manjaro.org/download/"

    def find_download_links(self) -> Dict[str, str]:
        try:
            r = self.session.get(self.products_url, timeout=self.timeout)
            r.raise_for_status()
            m = re.search(r'href="(https://download\.manjaro\.org/kde/[^"]+\.iso)"', r.text)
            if m:
                return {'kde': m.group(1)}
            return {'download_page': self.download_url}
        except Exception:
            return {'download_page': self.download_url}


class MXLinuxFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("MX Linux", timeout)
        self.sf_rss   = "https://sourceforge.net/projects/mx-linux/rss?path=/Final&limit=50"
        self.sf_final = "https://sourceforge.net/projects/mx-linux/files/Final/"

    def find_download_links(self) -> Dict[str, str]:
        # SourceForge RSS feed — no JS required, always current
        # File structure: Final/Xfce/MX-X.X_Xfce_x64.iso
        try:
            r = self.session.get(self.sf_rss, timeout=self.timeout)
            if r.status_code == 200:
                paths = re.findall(
                    r'files/(Final/Xfce/MX-[\d.]+_Xfce_x64\.iso)/download',
                    r.text,
                )
                if paths:
                    # Pick the newest version (sort by version numbers in filename)
                    paths.sort(
                        key=lambda p: tuple(int(x) for x in re.findall(r'\d+', p)),
                        reverse=True,
                    )
                    return {'xfce-x64': f"https://downloads.sourceforge.net/project/mx-linux/{paths[0]}"}
        except Exception:
            pass

        return {'download_page': self.sf_final}


class PuppyLinuxFinder(BaseOSFinder):
    # SourceForge projects to try before falling back to ibiblio (CDN-backed = much faster)
    SF_PROJECTS = [
        ('fossapup64', 'fossapup'),
        ('bionicpup64', 'bionicpup'),
    ]
    VARIANT_DIRS = ['puppy-trixie', 'puppy-bookwormpup', 'puppy-fossa', 'puppy-bionic']

    def __init__(self, timeout: int = 15):
        super().__init__("Puppy Linux", timeout)
        self.distro_url = "http://distro.ibiblio.org/puppylinux/"
        self.download_url = "http://puppylinux-woof-ce.github.io/woof-CE/index.html#downloads"

    def _try_sourceforge(self) -> Optional[Tuple[str, str]]:
        for project, variant in self.SF_PROJECTS:
            try:
                r = self.session.get(
                    f"https://sourceforge.net/projects/{project}/files/",
                    timeout=self.timeout,
                )
                if r.status_code != 200:
                    continue
                # Look for version subdirectories (e.g. title="9.5")
                subdirs = re.findall(r'title="([\d.]+)"', r.text)
                if subdirs:
                    subdirs.sort(key=lambda v: tuple(int(x) for x in re.findall(r'\d+', v) or ['0']))
                    latest = subdirs[-1]
                    r2 = self.session.get(
                        f"https://sourceforge.net/projects/{project}/files/{latest}/",
                        timeout=self.timeout,
                    )
                    if r2.status_code == 200:
                        isos = re.findall(r'title="([\w.-]+\.iso)"', r2.text, re.IGNORECASE)
                        if isos:
                            iso = next((i for i in isos if '64' in i), isos[0])
                            url = f"https://downloads.sourceforge.net/project/{project}/{latest}/{iso}"
                            return variant, url
                # ISOs might be at root level
                isos = re.findall(r'title="([\w.-]+\.iso)"', r.text, re.IGNORECASE)
                if isos:
                    iso = next((i for i in isos if '64' in i), isos[0])
                    url = f"https://downloads.sourceforge.net/project/{project}/{iso}"
                    return variant, url
            except Exception:
                continue
        return None

    def find_download_links(self) -> Dict[str, str]:
        sf = self._try_sourceforge()
        if sf:
            variant, url = sf
            return {variant: url}

        for dirname in self.VARIANT_DIRS:
            dir_url = f"{self.distro_url}{dirname}/"
            try:
                r = self.session.get(dir_url, timeout=self.timeout)
                if r.status_code != 200:
                    continue
                isos = re.findall(r'href="([^"]*\.iso)"', r.text, re.IGNORECASE)
                if not isos:
                    continue
                iso = next((i for i in isos if '64' in i), isos[0])
                url = urljoin(dir_url, iso)
                return {dirname.replace('puppy-', ''): url}
            except Exception:
                continue

        return {'download_page': self.download_url}


class CachyOSFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("CachyOS", timeout)
        self.mirror_base = "https://mirror.cachyos.org/ISO/desktop/"

    def find_download_links(self) -> Dict[str, str]:
        try:
            r = self.session.get(self.mirror_base, timeout=self.timeout)
            r.raise_for_status()
            versions = re.findall(r'href="(\d{6})/"', r.text)
            if not versions:
                return {'download_page': 'https://cachyos.org/download/'}

            versions.sort()
            version_url = f"{self.mirror_base}{versions[-1]}/"
            r = self.session.get(version_url, timeout=self.timeout)
            m = re.search(r'href="(cachyos-desktop-linux-[^"]+\.iso)"', r.text)
            if not m:
                return {'download_page': 'https://cachyos.org/download/'}

            return {'desktop': version_url + m.group(1)}
        except Exception:
            return {'download_page': 'https://cachyos.org/download/'}


def _prompt_override_url(os_name: str) -> Optional[str]:
    console.print(f"\n[yellow]💬 No direct ISO found for {os_name}.[/]")
    try:
        url = input("   Enter an override URL (or press Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not url:
        return None

    if not url.startswith(("http://", "https://")):
        console.print("   [red]⚠ URL must start with http:// or https:// — skipping.[/]")
        return None

    try:
        r = _session.head(url, timeout=10, allow_redirects=True)
        if r.status_code == 200:
            console.print("   [green]✓ URL verified.[/]")
        else:
            console.print(f"   [yellow]⚠ Server returned {r.status_code} — may still work.[/]")
    except Exception as e:
        console.print(f"   [yellow]⚠ Could not verify: {e}[/]")
    return url


def _has_iso_link(links: Dict[str, str]) -> bool:
    return any(
        url.lower().endswith(".iso") or url.lower().endswith(".iso.bz2")
        or url.lower().endswith(".iso.gz") or url.startswith("mido://")
        for url in links.values()
    )


def _run_finder(finder: BaseOSFinder):
    """Run a finder, suppressing its stdout. Returns (links, captured_output)."""
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            links = finder.find_download_links()
    except Exception as e:
        buf.write(f"Error: {e}\n")
        links = {}
    return links, buf.getvalue()


class MultiOSDownloadFinder:
    def __init__(self, timeout: int = 15):
        self.finders = {
            'ubuntu': UbuntuFinder(timeout),
            'opnsense': OPNsenseFinder(timeout),
            'pfsense': PfSenseFinder(timeout),
            'debian': DebianFinder(timeout),
            'truenas': TrueNASFinder(timeout),
            'windows11': Windows11Finder(timeout),
            'manjaro': ManjaroKDEFinder(timeout),
            'mxlinux': MXLinuxFinder(timeout),
            'puppy': PuppyLinuxFinder(timeout),
            'cachyos': CachyOSFinder(timeout),
        }

    def find_all_links(
        self,
        os_list: List[str] = None,
        interactive: bool = True,
        quiet: bool = False,
    ) -> Dict[str, Dict[str, str]]:
        valid = [n for n in (os_list or list(self.finders)) if n in self.finders]
        for name in (os_list or []):
            if name not in self.finders:
                console.print(f"[yellow]⚠ Unknown OS: {name}[/]")

        results: Dict[str, Dict[str, str]] = {}

        if quiet:
            with ThreadPoolExecutor(max_workers=len(valid)) as executor:
                futures = {executor.submit(_run_finder, self.finders[n]): n for n in valid}
                for future in as_completed(futures):
                    links, _ = future.result()
                    results[futures[future]] = links
        else:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold cyan]{task.description:<20}"),
                TextColumn("{task.fields[status]}"),
                TimeElapsedColumn(),
                console=console,
                transient=False,
            ) as progress:
                task_ids = {
                    name: progress.add_task(
                        self.finders[name].name,
                        status="[dim]searching...[/dim]",
                        total=None,
                    )
                    for name in valid
                }

                try:
                    with ThreadPoolExecutor(max_workers=len(valid)) as executor:
                        futures = {executor.submit(_run_finder, self.finders[n]): n for n in valid}
                        for future in as_completed(futures):
                            name = futures[future]
                            links, _ = future.result()
                            results[name] = links
                            logger.info("FINDER  %-14s  links=%d  %s",
                                        name, len(links), list(links.keys()))

                            if links:
                                variants = ", ".join(links.keys())
                                status = f"[green]✓ {variants}[/green]"
                            else:
                                status = "[red]✗ not found[/red]"

                            progress.update(task_ids[name], status=status, completed=1, total=1)
                except KeyboardInterrupt:
                    console.print("\n[yellow]⏸  Interrupted — returning partial results.[/]")
                    logger.warning("FINDER INTERRUPTED by user")

        # Offer interactive overrides after the progress display closes
        all_links: Dict[str, Dict[str, str]] = {}
        for name in valid:
            links = results.get(name, {})
            if interactive and not _has_iso_link(links):
                override = _prompt_override_url(self.finders[name].name)
                if override:
                    links['override'] = override
            if links:
                all_links[name] = links

        return all_links

    def save_links_to_file(self, all_links: Dict[str, Dict[str, str]], output_path: str = './os-links/all_os.txt'):
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'w') as f:
            for links in all_links.values():
                for url in links.values():
                    if (url.lower().endswith('.iso')
                            or url.lower().endswith('.iso.bz2')
                            or url.lower().endswith('.iso.gz')
                            or url.startswith('mido://')):
                        f.write(f"{url}\n")
        console.print(f"[green]💾 ISO links saved to:[/] {output_path}")


_ISO_EXTS = ('.iso', '.iso.bz2', '.iso.gz')


def _url_kind(url: str) -> Tuple[str, str]:
    """Returns (label, rich_color) for a URL."""
    if url.startswith("mido://"):
        return "Mido", "blue"
    lo = url.lower()
    if any(lo.endswith(e) for e in _ISO_EXTS):
        return "ISO", "green"
    return "link", "yellow"


def _print_summary(finder: 'MultiOSDownloadFinder', all_links: Dict[str, Dict[str, str]]):
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
        for i, (variant, url) in enumerate(links.items()):
            kind, color = _url_kind(url)
            if kind == "ISO":
                iso_count += 1
            table.add_row(
                display_name if i == 0 else "",
                variant,
                f"[{color}]{kind}[/]",
                f"[{color}]{url}[/]",
            )

    console.print(table)
    n = len(all_links)
    console.print(
        f"  [dim]{n} OS{'es' if n != 1 else ''} resolved  ·  "
        f"[green]{iso_count} ISO link{'s' if iso_count != 1 else ''} ready to download[/dim]"
    )


def main():
    parser = argparse.ArgumentParser(description='Multi-OS Download Link Finder')
    parser.add_argument(
        '--os', nargs='+',
        choices=['ubuntu', 'opnsense', 'pfsense', 'debian', 'truenas',
                 'windows11', 'manjaro', 'mxlinux', 'puppy', 'cachyos', 'all'],
        default=['all'],
        help='Operating systems to find download links for',
    )
    parser.add_argument('--no-interactive', action='store_true',
                        help='Disable the override URL prompt when a link cannot be found')
    parser.add_argument('--output', default='./os-links/all_os.txt',
                        help='Output file for ISO URLs (default: ./os-links/all_os.txt)')
    parser.add_argument('--timeout', type=int, default=15,
                        help='HTTP request timeout in seconds (default: 15)')
    parser.add_argument('--json', action='store_true',
                        help='Output results as JSON and suppress progress messages')
    parser.add_argument('--log', metavar='FILE', default='./logs/os-finder.log',
                        help='Write log to FILE (default: ./logs/os-finder.log)')
    args = parser.parse_args()

    setup_logging(args.log)

    finder = MultiOSDownloadFinder(timeout=args.timeout)
    os_list = list(finder.finders.keys()) if 'all' in args.os else args.os

    if args.json:
        all_links = finder.find_all_links(os_list, interactive=False, quiet=True)
        print(json.dumps(all_links, indent=2))
        return

    os_display = "  ·  ".join(finder.finders[k].name for k in os_list)
    console.print(Panel(
        f"[bold]Multi-OS Download Link Finder[/]\n[dim]{os_display}[/]",
        expand=False,
    ))

    all_links = finder.find_all_links(os_list, interactive=not args.no_interactive)

    if all_links:
        console.print()
        _print_summary(finder, all_links)
        console.print()
        finder.save_links_to_file(all_links, output_path=args.output)

        iso_count = sum(
            1 for links in all_links.values()
            for url in links.values()
            if any(url.lower().endswith(e) for e in _ISO_EXTS)
        )
        console.print(Panel(
            f"  [green]✓[/]  [bold]{iso_count} ISO URL{'s' if iso_count != 1 else ''}[/] "
            f"saved to [cyan]{args.output}[/]\n"
            f"  Run [bold cyan]uv run os-download[/] to start downloading",
            title="[bold green]Ready[/]",
            border_style="green",
            expand=False,
        ))
    else:
        console.print("[red]✗ No download links found for any operating system[/]")
        sys.exit(1)


if __name__ == "__main__":
    main()
