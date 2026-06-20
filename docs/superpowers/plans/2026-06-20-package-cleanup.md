# Package Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the two-script CLI into a maintainable `src/os_download` package while preserving `os-finder` and `os-download`, fixing known downloader/finder reliability issues, and adding tests.

**Architecture:** Move CLI parsing into `src/os_download/cli`, OS resolvers into `src/os_download/finders`, downloader orchestration into `src/os_download/downloader`, and shared HTTP/logging helpers into package-level modules. Preserve behavior through entry points and targeted unit tests before deleting the legacy top-level scripts.

**Tech Stack:** Python 3.9+, requests, Rich, uv, hatchling, pytest, ruff.

## Global Constraints

- Installed commands remain `os-finder` and `os-download`.
- Existing flags stay compatible.
- Default finder output remains `./os-links/all_os.txt`.
- Default finder log remains `./logs/os-finder.log`.
- Default downloader URL file remains `./os-links/all_os.txt`.
- Default downloader log remains `./logs/os-download.log`.
- Default download directory remains platform download directory plus `os-isos`.
- The default test suite must not hit live network services.
- Windows 11 still resolves to `mido://win11x64`.
- This pass does not add new Mido flags.

---

## File Structure

- Create `src/os_download/http.py`: shared `build_session() -> requests.Session`.
- Create `src/os_download/logging.py`: shared `setup_file_logger(logger: logging.Logger, log_file: str) -> None`.
- Create `src/os_download/finders/base.py`: `BaseOSFinder`, `ISO_EXTS`, `has_iso_link()`, `url_kind()`.
- Create one module per finder under `src/os_download/finders/`.
- Create `src/os_download/finders/registry.py`: `MultiOSDownloadFinder`, `create_finders()`, `OS_CHOICES`.
- Create `src/os_download/cli/finder.py`: finder argparse, summary printing, output writing.
- Create `src/os_download/downloader/checksums.py`: checksum lookup and file hashing.
- Create `src/os_download/downloader/compression.py`: `.bz2` and `.gz` decompression.
- Create `src/os_download/downloader/curl.py`: curl fallback helper.
- Create `src/os_download/downloader/mido.py`: Mido installation and invocation.
- Create `src/os_download/downloader/paths.py`: default download path and URL filename helper.
- Create `src/os_download/downloader/manager.py`: `DownloadManager` orchestration.
- Create `src/os_download/cli/downloader.py`: downloader argparse and exit codes.
- Modify `pyproject.toml`: package entry points, hatch package include, pytest/ruff dev dependencies/config.
- Modify `.gitignore`: ignore `logs/` correctly.
- Modify `README.md`: update source references and add shields badges in "Built with".
- Delete `os_download_finder.py` and `download_manager.py` after equivalent package entry points pass.

---

