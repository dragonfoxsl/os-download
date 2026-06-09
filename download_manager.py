#!/usr/bin/env python3
"""
Download Manager

Downloads files from URL lists with progress tracking, resume support,
parallel downloads, bz2/gz decompression, and checksum verification.
"""

import bz2
import gzip
import hashlib
import logging
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed, wait as cf_wait, FIRST_COMPLETED
from pathlib import Path
from typing import Deque, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import argparse
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

console = Console()
logger = logging.getLogger("os_download")

_MIDO_DIR = Path.home() / ".local" / "share" / "mido"


def setup_logging(log_file: str) -> None:
    """Configure file logging. Console output is handled by Rich separately."""
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


def _keyboard_listener(quit_event: threading.Event, stop_event: threading.Event) -> None:
    """Set quit_event when 'q' is pressed. No-ops silently if stdin is not a TTY."""
    if not sys.stdin.isatty():
        return
    try:
        import termios
        import tty
        import select as _sel

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while not stop_event.is_set():
                if _sel.select([sys.stdin], [], [], 0.1)[0]:
                    if sys.stdin.read(1).lower() == 'q':
                        quit_event.set()
                        return
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        pass


def default_download_dir() -> Path:
    system = platform.system()
    home = Path.home()
    if system in ("Windows", "Darwin"):
        base = home / "Downloads"
    else:
        xdg = os.environ.get("XDG_DOWNLOAD_DIR")
        base = Path(xdg) if xdg else home / "Downloads"
    return base / "os-isos"


