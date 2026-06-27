#!/usr/bin/env python3
"""
StreamFlix Resolver - Standalone Version
Supports both movies and TV shows.
Returns JSON with stream URL and headers.
Based on StreamFlix provider (streamflix.js)
Requires: requests, websocket-client
"""

import re
import json
import time
import urllib.parse
import requests
import websocket
import threading
import queue
from typing import Dict, List, Optional, Any

__version__ = "1.0.0"

# Constants
TMDB_API_KEY = "439c478a771f35c05022f9feabcca01c"
STREAMFLIX_API_BASE = "https://api.streamflix.app"
CONFIG_URL = f"{STREAMFLIX_API_BASE}/config/config-streamflixapp.json"
DATA_URL = f"{STREAMFLIX_API_BASE}/data.json"
WEBSOCKET_URL = "wss://chilflix-410be-default-rtdb.asia-southeast1.firebasedatabase.app/.ws?ns=chilflix-410be-default-rtdb&v=5"

CACHE_TTL = 300  # seconds


class StreamFlixResolver:
    def __init__(self, debug=False):
        self.debug = debug
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive'
        })
        self.config_cache = None
        self.config_timestamp = 0
        self.data_cache = None
        self.data_timestamp = 0

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    def _get_config(self) -> Dict:
        """Fetch config with caching."""
        now = time.time()
        if self.config_cache and (now - self.config_timestamp) < CACHE_TTL:
            return self.config_cache
        self.log("Fetching config data...", "DEBUG")
        try:
            resp = self.session.get(CONFIG_URL, timeout=15)
            resp.raise_for_status()
            self.config_cache = resp.json()
            self.config_timestamp = now
            self.log("Config data cached successfully", "DEBUG")
            return self.config_cache
        except Exception as e:
            self.log(f"Failed to fetch config: {e}", "ERROR")
            raise

    def _get_data(self) -> Dict:
        """Fetch data (movie/tv index) with caching."""
        now = time.time()
        if self.data_cache and (now - self.data_timestamp) < CACHE_TTL:
            return self.data_cache
        self.log("Fetching data...", "DEBUG")
        try:
            resp = self.session.get(DATA_URL, timeout=15)
            resp.raise_for_status()
            self.data_cache = resp.json()
            self.data_timestamp = now
            self.log("Data cached successfully", "DEBUG")
            return self.data_cache
        except Exception as e:
            self.log(f"Failed to fetch data: {e}", "ERROR")
            raise

    def _get_tmdb_details(self, tmdb_id: str, media_type: str) -> Dict:
        """Fetch title and year from TMDB."""
        endpoint = "tv" if media_type == "tv" else "movie"
        url = f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}?api_key={TMDB_API_KEY}"
        try:
            resp = requests.get(url, headers={'Accept': 'application/json'}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            title = data.get('name') if media_type == 'tv' else data.get('title')
            release_date = data.get('first_air_date') if media_type == 'tv' else data.get('release_date')
            year = release_date.split('-')[0] if release_date else None
            return {'title': title, 'year': year}
        except Exception as e:
            self.log(f"TMDB fetch error: {e}", "ERROR")
            return None

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate word overlap similarity."""
        words1 = set(str1.lower().split())
        words2 = set(str2.lower().split())
        if not words1 or not words2:
            return 0.0
        # Count matches where a word from str1 is contained in a word from str2 or vice versa
        matches = 0
        for w1 in words1:
            if len(w1) > 2:
                for w2 in words2:
                    if w1 in w2 or w2 in w1:
                        matches += 1
                        break
        return matches / max(len(words1), len(words2))

    def _search_content(self, title: str, year: str, media_type: str) -> List[Dict]:
        """Search data for matches."""
        self.log(f"Searching for: '{title}' ({year})", "DEBUG")
        try:
            data = self._get_data()
            if not data or 'data' not in data:
                self.log("Invalid data structure", "ERROR")
                return []
            results = []
            title_words = title.lower().split()
            for item in data['data']:
                item_title = item.get('moviename', '')
                if not item_title:
                    continue
                # Check if all words from title are present in item title (case-insensitive)
                item_title_lower = item_title.lower()
                if all(word in item_title_lower for word in title_words):
                    results.append(item)
            self.log(f"Found {len(results)} search results", "DEBUG")
            return results
        except Exception as e:
            self.log(f"Search error: {e}", "ERROR")
            return []

    def _find_best_match(self, target_title: str, results: List[Dict]) -> Optional[Dict]:
        """Find best matching item."""
        if not results:
            return None
        best_match = None
        best_score = 0.0
        target_lower = target_title.lower()
        for item in results:
            score = self._calculate_similarity(target_lower, item.get('moviename', ''))
            if score > best_score:
                best_score = score
                best_match = item
        if best_match:
            self.log(f"Best match: '{best_match.get('moviename')}' (score: {best_score:.2f})", "DEBUG")
        return best_match

    def _get_episodes_via_websocket(self, movie_key: str, total_seasons: int) -> Dict[int, Dict]:
        """Fetch episode data using WebSocket (Firebase)."""
        self.log(f"Fetching episodes via WebSocket for movieKey: {movie_key}", "DEBUG")
        result_queue = queue.Queue()
        thread = threading.Thread(target=self._websocket_thread, args=(movie_key, total_seasons, result_queue))
        thread.daemon = True
        thread.start()
        thread.join(timeout=30)
        if thread.is_alive():
            self.log("WebSocket thread timeout", "WARNING")
            return {}
        try:
            return result_queue.get_nowait()
        except queue.Empty:
            return {}

    def _websocket_thread(self, movie_key: str, total_seasons: int, result_queue: queue.Queue):
        """WebSocket worker thread."""
        try:
            ws = websocket.create_connection(WEBSOCKET_URL, timeout=15)
        except Exception as e:
            self.log(f"WebSocket connection failed: {e}", "ERROR")
            result_queue.put({})
            return

        seasons_data = {}
        current_season = 1
        completed_seasons = 0
        expected_responses = 0
        responses_received = 0
        message_buffer = ""
        overall_timeout = time.time() + 30
        season_completed = False

        def send_season_request(season: int):
            payload = {
                "t": "d",
                "d": {
                    "a": "q",
                    "r": season,
                    "b": {
                        "p": f"Data/{movie_key}/seasons/{season}/episodes",
                        "h": ""
                    }
                }
            }
            try:
                ws.send(json.dumps(payload))
            except Exception:
                pass

        send_season_request(1)

        while time.time() < overall_timeout:
            try:
                ws.settimeout(5)
                raw = ws.recv()
                if not raw:
                    continue
                # Handle numeric count messages
                if raw.strip().isdigit():
                    expected_responses = int(raw.strip())
                    responses_received = 0
                    continue

                message_buffer += raw
                # Try to parse as JSON
                try:
                    data = json.loads(message_buffer)
                    message_buffer = ""
                except json.JSONDecodeError:
                    # Incomplete JSON, wait for more
                    continue

                # Handshake message
                if data.get('t') == 'c':
                    continue

                if data.get('t') == 'd':
                    d_data = data.get('d', {})
                    b_data = d_data.get('b', {})
                    # Season completion
                    if d_data.get('r') == current_season and b_data.get('s') == 'ok':
                        completed_seasons += 1
                        if completed_seasons < total_seasons:
                            current_season += 1
                            expected_responses = 0
                            responses_received = 0
                            send_season_request(current_season)
                        else:
                            # All seasons done
                            result_queue.put(seasons_data)
                            ws.close()
                            return
                        continue

                    # Episode data
                    if b_data.get('d'):
                        episodes_obj = b_data['d']
                        season_episodes = seasons_data.get(current_season, {})
                        for ep_key, ep_data in episodes_obj.items():
                            if isinstance(ep_data, dict):
                                ep_num = int(ep_key)
                                season_episodes[ep_num] = {
                                    'key': ep_data.get('key'),
                                    'link': ep_data.get('link'),
                                    'name': ep_data.get('name'),
                                    'overview': ep_data.get('overview'),
                                    'runtime': ep_data.get('runtime'),
                                    'still_path': ep_data.get('still_path'),
                                    'vote_average': ep_data.get('vote_average')
                                }
                                responses_received += 1
                        seasons_data[current_season] = season_episodes
            except websocket.WebSocketTimeoutException:
                continue
            except Exception as e:
                self.log(f"WebSocket error: {e}", "WARNING")
                break

        ws.close()
        if not result_queue.empty():
            return
        result_queue.put(seasons_data)

    def _process_movie_streams(self, movie_data: Dict, config: Dict) -> List[Dict]:
        """Generate movie streams."""
        streams = []
        movielink = movie_data.get('movielink')
        if not movielink:
            return streams

        # Premium streams
        premium_urls = config.get('premium', [])
        for url in premium_urls:
            stream_url = url.rstrip('/') + '/' + movielink.lstrip('/')
            streams.append({
                'name': 'StreamFlix',
                'title': f"{movie_data.get('moviename', 'Movie')} - Premium",
                'url': stream_url,
                'quality': '1080p',
                'size': movie_data.get('movieduration', 'Unknown'),
                'headers': {
                    'Referer': 'https://api.streamflix.app',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            })

        # Regular movie streams
        movie_urls = config.get('movies', [])
        for url in movie_urls:
            stream_url = url.rstrip('/') + '/' + movielink.lstrip('/')
            streams.append({
                'name': 'StreamFlix',
                'title': f"{movie_data.get('moviename', 'Movie')} - Standard",
                'url': stream_url,
                'quality': '720p',
                'size': movie_data.get('movieduration', 'Unknown'),
                'headers': {
                    'Referer': 'https://api.streamflix.app',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            })

        self.log(f"Generated {len(streams)} movie streams", "DEBUG")
        return streams

    def _process_tv_streams(self, tv_data: Dict, config: Dict, season_num: int, episode_num: int) -> List[Dict]:
        """Generate TV streams."""
        streams = []
        movie_key = tv_data.get('moviekey')
        if not movie_key:
            return streams

        # Extract total seasons from movieduration (e.g., "3 Seasons")
        duration = tv_data.get('movieduration', '')
        season_match = re.search(r'(\d+)\s+Season', duration)
        total_seasons = int(season_match.group(1)) if season_match else 1

        # Get episodes via WebSocket
        episodes_data = self._get_episodes_via_websocket(movie_key, total_seasons)

        if episodes_data and season_num in episodes_data:
            season_episodes = episodes_data[season_num]
            episode_data = season_episodes.get(episode_num)
            if episode_data and episode_data.get('link'):
                link = episode_data['link']
                premium_urls = config.get('premium', [])
                for url in premium_urls:
                    stream_url = url.rstrip('/') + '/' + link.lstrip('/')
                    streams.append({
                        'name': 'StreamFlix',
                        'title': f"{tv_data.get('moviename', 'TV Show')} S{season_num:02d}E{episode_num:02d} - {episode_data.get('name', 'Episode')}",
                        'url': stream_url,
                        'quality': '1080p',
                        'size': f"{episode_data.get('runtime', 0)}min" if episode_data.get('runtime') else 'Unknown',
                        'headers': {
                            'Referer': 'https://api.streamflix.app',
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                        }
                    })
        # Fallback if WebSocket fails or no episodes found
        if not streams:
            self.log("Falling back to constructed TV URL", "DEBUG")
            premium_urls = config.get('premium', [])
            for url in premium_urls:
                fallback_url = f"{url.rstrip('/')}/tv/{movie_key}/s{season_num}/episode{episode_num}.mkv"
                streams.append({
                    'name': 'StreamFlix (Fallback)',
                    'title': f"{tv_data.get('moviename', 'TV Show')} S{season_num:02d}E{episode_num:02d}",
                    'url': fallback_url,
                    'quality': '720p',
                    'size': 'Unknown',
                    'headers': {
                        'Referer': 'https://api.streamflix.app',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                })

        self.log(f"Generated {len(streams)} TV streams", "DEBUG")
        return streams

    def resolve(self, url_or_id: str, media_type: str = 'movie', season: int = None, episode: int = None) -> str:
        """Main resolve method."""
        self.log("=" * 80)
        self.log(f"StreamFlix Resolver Started - {media_type} ID: {url_or_id}")

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

        try:
            # Get TMDB details
            tmdb_info = self._get_tmdb_details(tmdb_id, media_type)
            if not tmdb_info:
                raise Exception("Failed to fetch TMDB details")
            title = tmdb_info.get('title')
            year = tmdb_info.get('year')
            self.log(f"TMDB Info: '{title}' ({year})")

            # Search
            search_results = self._search_content(title, year, media_type)
            if not search_results:
                raise Exception("No search results found")

            selected = self._find_best_match(title, search_results)
            if not selected:
                raise Exception("No suitable match found")

            # Get config
            config = self._get_config()

            # Process streams
            if media_type == 'movie':
                streams = self._process_movie_streams(selected, config)
            else:
                if season is None or episode is None:
                    raise Exception("Season and episode required for TV shows")
                streams = self._process_tv_streams(selected, config, season, episode)

            if not streams:
                raise Exception("No playable streams found")

            # Build response
            playable_urls = []
            for s in streams:
                url = s['url']
                if '.m3u8' in url.lower():
                    stream_type = 'hls'
                elif '.mpd' in url.lower():
                    stream_type = 'dash'
                elif '.mp4' in url.lower() or '.mkv' in url.lower():
                    stream_type = 'mp4'
                else:
                    stream_type = 'direct'

                headers = s.get('headers', {})
                playable_urls.append({
                    'url': url,
                    'quality': s.get('quality', 'Unknown'),
                    'type': stream_type,
                    'headers': headers,
                    'server': 'StreamFlix',
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

    parser = argparse.ArgumentParser(description='StreamFlix Resolver')
    parser.add_argument('url_or_id', help='TMDB ID or URL')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie', help='Media type (default: movie)')
    parser.add_argument('--season', type=int, help='Season number (for TV)')
    parser.add_argument('--episode', type=int, help='Episode number (for TV)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON output')

    args = parser.parse_args()

    resolver = StreamFlixResolver(debug=args.debug)
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