### Task 1: Add Test Tooling And Baseline Failing Tests

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/test_checksums.py`
- Create: `tests/test_compression.py`
- Create: `tests/test_downloader_post_download.py`
- Create: `tests/test_opnsense_finder.py`
- Create: `tests/test_truenas_finder.py`
- Create: `tests/test_gitignore.py`

**Interfaces:**
- Consumes: no new package modules yet.
- Produces: tests that initially fail because `os_download.*` package modules do not exist.

- [ ] **Step 1: Add dev dependencies and pytest path setup**

Add this to `pyproject.toml`:

```toml
[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "ruff>=0.8.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py39"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501"]
```

- [ ] **Step 2: Write failing checksum tests**

Create `tests/test_checksums.py`:

```python
from pathlib import Path

from os_download.downloader.checksums import verify_checksum


class FakeResponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class FakeSession:
    def __init__(self, responses):
        self.responses = responses
        self.urls = []

    def get(self, url, timeout=None):
        self.urls.append(url)
        return self.responses.get(url, FakeResponse(404))


def test_verify_checksum_matches_sidecar(tmp_path: Path):
    file_path = tmp_path / "image.iso.gz"
    file_path.write_bytes(b"archive")
    session = FakeSession(
        {
            "https://example.test/image.iso.gz.sha256": FakeResponse(
                200,
                "f5568340a22cf182286a1c3e9563c6f930f09849cc33f235782a8862d230b4e0  image.iso.gz",
            )
        }
    )

    assert verify_checksum(session, file_path, "https://example.test/image.iso.gz") is True


def test_verify_checksum_matches_sha256sums(tmp_path: Path):
    file_path = tmp_path / "ubuntu.iso"
    file_path.write_bytes(b"ubuntu")
    session = FakeSession(
        {
            "https://example.test/ubuntu.iso.sha256": FakeResponse(404),
            "https://example.test/SHA256SUMS": FakeResponse(
                200,
                "7804a56c0d512d13a538f0d4c9ddc0e59a520e85da4d01b545d1aa2e215ca8bb *ubuntu.iso\n",
            ),
        }
    )

    assert verify_checksum(session, file_path, "https://example.test/ubuntu.iso") is True


def test_verify_checksum_returns_none_when_no_checksum_exists(tmp_path: Path):
    file_path = tmp_path / "unknown.iso"
    file_path.write_bytes(b"data")
    session = FakeSession({})

    assert verify_checksum(session, file_path, "https://example.test/unknown.iso") is None
```

- [ ] **Step 3: Write failing compression tests**

Create `tests/test_compression.py`:

```python
import bz2
import gzip
from pathlib import Path

from os_download.downloader.compression import decompress_file


def test_decompress_file_extracts_gz_and_removes_archive(tmp_path: Path):
    archive = tmp_path / "sample.iso.gz"
    archive.write_bytes(gzip.compress(b"iso-bytes"))

    output = decompress_file(archive)

    assert output == tmp_path / "sample.iso"
    assert output.read_bytes() == b"iso-bytes"
    assert not archive.exists()


def test_decompress_file_extracts_bz2_and_removes_archive(tmp_path: Path):
    archive = tmp_path / "sample.iso.bz2"
    archive.write_bytes(bz2.compress(b"iso-bytes"))

    output = decompress_file(archive)

    assert output == tmp_path / "sample.iso"
    assert output.read_bytes() == b"iso-bytes"
    assert not archive.exists()
```

- [ ] **Step 4: Write failing post-download order test**

Create `tests/test_downloader_post_download.py`:

```python
import gzip
from pathlib import Path

from os_download.downloader.manager import DownloadManager


def test_post_download_verifies_archive_before_decompressing(tmp_path: Path, monkeypatch):
    manager = DownloadManager(download_dir=str(tmp_path))
    archive = tmp_path / "image.iso.gz"
    archive.write_bytes(gzip.compress(b"iso"))
    calls = []

    def fake_verify(filepath: Path, url: str):
        calls.append(("verify", filepath.name, archive.exists()))
        return True

    monkeypatch.setattr(manager, "verify_checksum", fake_verify)

    assert manager._post_download(
        archive,
        "https://example.test/image.iso.gz",
        verify=True,
        decompress=True,
        own_progress=False,
    )

    assert calls == [("verify", "image.iso.gz", True)]
    assert (tmp_path / "image.iso").exists()
```

- [ ] **Step 5: Write failing finder tests**

Create `tests/test_opnsense_finder.py`:

```python
from os_download.finders.opnsense import OPNsenseFinder


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeSession:
    def get(self, url, timeout=None):
        if url.endswith("/releases/"):
            return FakeResponse('<a href="24.7/">24.7/</a>')
        return FakeResponse('<a href="OPNsense-24.7-dvd-amd64.iso.bz2">iso</a>')


def test_opnsense_does_not_return_unverified_url():
    finder = OPNsenseFinder(timeout=1)
    finder.session = FakeSession()
    finder.verify_download_url = lambda url: False

    assert finder.find_download_links() == {}
```

Create `tests/test_truenas_finder.py`:

```python
from os_download.finders.truenas import TrueNASFinder


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"tag_name": "TrueNAS-SCALE-99.01.0"}