class DownloadManager:
    def __init__(self, download_dir: str = "./downloads", chunk_size: int = 8192):
        self.download_dir = Path(download_dir)
        self.chunk_size = chunk_size
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.session = _build_session()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def get_filename_from_url(self, url: str) -> str:
        filename = os.path.basename(urlparse(url).path)
        if not filename or '.' not in filename:
            filename = f"download_{url[-8:]}.bin"
        return filename

    def get_resume_position(self, filepath: Path) -> int:
        return filepath.stat().st_size if filepath.exists() else 0

    def _final_filepath(self, url: str, decompress: bool) -> Path:
        fname = self.get_filename_from_url(url)
        fpath = self.download_dir / fname
        if decompress and fpath.suffix.lower() in ('.bz2', '.gz'):
            return fpath.with_suffix('')
        return fpath

    # ── Mido (Windows ISO) ────────────────────────────────────────────────────

    def _ensure_mido(self) -> Optional[Path]:
        """Return path to Mido.sh, cloning from GitHub if not present."""
        script = _MIDO_DIR / "Mido.sh"
        if script.exists():
            return script
        if shutil.which("git") is None:
            console.print("[red]✗ git is required to install Mido — install git and retry.[/]")
            return None
        console.print("[dim]Cloning Mido from GitHub…[/]")
        try:
            subprocess.run(
                ["git", "clone", "--depth=1",
                 "https://github.com/ElliotKillick/Mido", str(_MIDO_DIR)],
                check=True,
            )
        except subprocess.CalledProcessError:
            console.print("[red]✗ Failed to clone Mido.[/]")
            return None
        script.chmod(0o755)
        return script

    def _download_with_mido(self, variant: str) -> bool:
        """Run Mido to download a Windows ISO into self.download_dir."""
        script = self._ensure_mido()
        if script is None:
            return False
        console.print(f"\n[bold cyan]▶ Mido  →  {variant}[/bold cyan]")
        logger.info("MIDO START  %s", variant)
        try:
            result = subprocess.run(
                ["bash", str(script), variant],
                cwd=str(self.download_dir),
            )
            ok = result.returncode == 0
            if ok:
                logger.info("MIDO DONE  %s", variant)
            else:
                logger.error("MIDO FAILED  %s  rc=%d", variant, result.returncode)
            return ok
        except Exception as e:
            console.print(f"[red]✗ Mido error: {e}[/]")
            logger.error("MIDO ERROR  %s  —  %s", variant, e)
            return False

    def _hash_file(self, filepath: Path) -> str:
        sha256 = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                sha256.update(chunk)
        return sha256.hexdigest().lower()

    # ── Checksum verification ─────────────────────────────────────────────────

    def verify_checksum(self, filepath: Path, url: str) -> Optional[bool]:
        """Try to verify SHA256. Returns True/False on match/mismatch, None if no checksum found."""
        fname = filepath.name

        # 1. Per-file .sha256 sidecar (CachyOS, Puppy, etc.)
        try:
            r = self.session.get(url + '.sha256', timeout=10)
            if r.status_code == 200:
                expected = r.text.strip().split()[0]
                return self._hash_file(filepath) == expected.lower()
        except Exception:
            pass

        # 2. SHA256SUMS directory file (Ubuntu style)
        dir_url = url.rsplit('/', 1)[0] + '/SHA256SUMS'
        try:
            r = self.session.get(dir_url, timeout=10)
            if r.status_code == 200:
                for line in r.text.splitlines():
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2 and parts[1].lstrip('* ') == fname:
                        return self._hash_file(filepath) == parts[0].lower()
        except Exception:
            pass

        return None

    # ── Decompression ─────────────────────────────────────────────────────────

    def decompress(self, filepath: Path, verbose: bool = True) -> Path:
        """Decompress a .bz2 or .gz file in-place. Returns path to the decompressed file."""
        suffix = filepath.suffix.lower()
        out_path = filepath.with_suffix('')

        if verbose:
            console.print(f"[yellow]📦 Decompressing {filepath.name}…[/]")
        logger.info("DECOMPRESS  %s", filepath.name)

        if suffix == '.bz2':
            with bz2.open(filepath, 'rb') as f_in, open(out_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        elif suffix == '.gz':
            with gzip.open(filepath, 'rb') as f_in, open(out_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        else:
            return filepath

        filepath.unlink()
        if verbose:
            console.print(f"[green]✓ Decompressed →[/] {out_path.name}")
        logger.info("DECOMPRESS_DONE  %s", out_path.name)
        return out_path

    # ── Core download ─────────────────────────────────────────────────────────

    def download_file(
        self,
        url: str,
        filename: Optional[str] = None,
        resume: bool = True,
        verify: bool = False,
        decompress: bool = True,
        progress: Optional[Progress] = None,
        task_id: Optional[TaskID] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> bool:
        if not filename:
            filename = self.get_filename_from_url(url)

        filepath = self.download_dir / filename
        resume_pos = self.get_resume_position(filepath) if resume else 0
        headers = {'Range': f'bytes={resume_pos}-'} if resume_pos > 0 else {}

        own_progress = progress is None
        logger.info("START  %s  →  %s", url, filepath)

        try:
            response = self.session.get(url, headers=headers, stream=True, timeout=30)

            if resume_pos > 0:
                if response.status_code == 416:
                    # Range beyond file end — file may already be complete
                    try:
                        head = self.session.head(url, timeout=self.timeout, allow_redirects=True)
                        server_size = int(head.headers.get('content-length', 0))
                    except Exception:
                        server_size = 0
                    if server_size > 0 and filepath.stat().st_size >= server_size:
                        # File is fully downloaded; mark progress complete if visible
                        if not own_progress and task_id is not None and progress is not None:
                            progress.update(task_id, total=server_size, completed=server_size)
                        logger.info("ALREADY_COMPLETE  %s", filepath.name)
                        return True
                    # Size mismatch — restart from scratch
                    resume_pos = 0
                    response = self.session.get(url, stream=True, timeout=30)
                elif response.status_code != 206:
                    resume_pos = 0
                    response = self.session.get(url, stream=True, timeout=30)

            response.raise_for_status()

            # Determine total size
            total: Optional[int] = None
            if 'content-length' in response.headers:
                total = resume_pos + int(response.headers['content-length'])
            elif 'content-range' in response.headers:
                total = int(response.headers['content-range'].split('/')[-1])

            if own_progress:
                progress = Progress(
                    TextColumn("[bold cyan]{task.description}"),
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                    console=console,
                )
                task_id = progress.add_task(filename, total=total, completed=resume_pos)
                progress.start()
            else:
                progress.update(task_id, total=total, completed=resume_pos)  # type: ignore[arg-type]

            stopped_early = False
            mode = 'ab' if resume_pos > 0 else 'wb'
            with open(filepath, mode) as f:
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if stop_event and stop_event.is_set():
                        stopped_early = True
                        break
                    if chunk:
                        f.write(chunk)
                        progress.update(task_id, advance=len(chunk))  # type: ignore[arg-type]

            if own_progress:
                progress.stop()  # type: ignore[union-attr]

            if stopped_early:
                logger.info("STOPPED  %s  (partial, resumable)", filepath.name)
                return False

            # Decompress if needed — suppress console output when inside the Live dashboard
            if decompress and filepath.suffix.lower() in ('.bz2', '.gz'):
                filepath = self.decompress(filepath, verbose=own_progress)

            # Verify checksum
            if verify:
                result = self.verify_checksum(filepath, url)
                if result is True:
                    if own_progress:
                        console.print(f"  [green]✓ Checksum verified[/]")
                    logger.info("VERIFY OK  %s", filepath.name)
                elif result is False:
                    if own_progress:
                        console.print(f"  [red]✗ Checksum mismatch — file may be corrupt[/]")
                    logger.error("VERIFY FAIL  %s", filepath.name)
                    return False
                else:
                    if own_progress:
                        console.print(f"  [dim]⚠ No checksum available for verification[/]")
                    logger.warning("VERIFY SKIP  %s  (no checksum found)", filepath.name)

            logger.info("DONE   %s", filepath.name)
            return True

        except KeyboardInterrupt:
            logger.warning("INTERRUPTED  %s", url)
            raise  # propagate so the executor can shut down cleanly
        except Exception as e:
            if own_progress:
                console.print(f"[red]✗ Download failed:[/] {e}")
            logger.error("FAILED  %s  —  %s", url, e)
            return False

    # ── Batch download ────────────────────────────────────────────────────────

    def _read_urls(self, file_path: str) -> List[str]:
        path = Path(file_path)
        if not path.exists():
            console.print(f"[red]✗ URL file not found:[/] {file_path}")
            return []
        urls = []
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    urls.append(line)
        return urls

    def download_from_file(
        self,
        file_path: str,
        resume: bool = True,
        verify: bool = False,
        decompress: bool = True,
        interactive: bool = True,
        parallel: int = 1,
    ) -> bool:
        all_urls = self._read_urls(file_path)
        if not all_urls:
            console.print("[yellow]⚠ No URLs found in file[/]")
            return False

        # Mido (Windows) URLs bypass the Live dashboard entirely
        mido_urls = [u for u in all_urls if u.startswith("mido://")]
        all_urls  = [u for u in all_urls if not u.startswith("mido://")]

        if resume and interactive:
            partial = [
                url for url in all_urls
                if (self.download_dir / self.get_filename_from_url(url)).exists()
            ]
            if partial:
                n = len(partial)
                console.print(
                    f"\n  [yellow]Found {n} partial file{'s' if n != 1 else ''}.[/yellow]"
                    "  [bold]R[/bold]esume / [bold]s[/bold]tart from scratch?"
                    "  [dim](Enter = resume)[/dim]  ",
                    end="",
                )
                try:
                    ans = input().strip().lower()
                except (EOFError, KeyboardInterrupt):
                    ans = ''
                if ans in ('s', 'scratch', 'n', 'no'):
                    resume = False

        # Skip files downloaded less than 24 hours ago
        urls_to_skip: set = set()
        if interactive:
            recent = []
            for url in all_urls:
                fpath = self._final_filepath(url, decompress)
                if fpath.exists() and fpath.stat().st_size > 0:
                    age = time.time() - fpath.stat().st_mtime
                    if age < 86400:
                        recent.append((url, fpath.name, age))
            if recent:
                n = len(recent)
                console.print(
                    f"\n  [green]{n} file{'s' if n != 1 else ''} already downloaded "
                    f"in the last 24 hours:[/green]"
                )
                for url, fname, age in recent:
                    h, rem = divmod(int(age), 3600)
                    m = rem // 60
                    console.print(f"    [dim]·[/dim] {fname}  [dim]({h}h {m:02d}m ago)[/dim]")
                console.print(
                    "  Re-download anyway? [dim](y = yes / N = skip)[/dim]  ",
                    end="",
                )
                try:
                    ans = input().strip().lower()
                except (EOFError, KeyboardInterrupt):
                    ans = ''
                if ans not in ('y', 'yes'):
                    urls_to_skip = {url for url, _, _ in recent}
                else:
                    # Delete complete files so the re-download starts from byte 0 (avoids 416)
                    for url, _, _ in recent:
                        fpath = self._final_filepath(url, decompress)
                        try:
                            fpath.unlink(missing_ok=True)
                        except Exception:
                            pass

        urls_to_try = [u for u in all_urls if u not in urls_to_skip]

        total_success = 0
        total_interrupted = False

        # Run Mido downloads before the Live dashboard (they are interactive)
        for mido_url in mido_urls:
            variant = mido_url[len("mido://"):]
            if self._download_with_mido(variant):
                total_success += 1

        if not urls_to_try:
            if not mido_urls:
                console.print("[green]✓ All files are recent — nothing to download.[/]")
            return total_success > 0 or not mido_urls

        while True:
            urls = urls_to_try

            start_time = time.monotonic()
            done_count = 0
            failed: List[str] = []
            interrupted = False
            stop_event = threading.Event()
            speed_samples: Deque[Tuple[float, int]] = deque(maxlen=40)

            progress = Progress(
                TextColumn("[bold cyan]{task.description:.42}"),
                BarColumn(bar_width=None),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console,
                expand=True,
            )
            task_ids = {
                url: progress.add_task(self.get_filename_from_url(url), total=None)
                for url in urls
            }

            body_size = len(urls) + 2
            layout = Layout()
            layout.split_column(
                Layout(name="header", size=7),
                Layout(name="body", size=body_size),
                Layout(name="footer", size=1),
            )
            layout["body"].update(Panel(progress, title="[dim]Files[/]", border_style="dim"))

            shortcuts = Table.grid(expand=True, padding=(0, 1))
            shortcuts.add_column(justify="left")
            shortcuts.add_column(justify="right")
            shortcuts.add_row(
                "  [bold dim]q[/bold dim] [dim]quit[/dim]"
                "   [bold dim]Ctrl+C[/bold dim] [dim]interrupt[/dim]"
                "   [dim]— partial files resume automatically[/dim]",
                f"[dim]parallel={parallel}  resume={'on' if resume else 'off'}"
                f"  verify={'on' if verify else 'off'}  [/dim]",
            )
            layout["footer"].update(shortcuts)

            _SPARK = " ▁▂▃▄▅▆▇█"

            def _sparkline() -> str:
                if len(speed_samples) < 2:
                    return "[dim]—[/dim]"
                speeds = []
                for i in range(1, len(speed_samples)):
                    dt = speed_samples[i][0] - speed_samples[i - 1][0]
                    db = speed_samples[i][1] - speed_samples[i - 1][1]
                    if dt > 0:
                        speeds.append(max(0.0, db / dt))
                if not speeds:
                    return "[dim]—[/dim]"
                peak = max(speeds) or 1.0
                bars = "".join(_SPARK[min(8, int(s / peak * 8))] for s in speeds[-20:])
                current_mbs = speeds[-1] / 1_048_576
                return f"[yellow]{bars}[/yellow] [bold]{current_mbs:.1f} MB/s[/bold]"

            def _update_header() -> None:
                elapsed = time.monotonic() - start_time
                total_bytes = sum(t.completed for t in progress.tasks if t.completed is not None)
                speed_samples.append((time.monotonic(), total_bytes))
                mins, secs = divmod(int(elapsed), 60)
                active = min(parallel, max(0, len(urls) - done_count))
                done_ok = done_count - len(failed)
                waiting = max(0, len(urls) - done_count - active)
                pct = int(done_count / len(urls) * 100) if urls else 0

                parts: List[str] = []
                if active > 0:
                    parts.append(f"[cyan]▶ {active} downloading[/cyan]")
                if done_ok > 0:
                    parts.append(f"[green]✓ {done_ok} done[/green]")
                if failed:
                    last_name = self.get_filename_from_url(failed[-1])
                    short = last_name[:24] + "…" if len(last_name) > 25 else last_name
                    parts.append(f"[red]✗ {len(failed)} failed[/red] [dim]({short})[/dim]")
                if waiting > 0:
                    parts.append(f"[dim]○ {waiting} queued[/dim]")

                status = "  ".join(parts) if parts else "[dim]preparing…[/dim]"
                file_cell = f"{status}  [dim]·  {done_count}/{len(urls)}  {pct}%[/dim]"

                grid = Table.grid(expand=True, padding=(0, 3))
                grid.add_column(style="bold dim", min_width=14)
                grid.add_column(min_width=24)
                grid.add_column(style="bold dim", min_width=10)
                grid.add_column()

                grid.add_row(
                    "Files",      file_cell,
                    "Elapsed",    f"{mins:02d}:{secs:02d}",
                )
                grid.add_row(
                    "Downloaded", f"[cyan]{total_bytes / 1_048_576:.1f} MB[/cyan]",
                    "Speed",      _sparkline(),
                )

                if interrupted:
                    hdr_title = "[bold yellow]⏸  os-download[/bold yellow]"
                    hdr_border = "yellow"
                elif done_count == len(urls) and not failed:
                    hdr_title = "[bold green]✓  os-download[/bold green]"
                    hdr_border = "green"
                elif done_count == len(urls) and failed:
                    hdr_title = "[bold red]✗  os-download[/bold red]"
                    hdr_border = "red"
                else:
                    hdr_title = "[bold cyan]os-download[/bold cyan]"
                    hdr_border = "cyan"

                layout["header"].update(
                    Panel(grid, title=hdr_title, border_style=hdr_border, padding=(1, 2))
                )

            _update_header()

            def _refresh_loop() -> None:
                while not stop_event.is_set():
                    _update_header()
                    time.sleep(0.25)

            refresh_thread = threading.Thread(target=_refresh_loop, daemon=True)

            executor = ThreadPoolExecutor(max_workers=parallel)
            futures = {
                executor.submit(
                    self.download_file,
                    url, None, resume, verify, decompress,
                    progress, task_ids[url], stop_event,
                ): url
                for url in urls
            }

            quit_event = threading.Event()
            kb_thread = threading.Thread(
                target=_keyboard_listener, args=(quit_event, stop_event), daemon=True
            )

            pending: set = set()
            with Live(layout, console=console, refresh_per_second=4) as live:
                refresh_thread.start()
                kb_thread.start()
                try:
                    pending = set(futures.keys())
                    while pending:
                        if quit_event.is_set():
                            interrupted = True
                            stop_event.set()
                            for f in pending:
                                f.cancel()
                            logger.warning("SESSION QUIT by user (q)")
                            _update_header()
                            break

                        done_set, pending = cf_wait(
                            pending, timeout=0.2, return_when=FIRST_COMPLETED
                        )

                        for future in done_set:
                            furl = futures[future]
                            try:
                                ok = future.result()
                            except KeyboardInterrupt:
                                raise
                            except Exception as e:
                                logger.error("FUTURE ERROR  %s  —  %s", furl, e)
                                ok = False

                            done_count += 1
                            if not ok:
                                failed.append(furl)
                            _update_header()

                            if not ok and interactive and parallel == 1:
                                live.stop()
                                should_continue = True
                                try:
                                    ans = input("\n❓ Continue? (y/N): ").lower()
                                    if ans not in ('y', 'yes'):
                                        should_continue = False
                                except KeyboardInterrupt:
                                    interrupted = True
                                    should_continue = False
                                live.start()
                                if not should_continue:
                                    stop_event.set()
                                    for f in pending:
                                        f.cancel()
                                    pending = set()
                                    break

                except KeyboardInterrupt:
                    interrupted = True
                    stop_event.set()
                    for f in pending:
                        f.cancel()
                    logger.warning("SESSION INTERRUPTED by user")
                    _update_header()

                finally:
                    stop_event.set()

                kb_thread.join(timeout=0.5)
                executor.shutdown(wait=True)

                # Completion stats
                elapsed = time.monotonic() - start_time
                total_bytes = sum(t.completed for t in progress.tasks if t.completed is not None)
                mins, secs = divmod(int(elapsed), 60)
                success = len(urls) - len(failed)
                total_success += success
                if interrupted:
                    total_interrupted = True

                if interrupted:
                    border, title = "yellow", "⏸  Interrupted"
                elif failed:
                    border, title = "red", "✗  Finished with errors"
                else:
                    border, title = "green", "✓  Complete"

                lines = [
                    f"  [bold]Files[/bold]       [green]{success}[/green] downloaded"
                    + (f"  [red]{len(failed)} failed[/red]" if failed else ""),
                    f"  [bold]Data[/bold]        {total_bytes / 1_048_576:.1f} MB",
                    f"  [bold]Time[/bold]        {mins:02d}:{secs:02d}",
                ]
                if interrupted:
                    lines.append("\n  [dim]Partial files can be resumed with the same command.[/dim]")
                for furl in failed:
                    lines.append(f"  [red]✗[/red] {self.get_filename_from_url(furl)}")

                # Render completion panel inside the Live layout to eliminate the gap
                completion_size = 2 + len(lines) + (1 if interrupted else 0)
                layout.split_column(
                    Layout(name="header", size=7),
                    Layout(name="body", size=body_size),
                    Layout(name="completion", size=completion_size),
                    Layout(name="footer", size=1),
                )
                layout["body"].update(Panel(progress, title="[dim]Files[/]", border_style="dim"))
                layout["completion"].update(Panel(
                    "\n".join(lines),
                    title=f"[bold]{title}[/bold]",
                    border_style=border,
                    expand=True,
                ))
                layout["footer"].update(shortcuts)
                _update_header()
                time.sleep(0.15)

            logger.info(
                "SESSION DONE  success=%d  failed=%d  interrupted=%s  bytes=%d  elapsed=%.1fs",
                success, len(failed), interrupted, total_bytes, elapsed,
            )

            # Retry prompt — only when not interrupted and there are failures
            if failed and not interrupted and interactive:
                n = len(failed)
                console.print()
                console.print(
                    f"  [yellow]▶ {n} file{'s' if n != 1 else ''} failed.[/yellow]"
                    "  Retry? [dim](y/N)[/dim] ",
                    end="",
                )
                try:
                    ans = input().strip().lower()
                except (EOFError, KeyboardInterrupt):
                    ans = 'n'
                if ans in ('y', 'yes'):
                    urls_to_try = list(failed)
                    console.print(
                        f"\n  [dim]Queuing {n} file{'s' if n != 1 else ''} for retry…[/dim]\n"
                    )
                    continue

            break

        return total_success > 0 and not total_interrupted


def main():
    parser = argparse.ArgumentParser(description='OS ISO Download Manager')
    parser.add_argument('--file', '-f', default='./os-links/all_os.txt',
                        help='File containing URLs to download (default: ./os-links/all_os.txt)')
    parser.add_argument('--url', '-u', help='Single URL to download')
    parser.add_argument('--output', '-o', help='Output filename (single URL only)')
    _default_dir = str(default_download_dir())
    parser.add_argument('--dir', '-d', default=_default_dir,
                        help=f'Download directory (default: {_default_dir})')
    parser.add_argument('--no-resume', action='store_true', help='Disable resume')
    parser.add_argument('--no-interactive', action='store_true',
                        help='Do not prompt to continue after a failed download')
    parser.add_argument('--verify', action='store_true',
                        help='Verify SHA256 checksum after each download')
    parser.add_argument('--no-decompress', action='store_true',
                        help='Skip automatic decompression of .bz2/.gz files')
    parser.add_argument('--parallel', type=int, default=1, metavar='N',
                        help='Number of simultaneous downloads (default: 1)')
    parser.add_argument('--chunk-size', type=int, default=8192,
                        help='Download chunk size in bytes (default: 8192)')
    parser.add_argument('--log', metavar='FILE', default='./logs/os-download.log',
                        help='Write log to FILE (default: ./logs/os-download.log)')
    args = parser.parse_args()

    setup_logging(args.log)

    manager = DownloadManager(download_dir=args.dir, chunk_size=args.chunk_size)
    resume = not args.no_resume
    decompress = not args.no_decompress

    if args.url:
        success = manager.download_file(
            args.url, args.output,
            resume=resume, verify=args.verify, decompress=decompress,
        )
        sys.exit(0 if success else 1)

    if not Path(args.file).exists():
        console.print(f"[red]✗ URL file not found:[/] {args.file}")
        console.print("[dim]Run the OS finder first: uv run os-finder[/]")
        sys.exit(1)

    success = manager.download_from_file(
        args.file,
        resume=resume,
        verify=args.verify,
        decompress=decompress,
        interactive=not args.no_interactive,
        parallel=args.parallel,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
