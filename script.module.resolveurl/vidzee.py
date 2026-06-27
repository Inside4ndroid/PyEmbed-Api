#!/usr/bin/env python3
"""
Vidzee Resolver - Standalone Version
Returns JSON with stream URL and headers
Based on VidzeeProvider.kt
Requires: pycryptodome (pip install pycryptodome)
"""

import re
import json
import time
import base64
import hashlib
import urllib.request
import urllib.error
import ssl
from urllib.parse import urlencode, urljoin

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad, unpad
except ImportError:
    raise ImportError("Please install pycryptodome: pip install pycryptodome")

__version__ = "1.0.1"

API_KEY_URL = "https://core.vidzee.wtf/api-key"
SERVER_BASE = "https://player.vidzee.wtf/api/server"
ENCRYPTION_KEY = "c4a8f1d7e2b9a6c3d0f5e8a1b7c4d9e2"
PLAYER_REFERER = "https://player.vidzee.wtf/"
PLAYER_ORIGIN = "https://player.vidzee.wtf"

ALL_SERVERS = [
    (0, "Togi"), (1, "Duke"), (2, "Nazi"), (3, "Achilles"),
    (4, "Nflix"), (5, "Drag"), (6, "Blaze"), (7, "Shadow"),
    (8, "Storm"), (9, "Vortex"), (10, "Phoenix"), (11, "Falcon"),
    (12, "Titan"), (13, "Zen")
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


class VidzeeResolver:
    def __init__(self, debug=False):
        self.debug = debug
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        self.cached_api_key = None

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

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

    def _head_url(self, url, headers=None):
        if headers is None:
            headers = {}
        default_headers = {
            'User-Agent': HEADERS['User-Agent'],
            'Referer': PLAYER_REFERER,
            'Origin': PLAYER_ORIGIN,
        }
        req_headers = {**default_headers, **headers}
        try:
            req = urllib.request.Request(url, method='HEAD', headers=req_headers)
            response = urllib.request.urlopen(req, timeout=10, context=self.ssl_context)
            status = response.status if hasattr(response, 'status') else 200
            return status not in (403, 404, 410, 500)
        except urllib.error.HTTPError as e:
            return e.code not in (403, 404, 410, 500)
        except Exception:
            return False

    def _decrypt_api_key(self, encrypted_base64: str) -> str:
        try:
            raw = base64.b64decode(encrypted_base64.replace("\\s+", ""))
            if len(raw) <= 28:
                self.log("Encrypted data too short", "ERROR")
                return ""
            iv = raw[:12]
            auth_tag = raw[12:28]
            ciphertext = raw[28:]
            key_hash = hashlib.sha256(ENCRYPTION_KEY.encode('utf-8')).digest()
            cipher = AES.new(key_hash, AES.MODE_GCM, nonce=iv)
            plaintext = cipher.decrypt_and_verify(ciphertext, auth_tag)
            return plaintext.decode('utf-8')
        except Exception as e:
            self.log(f"API key decryption failed: {e}", "ERROR")
            return ""

    def _decrypt_video_link(self, encrypted_link: str, api_key: str) -> str:
        try:
            decoded = base64.b64decode(encrypted_link).decode('utf-8')
            colon = decoded.find(':')
            if colon == -1:
                return ""
            iv_b64 = decoded[:colon]
            ciphertext_b64 = decoded[colon+1:]
            iv = base64.b64decode(iv_b64)
            ciphertext = base64.b64decode(ciphertext_b64)
            key_bytes = api_key.encode('utf-8')
            key_padded = key_bytes.ljust(32, b'\x00')[:32]
            cipher = AES.new(key_padded, AES.MODE_CBC, iv)
            plaintext_padded = cipher.decrypt(ciphertext)
            try:
                plaintext = unpad(plaintext_padded, AES.block_size).decode('utf-8')
            except ValueError:
                plaintext = plaintext_padded.decode('utf-8', errors='ignore')
            return plaintext
        except Exception as e:
            self.log(f"Video link decryption failed: {e}", "ERROR")
            return ""

    def _get_api_key(self):
        if self.cached_api_key:
            return self.cached_api_key
        self.log("Fetching encrypted API key...")
        success, content, error, status = self._fetch_url(API_KEY_URL, timeout=10)
        if not success:
            self.log(f"API key request failed: {error}", "ERROR")
            return None
        encrypted = content.strip()
        if not encrypted:
            self.log("API key request returned empty body", "ERROR")
            return None
        decrypted = self._decrypt_api_key(encrypted)
        if decrypted:
            self.cached_api_key = decrypted
            self.log("API key obtained successfully")
            return decrypted
        self.log("API key decryption failed", "ERROR")
        return None

    def _fetch_server_streams(self, server_idx, server_name, base_params, api_key):
        url = f"{SERVER_BASE}?{base_params}&sr={server_idx}"
        self.log(f"Fetching server {server_name} (sr={server_idx})...", "DEBUG")
        success, content, error, status = self._fetch_url(url, timeout=15)
        if not success:
            self.log(f"Server {server_name} failed: {error}", "WARNING")
            return []
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            self.log(f"Server {server_name} returned invalid JSON", "WARNING")
            return []

        if data.get('error'):
            self.log(f"Server {server_name} returned error: {data['error']}", "WARNING")
            return []

        url_entries = data.get('url')
        if not url_entries:
            return []

        streams = []
        for entry in url_entries:
            encrypted_link = entry.get('link')
            if not encrypted_link:
                continue
            decrypted = self._decrypt_video_link(encrypted_link, api_key)
            if not decrypted or not decrypted.startswith('http'):
                continue

            headers = data.get('headers') or {}
            if 'Referer' not in headers:
                headers['Referer'] = PLAYER_REFERER
            if 'Origin' not in headers:
                headers['Origin'] = PLAYER_ORIGIN
            if 'User-Agent' not in headers:
                headers['User-Agent'] = HEADERS['User-Agent']

            if not self._head_url(decrypted, headers):
                self.log(f"Server {server_name} URL not reachable: {decrypted[:60]}", "WARNING")
                continue

            stream_type = entry.get('type')
            if not stream_type:
                stream_type = 'hls' if '.m3u8' in decrypted else 'mp4'
            lang = entry.get('lang', 'eng')

            streams.append({
                'server': server_name,
                'url': decrypted,
                'quality': 'Auto',
                'type': stream_type,
                'headers': headers,
                'lang': lang,
            })
        return streams

    def resolve(self, url_or_id, media_type='movie', season=None, episode=None):
        self.log("=" * 80)
        self.log(f"Vidzee Resolver Started - {media_type}")

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

        api_key = self._get_api_key()
        if not api_key:
            return json.dumps({
                'status': 'error',
                'message': 'Failed to obtain API key'
            })

        base_params = f"id={tmdb_id}"
        if media_type == 'tv' and season is not None and episode is not None:
            base_params += f"&ss={season}&ep={episode}"

        self.log(f"Base parameters: {base_params}")

        all_streams = []
        for sr, name in ALL_SERVERS:
            streams = self._fetch_server_streams(sr, name, base_params, api_key)
            all_streams.extend(streams)

        if not all_streams:
            return json.dumps({
                'status': 'error',
                'message': 'No playable sources found from any server'
            })

        playable_urls = []
        for s in all_streams:
            playable_urls.append({
                'server': s['server'],
                'url': s['url'],
                'quality': s['quality'],
                'type': s['type'],
                'headers': s['headers'],
                'lang': s.get('lang'),
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

    parser = argparse.ArgumentParser(description='Vidzee Resolver')
    parser.add_argument('url_or_id', help='Vidzee URL or TMDB ID')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie', help='Media type (default: movie)')
    parser.add_argument('--season', type=int, help='Season number (for TV)')
    parser.add_argument('--episode', type=int, help='Episode number (for TV)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON output')

    args = parser.parse_args()

    resolver = VidzeeResolver(debug=args.debug)
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