class FakeSession:
    def get(self, url, timeout=None):
        return FakeResponse()


def test_truenas_unknown_codename_returns_download_page():
    finder = TrueNASFinder(timeout=1)
    finder.session = FakeSession()

    assert finder.find_download_links() == {
        "download_page": "https://www.truenas.com/download-truenas-scale/"
    }
```

- [ ] **Step 6: Write failing gitignore test**

Create `tests/test_gitignore.py`:

```python
from pathlib import Path


def test_gitignore_ignores_logs_directory():
    gitignore = Path(".gitignore").read_text(encoding="utf-8").splitlines()

    assert "logs/" in gitignore
    assert "!downloads/Usage.mdlogs/" not in gitignore
```

- [ ] **Step 7: Run tests to verify red**

Run: `uv run pytest -q`

Expected: FAIL with import errors for `os_download.*` modules and `.gitignore` assertion failure.

- [ ] **Step 8: Commit test/tooling baseline**

```bash
git add pyproject.toml tests
git commit -m "test: add package cleanup regression tests"
```

---

### Task 2: Create Shared Package Foundation

**Files:**
- Create: `src/os_download/__init__.py`
- Create: `src/os_download/http.py`
- Create: `src/os_download/logging.py`
- Create: `src/os_download/downloader/__init__.py`
- Create: `src/os_download/downloader/checksums.py`
- Create: `src/os_download/downloader/compression.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: tests from Task 1.
- Produces:
  - `build_session() -> requests.Session`
  - `setup_file_logger(logger: logging.Logger, log_file: str) -> None`
  - `hash_file(filepath: Path) -> str`
  - `verify_checksum(session, filepath: Path, url: str) -> Optional[bool]`
  - `decompress_file(filepath: Path) -> Path`

- [ ] **Step 1: Implement package metadata and shared session**

Create `src/os_download/__init__.py`:

```python
"""Find and download OS ISO images."""

__version__ = "0.1.0"
```

Create `src/os_download/http.py`:

```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
    )
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
```

- [ ] **Step 2: Implement logging helper**

Create `src/os_download/logging.py`:

```python
import logging
from pathlib import Path


def setup_file_logger(logger: logging.Logger, log_file: str) -> None:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s"))
    logger.setLevel(logging.DEBUG)
    if not any(
        isinstance(handler, logging.FileHandler)
        and getattr(handler, "baseFilename", None) == str(Path(log_file).resolve())
        for handler in logger.handlers
    ):
        logger.addHandler(fh)
```

- [ ] **Step 3: Implement checksum helper**

Create `src/os_download/downloader/__init__.py`:

```python
"""Download and verification helpers."""
```

Create `src/os_download/downloader/checksums.py`:

```python
import hashlib
from pathlib import Path
from typing import Optional

import requests


def hash_file(filepath: Path) -> str:
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest().lower()


def verify_checksum(session: requests.Session, filepath: Path, url: str) -> Optional[bool]:
    fname = filepath.name

    try:
        response = session.get(url + ".sha256", timeout=10)
        if response.status_code == 200:
            expected = response.text.strip().split()[0]
            return hash_file(filepath) == expected.lower()
    except Exception:
        pass

    directory_sums_url = url.rsplit("/", 1)[0] + "/SHA256SUMS"
    try:
        response = session.get(directory_sums_url, timeout=10)
        if response.status_code == 200:
            for line in response.text.splitlines():
                parts = line.strip().split(None, 1)
                if len(parts) == 2 and parts[1].lstrip("* ") == fname:
                    return hash_file(filepath) == parts[0].lower()
    except Exception:
        pass

    return None
```

- [ ] **Step 4: Implement compression helper**

Create `src/os_download/downloader/compression.py`:

