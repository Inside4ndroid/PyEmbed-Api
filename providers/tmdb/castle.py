#!/usr/bin/env python3
"""
Castle Resolver - Standalone Version
Supports both movies and TV shows.
Returns JSON with stream URL and headers (subtitles omitted).
Based on castle.js (built from src/castle/)
Requires: pycryptodome (pip install pycryptodome), requests
"""

import re
import json
import time
import base64
import hashlib
import urllib.request
import urllib.error
import ssl
from urllib.parse import urljoin, urlencode, quote
import requests

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
except ImportError:
    raise ImportError("Please install pycryptodome: pip install pycryptodome")

__version__ = "1.0.1"

# Constants from castle.js
TMDB_API_KEY = "439c478a771f35c05022f9feabcca01c"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
CASTLE_BASE = "https://api.hlowb.com"
PKG = "com.external.castle"
CHANNEL = "IndiaA"
CLIENT = "1"
LANG = "en-US"
CASTLE_SUFFIX = "T!BgJB"

API_HEADERS = {
    "User-Agent": "okhttp/4.9.3",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "Keep-Alive",
    "Referer": CASTLE_BASE,
}

PLAYBACK_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Accept": "video/webm,video/ogg,video/*;q=0.9,application/ogg;q=0.7,audio/*;q=0.6,*/*;q=0.5",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "video",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "cross-site",
    "DNT": "1",
}


