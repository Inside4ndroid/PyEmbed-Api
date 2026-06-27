#!/usr/bin/env python3
"""
Vidrock Resolver - Standalone Version
Returns JSON with stream URL and headers
Based on VidrockProvider.kt
Requires: pycryptodome (pip install pycryptodome)
"""

import re
import json
import time
import base64
import urllib.request
import urllib.error
import ssl
from urllib.parse import urljoin, urlencode

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
except ImportError:
    raise ImportError("Please install pycryptodome: pip install pycryptodome")

__version__ = "1.0.1"

DOMAIN = "https://vidrock.net"
PASSPHRASE = "x7k9mPqT2rWvY8zA5bC3nF6hJ2lK4mN9"
BLOCKED_DOMAIN = "binge.vaporeen.workers.dev"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


class VidrockResolver:
    def __init__(self, debug=False):
        self.debug = debug
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    def _encrypt_and_encode(self, data: str) -> str:
        key = PASSPHRASE.encode('utf-8')
        iv = key[:16]
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded_data = pad(data.encode('utf-8'), AES.block_size)
        encrypted = cipher.encrypt(padded_data)
        return base64.urlsafe_b64encode(encrypted).decode('utf-8').rstrip('=')

    def _fetch_url(self, url, headers=None, timeout=15, method='GET', data=None, json_data=None):
        if headers is None:
            headers = HEADERS.copy()
        if json_data:
            data = json.dumps(json_data).encode('utf-8')
            headers['Content-Type'] = 'application/json'
            method = 'POST'
        elif data and isinstance(data, dict):
            data = urlencode(data).encode('utf-8')
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        if url.startswith('/'):
            url = urljoin(DOMAIN, url)
        try:
            req = urllib.request.Request(url, headers=headers, data=data, method=method)
            response = urllib.request.urlopen(req, timeout=timeout, context=self.ssl_context)
            content = response.read().decode('utf-8', errors='ignore')
            status = response.status if hasattr(response, 'status') else 200
            return True, content, None, status
        except urllib.error.HTTPError as e:
            return False, None, f"HTTP Error {e.code}: {e.reason}", e.code
        except urllib.error.URLError as e:
            return False, None, f"URL Error: {str(e)}", None
        except Exception as e:
            return False, None, f"Error: {str(e)}", None

    def _head_url(self, url):
        headers = {
            'Referer': DOMAIN,
            'Origin': DOMAIN,
            'User-Agent': HEADERS['User-Agent'],
        }
        try:
            req = urllib.request.Request(url, method='HEAD', headers=headers)
            response = urllib.request.urlopen(req, timeout=10, context=self.ssl_context)
            status = response.status if hasattr(response, 'status') else 200
            return status not in (403, 404, 410, 429, 500)
        except urllib.error.HTTPError as e:
            return e.code not in (403, 404, 410, 429, 500)
        except Exception:
            return False

    def _resolve_json_playlist(self, url):
        try:
            headers = {
                'Referer': DOMAIN,
                'Origin': DOMAIN,
                'User-Agent': HEADERS['User-Agent'],
                'Accept': 'application/json',
            }
            req = urllib.request.Request(url, headers=headers)
            response = urllib.request.urlopen(req, timeout=15, context=self.ssl_context)
            content = response.read().decode('utf-8', errors='ignore')
            content_type = response.headers.get('Content-Type', '')
            if not content.strip().startswith('[') or 'json' not in content_type.lower():
                return None
            data = json.loads(content)
            if not isinstance(data, list):
                return None
            best = None
            best_res = -1
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                url_val = entry.get('url')
                if not url_val or not isinstance(url_val, str):
                    continue
                res = entry.get('resolution')
                try:
                    res_int = int(res) if res is not None else 0
                except (ValueError, TypeError):
                    res_int = 0
                if res_int > best_res:
                    best_res = res_int
                    best = url_val
            if best:
                self.log(f"JSON playlist resolved to {best_res}p: {best[:80]}", "DEBUG")
            return best
        except Exception as e:
            self.log(f"JSON playlist resolution failed: {e}", "DEBUG")
            return None

    def resolve(self, url_or_id, media_type='movie', season=None, episode=None):
        self.log("=" * 80)
        self.log(f"Vidrock Resolver Started - {media_type}")

        # Extract TMDB ID from URL if needed
        if url_or_id.startswith('http'):
            match = re.search(r'/(?:movie|tv)/(\d+)', url_or_id)
            if match:
                tmdb_id = match.group(1)
                if '/tv/' in url_or_id:
                    media_type = 'tv'
                    se_match = re.search(r'/tv/\d+/(\d+)/(\d+)', url_or_id)
                    if se_match:
                        season = int(se_match.group(1))
                        episode = int(se_match.group(2))
            else:
                return json.dumps({
                    'status': 'error',
                    'message': 'Could not extract TMDB ID from URL'
                })
        else:
            tmdb_id = url_or_id

        self.log(f"TMDB ID: {tmdb_id}")
        self.log(f"Content Type: {'TV Show' if media_type == 'tv' else 'Movie'}")
        if media_type == 'tv':
            self.log(f"Season: {season}, Episode: {episode}")

        # Build item ID
        if media_type == 'tv' and season is not None and episode is not None:
            item_id = f"{tmdb_id}_{season}_{episode}"
        else:
            item_id = tmdb_id

        encrypted = self._encrypt_and_encode(item_id)
        self.log(f"Encrypted item ID: {encrypted}")

        api_url = f"{DOMAIN}/api/{media_type}/{encrypted}"
        self.log(f"Fetching API: {api_url}")

        success, content, error, status = self._fetch_url(api_url, timeout=15)
        if not success:
            return json.dumps({
                'status': 'error',
                'message': f'API request failed: {error}'
            })

        try:
            sources = json.loads(content)
        except json.JSONDecodeError as e:
            return json.dumps({
                'status': 'error',
                'message': f'Invalid JSON from API: {str(e)}'
            })

        if not isinstance(sources, dict):
            return json.dumps({
                'status': 'error',
                'message': f'Unexpected response format: {type(sources).__name__}'
            })

        self.log(f"Found {len(sources)} servers: {list(sources.keys())}")

        playable_urls = []
        for server_name, server_data in sources.items():
            if not isinstance(server_data, dict):
                continue
            url = server_data.get('url')
            if not url or url == "null":
                self.log(f"SKIP {server_name}: null/empty url", "DEBUG")
                continue
            if not url.startswith('http'):
                self.log(f"SKIP {server_name}: not http ({url})", "DEBUG")
                continue
            if BLOCKED_DOMAIN in url:
                self.log(f"SKIP {server_name}: blocked domain", "DEBUG")
                continue

            if not self._head_url(url):
                self.log(f"SKIP {server_name}: HEAD check failed", "DEBUG")
                continue

            resolved = self._resolve_json_playlist(url)
            final_url = resolved if resolved else url

            combined = f"{final_url} {server_name}".lower()
            if "4k" in combined or "2160" in combined:
                quality = "4K"
            elif "1080" in combined or "fhd" in combined:
                quality = "1080p"
            elif "720" in combined:
                quality = "720p"
            elif "480" in combined or "sd" in combined:
                quality = "480p"
            elif "360" in combined:
                quality = "360p"
            else:
                quality = "HD"

            stream_type = "hls" if ".m3u8" in final_url.lower() else "mp4" if ".mp4" in final_url.lower() else "hls"

            headers = {
                "Referer": DOMAIN,
                "Origin": DOMAIN,
                "User-Agent": HEADERS['User-Agent'],
            }

            playable_urls.append({
                'server': server_name,
                'url': final_url,
                'quality': quality,
                'type': stream_type,
                'headers': headers,
            })
            self.log(f"PASS {server_name}: {final_url[:80]}", "DEBUG")

        if not playable_urls:
            return json.dumps({
                'status': 'error',
                'message': 'No playable sources found'
            })

        response = {
            'status': 'success',
            'tmdb_id': tmdb_id,
            'playable_urls': playable_urls,
        }

        self.log("=" * 80)
        self.log("RESOLUTION COMPLETE")
        self.log(f"Found {len(playable_urls)} playable sources")
        return json.dumps(response, indent=2)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Vidrock Resolver')
    parser.add_argument('url_or_id', help='Vidrock URL or TMDB ID')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie', help='Media type (default: movie)')
    parser.add_argument('--season', type=int, help='Season number (for TV)')
    parser.add_argument('--episode', type=int, help='Episode number (for TV)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON output')

    args = parser.parse_args()

    resolver = VidrockResolver(debug=args.debug)
    result_json = resolver.resolve(
        args.url_or_id,
        media_type=args.type,
        season=args.season,
        episode=args.episode
    )

    if args.pretty:
        try:
            data = json.loads(result_json)
            print(json.dumps(data, indent=2))
        except:
            print(result_json)
    else:
        print(result_json)


if __name__ == "__main__":
    main()