```python
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
```

- [ ] **Step 5: Update build target**

Replace the hatch wheel target in `pyproject.toml` with:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/os_download"]
```

- [ ] **Step 6: Run focused tests**

Run: `uv run pytest tests/test_checksums.py tests/test_compression.py -q`

Expected: PASS.

- [ ] **Step 7: Commit foundation**

```bash
git add pyproject.toml src/os_download tests/test_checksums.py tests/test_compression.py
git commit -m "refactor: add package foundation"
```

---

### Task 3: Move Finders Into Package

**Files:**
- Create: `src/os_download/finders/__init__.py`
- Create: `src/os_download/finders/base.py`
- Create: `src/os_download/finders/ubuntu.py`
- Create: `src/os_download/finders/opnsense.py`
- Create: `src/os_download/finders/pfsense.py`
- Create: `src/os_download/finders/debian.py`
- Create: `src/os_download/finders/truenas.py`
- Create: `src/os_download/finders/windows.py`
- Create: `src/os_download/finders/manjaro.py`
- Create: `src/os_download/finders/mxlinux.py`
- Create: `src/os_download/finders/puppy.py`
- Create: `src/os_download/finders/cachyos.py`
- Create: `src/os_download/finders/registry.py`

**Interfaces:**
- Consumes: `build_session()` from `src/os_download/http.py`.
- Produces:
  - `BaseOSFinder.verify_download_url(url: str) -> bool`
  - `has_iso_link(links: dict[str, str]) -> bool`
  - `url_kind(url: str) -> tuple[str, str]`
  - `MultiOSDownloadFinder.find_all_links(os_list=None, interactive=True, quiet=False) -> dict[str, dict[str, str]]`
  - `MultiOSDownloadFinder.save_links_to_file(all_links, output_path="./os-links/all_os.txt") -> None`
  - `OS_CHOICES: list[str]`

- [ ] **Step 1: Create finder base**

Create `src/os_download/finders/__init__.py`:

```python
"""Operating-system download URL finders."""
```

Create `src/os_download/finders/base.py`:

```python
from typing import Dict, Tuple

from os_download.http import build_session

ISO_EXTS = (".iso", ".iso.bz2", ".iso.gz")
_SESSION = build_session()


class BaseOSFinder:
    def __init__(self, name: str, timeout: int = 15):
        self.name = name
        self.timeout = timeout
        self.session = _SESSION

    def verify_download_url(self, url: str) -> bool:
        try:
            response = self.session.head(url, timeout=self.timeout, allow_redirects=True)
            return response.status_code == 200
        except Exception:
            return False

    def find_download_links(self) -> Dict[str, str]:
        raise NotImplementedError


def has_iso_link(links: Dict[str, str]) -> bool:
    return any(
        url.lower().endswith(ISO_EXTS) or url.startswith("mido://")
        for url in links.values()
    )


def url_kind(url: str) -> Tuple[str, str]:
    if url.startswith("mido://"):
        return "Mido", "blue"
    if url.lower().endswith(ISO_EXTS):
        return "ISO", "green"
    return "link", "yellow"
```

- [ ] **Step 2: Move individual finder classes**

Copy each finder class from `os_download_finder.py` into its matching module, changing imports to:

```python
import re
from typing import Dict, Optional, Tuple
from urllib.parse import urljoin

