import logging
import os
import shutil
import subprocess
from pathlib import Path

from rich.console import Console

console = Console()
logger = logging.getLogger("os_download")
MIDO_DIR = Path.home() / ".local" / "share" / "mido"
MIDO_REPO = "https://github.com/ElliotKillick/Mido"

# Mido.sh is executed on the user's machine, so a specific reviewed commit is fetched rather
# than whatever the default branch currently points at. Override with OS_DOWNLOAD_MIDO_REF.
MIDO_COMMIT = "25d9fbdf20842d8f611e54e92f186901dbb3a04a"


def mido_ref() -> str:
    return os.environ.get("OS_DOWNLOAD_MIDO_REF", MIDO_COMMIT)


def ensure_mido(mido_dir: Path = MIDO_DIR) -> Path | None:
    script = mido_dir / "Mido.sh"
    ref = mido_ref()

    if script.exists() and _checked_out_ref(mido_dir) == ref:
        return script

    if shutil.which("git") is None:
        console.print("[red]git is required to install Mido, install git and retry.[/]")
        return None

    console.print(f"[dim]Fetching Mido {ref[:12]} from GitHub...[/]")
    try:
        mido_dir.mkdir(parents=True, exist_ok=True)
        _git(mido_dir, "init", "--quiet")
        _git(mido_dir, "remote", "remove", "origin", check=False)
        _git(mido_dir, "remote", "add", "origin", MIDO_REPO)
        _git(mido_dir, "fetch", "--quiet", "--depth=1", "origin", ref)
        _git(mido_dir, "checkout", "--quiet", "--force", "FETCH_HEAD")
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]Failed to fetch Mido at {ref[:12]}.[/]")
        logger.error("MIDO FETCH FAILED  %s  -  %s", ref, exc)
        return None

    if not script.exists():
        console.print("[red]Mido.sh missing from the fetched repository.[/]")
        return None

    script.chmod(0o755)
    return script


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _checked_out_ref(mido_dir: Path) -> str | None:
    try:
        result = _git(mido_dir, "rev-parse", "HEAD")
    except (subprocess.CalledProcessError, OSError):
        return None
    return result.stdout.strip() or None


def download_with_mido(variant: str, download_dir: Path) -> bool:
    script = ensure_mido()
    if script is None:
        return False
    console.print(f"\n[bold cyan]Mido -> {variant}[/bold cyan]")
    logger.info("MIDO START  %s", variant)
    try:
        result = subprocess.run(
            ["bash", str(script), variant],
            cwd=str(download_dir),
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        console.print(f"[red]Mido error: {exc}[/]")
        logger.error("MIDO ERROR  %s  -  %s", variant, exc)
        return False

    if result.returncode == 0:
        logger.info("MIDO DONE  %s", variant)
        return True
    console.print(
        f"[yellow]Warning:[/] Mido failed for {variant}. "
        "Microsoft may have changed or blocked the download flow; try again later."
    )
    logger.error("MIDO FAILED  %s  rc=%d", variant, result.returncode)
    if result.stdout:
        logger.debug("MIDO STDOUT  %s\n%s", variant, result.stdout)
    if result.stderr:
        logger.debug("MIDO STDERR  %s\n%s", variant, result.stderr)
    return False
