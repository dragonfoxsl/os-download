# OS Download Tool (Python)

A comprehensive Python-based tool for finding and downloading operating system ISO files. This tool consists of two main components:

1. **OS Download Finder** - Automatically finds download links for various operating systems
2. **Download Manager** - Downloads files with progress tracking and resume support

## Supported Operating Systems

| OS | Variants | Auto-Detection | Verification |
| --- | --- | --- | --- |
| **Ubuntu LTS** | Desktop, Server | Yes | Yes |
| **OPNsense** | AMD64 | Yes | Yes |
| **pfSense** | All variants | Partial | Download page |
| **Debian** | NetInst, DVD | Yes | Yes |
| **TrueNAS Scale** | Latest | Yes | Yes |
| **Windows 11** | Media Tool | Partial | Official links |
| **Manjaro KDE** | Latest | Partial | Download page |
| **Puppy Linux** | Various | Yes | Yes |

## Features

### OS Finder (`os_download_finder.py`)

- **Auto-detection**: Latest version finding for each OS via APIs and web scraping
- **Multiple sources**: APIs, web scraping, fallback methods
- **URL verification**: Checks if links are accessible before saving
- **Selective processing**: Choose specific OS or get all
- **Smart file output**: Download-ready URL list

### Download Manager (`download_manager.py`)

- **Progress tracking**: Real-time speed, percentage, ETA
- **Resume support**: Continue interrupted downloads via HTTP Range headers
- **Error handling**: Graceful failure recovery
- **File management**: Automatic filename detection from URL
- **Configurable**: Chunk size, directories, resume options

## Installation

### Requirements