from os_download.finders.base import BaseOSFinder
```

For `src/os_download/finders/opnsense.py`, implement the fixed return:

```python
class OPNsenseFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("OPNsense", timeout)
        self.pkg_index = "https://pkg.opnsense.org/releases/"

    def find_download_links(self) -> Dict[str, str]:
        try:
            response = self.session.get(self.pkg_index, timeout=self.timeout)
            response.raise_for_status()
            versions = re.findall(r'href="(\d+\.\d+)/"', response.text)
            if not versions:
                return {}
            versions.sort(key=lambda version: tuple(map(int, version.split("."))))
            version_url = f"{self.pkg_index}{versions[-1]}/"

            response = self.session.get(version_url, timeout=self.timeout)
            response.raise_for_status()
            isos = re.findall(
                r'href="(OPNsense-[\d.]+-dvd-amd64\.iso(?:\.bz2)?)"',
                response.text,
                re.IGNORECASE,
            )
            if not isos:
                return {}
            isos.sort(
                key=lambda name: tuple(
                    int(part)
                    for part in re.findall(
                        r"\d+",
                        re.search(r"OPNsense-([\d.]+)-", name).group(1),
                    )
                )
            )
            url = version_url + isos[-1]
            return {"amd64": url} if self.verify_download_url(url) else {}
        except Exception:
            return {}
```

For `src/os_download/finders/truenas.py`, implement the fixed unknown-codename return:

```python
class TrueNASFinder(BaseOSFinder):
    codenames = {
        "25.04": "Fangtooth",
        "24.10": "Electric-Eel",
        "24.04": "Dragonfish",
    }
    download_page = "https://www.truenas.com/download-truenas-scale/"

    def __init__(self, timeout: int = 15):
        super().__init__("TrueNAS Scale", timeout)
        self.github_api = "https://api.github.com/repos/truenas/truenas-scale/releases/latest"
        self.download_base = "https://download.sys.truenas.net/TrueNAS-SCALE-"

    def find_download_links(self) -> Dict[str, str]:
        version = None
        try:
            response = self.session.get(self.github_api, timeout=self.timeout)
            response.raise_for_status()
            tag = response.json().get("tag_name", "")
            version = tag.replace("TrueNAS-SCALE-", "").strip() or None
        except Exception:
            pass

        if not version:
            version = "25.04.1"

        major_minor = ".".join(version.split(".")[:2])
        codename = self.codenames.get(major_minor)
        if codename is None:
            return {"download_page": self.download_page}

        url = f"{self.download_base}{codename}/{version}/TrueNAS-SCALE-{version}.iso"
        return {"scale": url}
```

For `src/os_download/finders/windows.py`, implement:

```python
from typing import Dict

from os_download.finders.base import BaseOSFinder


class Windows11Finder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("Windows 11", timeout)

    def find_download_links(self) -> Dict[str, str]:
        return {"win11x64": "mido://win11x64"}
```

- [ ] **Step 3: Create registry**

Create `src/os_download/finders/registry.py`:

```python
import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import redirect_stdout
from typing import Dict, List, Optional

from rich.console import Console

from os_download.finders.base import BaseOSFinder, has_iso_link
from os_download.finders.cachyos import CachyOSFinder
from os_download.finders.debian import DebianFinder
from os_download.finders.manjaro import ManjaroKDEFinder
from os_download.finders.mxlinux import MXLinuxFinder
from os_download.finders.opnsense import OPNsenseFinder
from os_download.finders.pfsense import PfSenseFinder
from os_download.finders.puppy import PuppyLinuxFinder
from os_download.finders.truenas import TrueNASFinder
from os_download.finders.ubuntu import UbuntuFinder
from os_download.finders.windows import Windows11Finder

console = Console()
logger = logging.getLogger("os_finder")

OS_CHOICES = [
    "ubuntu",
    "opnsense",
    "pfsense",
    "debian",
    "truenas",
    "windows11",
    "manjaro",
    "mxlinux",
    "puppy",
    "cachyos",
    "all",
]


