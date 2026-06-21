import logging
import sys
import threading
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor
from concurrent.futures import wait as cf_wait
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table

from os_download.downloader.checksums import verify_checksum
from os_download.downloader.compression import decompress_file
from os_download.downloader.curl import download_with_curl
from os_download.downloader.mido import download_with_mido
from os_download.downloader.paths import filename_from_url
from os_download.http import build_session

console = Console()
logger = logging.getLogger("os_download")
_SPARK_CHARS = " ▁▂▃▄▅▆▇█"


def _keyboard_listener(quit_event: threading.Event, stop_event: threading.Event) -> None:
    if not sys.stdin.isatty():
        return
    try:
        import select as _sel
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while not stop_event.is_set():
                if _sel.select([sys.stdin], [], [], 0.1)[0]:
                    if sys.stdin.read(1).lower() == "q":
                        quit_event.set()
                        return
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except Exception:
        pass


class DownloadManager:
    def __init__(self, download_dir: str = "./downloads", chunk_size: int = 8192):
        self.download_dir = Path(download_dir)
        self.chunk_size = chunk_size
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.session = build_session()

    def get_filename_from_url(self, url: str) -> str:
        return filename_from_url(url)

    def verify_checksum(self, filepath: Path, url: str):
        return verify_checksum(self.session, filepath, url)

    def decompress(self, filepath: Path, verbose: bool = True) -> Path:
        if verbose:
            console.print(f"[yellow]Decompressing {filepath.name}...[/]")
        output = decompress_file(filepath)
        if verbose and output != filepath:
            console.print(f"[green]Decompressed ->[/] {output.name}")
        return output

    def get_resume_position(self, filepath: Path) -> int:
        return filepath.stat().st_size if filepath.exists() else 0

    def _final_filepath(self, url: str, decompress: bool) -> Path:
        filepath = self.download_dir / self.get_filename_from_url(url)
        if decompress and filepath.suffix.lower() in (".bz2", ".gz"):
            return filepath.with_suffix("")
        return filepath

    def _download_with_mido(self, variant: str) -> bool:
        return download_with_mido(variant, self.download_dir)

    def _download_with_curl(
        self,
        url: str,
        filepath: Path,
        resume_pos: int,
        progress: Optional[Progress],
        task_id: Optional[TaskID],
        stop_event: Optional[threading.Event],
    ) -> bool:
        return download_with_curl(url, filepath, resume_pos, progress, task_id, stop_event)

    def _post_download(
        self, filepath: Path, url: str, verify: bool, decompress: bool, own_progress: bool
    ) -> bool:
        if verify:
            result = self.verify_checksum(filepath, url)
            if result is True:
                if own_progress:
                    console.print("  [green]Checksum verified[/]")
                logger.info("VERIFY OK  %s", filepath.name)
            elif result is False:
                if own_progress:
                    console.print("  [red]Checksum mismatch, file may be corrupt[/]")
                logger.error("VERIFY FAIL  %s", filepath.name)
                return False
            else:
                if own_progress:
                    console.print("  [dim]No checksum available for verification[/]")
                logger.warning("VERIFY SKIP  %s  (no checksum found)", filepath.name)

        if decompress and filepath.suffix.lower() in (".bz2", ".gz"):
            filepath = self.decompress(filepath, verbose=own_progress)

        logger.info("DONE   %s", filepath.name)
        return True

    def _read_urls(self, file_path: str) -> list[str]:
        path = Path(file_path)
        if not path.exists():
            console.print(f"[red]URL file not found:[/] {file_path}")
            return []
        urls: list[str] = []
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)
        return urls

    def _build_speed_sparkline(self, speed_samples: deque[tuple[float, int]]) -> str:
        if len(speed_samples) < 2:
            return "[dim]—[/dim]"

        speeds = []
        for index in range(1, len(speed_samples)):
            delta_t = speed_samples[index][0] - speed_samples[index - 1][0]
            delta_b = speed_samples[index][1] - speed_samples[index - 1][1]
            if delta_t > 0:
                speeds.append(max(0.0, delta_b / delta_t))

        if not speeds:
            return "[dim]—[/dim]"

        peak = max(speeds) or 1.0
        bars = "".join(_SPARK_CHARS[min(8, int(speed / peak * 8))] for speed in speeds[-20:])
        current_mbs = speeds[-1] / 1_048_576
        return f"[yellow]{bars}[/yellow] [bold]{current_mbs:.1f} MB/s[/bold]"

    def _update_session_header(
        self,
        layout: Layout,
        progress: Progress,
        speed_samples: deque[tuple[float, int]],
        start_time: float,
        parallel: int,
        session_urls: list[str],
        session_state: dict[str, object],
    ) -> None:
        done_count = int(session_state["done_count"])
        failed = session_state["failed"]
        assert isinstance(failed, list)
        interrupted = bool(session_state["interrupted"])

        elapsed = time.monotonic() - start_time
        total_bytes = sum(task.completed for task in progress.tasks if task.completed is not None)
        speed_samples.append((time.monotonic(), total_bytes))
        minutes, seconds = divmod(int(elapsed), 60)
        active = min(parallel, max(0, len(session_urls) - done_count))
        done_ok = done_count - len(failed)
        waiting = max(0, len(session_urls) - done_count - active)
        pct = int(done_count / len(session_urls) * 100) if session_urls else 0

        parts: list[str] = []
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
        file_cell = f"{status}  [dim]·  {done_count}/{len(session_urls)}  {pct}%[/dim]"

        grid = Table.grid(expand=True, padding=(0, 3))
        grid.add_column(style="bold dim", min_width=14)
        grid.add_column(min_width=24)
        grid.add_column(style="bold dim", min_width=10)
        grid.add_column()
        grid.add_row("Files", file_cell, "Elapsed", f"{minutes:02d}:{seconds:02d}")
        grid.add_row(
            "Downloaded",
            f"[cyan]{total_bytes / 1_048_576:.1f} MB[/cyan]",
            "Speed",
            self._build_speed_sparkline(speed_samples),
        )

        if interrupted:
            header_title = "[bold yellow]⏸  os-download[/bold yellow]"
            border_style = "yellow"
        elif done_count == len(session_urls) and not failed:
            header_title = "[bold green]✓  os-download[/bold green]"
            border_style = "green"
        elif done_count == len(session_urls) and failed:
            header_title = "[bold red]✗  os-download[/bold red]"
            border_style = "red"
        else:
            header_title = "[bold cyan]os-download[/bold cyan]"
            border_style = "cyan"

        layout["header"].update(
            Panel(grid, title=header_title, border_style=border_style, padding=(1, 2))
        )

    def _refresh_session_header(
        self,
        stop_event: threading.Event,
        layout: Layout,
        progress: Progress,
        speed_samples: deque[tuple[float, int]],
        start_time: float,
        parallel: int,
        session_urls: list[str],
        session_state: dict[str, object],
    ) -> None:
        while not stop_event.is_set():
            self._update_session_header(
                layout,
                progress,
                speed_samples,
                start_time,
                parallel,
                session_urls,
                session_state,
            )
            time.sleep(0.25)

    def _build_completion_summary(
        self,
        success: int,
        failed: list[str],
        interrupted: bool,
        mido_failed_count: int,
        total_bytes: int,
        elapsed: float,
    ) -> tuple[str, str, list[str]]:
        minutes, seconds = divmod(int(elapsed), 60)

        if interrupted:
            border_style, title = "yellow", "⏸  Interrupted"
        elif failed or mido_failed_count:
            border_style, title = "red", "✗  Finished with errors"
        else:
            border_style, title = "green", "✓  Complete"

        lines = [
            f"  [bold]Files[/bold]       [green]{success}[/green] downloaded"
            + (f"  [red]{len(failed)} failed[/red]" if failed else "")
            + (
                f"  [red]{mido_failed_count} Mido failed[/red]"
                if mido_failed_count
                else ""
            ),
            f"  [bold]Data[/bold]        {total_bytes / 1_048_576:.1f} MB",
            f"  [bold]Time[/bold]        {minutes:02d}:{seconds:02d}",
        ]
        if interrupted:
            lines.append("\n  [dim]Partial files can be resumed with the same command.[/dim]")
        if mido_failed_count:
            lines.append(
                f"  [red]✗[/red] {mido_failed_count} Mido download"
                f"{'s' if mido_failed_count != 1 else ''} failed"
            )
        for failed_url in failed:
            lines.append(f"  [red]✗[/red] {self.get_filename_from_url(failed_url)}")

        return border_style, title, lines

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
        headers = {"Range": f"bytes={resume_pos}-"} if resume_pos > 0 else {}
        own_progress = progress is None

        logger.info("START  %s  ->  %s", url, filepath)

        try:
            response = self.session.get(url, headers=headers, stream=True, timeout=30)

            if response.status_code == 403:
                try:
                    response.close()
                except Exception:
                    pass
                logger.info("CURL_FALLBACK  %s  (403 from requests)", url)
                if own_progress:
                    progress = Progress(
                        TextColumn("[bold cyan]{task.description}"),
                        BarColumn(),
                        DownloadColumn(),
                        TransferSpeedColumn(),
                        TimeRemainingColumn(),
                        console=console,
                    )
                    task_id = progress.add_task(filename, total=None)
                    progress.start()
                ok = self._download_with_curl(url, filepath, resume_pos, progress, task_id, stop_event)
                if own_progress and progress is not None:
                    progress.stop()
                if not ok:
                    return False
                return self._post_download(filepath, url, verify, decompress, own_progress)

            if resume_pos > 0 and response.status_code != 206:
                if response.status_code == 416:
                    try:
                        head = self.session.head(url, timeout=30, allow_redirects=True)
                        server_size = int(head.headers.get("content-length", 0))
                    except Exception:
                        server_size = 0
                    if server_size > 0 and filepath.stat().st_size == server_size:
                        if not own_progress and task_id is not None and progress is not None:
                            progress.update(task_id, total=server_size, completed=server_size)
                        logger.info("ALREADY_COMPLETE  %s", filepath.name)
                        return self._post_download(filepath, url, verify, decompress, own_progress)
                resume_pos = 0
                response = self.session.get(url, stream=True, timeout=30)

            response.raise_for_status()

            total: Optional[int] = None
            if "content-length" in response.headers:
                total = resume_pos + int(response.headers["content-length"])
            elif "content-range" in response.headers:
                total = int(response.headers["content-range"].split("/")[-1])

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
            elif progress is not None and task_id is not None:
                progress.update(task_id, total=total, completed=resume_pos)

            stopped_early = False
            mode = "ab" if resume_pos > 0 else "wb"
            with open(filepath, mode) as handle:
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if stop_event and stop_event.is_set():
                        stopped_early = True
                        break
                    if chunk:
                        handle.write(chunk)
                        if progress is not None and task_id is not None:
                            progress.update(task_id, advance=len(chunk))

            if own_progress and progress is not None:
                progress.stop()

            if stopped_early:
                logger.info("STOPPED  %s  (partial, resumable)", filepath.name)
                return False

            return self._post_download(filepath, url, verify, decompress, own_progress)
        except KeyboardInterrupt:
            logger.warning("INTERRUPTED  %s", url)
            raise
        except Exception as exc:
            if own_progress:
                console.print(f"[red]Download failed:[/] {exc}")
            logger.error("FAILED  %s  -  %s", url, exc)
            return False

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
            console.print("[yellow]No URLs found in file[/]")
            return False

        parallel = max(1, parallel)
        mido_urls = [url for url in all_urls if url.startswith("mido://")]
        urls = [url for url in all_urls if not url.startswith("mido://")]
        urls_to_skip: set[str] = set()
        recent_urls: set[str] = set()
        mido_failed_count = 0

        if interactive:
            recent: list[tuple[str, str, float]] = []
            for url in urls:
                filepath = self._final_filepath(url, decompress)
                if filepath.exists() and filepath.stat().st_size > 0:
                    age = time.time() - filepath.stat().st_mtime
                    if age < 86400:
                        recent.append((url, filepath.name, age))
                        recent_urls.add(url)
            if recent:
                count = len(recent)
                console.print(
                    f"\n  [green]{count} file{'s' if count != 1 else ''} already downloaded "
                    f"in the last 24 hours:[/green]"
                )
                for _, filename, age in recent:
                    hours, remainder = divmod(int(age), 3600)
                    minutes = remainder // 60
                    console.print(f"    [dim]·[/dim] {filename}  [dim]({hours}h {minutes:02d}m ago)[/dim]")
                console.print(
                    "  Re-download anyway? [dim](y = yes / N = skip)[/dim]  ",
                    end="",
                )
                try:
                    ans = input().strip().lower()
                except (EOFError, KeyboardInterrupt):
                    ans = ""
                if ans not in ("y", "yes"):
                    urls_to_skip = {url for url, _, _ in recent}
                else:
                    for url, _, _ in recent:
                        filepath = self._final_filepath(url, decompress)
                        try:
                            filepath.unlink(missing_ok=True)
                        except Exception:
                            pass

        if resume and interactive:
            partial = [
                url
                for url in urls
                if url not in recent_urls
                and (self.download_dir / self.get_filename_from_url(url)).exists()
            ]
            if partial:
                count = len(partial)
                console.print(
                    f"\n  [yellow]Found {count} file{'s' if count != 1 else ''} from a previous session.[/yellow]"
                    "  Resume previous partial downloads? [dim](Y/n)[/dim]  ",
                    end="",
                )
                try:
                    ans = input().strip().lower()
                except (EOFError, KeyboardInterrupt):
                    ans = ""
                if ans in ("n", "no"):
                    resume = False

        urls_to_try = [url for url in urls if url not in urls_to_skip]

        total_success = 0
        total_interrupted = False

        for url in mido_urls:
            ok = self._download_with_mido(url[len("mido://") :])
            if ok:
                total_success += 1
            else:
                mido_failed_count += 1

        if not urls_to_try:
            if not mido_urls:
                console.print("[green]All files are recent; nothing to download.[/]")
            return (not mido_urls or total_success == len(mido_urls)) and not mido_failed_count

        while True:
            session_urls = urls_to_try
            start_time = time.monotonic()
            done_count = 0
            failed: list[str] = []
            interrupted = False
            stop_event = threading.Event()
            speed_samples: deque[tuple[float, int]] = deque(maxlen=40)
            session_state: dict[str, object] = {
                "done_count": done_count,
                "failed": failed,
                "interrupted": interrupted,
            }

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
                for url in session_urls
            }

            body_size = len(session_urls) + 2
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

            self._update_session_header(
                layout, progress, speed_samples, start_time, parallel, session_urls, session_state
            )

            refresh_thread = threading.Thread(
                target=self._refresh_session_header,
                args=(
                    stop_event,
                    layout,
                    progress,
                    speed_samples,
                    start_time,
                    parallel,
                    session_urls,
                    session_state,
                ),
                daemon=True,
            )
            executor = ThreadPoolExecutor(max_workers=parallel)
            futures = {
                executor.submit(
                    self.download_file,
                    url,
                    None,
                    resume,
                    verify,
                    decompress,
                    progress,
                    task_ids[url],
                    stop_event,
                ): url
                for url in session_urls
            }

            quit_event = threading.Event()
            kb_thread = threading.Thread(
                target=_keyboard_listener, args=(quit_event, stop_event), daemon=True
            )

            pending: set = set()
            with Live(layout, console=console, refresh_per_second=4):
                refresh_thread.start()
                kb_thread.start()
                try:
                    pending = set(futures.keys())
                    while pending:
                        if quit_event.is_set():
                            interrupted = True
                            session_state["interrupted"] = interrupted
                            stop_event.set()
                            for future in pending:
                                future.cancel()
                            logger.warning("SESSION QUIT by user (q)")
                            self._update_session_header(
                                layout,
                                progress,
                                speed_samples,
                                start_time,
                                parallel,
                                session_urls,
                                session_state,
                            )
                            break

                        done_set, pending = cf_wait(
                            pending, timeout=0.2, return_when=FIRST_COMPLETED
                        )

                        for future in done_set:
                            future_url = futures[future]
                            try:
                                ok = future.result()
                            except KeyboardInterrupt:
                                raise
                            except Exception as exc:
                                logger.error("FUTURE ERROR  %s  -  %s", future_url, exc)
                                ok = False

                            done_count += 1
                            session_state["done_count"] = done_count
                            if not ok:
                                failed.append(future_url)
                            self._update_session_header(
                                layout,
                                progress,
                                speed_samples,
                                start_time,
                                parallel,
                                session_urls,
                                session_state,
                            )

                            if not ok and interactive and parallel == 1:
                                should_continue = True
                                try:
                                    ans = input("\nContinue? [dim](y/N)[/dim] ").strip().lower()
                                    if ans not in ("y", "yes"):
                                        should_continue = False
                                except KeyboardInterrupt:
                                    interrupted = True
                                    should_continue = False
                                if not should_continue:
                                    stop_event.set()
                                    for pending_future in pending:
                                        pending_future.cancel()
                                    pending = set()
                                    break

                except KeyboardInterrupt:
                    interrupted = True
                    session_state["interrupted"] = interrupted
                    stop_event.set()
                    for future in pending:
                        future.cancel()
                    logger.warning("SESSION INTERRUPTED by user")
                    self._update_session_header(
                        layout,
                        progress,
                        speed_samples,
                        start_time,
                        parallel,
                        session_urls,
                        session_state,
                    )
                finally:
                    stop_event.set()

                kb_thread.join(timeout=0.5)
                executor.shutdown(wait=True)

                elapsed = time.monotonic() - start_time
                total_bytes = sum(task.completed for task in progress.tasks if task.completed is not None)
                success = len(session_urls) - len(failed)
                total_success += success
                if interrupted:
                    total_interrupted = True

                border_style, title, lines = self._build_completion_summary(
                    success=success,
                    failed=failed,
                    interrupted=interrupted,
                    mido_failed_count=mido_failed_count,
                    total_bytes=total_bytes,
                    elapsed=elapsed,
                )

                completion_size = 2 + len(lines) + (1 if interrupted else 0)
                layout.split_column(
                    Layout(name="header", size=7),
                    Layout(name="body", size=body_size),
                    Layout(name="completion", size=completion_size),
                    Layout(name="footer", size=1),
                )
                layout["body"].update(Panel(progress, title="[dim]Files[/]", border_style="dim"))
                layout["completion"].update(
                    Panel(
                        "\n".join(lines),
                        title=f"[bold]{title}[/bold]",
                        border_style=border_style,
                        expand=True,
                    )
                )
                layout["footer"].update(shortcuts)
                self._update_session_header(
                    layout,
                    progress,
                    speed_samples,
                    start_time,
                    parallel,
                    session_urls,
                    session_state,
                )
                time.sleep(0.15)

            logger.info(
                "SESSION DONE  success=%d  failed=%d  interrupted=%s  bytes=%d  elapsed=%.1fs",
                success,
                len(failed),
                interrupted,
                total_bytes,
                elapsed,
            )

            if failed and not interrupted and interactive:
                count = len(failed)
                console.print()
                console.print(
                    f"  [yellow]▶ {count} file{'s' if count != 1 else ''} failed.[/yellow]"
                    "  Retry? [dim](y/N)[/dim] ",
                    end="",
                )
                try:
                    ans = input().strip().lower()
                except (EOFError, KeyboardInterrupt):
                    ans = "n"
                if ans in ("y", "yes"):
                    urls_to_try = list(failed)
                    console.print(
                        f"\n  [dim]Queuing {count} file{'s' if count != 1 else ''} for retry…[/dim]\n"
                    )
                    continue

            break

        return total_success > 0 and not total_interrupted and not failed and not mido_failed_count
