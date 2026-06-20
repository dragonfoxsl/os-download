import bz2
import gzip
import shutil
from pathlib import Path


def decompress_file(filepath: Path) -> Path:
    suffix = filepath.suffix.lower()
    output_path = filepath.with_suffix("")

    if suffix == ".bz2":
        with bz2.open(filepath, "rb") as source, open(output_path, "wb") as target:
            shutil.copyfileobj(source, target)
    elif suffix == ".gz":
        with gzip.open(filepath, "rb") as source, open(output_path, "wb") as target:
            shutil.copyfileobj(source, target)
    else:
        return filepath

    filepath.unlink()
    return output_path
