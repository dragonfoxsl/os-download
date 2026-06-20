import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()
logger = logging.getLogger("os_download")
MIDO_DIR = Path.home() / ".local" / "share" / "mido"


def ensure_mido(mido_dir: Path = MIDO_DIR) -> Optional[Path]:
    script = mido_dir / "Mido.sh"
    if script.exists():
        return script
    if shutil.which("git") is None:
        console.print("[red]git is required to install Mido, install git and retry.[/]")
        return None
    console.print("[dim]Cloning Mido from GitHub...[/]")
    try:
        subprocess.run(
            ["git", "clone", "--depth=1", "https://github.com/ElliotKillick/Mido", str(mido_dir)],
            check=True,
        )
    except subprocess.CalledProcessError:
        console.print("[red]Failed to clone Mido.[/]")
        return None
    script.chmod(0o755)
    return script


def download_with_mido(variant: str, download_dir: Path) -> bool:
    script = ensure_mido()
    if script is None:
        return False
    console.print(f"\n[bold cyan]Mido -> {variant}[/bold cyan]")
    logger.info("MIDO START  %s", variant)
    try:
        result = subprocess.run(["bash", str(script), variant], cwd=str(download_dir))
    except Exception as exc:
        console.print(f"[red]Mido error: {exc}[/]")
        logger.error("MIDO ERROR  %s  -  %s", variant, exc)
        return False

    if result.returncode == 0:
        logger.info("MIDO DONE  %s", variant)
        return True
    logger.error("MIDO FAILED  %s  rc=%d", variant, result.returncode)
    return False
