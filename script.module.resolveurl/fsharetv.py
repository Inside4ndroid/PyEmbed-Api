#!/usr/bin/env python3
"""
FshareTV Resolver - Standalone Version
Supports both TMDB (numeric) and IMDb (tt) IDs
Returns JSON with stream URL and headers
Based on fshare.ts
Note: FshareTV only supports movies. TV show parameters will be ignored.
"""

import re
import json
import time
import urllib.request
import urllib.error
import ssl
from urllib.parse import urljoin, urlencode

__version__ = "1.0.3"

BASE_URL = 'https://fsharetv.cc'
TRAILER = 'Png81APqcxU'
TMDB_API_KEY = "f3c627493095a7e40ceca68355c94c6d"  # Public API key for TMDB

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36 Edg/148.0.0.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': BASE_URL,
}

API_HEADERS = {
    **HEADERS,
    'Accept': 'application/json, */*; q=0.01',
    'X-Requested-With': 'XMLHttpRequest',
}


class FshareTvResolver:
    def __init__(self, debug=False):
        self.debug = debug
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

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
        if url.startswith('/'):
            url = urljoin(BASE_URL, url)
        try:
            req = urllib.request.Request(url, headers=headers, data=data, method=method)
            response = urllib.request.urlopen(req, timeout=timeout, context=self.ssl_context)
            content = response.read().decode('utf-8', errors='ignore')
            return True, content, None
        except urllib.error.HTTPError as e:
            return False, None, f"HTTP Error {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            return False, None, f"URL Error: {str(e)}"
        except Exception as e:
            return False, None, f"Error: {str(e)}"

    def _get_imdb_from_tmdb(self, tmdb_id, media_type="movie"):
        """Convert TMDB ID to IMDb ID using TMDB API."""
        if media_type == "movie":
            url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/external_ids?api_key={TMDB_API_KEY}"
        else:
            url = f"https://api.themoviedb.org/3/tv/{tmdb_id}/external_ids?api_key={TMDB_API_KEY}"
        self.log(f"Converting TMDB ID to IMDb via: {url}", "DEBUG")
        success, content, error = self._fetch_url(url, timeout=10)
        if not success:
            return None
        try:
            data = json.loads(content)
            imdb_id = data.get('imdb_id')
            if imdb_id:
                self.log(f"Converted TMDB {tmdb_id} to IMDb {imdb_id}", "DEBUG")
                return imdb_id
        except:
            pass
        return None

    def _extract_id(self, url_or_id, media_type='movie'):
        """
        Extract IMDb ID from URL or determine if it's a TMDB ID.
        Returns (imdb_id, tmdb_id)
        """
        # If it's a URL
        if url_or_id.startswith('http'):
            # Try to extract IMDb ID
            match = re.search(r'/movie/(tt\d+)', url_or_id)
            if match:
                return match.group(1), None
            # Try to extract TMDB ID
            match = re.search(r'/(?:movie|tv)/(\d+)', url_or_id)
            if match:
                tmdb_id = match.group(1)
                # Determine if it's TV from URL or from media_type
                if '/tv/' in url_or_id:
                    media_type = 'tv'
                imdb_id = self._get_imdb_from_tmdb(tmdb_id, media_type)
                return imdb_id, tmdb_id
            # Try to extract IMDb ID from anywhere in URL
            match = re.search(r'(tt\d+)', url_or_id)
            if match:
                return match.group(1), None
        else:
            # If it starts with tt, it's an IMDb ID
            if re.match(r'^tt\d+$', url_or_id):
                return url_or_id, None
            # If it's numeric, treat as TMDB movie ID
            if url_or_id.isdigit():
                tmdb_id = url_or_id
                imdb_id = self._get_imdb_from_tmdb(tmdb_id, media_type)
                return imdb_id, tmdb_id
        return None, None

    def resolve(self, url_or_id, media_type='movie', season=None, episode=None):
        """
        Main method to resolve FshareTV URL
        Args:
            url_or_id: URL, TMDB ID (numeric), or IMDb ID (tt...)
            media_type: 'movie' or 'tv' (tv not supported)
            season, episode: ignored for movies
        Returns:
            JSON string with results
        """
        self.log("=" * 80)
        self.log(f"FshareTV Resolver Started - {media_type}")
        
        if media_type == 'tv':
            self.log("WARNING: FshareTV does not support TV shows. Attempting as movie anyway.", "WARNING")
            # Try to convert TV to movie? Usually not possible, but we still attempt.
            # We'll proceed with the same extraction, but using TV TMDB API might get IMDb.

        imdb_id, tmdb_id = self._extract_id(url_or_id, media_type)
        if not imdb_id:
            return json.dumps({
                'status': 'error',
                'message': 'Could not extract IMDb ID from input. Please provide an IMDb ID (tt...) or a TMDB movie ID.'
            })

        self.log(f"IMDb ID: {imdb_id}")

        try:
            # Step 1: Find watch path
            movie_url = f"{BASE_URL}/movie/{imdb_id}"
            self.log(f"Fetching movie page: {movie_url}")
            success, html, error = self._fetch_url(movie_url, headers=HEADERS, timeout=15)
            if not success:
                return json.dumps({
                    'status': 'error',
                    'message': f'Failed to fetch movie page: {error}'
                })

            watch_match = re.search(r'href="(/w/[^"]+)"', html)
            if not watch_match:
                return json.dumps({
                    'status': 'error',
                    'message': 'Could not find watch path on movie page'
                })
            watch_path = watch_match.group(1)
            self.log(f"Watch path: {watch_path}")

            # Step 2: Extract source ID from watch page
            watch_url = urljoin(BASE_URL, watch_path)
            self.log(f"Fetching watch page: {watch_url}")
            success, watch_html, error = self._fetch_url(watch_url, headers=HEADERS, timeout=15)
            if not success:
                return json.dumps({
                    'status': 'error',
                    'message': f'Failed to fetch watch page: {error}'
                })

            # Try multiple patterns to find source_id
            patterns = [
                r'Movie\.setSource\("([^"]+)"',
                r'setSource\("([^"]+)"',
                r"setSource\('([^']+)'",
                r'"source_id"\s*:\s*"([^"]+)"',
                r'source_id\s*=\s*"([^"]+)"',
                r'file_id\s*=\s*"([^"]+)"',
                r'"file_id"\s*:\s*"([^"]+)"'
            ]
            source_id = None
            for pattern in patterns:
                match = re.search(pattern, watch_html)
                if match:
                    source_id = match.group(1)
                    break
            if not source_id:
                return json.dumps({
                    'status': 'error',
                    'message': 'Could not extract source ID from watch page'
                })
            self.log(f"Source ID: {source_id}")

            # Step 3: Fetch API
            api_url = f"{BASE_URL}/api/file/{source_id}/source?trailer={TRAILER}&type=watch"
            self.log(f"Calling API: {api_url}")
            api_headers = {**API_HEADERS, 'Referer': f'{BASE_URL}/'}
            success, api_content, error = self._fetch_url(api_url, headers=api_headers, timeout=15)
            if not success:
                return json.dumps({
                    'status': 'error',
                    'message': f'API request failed: {error}'
                })

            try:
                api_data = json.loads(api_content)
            except json.JSONDecodeError as e:
                return json.dumps({
                    'status': 'error',
                    'message': f'Invalid JSON from API: {str(e)}'
                })

            if api_data.get('status') != 'ok':
                return json.dumps({
                    'status': 'error',
                    'message': f'API returned status: {api_data.get("status")}'
                })

            # Step 4: Parse sources
            file_data = api_data.get('data', {}).get('file', {})
            sources_list = []
            sources_list.extend(file_data.get('sources', []))
            sources_list.extend(file_data.get('backups', []))
            alternatives = file_data.get('alternatives', [])
            for alt_group in alternatives:
                if isinstance(alt_group, list):
                    sources_list.extend(alt_group)

            # Deduplicate by src
            seen = set()
            unique_sources = []
            for s in sources_list:
                src = s.get('src')
                if src and src not in seen:
                    seen.add(src)
                    unique_sources.append(s)

            if not unique_sources:
                return json.dumps({
                    'status': 'error',
                    'message': 'No playable sources found'
                })

            # Sort by quality descending
            unique_sources.sort(key=lambda x: int(x.get('quality', 0)), reverse=True)

            playable_urls = []
            for src_data in unique_sources:
                src_url = src_data.get('src')
                if not src_url:
                    continue
                if not src_url.startswith('http'):
                    src_url = urljoin(BASE_URL, src_url)

                # Infer type and quality
                media_type_str = src_data.get('type', '').replace('video/', '')
                if not media_type_str:
                    if '.m3u8' in src_url:
                        media_type_str = 'hls'
                    elif '.mpd' in src_url:
                        media_type_str = 'dash'
                    else:
                        media_type_str = 'mp4'

                quality_label = src_data.get('label')
                if quality_label:
                    qual_match = re.search(r'(\d+)p', quality_label)
                    if qual_match:
                        quality = f"{qual_match.group(1)}p"
                    else:
                        quality = quality_label
                else:
                    quality = 'Auto'

                headers = {
                    'User-Agent': HEADERS['User-Agent'],
                    'Referer': BASE_URL,
                }
                playable_urls.append({
                    'url': src_url,
                    'quality': quality,
                    'type': media_type_str,
                    'headers': headers,
                })

            response = {
                'status': 'success',
                'imdb_id': imdb_id,
                'playable_urls': playable_urls
            }

            self.log("=" * 80)
            self.log("RESOLUTION COMPLETE")
            self.log(f"Found {len(playable_urls)} playable sources")
            return json.dumps(response, indent=2)

        except Exception as e:
            self.log(f"Error: {str(e)}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
            return json.dumps({
                'status': 'error',
                'message': str(e)
            })


def main():
    import argparse

    parser = argparse.ArgumentParser(description='FshareTV Resolver (Movies only)')
    parser.add_argument('url_or_id', help='FshareTV URL, TMDB ID, or IMDb ID (tt...)')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie', help='Media type (default: movie; TV not supported)')
    parser.add_argument('--season', type=int, help='Season number (ignored, not supported)')
    parser.add_argument('--episode', type=int, help='Episode number (ignored, not supported)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON output')

    args = parser.parse_args()

    resolver = FshareTvResolver(debug=args.debug)
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