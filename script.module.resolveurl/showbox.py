#!/usr/bin/env python3
"""
ShowBox Resolver - Standalone Version (Fixed FebBox Extraction)
"""

import re
import json
import base64
import urllib.parse
import requests
from bs4 import BeautifulSoup

try:
    from Crypto.Cipher import DES3
    from Crypto.Util.Padding import unpad
except ImportError:
    raise ImportError("Please install pycryptodome: pip install pycryptodome")

__version__ = "1.0.2"

TMDB_API_KEY = "439c478a771f35c05022f9feabcca01c"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
DEFAULT_API_BASE = "https://id-mapping-api-showbox-proxy.hf.space/api/media"

WORKING_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json"
}

DES_KEY = "123d6cedf626dy54233aa1w6"
DES_IV = "wEiphTn!"


class ShowBoxResolver:
    def __init__(self, debug=False, ui_cookie=None, oss_group=None, api_base=None):
        self.debug = debug
        self.ui_cookie = ui_cookie
        self.oss_group = oss_group
        self.api_base = api_base or DEFAULT_API_BASE
        self.session = requests.Session()

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    def _get_ui_token(self, raw_token):
        if not raw_token:
            return ""

        if raw_token.count('.') == 2:
            parts = raw_token.split('.')
            if len(parts) == 3:
                try:
                    payload = parts[1]
                    missing = len(payload) % 4
                    if missing:
                        payload += '=' * (4 - missing)
                    decoded = base64.b64decode(payload).decode('utf-8')
                    parsed = json.loads(decoded)
                    if parsed and parsed.get('data') and parsed['data'].get('uid'):
                        self.log(f"Valid JWT detected for UID: {parsed['data']['uid']}", "DEBUG")
                        return raw_token
                except Exception as e:
                    self.log(f"Failed to parse JWT payload: {e}", "DEBUG")

        if raw_token.startswith("eyJ") and '.' not in raw_token:
            self.log("Base64 JSON token detected. Attempting decryption...", "DEBUG")
            try:
                missing = len(raw_token) % 4
                if missing:
                    raw_token += '=' * (4 - missing)
                decoded_bytes = base64.b64decode(raw_token)
                decoded_str = decoded_bytes.decode('utf-8')
                parsed = json.loads(decoded_str)
                if parsed and parsed.get('encrypt_data'):
                    key_bytes = DES_KEY.encode('utf-8')
                    iv_bytes = DES_IV.encode('utf-8')
                    cipher = DES3.new(key_bytes, DES3.MODE_CBC, iv_bytes)
                    encrypted_data = base64.b64decode(parsed['encrypt_data'])
                    decrypted_padded = cipher.decrypt(encrypted_data)
                    try:
                        decrypted = unpad(decrypted_padded, DES3.block_size).decode('utf-8')
                    except ValueError:
                        decrypted = decrypted_padded.decode('utf-8', errors='ignore')
                    self.log(f"Decrypted successfully: {decrypted}", "DEBUG")
                    decrypted_json = json.loads(decrypted)
                    if decrypted_json and decrypted_json.get('uid'):
                        self.log(f"Extracted UID from payload: {decrypted_json['uid']}", "DEBUG")
                        return str(decrypted_json['uid'])
            except Exception as e:
                self.log(f"Failed to decrypt base64 uiToken: {e}", "DEBUG")

        return raw_token

    def _get_tmdb_details(self, tmdb_id, media_type):
        endpoint = "tv" if media_type == "tv" else "movie"
        url = f"{TMDB_BASE_URL}/{endpoint}/{tmdb_id}?api_key={TMDB_API_KEY}"
        try:
            resp = requests.get(url, headers={'Accept': 'application/json'}, timeout=10)
            if resp.status_code != 200:
                self.log(f"TMDB API error: {resp.status_code}", "ERROR")
                return {"title": f"TMDB ID {tmdb_id}", "year": None}
            data = resp.json()
            title = data.get('name') if media_type == 'tv' else data.get('title')
            release_date = data.get('first_air_date') if media_type == 'tv' else data.get('release_date')
            year = int(release_date.split('-')[0]) if release_date else None
            return {"title": title, "year": year}
        except Exception as e:
            self.log(f"TMDB fetch error: {e}", "ERROR")
            return {"title": f"TMDB ID {tmdb_id}", "year": None}

    def _get_quality_from_name(self, quality_str):
        if not quality_str:
            return "Unknown"
        quality = quality_str.upper()
        if quality in ("ORG", "ORIGINAL"):
            return "Original"
        if quality in ("4K", "2160P"):
            return "4K"
        if quality in ("1440P", "2K"):
            return "1440p"
        if quality in ("1080P", "FHD"):
            return "1080p"
        if quality in ("720P", "HD"):
            return "720p"
        if quality in ("480P", "SD"):
            return "480p"
        if quality == "360P":
            return "360p"
        if quality == "240P":
            return "240p"
        match = re.search(r'(\d{3,4})[pP]?', quality_str)
        if match:
            res = int(match.group(1))
            if res >= 2160:
                return "4K"
            if res >= 1440:
                return "1440p"
            if res >= 1080:
                return "1080p"
            if res >= 720:
                return "720p"
            if res >= 480:
                return "480p"
            if res >= 360:
                return "360p"
            return "240p"
        return "Unknown"

    def _format_file_size(self, size_str):
        if not size_str:
            return "Unknown"
        if isinstance(size_str, str) and ("GB" in size_str or "MB" in size_str or "KB" in size_str):
            return size_str
        if isinstance(size_str, (int, float)):
            gb = size_str / (1024**3)
            if gb >= 1:
                return f"{gb:.2f} GB"
            mb = size_str / (1024**2)
            return f"{mb:.2f} MB"
        return str(size_str)

    def _process_showbox_response(self, data, media_info, media_type, season_num, episode_num):
        streams = []
        if not data:
            return streams

        self.log(f"Raw proxy response: {json.dumps(data, indent=2) if self.debug else '...'}", "DEBUG")

        if data.get('success') is False:
            self.log("Proxy API returned success=false", "WARNING")
            return streams

        versions = None
        if 'versions' in data and isinstance(data['versions'], list):
            versions = data['versions']
        elif 'data' in data and isinstance(data['data'], dict) and 'versions' in data['data']:
            versions = data['data']['versions']
        elif 'result' in data and isinstance(data['result'], dict) and 'versions' in data['result']:
            versions = data['result']['versions']

        if not versions:
            self.log("No 'versions' found in proxy response", "WARNING")
            return streams

        if media_type == 'tv' and season_num is not None and episode_num is not None:
            stream_title = f"{media_info['title']} S{season_num:02d}E{episode_num:02d}"
            if media_info.get('year'):
                stream_title += f" ({media_info['year']})"
        else:
            stream_title = media_info['title'] or "Unknown Title"
            if media_info.get('year'):
                stream_title += f" ({media_info['year']})"

        for vidx, version in enumerate(versions, 1):
            version_name = version.get('name', f"Version {vidx}")
            version_size = version.get('size', "Unknown")
            links = version.get('links', [])
            for link in links:
                url = link.get('url')
                if not url:
                    continue
                quality = self._get_quality_from_name(link.get('quality', 'Unknown'))
                size = link.get('size') or version_size
                stream_name = "ShowBox"
                if len(versions) > 1:
                    stream_name += f" V{vidx}"
                stream_name += f" {quality}"
                streams.append({
                    'name': stream_name,
                    'title': stream_title,
                    'url': url,
                    'quality': quality,
                    'size': self._format_file_size(size),
                    'provider': 'showbox',
                })
        return streams

    def _extract_febbox_share(self, showbox_id, media_type, season_num, episode_num, ui_token):
        streams = []
        try:
            box_type = 2 if media_type == 'tv' else 1
            share_url = f"https://www.febbox.com/mbp/to_share_page?box_type={box_type}&mid={showbox_id}&json=1"
            self.log(f"Requesting FebBox share link: {share_url}", "DEBUG")
            resp = requests.get(share_url, headers=WORKING_HEADERS, timeout=15)
            if resp.status_code != 200:
                self.log(f"FebBox share page returned status {resp.status_code}", "WARNING")
                return streams
            share_data = resp.json()
            if share_data.get('code') != 1 or not share_data.get('data'):
                self.log("FebBox share page returned error or no data", "WARNING")
                return streams
            share_link = share_data['data'].get('share_link') or share_data['data'].get('shareLink')
            if not share_link:
                return streams
            share_key = share_link.split('/')[-1]
            self.log(f"Resolved FebBox Share Key: {share_key}", "DEBUG")

            cookie = f"ui={ui_token}" if not ui_token.startswith("ui=") else ui_token

            list_url = f"https://www.febbox.com/file/file_share_list?share_key={share_key}"
            headers = WORKING_HEADERS.copy()
            headers['Accept-Language'] = 'en'
            headers['Cookie'] = cookie
            self.log(f"Fetching file list: {list_url}", "DEBUG")
            resp = requests.get(list_url, headers=headers, timeout=15)
            if resp.status_code != 200:
                self.log(f"FebBox list API returned {resp.status_code}", "WARNING")
                return streams
            list_data = resp.json()
            if self.debug:
                self.log(f"File list response: {json.dumps(list_data, indent=2)}", "DEBUG")
            if list_data.get('code') != 1 or not list_data.get('data') or not list_data['data'].get('file_list'):
                self.log("FebBox list API returned no files", "WARNING")
                return streams

            file_list = list_data['data']['file_list']
            target_files = []

            if media_type == 'movie':
                target_files = file_list
                self.log(f"Found {len(target_files)} files in share", "DEBUG")
            else:
                season_name = f"season {season_num}"
                season_folder = None
                for f in file_list:
                    if f.get('file_name') and f['file_name'].lower() == season_name:
                        season_folder = f
                        break
                if not season_folder:
                    self.log(f"Season folder not found: {season_name}", "WARNING")
                    return streams
                season_list_url = f"https://www.febbox.com/file/file_share_list?share_key={share_key}&parent_id={season_folder['fid']}&page=1"
                self.log(f"Fetching season list: {season_list_url}", "DEBUG")
                resp = requests.get(season_list_url, headers=headers, timeout=15)
                if resp.status_code != 200:
                    self.log(f"FebBox season list API returned {resp.status_code}", "WARNING")
                    return streams
                season_data = resp.json()
                if season_data.get('code') != 1 or not season_data.get('data') or not season_data['data'].get('file_list'):
                    self.log("FebBox season list API returned no files", "WARNING")
                    return streams
                episode_files = season_data['data']['file_list']
                season_slug = f"{season_num:02d}"
                episode_slug = f"{episode_num:02d}"
                target_files = [
                    f for f in episode_files
                    if f.get('file_name') and (
                        f['file_name'].lower().find(f"s{season_slug}e{episode_slug}") != -1 or
                        f['file_name'].lower().find(f"s{season_num}e{episode_num}") != -1
                    )
                ]
                self.log(f"Found {len(target_files)} matching episode files", "DEBUG")

            if not target_files:
                self.log("No matching files found in FebBox share", "WARNING")
                return streams

            video_headers = {
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.8",
                "Connection": "keep-alive",
                "Range": "bytes=0-",
                "Referer": "https://www.febbox.com/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Cookie": cookie
            }

            for file_item in target_files:
                fid = file_item.get('fid')
                if not fid:
                    continue
                quality_url = f"https://www.febbox.com/console/video_quality_list?fid={fid}&share_key={share_key}"
                self.log(f"Fetching quality list for fid {fid}: {quality_url}", "DEBUG")
                resp = requests.get(quality_url, headers=video_headers, timeout=15)
                if resp.status_code != 200:
                    self.log(f"Failed to fetch qualities for file {file_item.get('file_name')}: {resp.status_code}", "WARNING")
                    if self.debug:
                        self.log(f"Response: {resp.text[:500]}", "DEBUG")
                    continue
                try:
                    # Parse JSON response
                    quality_json = resp.json()
                    if quality_json.get('code') != 1:
                        self.log(f"Quality API returned error: {quality_json.get('msg', 'Unknown')}", "WARNING")
                        continue
                    html_content = quality_json.get('html', '')
                    if not html_content:
                        self.log("No HTML content in quality response", "WARNING")
                        continue
                    if self.debug:
                        self.log(f"Quality HTML (first 500 chars): {html_content[:500]}", "DEBUG")
                    
                    # Parse the HTML string with BeautifulSoup
                    soup = BeautifulSoup(html_content, 'html.parser')
                    quality_divs = soup.select('div.file_quality')
                    self.log(f"Found {len(quality_divs)} quality divs", "DEBUG")
                    for div in quality_divs:
                        stream_url = div.get('data-url')
                        quality_label = div.get('data-quality')
                        # Extract size from the div
                        size_span = div.find('span', class_='size')
                        size_text = size_span.get_text(strip=True) if size_span else file_item.get('file_size', 'Unknown')
                        if stream_url:
                            quality = self._get_quality_from_name(quality_label)
                            self.log(f"Extracted stream: {quality} - {stream_url[:100]}...", "DEBUG")
                            streams.append({
                                'name': f"ShowBox FebBox [{quality}]",
                                'title': file_item.get('file_name', 'Unknown'),
                                'url': stream_url,
                                'quality': quality,
                                'size': size_text,
                                'headers': {
                                    "Accept": "*/*",
                                    "Accept-Language": "en-US,en;q=0.8",
                                    "Connection": "keep-alive",
                                    "Range": "bytes=0-",
                                    "Referer": "https://www.febbox.com/",
                                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                                },
                                'provider': 'showbox'
                            })
                except Exception as e:
                    self.log(f"Error parsing quality response: {e}", "WARNING")
                    if self.debug:
                        import traceback
                        self.log(traceback.format_exc(), "DEBUG")
                    continue

        except Exception as e:
            self.log(f"FebBox share extraction error: {e}", "ERROR")
            if self.debug:
                import traceback
                self.log(traceback.format_exc(), "DEBUG")
        return streams

    def resolve(self, url_or_id, media_type='movie', season=None, episode=None):
        self.log("=" * 80)
        self.log(f"ShowBox Resolver Started - {media_type} ID: {url_or_id}")

        if not self.ui_cookie:
            return json.dumps({
                'status': 'error',
                'message': 'UI token (cookie) is required. Provide via --ui-cookie parameter.'
            })

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

        ui_token = self._get_ui_token(self.ui_cookie)
        if not ui_token:
            return json.dumps({
                'status': 'error',
                'message': 'Invalid UI token provided. Could not extract valid token.'
            })
        self.log(f"Processed UI token: {ui_token[:30]}...", "DEBUG")

        media_info = self._get_tmdb_details(tmdb_id, media_type)
        self.log(f"Title: {media_info['title']}, Year: {media_info.get('year', 'N/A')}")

        all_streams = []
        showbox_id = None

        # Try proxy API
        try:
            if media_type == 'tv' and season is not None and episode is not None:
                if self.oss_group:
                    proxy_url = f"{self.api_base}/tv/{tmdb_id}/oss={self.oss_group}/{season}/{episode}?cookie={urllib.parse.quote(ui_token)}"
                else:
                    proxy_url = f"{self.api_base}/tv/{tmdb_id}/{season}/{episode}?cookie={urllib.parse.quote(ui_token)}"
            else:
                proxy_url = f"{self.api_base}/movie/{tmdb_id}?cookie={urllib.parse.quote(ui_token)}"

            self.log(f"Querying proxy API: {proxy_url}")
            resp = requests.get(proxy_url, headers=WORKING_HEADERS, timeout=30)
            self.log(f"Proxy API status: {resp.status_code}", "DEBUG")
            if resp.status_code == 200:
                data = resp.json()
                self.log(f"Proxy API response keys: {list(data.keys())}", "DEBUG")
                streams = self._process_showbox_response(data, media_info, media_type, season, episode)
                if streams:
                    self.log(f"Proxy API returned {len(streams)} streams", "INFO")
                    all_streams.extend(streams)
                showbox_id = data.get('id') or data.get('mid')
                if not showbox_id and data.get('data'):
                    showbox_id = data['data'].get('id') or data['data'].get('mid')
                if showbox_id:
                    self.log(f"Extracted ShowBox ID: {showbox_id}", "INFO")
                else:
                    self.log("No ShowBox ID found in proxy response", "WARNING")
            else:
                self.log(f"Proxy API returned status {resp.status_code}", "WARNING")
        except Exception as e:
            self.log(f"Proxy API error: {e}", "WARNING")

        # Try FebBox share extraction
        if showbox_id:
            self.log(f"Attempting FebBox share extraction for ID: {showbox_id}")
            feb_streams = self._extract_febbox_share(showbox_id, media_type, season, episode, ui_token)
            if feb_streams:
                self.log(f"Found {len(feb_streams)} streams from FebBox share", "INFO")
                all_streams.extend(feb_streams)

        if not all_streams:
            return json.dumps({
                'status': 'error',
                'message': 'No playable sources found'
            })

        quality_order = {
            "Original": 6,
            "4K": 5,
            "1440p": 4,
            "1080p": 3,
            "720p": 2,
            "480p": 1,
            "360p": 0,
            "240p": -1,
            "Unknown": -2
        }
        all_streams.sort(key=lambda s: quality_order.get(s.get('quality', 'Unknown'), -2), reverse=True)

        playable_urls = []
        for s in all_streams:
            url = s['url']
            if '.m3u8' in url.lower():
                stream_type = 'hls'
            elif '.mpd' in url.lower():
                stream_type = 'dash'
            elif '.mp4' in url.lower() or '.mkv' in url.lower():
                stream_type = 'mp4'
            else:
                stream_type = 'hls'

            headers = s.get('headers', {})
            if not headers:
                headers = {
                    'User-Agent': WORKING_HEADERS['User-Agent'],
                    'Accept': '*/*',
                    'Referer': 'https://www.febbox.com/'
                }

            playable_urls.append({
                'url': url,
                'quality': s.get('quality', 'Unknown'),
                'type': stream_type,
                'headers': headers,
                'server': 'ShowBox',
                'size': s.get('size', 'Unknown'),
            })

        response = {
            'status': 'success',
            'tmdb_id': tmdb_id,
            'playable_urls': playable_urls
        }

        self.log("=" * 80)
        self.log("RESOLUTION COMPLETE")
        self.log(f"Found {len(playable_urls)} playable sources")
        return json.dumps(response, indent=2)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='ShowBox Resolver')
    parser.add_argument('url_or_id', help='TMDB ID or URL')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie', help='Media type (default: movie)')
    parser.add_argument('--season', type=int, help='Season number (for TV)')
    parser.add_argument('--episode', type=int, help='Episode number (for TV)')
    parser.add_argument('--ui-cookie', required=True, help='FebBox UI token (cookie value)')
    parser.add_argument('--oss-group', help='Optional OSS group parameter')
    parser.add_argument('--api-base', default=DEFAULT_API_BASE, help='Custom API base URL')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON output')

    args = parser.parse_args()

    resolver = ShowBoxResolver(
        debug=args.debug,
        ui_cookie=args.ui_cookie,
        oss_group=args.oss_group,
        api_base=args.api_base
    )
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