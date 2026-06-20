import logging
from pathlib import Path


def setup_file_logger(logger: logging.Logger, log_file: str) -> None:
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s"))
    logger.setLevel(logging.DEBUG)
    if not any(
        isinstance(handler, logging.FileHandler)
        and getattr(handler, "baseFilename", None) == str(log_path.resolve())
        for handler in logger.handlers
    ):
        logger.addHandler(fh)
