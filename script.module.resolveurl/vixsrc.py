#!/usr/bin/env python3
"""
VixSrc Resolver - Standalone Version
Returns JSON with stream URL and headers separated
"""

import re
import json
import time
import urllib.request
import urllib.error
import ssl
from urllib.parse import urljoin, urlencode

__version__ = "1.0.2"

BASE_URL = 'https://vixsrc.to'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150 Safari/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': BASE_URL,
    'Origin': BASE_URL,
}


class VixSrcResolver:
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

    def _is_token_expired(self, expires):
        """Check if token has expired (with 60s grace period)"""
        return int(expires) * 1000 - 60000 < time.time() * 1000

    def resolve(self, url_or_id, is_tv=False, season=None, episode=None):
        """
        Main method to resolve VixSrc URL
        Args:
            url_or_id: URL or TMDB ID
            is_tv: Whether it's a TV show
            season: Season number (for TV)
            episode: Episode number (for TV)
        Returns:
            JSON string with results
        """
        self.log("=" * 80)
        self.log("VixSrc Resolver Started - Standalone Mode")

        # Extract TMDB ID from URL if needed
        if url_or_id.startswith('http'):
            match = re.search(r'/movie/(\d+)', url_or_id)
            if match:
                tmdb_id = match.group(1)
            else:
                match = re.search(r'/tv/(\d+)', url_or_id)
                if match:
                    tmdb_id = match.group(1)
                    se_match = re.search(r'/tv/\d+/(\d+)/(\d+)', url_or_id)
                    if se_match:
                        season = int(se_match.group(1))
                        episode = int(se_match.group(2))
                        is_tv = True
                else:
                    return json.dumps({
                        'status': 'error',
                        'message': 'Could not extract TMDB ID from URL'
                    })
        else:
            tmdb_id = url_or_id

        self.log(f"TMDB ID: {tmdb_id}")
        self.log(f"Content Type: {'TV Show' if is_tv else 'Movie'}")
        if is_tv:
            self.log(f"Season: {season}, Episode: {episode}")

        # Step 1: Call the VixSrc API
        if is_tv:
            api_url = f"{BASE_URL}/api/tv/{tmdb_id}/{season}/{episode}"
        else:
            api_url = f"{BASE_URL}/api/movie/{tmdb_id}"

        self.log(f"Fetching API: {api_url}")
        success, content, error = self._fetch_url(api_url, headers=HEADERS, timeout=15)
        if not success:
            return json.dumps({
                'status': 'error',
                'message': f'Failed to fetch API: {error}'
            })

        try:
            api_data = json.loads(content)
        except json.JSONDecodeError as e:
            return json.dumps({
                'status': 'error',
                'message': f'Invalid JSON from API: {str(e)}'
            })

        src = api_data.get('src')
        if not src:
            return json.dumps({
                'status': 'error',
                'message': 'No "src" field in API response'
            })

        self.log(f"Embed source: {src}")

        # Step 2: Fetch the embed page
        embed_url = urljoin(BASE_URL, src)
        self.log(f"Fetching embed page: {embed_url}")
        headers_embed = HEADERS.copy()
        headers_embed['Accept'] = 'text/html,application/xhtml+xml,*/*'
        success, html, error = self._fetch_url(embed_url, headers=headers_embed, timeout=15)
        if not success:
            return json.dumps({
                'status': 'error',
                'message': f'Failed to fetch embed page: {error}'
            })

        # Step 3: Extract token, expires, playlist from HTML
        token = re.search(r'token["\']\s*:\s*["\']([^"\']+)', html)
        expires = re.search(r'expires["\']\s*:\s*["\']([^"\']+)', html)
        playlist = re.search(r'url\s*:\s*["\']([^"\']+)', html)

        if not token or not expires or not playlist:
            return json.dumps({
                'status': 'error',
                'message': 'Could not extract token, expires, or playlist from embed page'
            })

        token = token.group(1)
        expires = expires.group(1)
        playlist = playlist.group(1)

        self.log(f"Token: {token[:10]}...")
        self.log(f"Expires: {expires}")
        self.log(f"Playlist: {playlist}")

        # Check expiry
        if self._is_token_expired(expires):
            return json.dumps({
                'status': 'error',
                'message': 'Token has expired'
            })

        # Step 4: Build master playlist URL
        sep = '&' if '?' in playlist else '?'
        master_url = f"{playlist}{sep}token={token}&expires={expires}&h=1"
        self.log(f"Master URL: {master_url}")

        # Step 5: Fetch master playlist
        headers_playlist = HEADERS.copy()
        headers_playlist['Referer'] = api_url
        success, playlist_content, error = self._fetch_url(master_url, headers=headers_playlist, timeout=15)
        if not success:
            return json.dumps({
                'status': 'error',
                'message': f'Failed to fetch master playlist: {error}'
            })

        # Step 6: Parse playlist for best quality
        # Find highest resolution variant
        variant_regex = re.compile(r'#EXT-X-STREAM-INF:[^\n]*RESOLUTION=\d+x(\d+)[^\n]*\n([^\n]+)')
        variants = variant_regex.findall(playlist_content)

        best_res = 0
        best_url = None
        for res, url in variants:
            res_int = int(res)
            if res_int > best_res:
                best_res = res_int
                best_url = url

        # If no variants found, maybe the playlist itself is the stream
        if not best_url:
            if '#EXT-X-STREAM-INF' not in playlist_content:
                best_url = master_url
                best_res = 0

        if not best_url:
            return json.dumps({
                'status': 'error',
                'message': 'No playable stream found in playlist'
            })

        # Build the final stream URL (if relative, resolve against master_url)
        if not best_url.startswith('http'):
            best_url = urljoin(master_url, best_url)

        quality = f"{best_res}p" if best_res > 0 else "Auto"

        # Extract audio tracks
        audio_tracks = []
        for line in playlist_content.split('\n'):
            if line.startswith('#EXT-X-MEDIA:TYPE=AUDIO'):
                lang = re.search(r'LANGUAGE="([^"]+)"', line)
                label = re.search(r'NAME="([^"]+)"', line)
                if lang and label:
                    audio_tracks.append({
                        'language': lang.group(1),
                        'label': label.group(1)
                    })

        # Build response with clean URL and headers separate
        headers = {
            'User-Agent': HEADERS['User-Agent'],
            'Referer': api_url,
        }

        response = {
            'status': 'success',
            'tmdb_id': tmdb_id,
            'playable_urls': [
                {
                    'url': best_url,  # raw URL only
                    'quality': quality,
                    'headers': headers,
                    'audio_tracks': audio_tracks,
                }
            ]
        }

        self.log("=" * 80)
        self.log("RESOLUTION COMPLETE")
        self.log(f"Stream URL: {best_url[:100]}...")
        return json.dumps(response, indent=2)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='VixSrc Resolver')
    parser.add_argument('url_or_id', help='VixSrc URL or TMDB ID')
    parser.add_argument('--tv', action='store_true', help='Treat as TV show')
    parser.add_argument('--season', type=int, help='Season number (for TV)')
    parser.add_argument('--episode', type=int, help='Episode number (for TV)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON output')

    args = parser.parse_args()

    resolver = VixSrcResolver(debug=args.debug)
    result_json = resolver.resolve(args.url_or_id, args.tv, args.season, args.episode)

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