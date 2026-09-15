import bz2
import gzip
import os
import shutil
import tempfile
from pathlib import Path


def decompress_file(filepath: Path) -> Path:
    suffix = filepath.suffix.lower()
    output_path = filepath.with_suffix("")

    if suffix == ".bz2":
        source = bz2.open(filepath, "rb")
    elif suffix == ".gz":
        source = gzip.open(filepath, "rb")
    else:
        return filepath

    temporary_path: Path | None = None
    try:
        with source, tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".part",
            delete=False,
        ) as target:
            temporary_path = Path(target.name)
            shutil.copyfileobj(source, target)
            target.flush()
            os.fsync(target.fileno())
        temporary_path.replace(output_path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise

    filepath.unlink()
    return output_path
