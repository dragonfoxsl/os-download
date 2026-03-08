#!/usr/bin/env python3
"""
Python Download Manager

Replaces the Go download functionality with Python.
Downloads files from URL lists with progress tracking and resume support.
"""

import os
import sys
import time
import platform
import requests
import argparse
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse
from datetime import datetime


def default_download_dir() -> Path:
    """Return an OS-appropriate default download directory."""
    system = platform.system()
    home = Path.home()
    if system == "Windows":
        # Prefer the user's Downloads folder on Windows
        downloads = home / "Downloads"
    elif system == "Darwin":
        downloads = home / "Downloads"
    else:
        # Linux / other — honour XDG_DOWNLOAD_DIR if set, else ~/Downloads
        xdg = os.environ.get("XDG_DOWNLOAD_DIR")
        downloads = Path(xdg) if xdg else home / "Downloads"
    return downloads / "os-isos"


class DownloadManager:
    """Download manager with progress tracking and resume support"""
    
    def __init__(self, download_dir: str = "./downloads", chunk_size: int = 8192):
        self.download_dir = Path(download_dir)
        self.chunk_size = chunk_size
        self.download_dir.mkdir(exist_ok=True)
        
    def format_bytes(self, bytes_size: int) -> str:
        """Convert bytes to human readable format"""
        if bytes_size == 0:
            return "0B"
        
        size_names = ["B", "KB", "MB", "GB", "TB", "PB"]
        i = 0
        while bytes_size >= 1024 and i < len(size_names) - 1:
            bytes_size /= 1024.0
            i += 1
        
        return f"{bytes_size:.1f}{size_names[i]}"
    
    def format_time(self, seconds: float) -> str:
        """Format time duration to human readable format"""
        if seconds < 60:
            return f"{seconds:.0f}s"
        elif seconds < 3600:
            return f"{seconds/60:.0f}m {seconds%60:.0f}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours:.0f}h {minutes:.0f}m"
    
    def get_filename_from_url(self, url: str) -> str:
        """Extract filename from URL"""
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)
        
        # If no filename in URL, generate one
        if not filename or '.' not in filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"download_{timestamp}"
            
            # Try to get extension from Content-Type
            try:
                response = requests.head(url, timeout=10)
                content_type = response.headers.get('content-type', '')
                if 'iso' in content_type or url.endswith('.iso'):
                    filename += '.iso'
                elif 'zip' in content_type or url.endswith('.zip'):
                    filename += '.zip'
                else:
                    filename += '.bin'
            except Exception:
                filename += '.bin'
        
        return filename
    
    def get_resume_position(self, filepath: Path) -> int:
        """Get the position to resume download from"""
        if filepath.exists():
            return filepath.stat().st_size
        return 0
    
    def download_file(self, url: str, filename: Optional[str] = None, resume: bool = True) -> bool:
        """Download a single file with progress tracking"""
        
        if not filename:
            filename = self.get_filename_from_url(url)
        
        filepath = self.download_dir / filename
        resume_pos = 0
        
        if resume:
            resume_pos = self.get_resume_position(filepath)
        
        print(f"\n📥 Downloading: {url}")
        print(f"💾 Save as: {filepath}")
        
        if resume_pos > 0:
            print(f"🔄 Resuming from: {self.format_bytes(resume_pos)}")
        
        headers = {}
        if resume_pos > 0:
            headers['Range'] = f'bytes={resume_pos}-'
        
        try:
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            
            # Check if server supports resume
            if resume_pos > 0 and response.status_code not in [206, 416]:
                print("⚠️ Server doesn't support resume, starting from beginning")
                resume_pos = 0
                response = requests.get(url, stream=True, timeout=30)
            
            response.raise_for_status()
            
            # Get total file size
            total_size = resume_pos
            if 'content-length' in response.headers:
                total_size += int(response.headers['content-length'])
            elif 'content-range' in response.headers:
                # For resumed downloads
                range_info = response.headers['content-range']
                total_size = int(range_info.split('/')[-1])
            
            print(f"📦 Total size: {self.format_bytes(total_size)}")
            
            # Open file for writing
            mode = 'ab' if resume_pos > 0 else 'wb'
            with open(filepath, mode) as f:
                downloaded = resume_pos
                start_time = time.time()
                last_update = start_time
                
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        current_time = time.time()
                        
                        # Update progress every 2 seconds
                        if current_time - last_update >= 2.0:
                            self._print_progress(downloaded, total_size, current_time - start_time)
                            last_update = current_time
                
                # Final progress update
                elapsed_time = time.time() - start_time
                self._print_progress(downloaded, total_size, elapsed_time, final=True)
            
            print(f"✅ Download completed: {filepath}")
            return True
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Download failed: {e}")
            return False
        except KeyboardInterrupt:
            print(f"\n⏸️ Download interrupted. Resume with the same command.")
            return False
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return False
    
    def _print_progress(self, downloaded: int, total_size: int, elapsed_time: float, final: bool = False):
        """Print download progress"""
        if total_size > 0:
            progress = (downloaded / total_size) * 100
            speed = downloaded / elapsed_time if elapsed_time > 0 else 0
            
            if final:
                print(f"📊 Downloaded {self.format_bytes(downloaded)} / {self.format_bytes(total_size)} "
                      f"({progress:.1f}%) in {self.format_time(elapsed_time)}")
            else:
                eta = (total_size - downloaded) / speed if speed > 0 else 0
                print(f"📊 {self.format_bytes(downloaded)} / {self.format_bytes(total_size)} "
                      f"({progress:.1f}%) | Speed: {self.format_bytes(speed)}/s | "
                      f"ETA: {self.format_time(eta)}")
        else:
            speed = downloaded / elapsed_time if elapsed_time > 0 else 0
            print(f"📊 Downloaded {self.format_bytes(downloaded)} | "
                  f"Speed: {self.format_bytes(speed)}/s | "
                  f"Time: {self.format_time(elapsed_time)}")
    
    def download_from_file(self, file_path: str, resume: bool = True) -> bool:
        """Download all URLs from a file"""
        
        file_path = Path(file_path)
        if not file_path.exists():
            print(f"❌ File not found: {file_path}")
            return False
        
        print(f"📂 Reading URLs from: {file_path}")
        
        urls = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Skip empty lines and comments
                    if line and not line.startswith('#'):
                        urls.append(line)
        
        except Exception as e:
            print(f"❌ Error reading file: {e}")
            return False
        
        if not urls:
            print("⚠️ No URLs found in file")
            return False
        
        print(f"🎯 Found {len(urls)} URL(s) to download")
        
        success_count = 0
        for i, url in enumerate(urls, 1):
            print(f"\n{'='*60}")
            print(f"📥 Download {i}/{len(urls)}")
            print(f"{'='*60}")
            
            if self.download_file(url, resume=resume):
                success_count += 1
            else:
                print(f"❌ Failed to download: {url}")
                
                # Ask user if they want to continue
                try:
                    response = input("\n❓ Continue with remaining downloads? (y/N): ").lower()
                    if response not in ['y', 'yes']:
                        break
                except KeyboardInterrupt:
                    print("\n⏹️ Download process stopped by user")
                    break
        
        print(f"\n🎉 Download Summary:")
        print(f"✅ Successful: {success_count}/{len(urls)}")
        print(f"❌ Failed: {len(urls) - success_count}/{len(urls)}")
        
        return success_count > 0


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Python Download Manager')
    parser.add_argument('--file', '-f', 
                       default='./os-links/all_os.txt',
                       help='File containing URLs to download (default: ./os-links/all_os.txt)')
    parser.add_argument('--url', '-u',
                       help='Single URL to download')
    parser.add_argument('--output', '-o',
                       help='Output filename (for single URL downloads)')
    _default_dir = str(default_download_dir())
    parser.add_argument('--dir', '-d',
                       default=_default_dir,
                       help=f'Download directory (default: {_default_dir})')
    parser.add_argument('--no-resume',
                       action='store_true',
                       help='Disable resume functionality')
    parser.add_argument('--chunk-size',
                       type=int,
                       default=8192,
                       help='Download chunk size in bytes (default: 8192)')
    
    args = parser.parse_args()
    
    print("Python Download Manager")
    print("=" * 50)
    
    # Create download manager
    manager = DownloadManager(download_dir=args.dir, chunk_size=args.chunk_size)
    resume = not args.no_resume
    
    if args.url:
        # Download single URL
        print(f"🎯 Single URL download mode")
        success = manager.download_file(args.url, args.output, resume=resume)
        sys.exit(0 if success else 1)
    
    else:
        # Download from file
        print(f"📁 File download mode")
        
        # Check the default URL file exists
        file_path = args.file
        if not Path(file_path).exists():
            print(f"❌ URL file not found: {file_path}")
            print(f"\n💡 Run the OS finder first: uv run os-finder")
            sys.exit(1)
        
        success = manager.download_from_file(file_path, resume=resume)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main() 