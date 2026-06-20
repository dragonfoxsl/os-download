import logging
import sys
import threading
from pathlib import Path
from typing import List, Optional

from rich.console import Console
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
from os_download.http import build_session

console = Console()
logger = logging.getLogger("os_download")


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

    def _read_urls(self, file_path: str) -> List[str]:
        path = Path(file_path)
        if not path.exists():
            console.print(f"[red]URL file not found:[/] {file_path}")
            return []
        urls: List[str] = []
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)
        return urls

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
        del interactive, parallel

        all_urls = self._read_urls(file_path)
        if not all_urls:
            console.print("[yellow]No URLs found in file[/]")
            return False

        total_success = 0
        for url in all_urls:
            if url.startswith("mido://"):
                ok = self._download_with_mido(url[len("mido://") :])
            else:
                ok = self.download_file(url, resume=resume, verify=verify, decompress=decompress)
            if ok:
                total_success += 1

        return total_success == len(all_urls)
