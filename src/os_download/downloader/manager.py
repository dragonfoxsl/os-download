import logging
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor
from concurrent.futures import wait as cf_wait
from pathlib import Path

import requests
from rich.console import Console
from rich.live import Live
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from os_download.downloader.checksums import verify_checksum
from os_download.downloader.compression import decompress_file
from os_download.downloader.curl import download_with_curl
from os_download.downloader.mido import download_with_mido
from os_download.downloader.paths import filename_from_url
from os_download.downloader.ui import SessionDashboard, SessionState, keyboard_listener
from os_download.http import get_session

console = Console()
logger = logging.getLogger("os_download")

# A file smaller than this is a truncated download or a mirror's HTML error page, never an ISO.
MIN_COMPLETE_BYTES = 1_048_576

RECENT_SECONDS = 86400


class DownloadManager:
    def __init__(self, download_dir: str = "./downloads", chunk_size: int = 8192):
        self.download_dir = Path(download_dir)
        self.chunk_size = chunk_size
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._session_override: requests.Session | None = None

    @property
    def session(self) -> requests.Session:
        """Thread-local by default so parallel downloads don't share one requests.Session."""
        if self._session_override is not None:
            return self._session_override
        return get_session()

    @session.setter
    def session(self, session: requests.Session) -> None:
        self._session_override = session

    def get_filename_from_url(self, url: str) -> str:
        return filename_from_url(url)

    def verify_checksum(self, filepath: Path, url: str) -> bool | None:
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
        progress: Progress | None,
        task_id: TaskID | None,
        stop_event: threading.Event | None,
    ) -> bool:
        return download_with_curl(url, filepath, resume_pos, progress, task_id, stop_event)

    def _quarantine(self, filepath: Path) -> Path | None:
        """Move a file that failed verification aside so a later resume cannot extend it."""
        corrupt = filepath.with_name(filepath.name + ".corrupt")
        try:
            filepath.replace(corrupt)
        except OSError as exc:
            logger.error("QUARANTINE FAILED  %s  -  %s", filepath.name, exc)
            return None
        logger.error("QUARANTINED  %s  ->  %s", filepath.name, corrupt.name)
        return corrupt

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
                logger.error("VERIFY FAIL  %s", filepath.name)
                corrupt = self._quarantine(filepath)
                if own_progress:
                    console.print("  [red]Checksum mismatch, file is corrupt[/]")
                    if corrupt is not None:
                        console.print(f"  [dim]Moved to {corrupt.name}; delete it and retry.[/]")
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

    def _single_file_progress(self) -> Progress:
        return Progress(
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
        )

    def _session_progress(self) -> Progress:
        return Progress(
            TextColumn("[bold cyan]{task.description:.42}"),
            BarColumn(bar_width=None),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
            expand=True,
        )

    def download_file(
        self,
        url: str,
        filename: str | None = None,
        resume: bool = True,
        verify: bool = False,
        decompress: bool = True,
        progress: Progress | None = None,
        task_id: TaskID | None = None,
        stop_event: threading.Event | None = None,
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
                    progress = self._single_file_progress()
                    task_id = progress.add_task(filename, total=None)
                    progress.start()
                ok = self._download_with_curl(
                    url, filepath, resume_pos, progress, task_id, stop_event
                )
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

            total: int | None = None
            if "content-length" in response.headers:
                total = resume_pos + int(response.headers["content-length"])
            elif "content-range" in response.headers:
                total = int(response.headers["content-range"].split("/")[-1])

            if own_progress:
                progress = self._single_file_progress()
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

    def _looks_complete(self, filepath: Path) -> bool:
        return filepath.exists() and filepath.stat().st_size >= MIN_COMPLETE_BYTES

    def _prompt_recent_files(self, urls: list[str], decompress: bool) -> tuple[set[str], set[str]]:
        """Ask whether recently downloaded files should be fetched again.

        Returns the URLs to skip, and the URLs recognised as recent.
        """
        recent: list[tuple[str, str, float]] = []
        for url in urls:
            filepath = self._final_filepath(url, decompress)
            if self._looks_complete(filepath):
                age = time.time() - filepath.stat().st_mtime
                if age < RECENT_SECONDS:
                    recent.append((url, filepath.name, age))

        if not recent:
            return set(), set()

        recent_urls = {url for url, _, _ in recent}
        count = len(recent)
        console.print(
            f"\n  [green]{count} file{'s' if count != 1 else ''} already downloaded "
            f"in the last 24 hours:[/green]"
        )
        for _, filename, age in recent:
            hours, remainder = divmod(int(age), 3600)
            minutes = remainder // 60
            console.print(f"    [dim]·[/dim] {filename}  [dim]({hours}h {minutes:02d}m ago)[/dim]")
        console.print("  Re-download anyway? [dim](y = yes / N = skip)[/dim]  ", end="")

        try:
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""

        if answer not in ("y", "yes"):
            return recent_urls, recent_urls

        for url in recent_urls:
            try:
                self._final_filepath(url, decompress).unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("UNLINK FAILED  %s  -  %s", url, exc)
        return set(), recent_urls

    def _prompt_resume_partials(self, urls: list[str], recent_urls: set[str]) -> bool:
        partial = [
            url
            for url in urls
            if url not in recent_urls
            and (self.download_dir / self.get_filename_from_url(url)).exists()
        ]
        if not partial:
            return True

        count = len(partial)
        console.print(
            f"\n  [yellow]Found {count} file{'s' if count != 1 else ''} "
            "from a previous session.[/yellow]"
            "  Resume previous partial downloads? [dim](Y/n)[/dim]  ",
            end="",
        )
        try:
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        return answer not in ("n", "no")

    def _prompt_skip(self) -> bool:
        try:
            answer = input("\nSkip this file and continue? [dim](Y/n)[/dim] ").strip().lower()
        except KeyboardInterrupt:
            return False
        return answer not in ("n", "no")

    def _prompt_retry(self, failed: list[str]) -> bool:
        count = len(failed)
        console.print()
        console.print(
            f"  [yellow]▶ {count} file{'s' if count != 1 else ''} failed.[/yellow]"
            "  Retry? [dim](y/N)[/dim] ",
            end="",
        )
        try:
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if answer not in ("y", "yes"):
            return False
        console.print(f"\n  [dim]Queuing {count} file{'s' if count != 1 else ''} for retry…[/dim]\n")
        return True

    def _cancel(self, pending, stop_event: threading.Event) -> None:
        stop_event.set()
        for future in pending:
            future.cancel()

    def _run_session(
        self,
        urls: list[str],
        resume: bool,
        verify: bool,
        decompress: bool,
        interactive: bool,
        parallel: int,
        mido_failed: int,
    ) -> SessionState:
        state = SessionState(
            urls=urls, parallel=parallel, resume=resume, verify=verify, mido_failed=mido_failed
        )
        progress = self._session_progress()
        task_ids = {
            url: progress.add_task(self.get_filename_from_url(url), total=None) for url in urls
        }
        dashboard = SessionDashboard(console, progress, state)

        stop_event = threading.Event()
        quit_event = threading.Event()
        kb_thread = threading.Thread(
            target=keyboard_listener, args=(quit_event, stop_event), daemon=True
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
            for url in urls
        }

        pending: set = set(futures)
        with Live(dashboard.layout, console=console, refresh_per_second=4):
            dashboard.start_refresh()
            kb_thread.start()
            try:
                while pending:
                    if quit_event.is_set():
                        state.interrupted = True
                        logger.warning("SESSION QUIT by user (q)")
                        self._cancel(pending, stop_event)
                        break

                    done_set, pending = cf_wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)

                    for future in done_set:
                        url = futures[future]
                        try:
                            ok = future.result()
                        except KeyboardInterrupt:
                            raise
                        except Exception as exc:
                            logger.error("FUTURE ERROR  %s  -  %s", url, exc)
                            ok = False

                        state.record(url, ok)
                        dashboard.update()

                        if not ok and interactive and parallel == 1 and not self._prompt_skip():
                            self._cancel(pending, stop_event)
                            pending = set()
                            break
            except KeyboardInterrupt:
                state.interrupted = True
                logger.warning("SESSION INTERRUPTED by user")
                self._cancel(pending, stop_event)
            finally:
                stop_event.set()

            dashboard.stop_refresh()
            kb_thread.join(timeout=0.5)
            executor.shutdown(wait=True)
            dashboard.show_completion()
            time.sleep(0.15)

        logger.info(
            "SESSION DONE  success=%d  failed=%d  not_started=%d  interrupted=%s  elapsed=%.1fs",
            len(state.succeeded),
            len(state.failed),
            len(urls) - state.done_count,
            state.interrupted,
            state.elapsed,
        )
        return state

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
        if interactive:
            urls_to_skip, recent_urls = self._prompt_recent_files(urls, decompress)
        if resume and interactive:
            resume = self._prompt_resume_partials(urls, recent_urls)

        mido_success = 0
        mido_failed = 0
        for url in mido_urls:
            if self._download_with_mido(url[len("mido://") :]):
                mido_success += 1
            else:
                mido_failed += 1

        urls_to_try = [url for url in urls if url not in urls_to_skip]
        if not urls_to_try:
            if not mido_urls:
                console.print("[green]All files are recent; nothing to download.[/]")
            return mido_success == len(mido_urls)

        total_success = 0
        while True:
            state = self._run_session(
                urls_to_try, resume, verify, decompress, interactive, parallel, mido_failed
            )
            total_success += len(state.succeeded)

            retry = (
                state.failed
                and not state.interrupted
                and interactive
                and self._prompt_retry(state.failed)
            )
            if not retry:
                break
            urls_to_try = list(state.failed)

        return (
            total_success > 0
            and not state.interrupted
            and not state.failed
            and not mido_failed
            and state.done_count == len(state.urls)
        )