- Python 3.9+
- [uv](https://docs.astral.sh/uv/) — fast Python package manager

### Setup

```bash
# Install uv (Linux/macOS)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install uv (Windows PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Clone and install
git clone https://github.com/dragonfoxsl/os-download
cd os-download
uv sync
```

## Usage

### Step 1: Find OS Download Links

```bash
# Find all supported operating systems
uv run os-finder

# Find specific operating systems
uv run os-finder --os ubuntu debian manjaro

# Find just Ubuntu LTS
uv run os-finder --os ubuntu

# Find firewall OSes
uv run os-finder --os opensense pfsense
```

### Step 2: Download Files

```bash
# Download all found URLs
uv run os-download

# Download from specific file
uv run os-download --file ./os-links/all_os.txt

# Download single URL
uv run os-download --url "https://example.com/file.iso"

# Download to specific directory
uv run os-download --dir ./my_downloads

# Disable resume functionality
uv run os-download --no-resume
```

## Command Reference

### OS Finder Options

```text
uv run os-finder [OPTIONS]

Options:
  --os {ubuntu,opensense,pfsense,debian,truenas,windows11,manjaro,puppy,all}
      Operating systems to find (default: all)
```

### Download Manager Options

```text
uv run os-download [OPTIONS]

Options:
  -f, --file FILE       File with URLs (default: ./os-links/all_os.txt)
  -u, --url URL         Single URL to download
  -o, --output OUTPUT   Output filename (for single URL)
  -d, --dir DIR         Download directory (default: ./downloads)
  --no-resume           Disable resume functionality
  --chunk-size SIZE     Download chunk size in bytes (default: 8192)
```

## File Structure

After running both tools, your directory will look like:

```text
os-download/
├── os_download_finder.py   # OS link finder
├── download_manager.py     # Download manager
├── pyproject.toml          # uv project config & dependencies
├── uv.lock                 # Locked dependency versions
├── README.md               # This file
├── os-links/
│   └── all_os.txt          # Download-ready URLs
└── downloads/              # Downloaded ISO files
    ├── ubuntu-24.04.4-desktop-amd64.iso
    ├── debian-13.3.0-amd64-netinst.iso
    └── ...
```

## Typical Workflow

### Quick Start (All OS)

```bash
# 1. Find all OS download links
uv run os-finder

# 2. Download all found ISOs
uv run os-download
```

### Selective Download

```bash
# 1. Find specific OS links
uv run os-finder --os ubuntu debian

# 2. Download only those
uv run os-download --file ./os-links/all_os.txt
```

### Single File Download

```bash
uv run os-download --url "https://releases.ubuntu.com/24.04/ubuntu-24.04.4-desktop-amd64.iso"
```

## Sample Output

### OS Finder Output

```text
Multi-OS Download Link Finder
============================================================
Processing: ubuntu, debian

Processing: Ubuntu LTS
Finding Ubuntu LTS download links...
Found latest LTS from API: 24.04
Desktop URL verified
Found 2 link(s) for Ubuntu LTS

SUMMARY - Found links for 2 operating system(s):
Ubuntu LTS:
  desktop: http://releases.ubuntu.com/24.04/ubuntu-24.04.4-desktop-amd64.iso
  server: http://releases.ubuntu.com/24.04/ubuntu-24.04.4-live-server-amd64.iso
```

### Download Manager Output

```text
Python Download Manager
==================================================
Reading URLs from: os-links/all_os.txt
Found 7 URL(s) to download

Downloading: http://releases.ubuntu.com/24.04/ubuntu-24.04.4-desktop-amd64.iso
Save as: downloads/ubuntu-24.04.4-desktop-amd64.iso
Total size: 5.9GB
203.3MB / 5.9GB (3.4%) | Speed: 11.0MB/s | ETA: 9m 53s
```

## Advanced Features

### Resume Downloads

The download manager automatically resumes interrupted downloads:

```bash
# If download was interrupted, simply run again
uv run os-download
# It will automatically resume from where it left off
```

### Custom Download Directory

```bash
uv run os-download --dir /path/to/my/isos
```

### Performance Tuning

```bash
# Increase chunk size for faster downloads on good connections
uv run os-download --chunk-size 65536

# Decrease for slower/unstable connections
uv run os-download --chunk-size 4096
```

## Troubleshooting

### Common Issues

#### "No URL files found"

- Run the OS finder first: `uv run os-finder`
- Check that `./os-links/all_os.txt` exists

#### Downloads are slow

- Try increasing chunk size: `--chunk-size 65536`
- Check your internet connection
- Some servers may have rate limiting

#### Resume not working

- Some servers don't support resume
- The tool will automatically restart from beginning
- Use `--no-resume` to force fresh downloads

#### URL verification fails

- URLs may still work even if verification fails
- Some servers don't respond to HEAD requests
- The finder includes unverified URLs with warnings

### OS-Specific Notes

- **pfSense**: Requires registration, provides download page
- **Windows 11**: Microsoft restrictions, provides official tools
- **TrueNAS**: May require form submission
- **Manjaro**: Download structure changes frequently

## Migration from Go Version

If you previously used the Go version of this tool:

### What Changed

- **Go removed**: No more `go run main.go`
- **Pure Python + uv**: Single language, easier to maintain
- **Better resume**: More robust resume functionality
- **More OS support**: Added 7 new operating systems
- **Better progress**: Enhanced progress tracking

### Migration Steps

1. Remove old Go files (done automatically)
2. Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
3. Install dependencies: `uv sync`
4. Use new commands:
   - Old: `go run main.go`
   - New: `uv run os-download`

## Performance

### Download Speeds

- Typical: 5-15 MB/s (depends on server and connection)
- Large files: Resume support prevents starting over
- Progress updates: Every 2 seconds (non-blocking)

### Memory Usage

- Low memory footprint
- Streaming downloads (doesn't load entire file into memory)
- Configurable chunk sizes for optimization

## Contributing

To add a new operating system:

1. Create a new finder class in `os_download_finder.py`:

```python
class NewOSFinder(BaseOSFinder):
    def find_download_links(self) -> Dict[str, str]:
        # Implementation here
        return {'variant': 'download_url'}
```

1. Add to the finder registry in `MultiOSDownloadFinder`
2. Update the argument parser choices
3. Test and submit a pull request

## License

This tool is provided as-is for educational and personal use. Please respect the download policies and licensing terms of each operating system.
