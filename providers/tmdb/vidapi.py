#!/usr/bin/env python3
"""
VidApi Resolver - Standalone Version
Supports both movies and TV shows.
Returns JSON with stream URL and headers
Based on vidapi.ts
"""

import re
import json
import time
import random
import urllib.request
import urllib.error
import ssl
from urllib.parse import urlencode, urljoin

__version__ = "1.0.1"

BASE_URL = 'https://vaplayer.ru'
API_URL = 'https://streamdata.vaplayer.ru/api.php'
IFRAME_URL = 'https://brightpathsignals.com'

# Common user agents to rotate
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

HEADERS = {
    'Referer': f'{IFRAME_URL}/',
    'Origin': IFRAME_URL,
    'Accept': '*/*',
}


class VidApiResolver:
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
        # If no User-Agent, set a random one
        if 'User-Agent' not in headers:
            headers['User-Agent'] = random.choice(USER_AGENTS)
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

    def resolve(self, url_or_id, media_type='movie', season=None, episode=None):
        """
        Main method to resolve VidApi URL
        Args:
            url_or_id: URL or TMDB ID
            media_type: 'movie' or 'tv'
            season: Season number (for TV)
            episode: Episode number (for TV)
        Returns:
            JSON string with results
        """
        self.log("=" * 80)
        self.log(f"VidApi Resolver Started - Standalone Mode ({media_type})")

        # Extract TMDB ID from URL if needed
        if url_or_id.startswith('http'):
            match = re.search(r'/(?:movie|tv)/(\d+)', url_or_id)
            if match:
                tmdb_id = match.group(1)
                # Override media_type if URL indicates TV
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

        # Build API URL
        params = {
            'tmdb': tmdb_id,
            'type': media_type,
        }
        if media_type == 'tv' and season is not None and episode is not None:
            params['season'] = str(season)
            params['episode'] = str(episode)

        # Choose a random User-Agent for this request
        user_agent = random.choice(USER_AGENTS)
        headers = HEADERS.copy()
        headers['User-Agent'] = user_agent

        api_url = f"{API_URL}?{urlencode(params)}"
        self.log(f"Calling API: {api_url}")
        success, content, error = self._fetch_url(api_url, headers=headers, timeout=15)
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

        status_code = data.get('status_code')
        if status_code != '200':
            return json.dumps({
                'status': 'error',
                'message': f'API returned status: {status_code}'
            })

        api_data = data.get('data', {})
        stream_urls = api_data.get('stream_urls', [])
        if not stream_urls:
            return json.dumps({
                'status': 'error',
                'message': 'No stream URLs in API response'
            })

        # Determine quality from file_name if available
        file_name = api_data.get('file_name', '')
        quality = 'Auto'
        if file_name:
            qual_match = re.search(r'(\d+)p', file_name)
            if qual_match:
                quality = f"{qual_match.group(1)}p"
            else:
                quality = file_name

        # Build playable URLs
        playable_urls = []
        for url in stream_urls:
            # Determine type
            if '.m3u8' in url.lower():
                stream_type = 'hls'
            elif '.mpd' in url.lower():
                stream_type = 'dash'
            elif '.mp4' in url.lower() or '.mkv' in url.lower():
                stream_type = 'mp4'
            else:
                stream_type = 'hls'  # default

            headers_out = {
                'User-Agent': user_agent,
                'Referer': IFRAME_URL + '/',
                'Origin': IFRAME_URL,
            }
            playable_urls.append({
                'url': url,
                'quality': quality,
                'type': stream_type,
                'headers': headers_out,
                'server': 'VidApi',
            })

        # Subtitles
        subtitles = []
        default_subs = data.get('default_subs', [])
        for sub in default_subs:
            sub_url = sub.get('url')
            if not sub_url:
                continue
            # Determine format from extension
            ext = sub_url.split('.')[-1].lower()
            if ext == 'vtt':
                fmt = 'vtt'
            elif ext == 'ass':
                fmt = 'ass'
            elif ext == 'ssa':
                fmt = 'ssa'
            elif ext == 'ttml':
                fmt = 'ttml'
            else:
                fmt = 'srt'
            subtitles.append({
                'url': sub_url,
                'label': sub.get('lang', 'Unknown'),
                'format': fmt,
                'headers': None,
            })

        response = {
            'status': 'success',
            'tmdb_id': tmdb_id,
            'playable_urls': playable_urls,
            'subtitles': subtitles,
        }

        self.log("=" * 80)
        self.log("RESOLUTION COMPLETE")
        self.log(f"Found {len(playable_urls)} playable sources and {len(subtitles)} subtitles")
        return json.dumps(response, indent=2)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='VidApi Resolver')
    parser.add_argument('url_or_id', help='VidApi URL or TMDB ID')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie', help='Media type (default: movie)')
    parser.add_argument('--season', type=int, help='Season number (for TV)')
    parser.add_argument('--episode', type=int, help='Episode number (for TV)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON output')

    args = parser.parse_args()

    resolver = VidApiResolver(debug=args.debug)
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