class CastleResolver:
    def __init__(self, debug=False):
        self.debug = debug
        self.session = requests.Session()
        self.session.headers.update(API_HEADERS)

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    def _fetch_url(self, url, method='GET', headers=None, json_data=None, timeout=30):
        if headers is None:
            headers = API_HEADERS.copy()
        try:
            if method.upper() == 'GET':
                resp = self.session.get(url, headers=headers, timeout=timeout)
            else:
                resp = self.session.post(url, headers=headers, json=json_data, timeout=timeout)
            if resp.status_code >= 400:
                return False, None, f"HTTP Error {resp.status_code}: {resp.text[:100]}"
            return True, resp, None
        except Exception as e:
            return False, None, str(e)

    def _decrypt_castle(self, encrypted_b64, security_key_b64):
        try:
            security_bytes = base64.b64decode(security_key_b64)
            suffix = CASTLE_SUFFIX.encode('utf-8')
            combined = security_bytes + suffix

            if len(combined) < 16:
                combined += b'\x00' * (16 - len(combined))
            elif len(combined) > 16:
                combined = combined[:16]

            key = combined
            iv = key

            ciphertext = base64.b64decode(encrypted_b64)
            cipher = AES.new(key, AES.MODE_CBC, iv)
            decrypted_padded = cipher.decrypt(ciphertext)

            try:
                decrypted = unpad(decrypted_padded, AES.block_size).decode('utf-8')
            except ValueError:
                decrypted = decrypted_padded.decode('utf-8', errors='ignore')
            return decrypted
        except Exception as e:
            self.log(f"Decryption failed: {e}", "ERROR")
            raise

    def _extract_cipher_from_response(self, response):
        try:
            data = response.json()
            if data and isinstance(data, dict) and data.get('data'):
                if isinstance(data['data'], str):
                    return data['data'].strip()
                else:
                    return json.dumps(data['data'])
            else:
                return response.text.strip()
        except:
            return response.text.strip()

    def _extract_data_block(self, obj):
        if obj and isinstance(obj, dict) and 'data' in obj:
            return obj['data']
        return obj

    def _get_tmdb_details(self, tmdb_id, media_type):
        endpoint = "tv" if media_type == "tv" else "movie"
        url = f"{TMDB_BASE_URL}/{endpoint}/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=external_ids"
        try:
            resp = requests.get(url, headers={'Accept': 'application/json'}, timeout=10)
            if resp.status_code != 200:
                self.log(f"TMDB API error: {resp.status_code}", "ERROR")
                return None
            data = resp.json()
            title = data.get('name') if media_type == 'tv' else data.get('title')
            release_date = data.get('first_air_date') if media_type == 'tv' else data.get('release_date')
            year = int(release_date.split('-')[0]) if release_date else None
            return {'title': title, 'year': year}
        except Exception as e:
            self.log(f"TMDB fetch error: {e}", "ERROR")
            return None

    def _get_security_key(self):
        url = f"{CASTLE_BASE}/v0.1/system/getSecurityKey/1?channel={CHANNEL}&clientType={CLIENT}&lang={LANG}"
        self.log(f"Fetching security key from {url}", "DEBUG")
        success, resp, err = self._fetch_url(url)
        if not success:
            raise Exception(f"Security key request failed: {err}")
        try:
            data = resp.json()
            if data.get('code') != 200 or not data.get('data'):
                raise Exception(f"Security key API error: {data}")
            return data['data']
        except Exception as e:
            raise Exception(f"Failed to parse security key: {e}")

    def _search_castle(self, security_key, keyword, page=1, size=30):
        params = {
            'channel': CHANNEL,
            'clientType': CLIENT,
            'keyword': keyword,
            'lang': LANG,
            'mode': '1',
            'packageName': PKG,
            'page': str(page),
            'size': str(size),
        }
        url = f"{CASTLE_BASE}/film-api/v1.1.0/movie/searchByKeyword?{urlencode(params)}"
        self.log(f"Searching Castle: {keyword}", "DEBUG")
        success, resp, err = self._fetch_url(url)
        if not success:
            raise Exception(f"Search request failed: {err}")
        cipher = self._extract_cipher_from_response(resp)
        decrypted = self._decrypt_castle(cipher, security_key)
        return json.loads(decrypted)

    def _get_details(self, security_key, movie_id):
        url = f"{CASTLE_BASE}/film-api/v1.9.9/movie?channel={CHANNEL}&clientType={CLIENT}&lang={LANG}&movieId={movie_id}&packageName={PKG}"
        self.log(f"Fetching details for movieId: {movie_id}", "DEBUG")
        success, resp, err = self._fetch_url(url)
        if not success:
            raise Exception(f"Details request failed: {err}")
        cipher = self._extract_cipher_from_response(resp)
        decrypted = self._decrypt_castle(cipher, security_key)
        return json.loads(decrypted)

    def _get_video_v1(self, security_key, movie_id, episode_id, language_id, resolution=2):
        url = f"{CASTLE_BASE}/film-api/v2.0.1/movie/getVideo2?clientType={CLIENT}&packageName={PKG}&channel={CHANNEL}&lang={LANG}"
        body = {
            "mode": "1",
            "appMarket": "GuanWang",
            "clientType": CLIENT,
            "woolUser": "false",
            "apkSignKey": "ED0955EB04E67A1D9F3305B95454FED485261475",
            "androidVersion": "13",
            "movieId": str(movie_id),
            "episodeId": str(episode_id),
            "languageId": str(language_id),
            "isNewUser": "true",
            "resolution": str(resolution),
            "packageName": PKG,
        }
        self.log(f"Fetching video (v1) for movieId: {movie_id}, languageId: {language_id}", "DEBUG")
        success, resp, err = self._fetch_url(url, method='POST', json_data=body)
        if not success:
            raise Exception(f"Video v1 request failed: {err}")
        cipher = self._extract_cipher_from_response(resp)
        decrypted = self._decrypt_castle(cipher, security_key)
        return json.loads(decrypted)

    def _get_video_v2(self, security_key, movie_id, episode_id, resolution=2):
        url = f"{CASTLE_BASE}/film-api/v2.0.1/movie/getVideo2?clientType={CLIENT}&packageName={PKG}&channel={CHANNEL}&lang={LANG}"
        body = {
            "mode": "1",
            "appMarket": "GuanWang",
            "clientType": CLIENT,
            "woolUser": "false",
            "apkSignKey": "ED0955EB04E67A1D9F3305B95454FED485261475",
            "androidVersion": "13",
            "movieId": str(movie_id),
            "episodeId": str(episode_id),
            "isNewUser": "true",
            "resolution": str(resolution),
            "packageName": PKG,
        }
        self.log(f"Fetching video (v2) for movieId: {movie_id}, episodeId: {episode_id}", "DEBUG")
        success, resp, err = self._fetch_url(url, method='POST', json_data=body)
        if not success:
            raise Exception(f"Video v2 request failed: {err}")
        cipher = self._extract_cipher_from_response(resp)
        decrypted = self._decrypt_castle(cipher, security_key)
        return json.loads(decrypted)

    def _find_castle_movie_id(self, security_key, tmdb_info):
        search_term = f"{tmdb_info['title']} {tmdb_info['year']}" if tmdb_info.get('year') else tmdb_info['title']
        search_result = self._search_castle(security_key, search_term)
        data = self._extract_data_block(search_result)
        rows = data.get('rows', [])
        if not rows:
            raise Exception("No search results found")

        tmdb_title_lower = tmdb_info['title'].lower()
        for item in rows:
            item_title = (item.get('title') or item.get('name') or '').lower()
            if tmdb_title_lower in item_title or item_title in tmdb_title_lower:
                movie_id = item.get('id') or item.get('redirectId') or item.get('redirectIdStr')
                if movie_id:
                    self.log(f"Found match: {item.get('title') or item.get('name')} (id: {movie_id})")
                    return str(movie_id)

        first = rows[0]
        movie_id = first.get('id') or first.get('redirectId') or first.get('redirectIdStr')
        if movie_id:
            self.log(f"Using first result: {first.get('title') or first.get('name')} (id: {movie_id})")
            return str(movie_id)

        raise Exception("Could not extract movie ID from search results")

    def _process_video_response(self, video_data, tmdb_info, season_num, episode_num, resolution, language_info):
        streams = []
        data = self._extract_data_block(video_data)
        video_url = data.get('videoUrl')
        if not video_url:
            self.log("No videoUrl found in response", "WARNING")
            return streams

        # Media title
        if season_num and episode_num:
            media_title = f"{tmdb_info['title']} S{season_num:02d}E{episode_num:02d}"
        else:
            media_title = f"{tmdb_info['title']} ({tmdb_info['year']})" if tmdb_info.get('year') else tmdb_info['title']

        quality_map = {1: "480p", 2: "720p", 3: "1080p"}
        base_quality = quality_map.get(resolution, f"{resolution}p")

        if data.get('videos') and isinstance(data['videos'], list):
            for video in data['videos']:
                video_quality = video.get('resolutionDescription') or video.get('resolution') or base_quality
                video_quality = re.sub(r'^(SD|HD|FHD)\s+', '', video_quality)
                stream_name = f"Castle {language_info} - {video_quality}" if language_info else f"Castle - {video_quality}"
                video_url_final = video.get('url') or video_url
                streams.append({
                    'name': stream_name,
                    'title': media_title,
                    'url': video_url_final,
                    'quality': video_quality,
                    'size': self._format_size(video.get('size')),
                    'headers': PLAYBACK_HEADERS,
                    'provider': 'castle',
                })
        else:
            stream_name = f"Castle {language_info} - {base_quality}" if language_info else f"Castle - {base_quality}"
            streams.append({
                'name': stream_name,
                'title': media_title,
                'url': video_url,
                'quality': base_quality,
                'size': self._format_size(data.get('size')),
                'headers': PLAYBACK_HEADERS,
                'provider': 'castle',
            })

        return streams

    def _format_size(self, size_value):
        if not isinstance(size_value, (int, float)) or size_value <= 0:
            return "Unknown"
        if size_value > 1e9:
            return f"{size_value / 1e9:.2f} GB"
        return f"{size_value / 1e6:.0f} MB"

    def resolve(self, url_or_id, media_type='movie', season=None, episode=None):
        self.log("=" * 80)
        self.log(f"Castle Resolver Started - {media_type} ID: {url_or_id}")

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

        try:
            tmdb_info = self._get_tmdb_details(tmdb_id, media_type)
            if not tmdb_info:
                raise Exception("Failed to get TMDB details")
            self.log(f"TMDB Info: {tmdb_info['title']} ({tmdb_info.get('year', 'N/A')})")

            security_key = self._get_security_key()
            self.log("Security key obtained")

            movie_id = self._find_castle_movie_id(security_key, tmdb_info)
            self.log(f"Castle movie ID: {movie_id}")

            details = self._get_details(security_key, movie_id)
            current_movie_id = movie_id

            if media_type == 'tv' and season is not None:
                data = self._extract_data_block(details)
                seasons = data.get('seasons', [])
                season_data = None
                for s in seasons:
                    if s.get('number') == season:
                        season_data = s
                        break
                if season_data and season_data.get('movieId') and str(season_data['movieId']) != str(movie_id):
                    self.log(f"Fetching season {season} details...")
                    details = self._get_details(security_key, str(season_data['movieId']))
                    current_movie_id = str(season_data['movieId'])

            details_data = self._extract_data_block(details)
            episodes = details_data.get('episodes', [])
            episode_id = None
            if media_type == 'tv' and season is not None and episode is not None:
                for ep in episodes:
                    if ep.get('number') == episode:
                        episode_id = str(ep.get('id'))
                        break
            elif episodes:
                episode_id = str(episodes[0].get('id'))
            else:
                raise Exception("No episodes found")

            if not episode_id:
                raise Exception("Could not find episode ID")

            episode_obj = None
            for ep in episodes:
                if str(ep.get('id')) == episode_id:
                    episode_obj = ep
                    break
            if not episode_obj:
                raise Exception("Episode not found in details")

            tracks = episode_obj.get('tracks', [])
            resolution = 2

            all_streams = []
            for track in tracks:
                lang_name = track.get('languageName') or track.get('abbreviate') or 'Unknown'
                if track.get('existIndividualVideo') and track.get('languageId'):
                    try:
                        self.log(f"Fetching {lang_name} (languageId: {track['languageId']})")
                        video_data = self._get_video_v1(security_key, current_movie_id, episode_id, track['languageId'], resolution)
                        streams = self._process_video_response(video_data, tmdb_info, season, episode, resolution, f"[{lang_name}]")
                        if streams:
                            self.log(f"✅ {lang_name}: Found {len(streams)} streams")
                            all_streams.extend(streams)
                    except Exception as e:
                        self.log(f"⚠️ {lang_name}: Failed - {e}", "WARNING")

            if not all_streams:
                self.log("Falling back to shared stream (v2)")
                video_data = self._get_video_v2(security_key, current_movie_id, episode_id, resolution)
                streams = self._process_video_response(video_data, tmdb_info, season, episode, resolution, "[Shared]")
                all_streams.extend(streams)

            if not all_streams:
                return json.dumps({
                    'status': 'error',
                    'message': 'No playable streams found'
                })

            # Sort by quality (descending)
            def quality_sort(s):
                q = s['quality']
                num_match = re.search(r'(\d+)', q)
                return int(num_match.group(1)) if num_match else 0

            all_streams.sort(key=quality_sort, reverse=True)

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

                headers = s.get('headers', PLAYBACK_HEADERS.copy())
                playable_urls.append({
                    'url': url,
                    'quality': s['quality'],
                    'type': stream_type,
                    'headers': None,
                    'server': 'Castle',
                    # Subtitles omitted
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

        except Exception as e:
            self.log(f"Error: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
            return json.dumps({
                'status': 'error',
                'message': str(e)
            })


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Castle Resolver (subtitles omitted)')
    parser.add_argument('url_or_id', help='TMDB ID or URL')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie', help='Media type (default: movie)')
    parser.add_argument('--season', type=int, help='Season number (for TV)')
    parser.add_argument('--episode', type=int, help='Episode number (for TV)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON output')

    args = parser.parse_args()

    resolver = CastleResolver(debug=args.debug)
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