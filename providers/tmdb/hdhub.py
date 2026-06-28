#!/usr/bin/env python3
"""
HdHub Resolver - Standalone Version
Supports both TMDB (numeric) and IMDb (tt) IDs
Returns JSON with stream URL and headers
Based on HdHubProvider.kt (Kotlin)
"""

import re
import json
import time
import urllib.request
import urllib.error
import ssl
from urllib.parse import urlencode

__version__ = "1.0.2"

API_BASE = "https://hdhub.thevolecitor.qzz.io/eyJ0b3Jib3giOiJ1bnNldCIsInF1YWxpdGllcyI6IjIxNjBwLDEwODBwLDcyMHAiLCJzb3J0IjoiZGVzYyJ9"

TMDB_API_KEY = "439c478a771f35c05022f9feabcca01c"  # Public API key for TMDB

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, */*',
    'Accept-Language': 'en-US,en;q=0.9',
}


class HdHubResolver:
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
        elif data and isinstance(data, dict):
            data = urlencode(data).encode('utf-8')
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
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

    def resolve(self, url_or_id, media_type='movie', season=None, episode=None):
        """
        Main method to resolve HdHub URL
        Args:
            url_or_id: URL, TMDB ID (numeric), or IMDb ID (tt...)
            media_type: 'movie' or 'tv'
            season: Season number (for TV)
            episode: Episode number (for TV)
        Returns:
            JSON string with results
        """
        self.log("=" * 80)
        self.log(f"HdHub Resolver Started - Standalone Mode ({media_type})")

        # Extract ID from URL if needed
        if url_or_id.startswith('http'):
            match = re.search(r'(tt\d+)', url_or_id)
            if match:
                imdb_id = match.group(1)
            else:
                match = re.search(r'/(?:movie|tv)/(\d+)', url_or_id)
                if match:
                    tmdb_id = match.group(1)
                    # Try to convert TMDB to IMDb
                    imdb_id = self._get_imdb_from_tmdb(tmdb_id, media_type)
                    if not imdb_id:
                        return json.dumps({
                            'status': 'error',
                            'message': f'Could not convert TMDB ID {tmdb_id} to IMDb ID. Please provide an IMDb ID directly (tt...).'
                        })
                else:
                    return json.dumps({
                        'status': 'error',
                        'message': 'Could not extract ID from URL'
                    })
        else:
            # If it's numeric, treat as TMDB ID
            if url_or_id.isdigit():
                tmdb_id = url_or_id
                imdb_id = self._get_imdb_from_tmdb(tmdb_id, media_type)
                if not imdb_id:
                    return json.dumps({
                        'status': 'error',
                        'message': f'Could not convert TMDB ID {tmdb_id} to IMDb ID. Please provide an IMDb ID directly (tt...).'
                    })
            else:
                # Assume it's an IMDb ID
                if not re.match(r'^tt\d+$', url_or_id):
                    return json.dumps({
                        'status': 'error',
                        'message': 'Invalid ID format. Please provide a TMDB numeric ID or IMDb ID (tt...).'
                    })
                imdb_id = url_or_id

        self.log(f"IMDb ID: {imdb_id}")
        self.log(f"Content Type: {'TV Show' if media_type == 'tv' else 'Movie'}")
        if media_type == 'tv':
            if season is None or episode is None:
                return json.dumps({
                    'status': 'error',
                    'message': 'Season and episode are required for TV shows.'
                })
            self.log(f"Season: {season}, Episode: {episode}")

        # Build API URL
        if media_type == 'tv':
            api_url = f"{API_BASE}/stream/series/{imdb_id}:{season}:{episode}.json"
        else:
            api_url = f"{API_BASE}/stream/movie/{imdb_id}.json"

        self.log(f"Fetching API: {api_url}")
        success, content, error = self._fetch_url(api_url, headers=HEADERS, timeout=15)
        if not success:
            return json.dumps({
                'status': 'error',
                'message': f'API request failed: {error}'
            })

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            return json.dumps({
                'status': 'error',
                'message': f'Invalid JSON from API: {str(e)}'
            })

        streams = data.get('streams', [])
        if not streams:
            return json.dumps({
                'status': 'error',
                'message': 'No streams in API response'
            })

        playable_urls = []
        for stream in streams:
            url = stream.get('url')
            if not url:
                continue

            name = stream.get('name', 'HdHub')
            description = stream.get('description', '')
            combined_text = f"{name} {description}"

            # Extract quality
            quality = "HD"
            if re.search(r'2160p|4K', combined_text, re.IGNORECASE):
                quality = "4K"
            elif re.search(r'1080p', combined_text, re.IGNORECASE):
                quality = "1080p"
            elif re.search(r'720p', combined_text, re.IGNORECASE):
                quality = "720p"
            elif re.search(r'480p', combined_text, re.IGNORECASE):
                quality = "480p"

            # Determine type
            if '.m3u8' in url.lower():
                stream_type = 'hls'
            elif '.mpd' in url.lower():
                stream_type = 'dash'
            elif '.mp4' in url.lower() or '.mkv' in url.lower():
                stream_type = 'mp4'
            else:
                stream_type = 'hls'

            # Headers from behaviorHints
            headers = {}
            behavior_hints = stream.get('behaviorHints', {})
            proxy_headers = behavior_hints.get('proxyHeaders', {})
            request_headers = proxy_headers.get('request', {})
            if isinstance(request_headers, dict):
                for key, value in request_headers.items():
                    headers[key] = value

            # Add standard headers if not present
            if 'User-Agent' not in headers:
                headers['User-Agent'] = HEADERS['User-Agent']
            if 'Referer' not in headers:
                headers['Referer'] = 'https://hdhub.thevolecitor.qzz.io/'

            playable_urls.append({
                'url': url,
                'quality': quality,
                'type': stream_type,
                'headers': headers,
                'server': 'HdHub',
            })

        response = {
            'status': 'success',
            'imdb_id': imdb_id,
            'playable_urls': playable_urls,
        }

        self.log("=" * 80)
        self.log("RESOLUTION COMPLETE")
        self.log(f"Found {len(playable_urls)} playable sources")
        return json.dumps(response, indent=2)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='HdHub Resolver')
    parser.add_argument('url_or_id', help='HdHub URL, TMDB ID, or IMDb ID (tt...)')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie', help='Media type (default: movie)')
    parser.add_argument('--season', type=int, help='Season number (for TV)')
    parser.add_argument('--episode', type=int, help='Episode number (for TV)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON output')

    args = parser.parse_args()

    resolver = HdHubResolver(debug=args.debug)
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