import logging
import sys
from pathlib import Path


def setup_file_logger(logger: logging.Logger, log_file: str) -> None:
    log_path = Path(log_file)
    target = str(log_path.resolve())
    if any(
        isinstance(handler, logging.FileHandler)
        and getattr(handler, "baseFilename", None) == target
        for handler in logger.handlers
    ):
        return

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, encoding="utf-8")
    except OSError as exc:
        print(f"Warning: File logging disabled for {log_path}: {exc}", file=sys.stderr)
        return

    fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s"))
    logger.setLevel(logging.DEBUG)
    logger.addHandler(fh)