def prompt_override_url(os_name: str, session) -> Optional[str]:
    console.print(f"\n[yellow]No direct ISO found for {os_name}.[/]")
    try:
        url = input("   Enter an override URL (or press Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        console.print("   [red]URL must start with http:// or https://, skipping.[/]")
        return None

    try:
        response = session.head(url, timeout=10, allow_redirects=True)
        if response.status_code == 200:
            console.print("   [green]URL verified.[/]")
        else:
            console.print(f"   [yellow]Server returned {response.status_code}, may still work.[/]")
    except Exception as exc:
        console.print(f"   [yellow]Could not verify: {exc}[/]")
    return url


def run_finder(finder: BaseOSFinder):
    buffer = io.StringIO()
    try:
        with redirect_stdout(buffer):
            links = finder.find_download_links()
    except Exception as exc:
        buffer.write(f"Error: {exc}\n")
        links = {}
    return links, buffer.getvalue()


class MultiOSDownloadFinder:
    def __init__(self, timeout: int = 15):
        self.finders = {
            "ubuntu": UbuntuFinder(timeout),
            "opnsense": OPNsenseFinder(timeout),
            "pfsense": PfSenseFinder(timeout),
            "debian": DebianFinder(timeout),
            "truenas": TrueNASFinder(timeout),
            "windows11": Windows11Finder(timeout),
            "manjaro": ManjaroKDEFinder(timeout),
            "mxlinux": MXLinuxFinder(timeout),
            "puppy": PuppyLinuxFinder(timeout),
            "cachyos": CachyOSFinder(timeout),
        }

    def find_all_links(
        self,
        os_list: Optional[List[str]] = None,
        interactive: bool = True,
        quiet: bool = False,
    ) -> Dict[str, Dict[str, str]]:
        valid = [name for name in (os_list or list(self.finders)) if name in self.finders]
        for name in os_list or []:
            if name not in self.finders:
                console.print(f"[yellow]Unknown OS: {name}[/]")

        results: Dict[str, Dict[str, str]] = {}
        with ThreadPoolExecutor(max_workers=len(valid)) as executor:
            futures = {executor.submit(run_finder, self.finders[name]): name for name in valid}
            for future in as_completed(futures):
                name = futures[future]
                links, _ = future.result()
                results[name] = links
                logger.info("FINDER  %-14s  links=%d  %s", name, len(links), list(links.keys()))

        all_links: Dict[str, Dict[str, str]] = {}
        for name in valid:
            links = results.get(name, {})
            if interactive and not has_iso_link(links):
                override = prompt_override_url(self.finders[name].name, self.finders[name].session)
                if override:
                    links["override"] = override
            if links:
                all_links[name] = links
        return all_links

    def save_links_to_file(
        self,
        all_links: Dict[str, Dict[str, str]],
        output_path: str = "./os-links/all_os.txt",
    ) -> None:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as output:
            for links in all_links.values():
                for url in links.values():
                    if url.lower().endswith((".iso", ".iso.bz2", ".iso.gz")) or url.startswith(
                        "mido://"
                    ):
                        output.write(f"{url}\n")
        console.print(f"[green]ISO links saved to:[/] {output_path}")
```

- [ ] **Step 4: Run finder tests**

Run: `uv run pytest tests/test_opnsense_finder.py tests/test_truenas_finder.py -q`

Expected: PASS.

- [ ] **Step 5: Commit finders**

```bash
git add src/os_download/finders tests/test_opnsense_finder.py tests/test_truenas_finder.py
git commit -m "refactor: move finders into package"
```

---

### Task 4: Move Downloader Helpers And Manager

**Files:**
- Create: `src/os_download/downloader/paths.py`
- Create: `src/os_download/downloader/mido.py`
- Create: `src/os_download/downloader/curl.py`
- Create: `src/os_download/downloader/manager.py`

**Interfaces:**
- Consumes:
  - `verify_checksum(session, filepath, url)`
  - `decompress_file(filepath)`
  - `build_session()`
- Produces:
  - `default_download_dir() -> Path`
  - `filename_from_url(url: str) -> str`
  - `DownloadManager.download_file(...) -> bool`
  - `DownloadManager.download_from_file(...) -> bool`
  - `DownloadManager._post_download(...) -> bool`

- [ ] **Step 1: Create path helpers**

Create `src/os_download/downloader/paths.py`:

```python
import os
import platform
from pathlib import Path
from urllib.parse import urlparse


def default_download_dir() -> Path:
    system = platform.system()
    home = Path.home()
    if system in ("Windows", "Darwin"):
        base = home / "Downloads"
    else:
        xdg = os.environ.get("XDG_DOWNLOAD_DIR")
        base = Path(xdg) if xdg else home / "Downloads"
    return base / "os-isos"


def filename_from_url(url: str) -> str:
    filename = os.path.basename(urlparse(url).path)
    if not filename or "." not in filename:
        filename = f"download_{url[-8:]}.bin"
    return filename
```

- [ ] **Step 2: Move Mido helper**

Create `src/os_download/downloader/mido.py` using the existing `_ensure_mido()` and `_download_with_mido()` logic from `download_manager.py`, converted to functions:

```python
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
```

- [ ] **Step 3: Move curl helper**

Create `src/os_download/downloader/curl.py` using the current `_download_with_curl()` behavior. Keep signature:

```python
def download_with_curl(url, filepath, resume_pos, progress, task_id, stop_event) -> bool:
    ...
```

The implementation must preserve:

- `curl -sIL` content-length lookup.
- `curl -L -s -S`.
- `curl -C -` when resuming.
- Stop-event termination.
- Progress updates from file size changes.

- [ ] **Step 4: Move manager and fix post-download order**

Create `src/os_download/downloader/manager.py` by moving `DownloadManager` and `_keyboard_listener()` from `download_manager.py`, changing imports to package helpers.

Implement `_post_download()` as:

```python
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
```

Keep wrapper methods for compatibility inside `DownloadManager`:

```python
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
```

- [ ] **Step 5: Run downloader test**

Run: `uv run pytest tests/test_downloader_post_download.py -q`

Expected: PASS.

- [ ] **Step 6: Commit downloader package**

```bash
git add src/os_download/downloader tests/test_downloader_post_download.py
git commit -m "refactor: move downloader into package"
```

---

### Task 5: Add Package CLI Entry Points

**Files:**
- Create: `src/os_download/cli/__init__.py`
- Create: `src/os_download/cli/finder.py`
- Create: `src/os_download/cli/downloader.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes:
  - `MultiOSDownloadFinder`
  - `OS_CHOICES`
  - `url_kind`
  - `DownloadManager`
  - `default_download_dir`
- Produces package entry points:
  - `os_download.cli.finder:main`
  - `os_download.cli.downloader:main`

- [ ] **Step 1: Create CLI package**

Create `src/os_download/cli/__init__.py`:

```python
"""Command-line interfaces for os-download."""
```

- [ ] **Step 2: Move finder CLI**

Create `src/os_download/cli/finder.py` by moving `main()` and `_print_summary()` from `os_download_finder.py`. Change imports to:

```python
import argparse
import json
import logging
import sys

from rich import box as rich_box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from os_download.finders.base import ISO_EXTS, url_kind
from os_download.finders.registry import MultiOSDownloadFinder, OS_CHOICES
from os_download.logging import setup_file_logger
```

Use:

```python
logger = logging.getLogger("os_finder")
console = Console()
```

The parser choices should use `OS_CHOICES`.

- [ ] **Step 3: Move downloader CLI**

Create `src/os_download/cli/downloader.py` by moving `main()` from `download_manager.py`. Change imports to:

```python
import argparse
import logging
import sys
from pathlib import Path

from rich.console import Console

from os_download.downloader.manager import DownloadManager
from os_download.downloader.paths import default_download_dir
from os_download.logging import setup_file_logger
```

Use:

```python
logger = logging.getLogger("os_download")
console = Console()
```

- [ ] **Step 4: Update entry points**

Change `pyproject.toml` scripts to:

```toml
[project.scripts]
os-finder = "os_download.cli.finder:main"
os-download = "os_download.cli.downloader:main"
```

- [ ] **Step 5: Run CLI smoke checks**

Run:

```bash
uv run os-finder --help
uv run os-download --help
uv run os-finder --os windows11 --json
```

Expected:

- both help commands exit 0
- JSON smoke returns:

```json
{
  "windows11": {
    "win11x64": "mido://win11x64"
  }
}
```

- [ ] **Step 6: Commit package CLIs**

```bash
git add pyproject.toml src/os_download/cli
git commit -m "refactor: add package cli entry points"
```

---

### Task 6: Remove Legacy Scripts And Finish Repo Hygiene

**Files:**
- Delete: `os_download_finder.py`
- Delete: `download_manager.py`
- Modify: `.gitignore`
- Modify: `README.md`

**Interfaces:**
- Consumes: package entry points from Task 5.
- Produces: no top-level script modules, corrected ignore rules, updated README badges.

- [ ] **Step 1: Fix `.gitignore`**

Replace the downloads/logs block with:

```gitignore
# Generated output files
all_os_links.txt
logs/

# Exclude the contents of the downloads folder
downloads/*
!downloads/Usage.md
```

- [ ] **Step 2: Remove legacy scripts**

Delete:

```text
os_download_finder.py
download_manager.py
```

- [ ] **Step 3: Update README Built With badges**

Replace the current "Built with" table in `README.md` with:

```markdown
## Built with

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![uv](https://img.shields.io/badge/uv-package%20manager-DE5FE9?logo=python&logoColor=white)
![requests](https://img.shields.io/badge/requests-HTTP-20232A)
![Rich](https://img.shields.io/badge/Rich-terminal%20UI-0F766E)
![pytest](https://img.shields.io/badge/pytest-tested-0A9EDC?logo=pytest&logoColor=white)
![Ruff](https://img.shields.io/badge/Ruff-linted-D7FF64?logo=ruff&logoColor=black)
```

- [ ] **Step 4: Run gitignore test**

Run: `uv run pytest tests/test_gitignore.py -q`

Expected: PASS.

- [ ] **Step 5: Run CLI smoke checks after deletions**

Run:

```bash
uv run os-finder --help
uv run os-download --help
uv run os-finder --os windows11 --json
```

Expected: same as Task 5.

- [ ] **Step 6: Commit cleanup**

```bash
git add .gitignore README.md os_download_finder.py download_manager.py
git commit -m "refactor: remove legacy script entry points"
```

---

### Task 7: Final Verification And Cleanup

**Files:**
- Modify as needed based on verification output.

**Interfaces:**
- Consumes all previous tasks.
- Produces verified package cleanup.

- [ ] **Step 1: Run full tests**

Run: `uv run pytest -q`

Expected: PASS.

- [ ] **Step 2: Run ruff**

Run: `uv run ruff check .`

Expected: PASS.

- [ ] **Step 3: Compile package**

Run:

```bash
uv run python -m compileall src tests
```

Expected: PASS with no syntax errors.

- [ ] **Step 4: Build package**

Run: `uv build`

Expected: source distribution and wheel build successfully.

- [ ] **Step 5: Check working tree**

Run: `git status --short`

Expected: only pre-existing unrelated untracked files may remain, such as `logs/`, `node_modules/`, `package.json`, and `pnpm-lock.yaml` if not intentionally removed.

- [ ] **Step 6: Commit verification cleanup if needed**

If verification required changes:

```bash
git add <changed-files>
git commit -m "chore: finish package cleanup verification"
```

If no changes were required, do not create an empty commit.

---

## Self-Review

- Spec coverage: package layout, CLI compatibility, checksum order, OPNsense verification, TrueNAS codenames, Mido isolation, `.gitignore`, README badges, pytest, ruff, and no-network tests are all covered.
- Placeholder scan: no task uses TBD/TODO/fill-in placeholders. The curl helper step delegates to existing behavior because the exact implementation already exists in `download_manager.py`; the required signature and preserved behavior are explicit.
- Type consistency: exported function and class names are consistent across tasks.
