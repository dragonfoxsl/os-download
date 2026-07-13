import argparse
import logging
import sys
from pathlib import Path

from rich.console import Console

from os_download import __version__
from os_download.downloader.aria2 import aria2_available
from os_download.downloader.manager import DownloadManager
from os_download.downloader.paths import default_download_dir
from os_download.logging import setup_file_logger

logger = logging.getLogger("os_download")
console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="OS ISO Download Manager")
    parser.add_argument("--version", action="version", version=f"os-download {__version__}")
    parser.add_argument(
        "--file",
        "-f",
        default="./os-links/all_os.txt",
        help="File containing URLs to download (default: ./os-links/all_os.txt)",
    )
    parser.add_argument("--url", "-u", help="Single URL to download")
    parser.add_argument("--output", "-o", help="Output filename (single URL only)")
    default_dir = str(default_download_dir())
    parser.add_argument(
        "--dir",
        "-d",
        default=default_dir,
        help=f"Download directory (default: {default_dir})",
    )
    parser.add_argument("--no-resume", action="store_true", help="Disable resume")
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Do not prompt to continue after a failed download",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip SHA256 checksum verification (verification is on by default)",
    )
    parser.add_argument(
        "--require-signature",
        action="store_true",
        help=(
            "Fail a download unless its checksum file carries a valid signature from a "
            "pinned distribution key (by default an unsigned checksum only warns)"
        ),
    )
    parser.add_argument(
        "--no-decompress",
        action="store_true",
        help="Skip automatic decompression of .bz2/.gz files",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        metavar="N",
        help="Number of simultaneous downloads (default: 1)",
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "aria2", "python"),
        default="auto",
        help=(
            "Download backend. 'auto' uses aria2c for multi-connection downloads when it is "
            "installed and falls back to the built-in one (default: auto)"
        ),
    )
    parser.add_argument(
        "--connections",
        type=int,
        default=8,
        metavar="N",
        help="Connections per file when using aria2c (default: 8)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        metavar="N",
        help="Attempts per file before giving up; a retry resumes (default: 3)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=8192,
        help="Download chunk size in bytes (default: 8192)",
    )
    parser.add_argument(
        "--log",
        metavar="FILE",
        default="./logs/os-download.log",
        help="Write log to FILE (default: ./logs/os-download.log)",
    )
    args = parser.parse_args()

    setup_file_logger(logger, args.log)

    manager = DownloadManager(
        download_dir=args.dir,
        chunk_size=args.chunk_size,
        require_signature=args.require_signature,
        backend=args.backend,
        connections=args.connections,
        max_retries=args.retries,
    )
    if args.backend == "aria2" and not aria2_available():
        console.print("[red]✗ --backend aria2 was requested but aria2c is not installed[/]")
        sys.exit(1)
    resume = not args.no_resume
    decompress = not args.no_decompress
    verify = not args.no_verify

    if args.url:
        success = manager.download_file(
            args.url,
            args.output,
            resume=resume,
            verify=verify,
            decompress=decompress,
        )
        sys.exit(0 if success else 1)

    if not Path(args.file).exists():
        console.print(f"[red]✗ URL file not found:[/] {args.file}")
        console.print("[dim]Run the OS finder first: uv run os-finder[/]")
        sys.exit(1)

    success = manager.download_from_file(
        args.file,
        resume=resume,
        verify=verify,
        decompress=decompress,
        interactive=not args.no_interactive,
        parallel=args.parallel,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
