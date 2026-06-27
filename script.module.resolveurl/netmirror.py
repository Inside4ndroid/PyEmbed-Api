#!/usr/bin/env python3
"""
NetMirror Resolver - Standalone Version
Supports both movies and TV shows.
Returns JSON with stream URL and headers.
Based on NetMirror provider (index.js, utils.js, constants.js)
Requires: requests
"""

import re
import json
import time
import base64
import urllib.parse
import requests

__version__ = "1.0.0"

# Constants from constants.js
TMDB_API_KEY = "439c478a771f35c05022f9feabcca01c"

PLATFORM_MAP = {
    "netflix": {
        "ott": "nf",
        "search": "/mobile/search.php",
        "post": "/mobile/post.php",
        "episodes": "/mobile/episodes.php",
        "playlist": "/mobile/playlist.php",
        "img": "poster/v",
        "epImg": "epimg/150"
    },
    "primevideo": {
        "ott": "pv",
        "search": "/mobile/pv/search.php",
        "post": "/mobile/pv/post.php",
        "episodes": "/mobile/pv/episodes.php",
        "playlist": "/mobile/pv/playlist.php",
        "img": "pv/v",
        "epImg": "pvepimg"
    },
    "hotstar": {
        "ott": "hs",
        "search": "/mobile/hs/search.php",
        "post": "/mobile/hs/post.php",
        "episodes": "/mobile/hs/episodes.php",
        "playlist": "/mobile/hs/playlist.php",
        "img": "hs/v",
        "epImg": "hsepimg"
    },
    "disney": {
        "ott": "hs",
        "search": "/mobile/hs/search.php",
        "post": "/mobile/hs/post.php",
        "episodes": "/mobile/hs/episodes.php",
        "playlist": "/mobile/hs/playlist.php",
        "img": "hs/v",
        "epImg": "hsepimg"
    }
}

BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Android WebView";v="144"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Android"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 5 Build/TQ3A.230901.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/144.0.7559.132 Safari/537.36 /OS.Gatu v3.0",
    "X-Requested-With": "XMLHttpRequest"
}

NEW_TV_BASE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
    "X-Requested-With": "NetmirrorNewTV v1.0",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0 /OS.GatuNewTV v1.0",
    "Accept": "application/json, text/plain, */*"
}

NEW_TV_DOMAINS = [
    "aHR0cHM6Ly9tb2JpbGVkZXRlY3RzLmNvbQ==",
    "aHR0cHM6Ly9tb2JpbGVkZXRlY3QuYXBw",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0LmFydA==",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0LmNj",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0LmNsaWNr",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0Lmluaw==",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0LmxpdmU=",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0LnBybw==",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0LnNob3A=",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0LnNpdGU=",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0LnNwYWNl",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0LnN0b3Jl",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0LnZpcA==",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0Lndpa2k=",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0Lnh5eg==",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0cy5hcnQ=",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0cy5jYw==",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0cy5pbmZv",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0cy5pbms=",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0cy5saXZl",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0cy5wcm8=",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0cy5zdG9yZQ==",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0cy50b3A=",
    "aHR0cHM6Ly9tb2JpZGV0ZWN0cy54eXo="
]


