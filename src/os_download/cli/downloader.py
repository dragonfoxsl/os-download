import argparse
import logging
import sys
from pathlib import Path

from rich.console import Console

from os_download.downloader.manager import DownloadManager
from os_download.downloader.paths import default_download_dir
from os_download.logging import setup_file_logger

logger = logging.getLogger("os_download")
console = Console()


def main() -> None:
    parser = argparse.ArgumentParser(description="OS ISO Download Manager")
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
        "--verify",
        action="store_true",
        help="Verify SHA256 checksum after each download",
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

    manager = DownloadManager(download_dir=args.dir, chunk_size=args.chunk_size)
    resume = not args.no_resume
    decompress = not args.no_decompress

    if args.url:
        success = manager.download_file(
            args.url,
            args.output,
            resume=resume,
            verify=args.verify,
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
        verify=args.verify,
        decompress=decompress,
        interactive=not args.no_interactive,
        parallel=args.parallel,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
