#!/usr/bin/env python3
"""
Multi-OS Download Link Finder

This script finds download links for various operating systems including:
- Ubuntu LTS (Server & Desktop)
- OpenSense
- pfSense
- Debian (Stable)
- TrueNAS Scale
- Windows 11
- Manjaro KDE
- Puppy Linux
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
import sys
from datetime import datetime
import argparse


def _build_session() -> requests.Session:
    """Build a shared session with browser-like User-Agent and retry logic."""
    session = requests.Session()
    session.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        )
    })
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


# Shared session used by all finders
_session = _build_session()


class BaseOSFinder:
    """Base class for OS finders"""

    def __init__(self, name: str):
        self.name = name
        self.session = _session

    def verify_download_url(self, url: str, timeout: int = 10) -> bool:
        """Verify if a download URL is accessible"""
        try:
            response = self.session.head(url, timeout=timeout, allow_redirects=True)
            return response.status_code == 200
        except Exception:
            return False

    def find_download_links(self) -> Dict[str, str]:
        """Find download links for this OS. Must be implemented by subclasses."""
        raise NotImplementedError


class UbuntuLTSFinder(BaseOSFinder):
    """Ubuntu LTS download finder"""
    
    def __init__(self):
        super().__init__("Ubuntu LTS")
        self.base_url = "http://releases.ubuntu.com/"
        self.api_url = "https://api.launchpad.net/1.0/ubuntu/series"
    
    def get_latest_lts_version(self) -> Optional[str]:
        """Get the latest LTS version"""
        try:
            print(f"🌐 Checking Ubuntu API for latest LTS version...")
            response = self.session.get(self.api_url, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            lts_versions = []
            
            for entry in data.get('entries', []):
                if entry.get('supported') and 'LTS' in entry.get('displayname', ''):
                    version = entry.get('version', '')
                    if version:
                        lts_versions.append(version)
            
            if lts_versions:
                lts_versions.sort(key=lambda x: tuple(map(int, x.split('.'))))
                latest = lts_versions[-1]
                print(f"✅ Found latest LTS from API: {latest}")
                return latest
        except Exception as e:
            print(f"⚠️ Error fetching from API: {e}")
        
        # Fallback method
        try:
            print("🔧 Trying fallback method...")
            response = self.session.get(self.base_url, timeout=15)
            response.raise_for_status()
            
            content = response.text
            lts_pattern = r'href="(\d+\.\d+)/"'
            matches = re.findall(lts_pattern, content)
            
            if matches:
                lts_candidates = []
                for version in matches:
                    year = int(version.split('.')[0])
                    month = int(version.split('.')[1])
                    if year % 2 == 0 and month == 4:
                        lts_candidates.append(version)
                
                if lts_candidates:
                    lts_candidates.sort(key=lambda x: tuple(map(int, x.split('.'))))
                    latest = lts_candidates[-1]
                    print(f"✅ Found latest LTS from releases page: {latest}")
                    return latest
        except Exception as e:
            print(f"⚠️ Fallback method failed: {e}")
        
        return "22.04"  # Final fallback
    
    def find_download_links(self) -> Dict[str, str]:
        """Find Ubuntu LTS download links"""
        print(f"🔍 Finding {self.name} download links...")
        
        version = self.get_latest_lts_version()
        if not version:
            return {}
        
        print(f"📦 Latest Ubuntu LTS version: {version}")
        
        # Construct URLs
        base_url = f"{self.base_url}{version}/"
        links = {
            'desktop': f"{base_url}ubuntu-{version}-desktop-amd64.iso",
            'server': f"{base_url}ubuntu-{version}-server-amd64.iso"
        }
        
        # Try to find actual filenames by scraping
        try:
            response = self.session.get(base_url, timeout=10)
            if response.status_code == 200:
                content = response.text
                
                desktop_pattern = r'href="([^"]*ubuntu[^"]*desktop[^"]*\.iso)"'
                desktop_match = re.search(desktop_pattern, content, re.IGNORECASE)
                if desktop_match:
                    links['desktop'] = urljoin(base_url, desktop_match.group(1))
                
                server_pattern = r'href="([^"]*ubuntu[^"]*server[^"]*\.iso)"'
                server_match = re.search(server_pattern, content, re.IGNORECASE)
                if server_match:
                    links['server'] = urljoin(base_url, server_match.group(1))
        except Exception:
            pass

        # Verify URLs
        verified_links = {}
        for variant, url in links.items():
            print(f"🔗 Checking {variant} URL...")
            if self.verify_download_url(url):
                verified_links[variant] = url
                print(f"✅ {variant.capitalize()} URL verified")
            else:
                print(f"❌ {variant.capitalize()} URL not accessible")
        
        return verified_links


class OpenSenseFinder(BaseOSFinder):
    """OPNsense download finder"""

    def __init__(self):
        super().__init__("OpenSense")
        self.mirror_index = "https://mirror.opnsense.org/releases/"

    def _latest_version_from_mirror(self) -> Optional[str]:
        """Scrape the OPNsense mirror releases index for the latest version."""
        try:
            r = self.session.get(self.mirror_index, timeout=15)
            r.raise_for_status()
            versions = re.findall(r'href="(\d+\.\d+)/"', r.text)
            if versions:
                versions.sort(key=lambda v: tuple(map(int, v.split('.'))))
                return versions[-1]
        except Exception as e:
            print(f"⚠️ Could not determine OPNsense version from mirror: {e}")
        return None

    def find_download_links(self) -> Dict[str, str]:
        """Find OPNsense download links"""
        print(f"🔍 Finding {self.name} download links...")

        version = self._latest_version_from_mirror()
        if version:
            print(f"✅ Latest OPNsense version from mirror: {version}")
        else:
            version = "25.1"
            print(f"⚠️ Falling back to version {version}")

        # Scrape the version directory for the dvd amd64 ISO
        version_url = f"{self.mirror_index}{version}/"
        links = {}
        try:
            r = self.session.get(version_url, timeout=15)
            if r.status_code == 200:
                match = re.search(
                    r'href="(OPNsense[^"]*dvd[^"]*amd64\.iso(?:\.bz2)?)"',
                    r.text, re.IGNORECASE
                )
                if match:
                    links['amd64'] = version_url + match.group(1)
        except Exception as e:
            print(f"⚠️ Could not scrape version directory: {e}")

        if not links:
            print("🔧 Using constructed OPNsense URL pattern...")
            links['amd64'] = (
                f"https://mirror.opnsense.org/releases/{version}/"
                f"OPNsense-{version}-OpenSSL-dvd-amd64.iso"
            )

        verified_links = {}
        for variant, url in links.items():
            print(f"🔗 Checking {variant} URL...")
            if self.verify_download_url(url):
                verified_links[variant] = url
                print(f"✅ {variant.capitalize()} URL verified")
            else:
                print(f"⚠️ {variant.capitalize()} URL not verified (but may still work)")
                verified_links[variant] = url

        return verified_links


class PfSenseFinder(BaseOSFinder):
    """pfSense download finder"""
    
    def __init__(self):
        super().__init__("pfSense")
        self.download_url = "https://www.pfsense.org/download/"
    
    def find_download_links(self) -> Dict[str, str]:
        """Find pfSense download links"""
        print(f"🔍 Finding {self.name} download links...")
        
        try:
            response = self.session.get(self.download_url, timeout=15)
            response.raise_for_status()
            content = response.text

            links = {}

            # Look for download links
            iso_pattern = r'href="([^"]*\.iso[^"]*)"'
            matches = re.findall(iso_pattern, content, re.IGNORECASE)

            for match in matches:
                if 'amd64' in match.lower():
                    links['amd64'] = match
                    break
            
            # Manual fallback for pfSense
            if not links:
                print("🔧 Using manual pfSense URL pattern...")
                # Note: pfSense requires registration, so we provide the download page
                links['download_page'] = "https://www.pfsense.org/download/"
                print("⚠️ pfSense requires registration. Download page provided.")
            
            return links
            
        except Exception as e:
            print(f"❌ Error finding pfSense links: {e}")
            return {'download_page': "https://www.pfsense.org/download/"}


class DebianFinder(BaseOSFinder):
    """Debian stable download finder"""
    
    def __init__(self):
        super().__init__("Debian")
        self.base_url = "https://www.debian.org"
        self.download_url = "https://www.debian.org/CD/"
    
    def find_download_links(self) -> Dict[str, str]:
        """Find Debian download links"""
        print(f"🔍 Finding {self.name} download links...")
        
        try:
            links = {}

            # Scrape netinst
            try:
                r = self.session.get("https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/", timeout=10)
                if r.status_code == 200:
                    match = re.search(r'href="(debian[^"]*netinst\.iso)"', r.text)
                    if match:
                        links['netinst'] = f"https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/{match.group(1)}"
            except Exception:
                pass

            # Scrape DVD-1
            try:
                r = self.session.get("https://cdimage.debian.org/debian-cd/current/amd64/iso-dvd/", timeout=10)
                if r.status_code == 200:
                    match = re.search(r'href="(debian[^"]*DVD-1\.iso)"', r.text)
                    if match:
                        links['dvd'] = f"https://cdimage.debian.org/debian-cd/current/amd64/iso-dvd/{match.group(1)}"
            except Exception:
                pass

            # Fallbacks if scraping failed
            if 'netinst' not in links:
                links['netinst'] = "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/debian-12.11.0-amd64-netinst.iso"
            if 'dvd' not in links:
                links['dvd'] = "https://cdimage.debian.org/debian-cd/current/amd64/iso-dvd/debian-12.11.0-amd64-DVD-1.iso"
            
            verified_links = {}
            for variant, url in links.items():
                print(f"🔗 Checking {variant} URL...")
                if self.verify_download_url(url):
                    verified_links[variant] = url
                    print(f"✅ {variant.capitalize()} URL verified")
                else:
                    print(f"⚠️ {variant.capitalize()} URL not verified (but may still work)")
                    verified_links[variant] = url
            
            return verified_links
            
        except Exception as e:
            print(f"❌ Error finding Debian links: {e}")
            return {}


class TrueNASFinder(BaseOSFinder):
    """TrueNAS Scale download finder"""

    def __init__(self):
        super().__init__("TrueNAS Scale")
        self.github_api = "https://api.github.com/repos/truenas/truenas-scale/releases/latest"
        self.download_base = "https://download.sys.truenas.net/TrueNAS-SCALE-"

    def _latest_from_github(self) -> Optional[str]:
        """Get latest TrueNAS Scale version from GitHub Releases API."""
        try:
            r = self.session.get(self.github_api, timeout=15)
            r.raise_for_status()
            tag = r.json().get('tag_name', '')
            # Tags are like "TrueNAS-SCALE-25.04.1" or just "25.04.1"
            version = tag.replace('TrueNAS-SCALE-', '').strip()
            if version:
                return version
        except Exception as e:
            print(f"⚠️ GitHub API unavailable for TrueNAS: {e}")
        return None

    def find_download_links(self) -> Dict[str, str]:
        """Find TrueNAS Scale download links"""
        print(f"🔍 Finding {self.name} download links...")

        version = self._latest_from_github()
        if version:
            print(f"✅ Latest TrueNAS Scale version from GitHub: {version}")
        else:
            version = "25.04.1"
            print(f"⚠️ Falling back to version {version}")

        # Codename mapping (major.minor -> codename), extend as needed
        codenames = {
            '25.04': 'Fangtooth',
            '24.10': 'Electric-Eel',
            '24.04': 'Dragonfish',
        }
        major_minor = '.'.join(version.split('.')[:2])
        codename = codenames.get(major_minor, 'Fangtooth')

        url = f"{self.download_base}{codename}/{version}/TrueNAS-SCALE-{version}.iso"
        links = {'scale': url}

        verified_links = {}
        for variant, u in links.items():
            print(f"🔗 Checking {variant} URL...")
            if self.verify_download_url(u):
                verified_links[variant] = u
                print(f"✅ {variant.capitalize()} URL verified")
            else:
                print(f"⚠️ {variant.capitalize()} URL not verified (but may still work)")
                verified_links[variant] = u

        return verified_links


class Windows11Finder(BaseOSFinder):
    """Windows 11 download finder"""
    
    def __init__(self):
        super().__init__("Windows 11")
        self.download_url = "https://www.microsoft.com/software-download/windows11"
    
    def find_download_links(self) -> Dict[str, str]:
        """Find Windows 11 download links"""
        print(f"🔍 Finding {self.name} download links...")
        
        # Windows 11 requires Microsoft's media creation tool or direct ISO access
        links = {
            'media_creation_tool': "https://go.microsoft.com/fwlink/?linkid=2156295",
            'download_page': self.download_url
        }
        
        print("⚠️ Windows 11 ISOs require Microsoft account or media creation tool.")
        print("📎 Media Creation Tool and download page links provided.")
        
        return links


class ManjaroKDEFinder(BaseOSFinder):
    """Manjaro KDE download finder"""
    
    def __init__(self):
        super().__init__("Manjaro KDE")
        self.download_url = "https://manjaro.org/downloads/"
        self.api_url = "https://download.manjaro.org/kde/"
    
    def find_download_links(self) -> Dict[str, str]:
        """Find Manjaro KDE download links"""
        print(f"🔍 Finding {self.name} download links...")
        
        try:
            # Try the direct download directory
            response = self.session.get(self.api_url, timeout=15)
            response.raise_for_status()
            content = response.text
            
            links = {}
            
            # Look for latest version directory
            version_pattern = r'href="(\d+\.\d+\.\d+)/"'
            versions = re.findall(version_pattern, content)
            
            if versions:
                # Sort versions and get latest
                versions.sort(key=lambda x: tuple(map(int, x.split('.'))))
                latest_version = versions[-1]
                
                # Check the latest version directory for ISO
                version_url = f"{self.api_url}{latest_version}/"
                try:
                    version_response = self.session.get(version_url, timeout=10)
                    if version_response.status_code == 200:
                        version_content = version_response.text
                        iso_pattern = r'href="(manjaro[^"]*\.iso)"'
                        iso_match = re.search(iso_pattern, version_content, re.IGNORECASE)
                        if iso_match:
                            links['kde'] = urljoin(version_url, iso_match.group(1))
                except Exception:
                    pass
            
            # Manual fallback
            if not links:
                print("🔧 Using manual Manjaro KDE pattern...")
                links['download_page'] = self.download_url
                print("⚠️ Please visit the Manjaro downloads page for latest ISO.")
            
            verified_links = {}
            for variant, url in links.items():
                if url.endswith('.iso'):
                    print(f"🔗 Checking {variant} URL...")
                    if self.verify_download_url(url):
                        verified_links[variant] = url
                        print(f"✅ {variant.capitalize()} URL verified")
                    else:
                        print(f"⚠️ {variant.capitalize()} URL not verified (but may still work)")
                        verified_links[variant] = url
                else:
                    verified_links[variant] = url
            
            return verified_links
            
        except Exception as e:
            print(f"❌ Error finding Manjaro KDE links: {e}")
            return {'download_page': self.download_url}


class PuppyLinuxFinder(BaseOSFinder):
    """Puppy Linux download finder"""
    
    def __init__(self):
        super().__init__("Puppy Linux")
        self.download_url = "http://puppylinux-woof-ce.github.io/woof-CE/index.html#downloads"
        self.distro_url = "http://distro.ibiblio.org/puppylinux/"
    
    def find_download_links(self) -> Dict[str, str]:
        """Find Puppy Linux download links"""
        print(f"🔍 Finding {self.name} download links...")
        
        try:
            # Try to scrape the ibiblio mirror
            response = self.session.get(self.distro_url, timeout=15)
            response.raise_for_status()
            content = response.text
            
            links = {}
            
            # Look for recent puppy directories
            dir_pattern = r'href="(puppy[^"/]*/)"|href="([^"/]*puppy[^"/]*/)"'
            matches = re.findall(dir_pattern, content, re.IGNORECASE)
            
            puppy_dirs = []
            for match in matches:
                dirname = match[0] if match[0] else match[1]
                if dirname and 'puppy' in dirname.lower():
                    puppy_dirs.append(dirname)
            
            if puppy_dirs:
                # Try the first few directories for ISO files
                for dirname in puppy_dirs[:3]:
                    try:
                        dir_url = urljoin(self.distro_url, dirname)
                        dir_response = self.session.get(dir_url, timeout=10)
                        if dir_response.status_code == 200:
                            dir_content = dir_response.text
                            iso_pattern = r'href="([^"]*\.iso)"'
                            iso_matches = re.findall(iso_pattern, dir_content, re.IGNORECASE)
                            if iso_matches:
                                # Take the first ISO found
                                links[dirname.strip('/')] = urljoin(dir_url, iso_matches[0])
                                break
                    except Exception:
                        continue
            
            # Manual fallback
            if not links:
                print("🔧 Using Puppy Linux download page...")
                links['download_page'] = self.download_url
                print("⚠️ Please visit the Puppy Linux page for latest ISO.")
            
            verified_links = {}
            for variant, url in links.items():
                if url.endswith('.iso'):
                    print(f"🔗 Checking {variant} URL...")
                    if self.verify_download_url(url):
                        verified_links[variant] = url
                        print(f"✅ {variant.capitalize()} URL verified")
                    else:
                        print(f"⚠️ {variant.capitalize()} URL not verified (but may still work)")
                        verified_links[variant] = url
                else:
                    verified_links[variant] = url
            
            return verified_links
            
        except Exception as e:
            print(f"❌ Error finding Puppy Linux links: {e}")
            return {'download_page': self.download_url}


def _prompt_override_url(os_name: str, session: requests.Session) -> Optional[str]:
    """Interactively ask the user for a manual download URL."""
    print(f"\n💬 No valid ISO URL found for {os_name}.")
    try:
        url = input("   Enter an override URL (or press Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not url:
        return None

    if not url.startswith(("http://", "https://")):
        print("   ⚠️ URL must start with http:// or https:// — skipping.")
        return None

    print(f"   🔗 Verifying override URL...")
    try:
        r = session.head(url, timeout=10, allow_redirects=True)
        if r.status_code == 200:
            print(f"   ✅ Override URL verified.")
        else:
            print(f"   ⚠️ Server returned {r.status_code} — URL may still work.")
    except Exception as e:
        print(f"   ⚠️ Could not verify URL: {e}")

    return url


def _has_iso_link(links: Dict[str, str]) -> bool:
    """Return True if at least one link is a direct ISO (not just a download page)."""
    return any(
        url.lower().endswith(".iso") or url.lower().endswith(".iso.bz2")
        for url in links.values()
    )


class MultiOSDownloadFinder:
    """Main class for finding download links for multiple operating systems"""

    def __init__(self):
        self.finders = {
            'ubuntu': UbuntuLTSFinder(),
            'opensense': OpenSenseFinder(),
            'pfsense': PfSenseFinder(),
            'debian': DebianFinder(),
            'truenas': TrueNASFinder(),
            'windows11': Windows11Finder(),
            'manjaro': ManjaroKDEFinder(),
            'puppy': PuppyLinuxFinder()
        }

    def find_all_links(self, os_list: List[str] = None, interactive: bool = True) -> Dict[str, Dict[str, str]]:
        """Find download links for specified operating systems."""
        if os_list is None:
            os_list = list(self.finders.keys())

        all_links = {}

        for os_name in os_list:
            if os_name not in self.finders:
                print(f"⚠️ Unknown OS: {os_name}")
                continue

            print(f"\n{'='*50}")
            print(f"Processing: {self.finders[os_name].name}")
            print(f"{'='*50}")

            try:
                links = self.finders[os_name].find_download_links()
            except Exception as e:
                print(f"❌ Error processing {self.finders[os_name].name}: {e}")
                links = {}

            # Offer override if no direct ISO link was found
            if interactive and not _has_iso_link(links):
                override = _prompt_override_url(self.finders[os_name].name, _session)
                if override:
                    links['override'] = override

            if links:
                all_links[os_name] = links
                print(f"✅ Found {len(links)} link(s) for {self.finders[os_name].name}")
            else:
                print(f"❌ No links found for {self.finders[os_name].name}")

        return all_links
    
    def save_links_to_files(self, all_links: Dict[str, Dict[str, str]]):
        """Save download links to files"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Save comprehensive file
        try:
            with open('all_os_links.txt', 'w') as f:
                f.write(f"# Multi-OS Download Links\n")
                f.write(f"# Generated on: {timestamp}\n\n")
                
                for os_name, links in all_links.items():
                    f.write(f"# {self.finders[os_name].name}\n")
                    for variant, url in links.items():
                        f.write(f"# {variant.capitalize()}: {url}\n")
                    f.write("\n")
            
            print(f"💾 All links saved to: all_os_links.txt")
        except Exception as e:
            print(f"❌ Error saving comprehensive file: {e}")
        
        # Save Go-compatible file
        try:
            import os
            os.makedirs("./os-links", exist_ok=True)
            
            with open('./os-links/all_os.txt', 'w') as f:
                for os_name, links in all_links.items():
                    for variant, url in links.items():
                        if url.endswith('.iso') or 'iso' in url:
                            f.write(f"{url}\n")
            
            print(f"💾 ISO links saved to: ./os-links/all_os.txt")
            print("   (Compatible with the Python download manager)")
        except Exception as e:
            print(f"❌ Error saving Go-compatible file: {e}")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Multi-OS Download Link Finder')
    parser.add_argument('--os', nargs='+',
                        choices=['ubuntu', 'opensense', 'pfsense', 'debian', 'truenas', 'windows11', 'manjaro', 'puppy', 'all'],
                        default=['all'],
                        help='Operating systems to find download links for')
    parser.add_argument('--no-interactive', action='store_true',
                        help='Disable the override URL prompt when a link cannot be found')

    args = parser.parse_args()
    
    print("Multi-OS Download Link Finder")
    print("=" * 60)
    print("Supported OS: Ubuntu LTS, OpenSense, pfSense, Debian, TrueNAS Scale,")
    print("              Windows 11, Manjaro KDE, Puppy Linux")
    print("=" * 60)
    
    finder = MultiOSDownloadFinder()
    
    # Determine which OSes to process
    if 'all' in args.os:
        os_list = list(finder.finders.keys())
    else:
        os_list = args.os
    
    print(f"🎯 Processing: {', '.join(os_list)}")
    
    # Find all links
    all_links = finder.find_all_links(os_list, interactive=not args.no_interactive)
    
    if all_links:
        print(f"\n🎉 SUMMARY - Found links for {len(all_links)} operating system(s):")
        print("-" * 60)
        
        for os_name, links in all_links.items():
            print(f"\n{finder.finders[os_name].name}:")
            for variant, url in links.items():
                print(f"  {variant}: {url}")
        
        # Save to files
        print("\n" + "="*60)
        finder.save_links_to_files(all_links)
        
    else:
        print("❌ No download links found for any operating system")
        sys.exit(1)


if __name__ == "__main__":
    main() 