class NetMirrorResolver:
    def __init__(self, debug=False):
        self.debug = debug
        self.session = requests.Session()
        self.session.headers.update(BASE_HEADERS)
        self.resolved_api_url = None

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    def _safe_b64decode(self, encoded):
        """Decode base64, handle padding."""
        try:
            # Add padding if missing
            missing = len(encoded) % 4
            if missing:
                encoded += '=' * (4 - missing)
            return base64.b64decode(encoded).decode('utf-8')
        except Exception as e:
            self.log(f"Base64 decode error: {e}", "ERROR")
            return None

    def _resolve_api_url(self):
        """Resolve the actual API base URL by probing domains."""
        if self.resolved_api_url:
            return self.resolved_api_url

        for encoded in NEW_TV_DOMAINS:
            base = self._safe_b64decode(encoded)
            if not base:
                continue
            base = base.rstrip('/')
            check_url = f"{base}/checknewtv.php"
            headers = NEW_TV_BASE_HEADERS.copy()
            headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            try:
                self.log(f"Checking domain: {check_url}", "DEBUG")
                resp = self.session.get(check_url, headers=headers, timeout=10)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                token_hash = data.get('token_hash')
                if token_hash:
                    decoded_base = self._safe_b64decode(token_hash)
                    if decoded_base:
                        self.resolved_api_url = decoded_base.rstrip('/')
                        self.log(f"Resolved API URL: {self.resolved_api_url}")
                        return self.resolved_api_url
            except Exception as e:
                self.log(f"Domain check failed: {e}", "DEBUG")
                continue

        raise Exception("Failed to resolve NewTV API base URL")

    def _fetch_json(self, url, headers=None, timeout=15):
        """Fetch URL and return JSON."""
        if headers is None:
            headers = NEW_TV_BASE_HEADERS.copy()
        try:
            resp = self.session.get(url, headers=headers, timeout=timeout)
            if resp.status_code != 200:
                self.log(f"HTTP error {resp.status_code} from {url}", "ERROR")
                return None
            return resp.json()
        except Exception as e:
            self.log(f"Request failed: {e}", "ERROR")
            return None

    def _get_tmdb_details(self, tmdb_id, media_type):
        """Get title from TMDB."""
        endpoint = "tv" if media_type == "tv" else "movie"
        url = f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}?api_key={TMDB_API_KEY}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': 'application/json'
        }
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                self.log(f"TMDB API error: {resp.status_code}", "ERROR")
                return None
            data = resp.json()
            title = data.get('name') if media_type == 'tv' else data.get('title')
            return title
        except Exception as e:
            self.log(f"TMDB fetch error: {e}", "ERROR")
            return None

    def _build_newtv_headers(self, ott, extra=None):
        """Build headers for NewTV API."""
        headers = NEW_TV_BASE_HEADERS.copy()
        headers['Ott'] = ott
        if extra:
            headers.update(extra)
        return headers

    def _fetch_episodes_page(self, api_base, season_id, page, season_number, ott):
        """Fetch a page of episodes for a season."""
        url = f"{api_base}/newtv/episodes.php?id={season_id}&page={page}"
        headers = self._build_newtv_headers(ott)
        data = self._fetch_json(url, headers)
        if not data:
            return [], False

        episodes = []
        if data.get('episodes'):
            for ep in data['episodes']:
                if ep is None:
                    continue
                ep_num = ep.get('ep')
                if ep_num is None:
                    # Try epNum
                    ep_num_str = ep.get('epNum')
                    if ep_num_str and ep_num_str.startswith('E'):
                        ep_num = int(ep_num_str[1:])
                    else:
                        ep_num = None
                if ep_num is None:
                    continue
                s_num = season_number
                if s_num is None:
                    s_num_str = ep.get('sNum')
                    if s_num_str and s_num_str.startswith('S'):
                        s_num = int(s_num_str[1:])
                episodes.append({
                    'id': ep.get('id'),
                    's': s_num,
                    'ep': ep_num
                })
        next_page = data.get('nextPageShow') == 1
        return episodes, next_page

    def _get_all_episodes(self, content_id, post_data, platform, api_base):
        """Collect all episodes from all seasons."""
        episodes = []

        # Find selected season
        seasons = post_data.get('season', [])
        selected_season_idx = -1
        for idx, s in enumerate(seasons):
            if s.get('selected') is True:
                selected_season_idx = idx
                break
        selected_season_id = None
        selected_season_number = None
        if selected_season_idx >= 0:
            selected_season_id = seasons[selected_season_idx].get('id')
            selected_season_number = selected_season_idx + 1
        else:
            selected_season_id = post_data.get('nextPageSeason')
            selected_season_number = None

        # Episodes from post_data
        if post_data.get('episodes'):
            for ep in post_data['episodes']:
                if ep is None:
                    continue
                ep_num = ep.get('ep')
                if ep_num is None:
                    ep_num_str = ep.get('epNum')
                    if ep_num_str and ep_num_str.startswith('E'):
                        ep_num = int(ep_num_str[1:])
                    else:
                        continue
                s_num = selected_season_number
                if s_num is None:
                    s_num_str = ep.get('sNum')
                    if s_num_str and s_num_str.startswith('S'):
                        s_num = int(s_num_str[1:])
                episodes.append({
                    'id': ep.get('id'),
                    's': s_num,
                    'ep': ep_num
                })

        # If there's a next page for selected season
        if post_data.get('nextPageShow') == 1 and selected_season_id:
            page = 2
            while True:
                more, has_next = self._fetch_episodes_page(
                    api_base, selected_season_id, page, selected_season_number, platform['ott']
                )
                episodes.extend(more)
                if not has_next:
                    break
                page += 1

        # Fetch other seasons
        for idx, season in enumerate(seasons):
            season_id = season.get('id')
            if season_id and season_id != selected_season_id:
                page = 1
                season_number = idx + 1
                while True:
                    more, has_next = self._fetch_episodes_page(
                        api_base, season_id, page, season_number, platform['ott']
                    )
                    episodes.extend(more)
                    if not has_next:
                        break
                    page += 1

        return episodes

    def _fetch_from_platform(self, platform_key, title, media_type, season, episode):
        """Try to get streams from a specific platform."""
        platform = PLATFORM_MAP.get(platform_key)
        if not platform:
            return None

        api_base = self._resolve_api_url()
        ott = platform['ott']

        # 1. Search
        search_url = f"{api_base}/newtv/search.php?s={urllib.parse.quote(title)}"
        headers = self._build_newtv_headers(ott)
        search_data = self._fetch_json(search_url, headers)
        if not search_data:
            return None
        search_results = search_data.get('searchResult')
        if not search_results:
            return None

        result = search_results[0]
        content_id = result.get('id')
        if not content_id:
            return None

        # 2. Post (get details)
        post_url = f"{api_base}/newtv/post.php?id={content_id}"
        post_headers = self._build_newtv_headers(ott, {'Lastep': '', 'Usertoken': ''})
        post_data = self._fetch_json(post_url, post_headers)
        if not post_data:
            return None

        target_id = content_id

        if media_type == 'tv':
            # Get all episodes
            episodes = self._get_all_episodes(content_id, post_data, platform, api_base)
            target_ep = None
            for ep in episodes:
                if ep.get('s') == season and ep.get('ep') == episode:
                    target_ep = ep
                    break
            if not target_ep:
                return None
            target_id = target_ep['id']
        else:
            # Check if it's a series
            is_series = post_data.get('type') == 't'
            if not is_series:
                episodes = post_data.get('episodes')
                if episodes:
                    # Count non-null episodes
                    non_null = [e for e in episodes if e is not None]
                    if non_null:
                        is_series = True
            if is_series:
                # Movie not found in series
                return None
            target_id = post_data.get('main_id') or content_id

        # 3. Player
        player_url = f"{api_base}/newtv/player.php?id={target_id}"
        player_headers = self._build_newtv_headers(ott, {'Usertoken': ''})
        player_data = self._fetch_json(player_url, player_headers)
        if not player_data:
            return None

        if player_data.get('status') != 'ok':
            return None

        video_link = player_data.get('video_link')
        if not video_link:
            return None

        # Build stream
        platform_name = platform_key.capitalize()
        stream = {
            'name': f"NetMirror ({platform_name})",
            'title': title,
            'url': video_link,
            'quality': 'Auto',
            'headers': {
                'Referer': player_data.get('referer') or api_base
            },
            'platform': platform_key
        }
        return [stream]

    def resolve(self, url_or_id, media_type='movie', season=None, episode=None):
        """Main resolve method."""
        self.log("=" * 80)
        self.log(f"NetMirror Resolver Started - {media_type} ID: {url_or_id}")

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

        # Get title from TMDB
        title = self._get_tmdb_details(tmdb_id, media_type)
        if not title:
            return json.dumps({
                'status': 'error',
                'message': 'Failed to get title from TMDB'
            })
        self.log(f"Title: {title}")

        # Try platforms
        platforms = ['netflix', 'primevideo', 'hotstar', 'disney']
        all_streams = []
        for p in platforms:
            try:
                self.log(f"Trying platform: {p}")
                streams = self._fetch_from_platform(p, title, media_type, season, episode)
                if streams:
                    self.log(f"Found streams on {p}")
                    all_streams.extend(streams)
                    # Break after first successful platform? The JS tries all and returns first non-empty.
                    # We'll collect all but break if found any (to avoid multiple duplicates)
                    # Actually JS returns immediately if any streams found.
                    if all_streams:
                        break
            except Exception as e:
                self.log(f"Platform {p} failed: {e}", "WARNING")
                continue

        if not all_streams:
            return json.dumps({
                'status': 'error',
                'message': 'No playable sources found'
            })

        # Build playable_urls
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
            # Ensure User-Agent is set
            if 'User-Agent' not in headers:
                headers['User-Agent'] = BASE_HEADERS['User-Agent']

            playable_urls.append({
                'url': url,
                'quality': s.get('quality', 'Auto'),
                'type': stream_type,
                'headers': headers,
                'server': s.get('name', 'NetMirror'),
                'platform': s.get('platform', 'unknown')
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

    parser = argparse.ArgumentParser(description='NetMirror Resolver')
    parser.add_argument('url_or_id', help='TMDB ID or URL')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie', help='Media type (default: movie)')
    parser.add_argument('--season', type=int, help='Season number (for TV)')
    parser.add_argument('--episode', type=int, help='Episode number (for TV)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON output')

    args = parser.parse_args()

    resolver = NetMirrorResolver(debug=args.debug)
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