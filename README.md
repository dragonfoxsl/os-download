<p align="center">
  <img src="assets/logo.svg" alt="os-download" width="520"/>
</p>

<br>

**os-download** is a two-command Python CLI that finds the latest download URL for every major OS ISO and pulls them to disk with resume support, parallel downloads, and checksum verification.

```bash
os-finder          # resolve latest ISO URLs for all supported OSes
os-download        # download everything that was found
```

---

## Supported operating systems

| OS | Source | Auto-version | Format | Checksum |
|---|---|---|---|---|
| **Ubuntu** | Launchpad API + releases.ubuntu.com | Yes (LTS + latest) | `.iso` | `SHA256SUMS` |
| **OPNsense** | pkg.opnsense.org | Yes | `.iso.bz2` (auto-extracted) | |
| **pfSense CE** | Netgate CDN | Yes | `.iso.gz` (auto-extracted) | `.sha256` |
| **Debian** | cdimage.debian.org | Yes | `.iso` | |
| **TrueNAS Scale** | GitHub Releases API | Yes | `.iso` | |
| **Windows 11** | [Mido](https://github.com/ElliotKillick/Mido) | Yes | `.iso` | |
| **Manjaro KDE** | manjaro.org/products | Yes | `.iso` | |
| **MX Linux** | mxlinux.org / SourceForge | Yes (Xfce x64) | `.iso` | |
| **Puppy Linux** | SourceForge CDN → ibiblio fallback | Yes (fossapup64) | `.iso` | |
| **CachyOS** | mirror.cachyos.org | Yes | `.iso` | `.sha256` |

> **Windows 11** — Microsoft's ISO download requires a JavaScript session-token flow that cannot be replicated with plain HTTP. os-download delegates this to [Mido](https://github.com/ElliotKillick/Mido), which is cloned automatically on first use.

---

## Installation

### With uv (recommended)

[uv](https://docs.astral.sh/uv/) installs the tool into an isolated environment and puts `os-finder` and `os-download` on your PATH.

```bash
# 1. Install uv (skip if you already have it)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install os-download
uv tool install git+https://github.com/dragonfoxsl/os-download
```

Both commands are now available from any directory.

```bash
# Upgrade to the latest version at any time
uv tool upgrade os-download

# Uninstall
uv tool uninstall os-download
```

### With pipx

```bash
pipx install git+https://github.com/dragonfoxsl/os-download
```

### Development install

```bash
git clone https://github.com/dragonfoxsl/os-download
cd os-download
uv sync

# Run from the project directory
uv run os-finder
uv run os-download
```

---

## Usage

### Step 1: Find ISO URLs

```bash
# All supported OSes (runs in parallel)
os-finder

# Specific OSes
os-finder --os ubuntu debian cachyos mxlinux

# Save URLs to a custom path
os-finder --output ~/isos/urls.txt

# Increase timeout for slow connections
os-finder --timeout 30

# Machine-readable JSON output
os-finder --json
```

### Step 2: Download

```bash
# Download everything found
os-download

# Three simultaneous downloads
os-download --parallel 3

# Download and verify checksums
os-download --verify

# Download to a specific directory
os-download --dir /mnt/nas/isos

# Single URL
os-download --url "https://example.com/file.iso"

# Skip automatic decompression of .bz2 / .gz files
os-download --no-decompress
```

### Keyboard shortcuts (download dashboard)

| Key | Action |
|---|---|
| `q` | Quit cleanly — partial files are saved and can be resumed |
| `Ctrl+C` | Interrupt — same as `q`, partial files resume automatically |

---

## Download dashboard

When downloading multiple files, os-download shows a live dashboard:

- **Header** — active / done / failed counts, total data downloaded, speed sparkline, elapsed time
- **Files** — one progress bar per file with size, speed, and ETA
- **Footer** — keyboard shortcuts and current session settings

On completion the dashboard transitions to a summary panel showing files downloaded, total data, time taken, and any failures. If downloads fail you are prompted to retry them; the retry runs only the failed files.

At startup, if partial files are detected you are prompted to resume or start from scratch. Files downloaded within the last 24 hours are listed and can be skipped.

---

## All flags

**`os-finder`**

| Flag | Default | Description |
|---|---|---|
| `--os` | `all` | Space-separated list: `ubuntu opnsense pfsense debian truenas windows11 manjaro mxlinux puppy cachyos` |
| `--output` | `./os-links/all_os.txt` | Output file for resolved ISO URLs |
| `--timeout` | `15` | HTTP timeout in seconds |
| `--no-interactive` | off | Skip manual override prompt when a URL cannot be found |
| `--json` | off | Print JSON to stdout, suppress progress display |
| `--log` | `./logs/os-finder.log` | Log file path |

**`os-download`**

| Flag | Default | Description |
|---|---|---|
| `--file` / `-f` | `./os-links/all_os.txt` | URL list file |
| `--url` / `-u` | | Download a single URL |
| `--dir` / `-d` | `~/Downloads/os-isos` | Output directory |
| `--parallel` | `1` | Simultaneous downloads |
| `--verify` | off | SHA256 checksum verification after each download |
| `--no-decompress` | off | Keep `.bz2` / `.gz` files compressed |
| `--no-resume` | off | Start downloads from the beginning even if partial file exists |
| `--no-interactive` | off | Fail fast on error without prompting to continue |
| `--chunk-size` | `8192` | Download chunk size in bytes |
| `--log` | `./logs/os-download.log` | Log file path |

---

## How it works

```
os-finder                          os-download
─────────────────────────────      ─────────────────────────────
MultiOSDownloadFinder              DownloadManager
  └─ runs all finders in             └─ reads ./os-links/all_os.txt
     parallel via                       runs downloads in parallel
     ThreadPoolExecutor                 via ThreadPoolExecutor

Each finder (BaseOSFinder          Each download
subclass) is independent:            • streams in chunks
  • scrapes its source               • resumes via Range header
  • verifies the URL                 • decompresses .bz2/.gz
  • returns {variant: url}           • verifies SHA256 if --verify
                                     • mido:// URIs delegated to Mido
```

### Adding a new OS

1. Add a finder module under `src/os_download/finders/` that subclasses `BaseOSFinder` from `src/os_download/finders/base.py`:

```python
class MyOSFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("My OS", timeout)

    def find_download_links(self) -> Dict[str, str]:
        # fetch, scrape, return {variant: url}
        return {'amd64': 'https://...'}
```

2. Register it in `src/os_download/finders/registry.py`:

```python
'myos': MyOSFinder(timeout),
```

3. Add `'myos'` to `OS_CHOICES` so `src/os_download/cli/finder.py` exposes it through `--os`.

---

## Credits

| Project | Role |
|---|---|
| [Mido](https://github.com/ElliotKillick/Mido) by [@ElliotKillick](https://github.com/ElliotKillick) | Windows 11 ISO download — Mido replicates Microsoft's JavaScript session-token flow to deliver a direct ISO. os-download clones and invokes it automatically. |

---

## Built with

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)
![uv](https://img.shields.io/badge/uv-package%20manager-DE5FE9?logo=python&logoColor=white)
![requests](https://img.shields.io/badge/requests-HTTP-20232A)
![Rich](https://img.shields.io/badge/Rich-terminal%20UI-0F766E)
![pytest](https://img.shields.io/badge/pytest-tested-0A9EDC?logo=pytest&logoColor=white)
![Ruff](https://img.shields.io/badge/Ruff-linted-D7FF64?logo=ruff&logoColor=black)

---

## License

MIT
