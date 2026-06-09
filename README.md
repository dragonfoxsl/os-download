<p align="center">
  <img src="assets/logo.svg" alt="os-download" width="520"/>
</p>

<br>

**os-download** is a two-command Python CLI that finds the latest download URL for every major OS ISO and pulls them to disk with resume support, parallel downloads, and checksum verification.

```bash
uv run os-finder          # resolve latest ISO URLs for all supported OSes
uv run os-download        # download everything that was found
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

Requires **Python 3.9+** and [uv](https://docs.astral.sh/uv/).

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone https://github.com/dragonfoxsl/os-download
cd os-download
uv sync
```

---

## Usage

### Step 1: Find ISO URLs

```bash
# All supported OSes (runs in parallel)
uv run os-finder

# Specific OSes
uv run os-finder --os ubuntu debian cachyos mxlinux

# Save URLs to a custom path
uv run os-finder --output ~/isos/urls.txt

# Increase timeout for slow connections
uv run os-finder --timeout 30

# Machine-readable JSON output
uv run os-finder --json
```

### Step 2: Download

```bash
# Download everything found
uv run os-download

# Three simultaneous downloads
uv run os-download --parallel 3

# Download and verify checksums
uv run os-download --verify

# Download to a specific directory
uv run os-download --dir /mnt/nas/isos

# Single URL
uv run os-download --url "https://example.com/file.iso"

# Skip automatic decompression of .bz2 / .gz files
uv run os-download --no-decompress
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

1. Subclass `BaseOSFinder` in `os_download_finder.py`:

```python
class MyOSFinder(BaseOSFinder):
    def __init__(self, timeout: int = 15):
        super().__init__("My OS", timeout)

    def find_download_links(self) -> Dict[str, str]:
        # fetch, scrape, return {variant: url}
        return {'amd64': 'https://...'}
```

2. Register it in `MultiOSDownloadFinder.__init__`:

```python
'myos': MyOSFinder(timeout),
```

3. Add `'myos'` to the `--os` argparse choices in `main()`.

---

## Credits

| Project | Role |
|---|---|
| [Mido](https://github.com/ElliotKillick/Mido) by [@ElliotKillick](https://github.com/ElliotKillick) | Windows 11 ISO download — Mido replicates Microsoft's JavaScript session-token flow to deliver a direct ISO. os-download clones and invokes it automatically. |

---

## Built with

| | |
|---|---|
| **Python 3.9+** | Core language |
| **requests** | HTTP with retry logic and resume support |
| **rich** | Terminal progress bars and formatted output |
| **uv** | Fast dependency management and script runner |

---

## License

MIT
