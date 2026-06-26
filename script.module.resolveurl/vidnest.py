#!/usr/bin/env python3
"""
VidNest Resolver - Standalone Version
Returns JSON with all backend results and headers separated
Compatible with AndroResolveURL
"""

import re
import json
import time
import threading
from queue import Queue
import urllib.request
import urllib.error
import ssl

# Custom alphabet used by VidNest for encoding
VIDNEST_ALPHABET = "RB0fpH8ZEyVLkv7c2i6MAJ5u3IKFDxlS1NTsnGaqmXYdUrtzjwObCgQP94hoeW+/="

# Backend configurations
BACKENDS = [
    {'name': 'MoviesAPI', 'path': 'moviesapi'},
    {'name': 'HollyMovieHD', 'path': 'hollymoviehd'},
    {'name': 'AllMovies', 'path': 'allmovies'},
    {'name': 'VidLink', 'path': 'vidlink'},
    {'name': 'KlikXXI', 'path': 'klikxxi'},
    {'name': 'Movies4F', 'path': 'movies4f'},
    {'name': 'MovieBox', 'path': 'moviebox'},
    {'name': 'Videasy', 'path': 'videasy'},
    {'name': 'Movies5F', 'path': 'movies5f'},
]

# User agents for different requests
USER_AGENTS = {
    'default': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'api': 'Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0',
    'mobile': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
}


class VidNestResolver:
    def __init__(self, debug=False):
        self.debug = debug
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    def _fetch_url(self, url, headers=None, timeout=15):
        if headers is None:
            headers = {
                'User-Agent': USER_AGENTS['default'],
                'Accept': 'application/json, */*',
            }
        try:
            req = urllib.request.Request(url, headers=headers)
            response = urllib.request.urlopen(req, timeout=timeout, context=self.ssl_context)
            content = response.read().decode('utf-8', errors='ignore')
            return True, content, None
        except urllib.error.HTTPError as e:
            return False, None, f"HTTP Error {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            return False, None, f"URL Error: {str(e)}"
        except Exception as e:
            return False, None, f"Error: {str(e)}"

    def resolve(self, url_or_id, is_tv=False):
        self.log("=" * 80)
        self.log("VidNest Resolver Started - Standalone Mode")

        if url_or_id.startswith('http'):
            match = re.search(r'/movie/(\d+)', url_or_id)
            if not match:
                match = re.search(r'/tv/(\d+)', url_or_id)
            if match:
                media_id = match.group(1)
            else:
                return json.dumps({
                    'status': 'error',
                    'message': 'Could not extract media ID from URL'
                })
        else:
            media_id = url_or_id

        self.log(f"Media ID: {media_id}")
        self.log(f"Content Type: {'TV Show' if is_tv else 'Movie'}")

        tmdb_id = media_id
        self.log(f"TMDB ID: {tmdb_id}")

        self.log(f"Starting parallel backend resolution...")
        self.log(f"Total backends to try: {len(BACKENDS)}")

        results = self._try_all_backends(tmdb_id, is_tv)
        json_response = self._build_json_response(results)
        self._log_results_summary(results)

        self.log("=" * 80)
        return json.dumps(json_response, indent=2)

    def _try_all_backends(self, tmdb_id, is_tv=False):
        results = []
        threads = []
        result_queue = Queue()

        for backend in BACKENDS:
            thread = threading.Thread(
                target=self._try_backend_thread,
                args=(tmdb_id, backend, is_tv, result_queue)
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join(timeout=15)

        while not result_queue.empty():
            results.append(result_queue.get())

        return results

    def _try_backend_thread(self, tmdb_id, backend, is_tv, result_queue):
        result = {
            'backend': backend['name'],
            'path': backend['path'],
            'success': False,
            'url': None,
            'headers': None,
            'error': None,
            'response_time': 0,
            'raw_data': None
        }

        start_time = time.time()

        try:
            self.log(f"Thread started for backend: {backend['name']}", "DEBUG")

            if is_tv:
                api_url = f'https://new.vidnest.fun/{backend["path"]}/tv/{tmdb_id}/1/1'
            else:
                api_url = f'https://new.vidnest.fun/{backend["path"]}/movie/{tmdb_id}'

            headers = {
                'User-Agent': USER_AGENTS['api'],
                'Accept': 'application/json, */*',
                'Origin': 'https://vidnest.fun',
                'Referer': 'https://vidnest.fun/',
            }

            success, content, error = self._fetch_url(api_url, headers)

            if not success:
                result['error'] = error
                result['response_time'] = time.time() - start_time
                result_queue.put(result)
                return

            response_data = json.loads(content)
            result['raw_data'] = response_data

            if response_data.get('encrypted', False):
                encrypted_data = response_data.get('data', '')
                decrypted_data = self._decrypt_vidnest(encrypted_data)
                if decrypted_data:
                    stream_url = self._parse_stream_data(decrypted_data)
                    if stream_url:
                        result['url'] = stream_url
                        result['success'] = True
                        result['headers'] = self._get_headers_for_url(stream_url)
            else:
                stream_url = self._parse_stream_data(response_data)
                if stream_url:
                    result['url'] = stream_url
                    result['success'] = True
                    result['headers'] = self._get_headers_for_url(stream_url)

        except Exception as e:
            result['error'] = str(e)
            result['success'] = False

        result['response_time'] = time.time() - start_time
        result_queue.put(result)

    def _get_headers_for_url(self, url):
        headers = {
            'User-Agent': USER_AGENTS['default'],
            'Referer': 'https://vidnest.fun/',
            'Origin': 'https://vidnest.fun',
        }
        if 'tripplestream' in url:
            headers['Accept'] = '*/*'
        elif 'hakunaymatata' in url:
            headers['Accept'] = '*/*'
        elif 'halcyoncreative' in url:
            headers['Accept'] = '*/*'
        return headers

    def _decrypt_vidnest(self, data):
        if not data:
            return None

        try:
            lookup = {char: idx for idx, char in enumerate(VIDNEST_ALPHABET)}
            result = bytearray()
            i = 0

            while i < len(data):
                chunk = data[i:i+4]
                while len(chunk) < 4:
                    chunk += '='

                vals = []
                for char in chunk:
                    if char in lookup:
                        vals.append(lookup[char])
                    else:
                        vals.append(64)

                if len(vals) >= 4:
                    result.append((vals[0] << 2) | (vals[1] >> 4))
                    if vals[2] != 64:
                        result.append(((vals[1] & 15) << 4) | (vals[2] >> 2))
                    if vals[3] != 64:
                        result.append(((vals[2] & 3) << 6) | vals[3])

                i += 4

            try:
                decoded = result.decode('utf-8')
                return json.loads(decoded)
            except:
                result_str = result.decode('utf-8', errors='ignore')
                json_match = re.search(r'\{.*\}', result_str, re.DOTALL)
                if json_match:
                    try:
                        return json.loads(json_match.group(0))
                    except:
                        pass
                return result_str

        except Exception as e:
            self.log(f"Decryption error: {str(e)}", "ERROR")
            return None

    def _parse_stream_data(self, data):
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except:
                json_match = re.search(r'\{.*\}', data, re.DOTALL)
                if json_match:
                    try:
                        data = json.loads(json_match.group(0))
                    except:
                        return None
                else:
                    return None

        if not isinstance(data, dict):
            return None

        if 'sources' in data and data['sources']:
            sources = data['sources']
            if isinstance(sources, list) and sources:
                for source in sources:
                    if isinstance(source, dict) and source.get('url'):
                        url = source['url']
                        if url.startswith('//'):
                            url = 'https:' + url
                        if self._is_valid_stream_url(url):
                            return url

        if 'streams' in data and data['streams']:
            streams = data['streams']
            if isinstance(streams, list) and streams:
                for stream in streams:
                    if isinstance(stream, dict) and stream.get('url'):
                        url = stream['url']
                        if url.startswith('//'):
                            url = 'https:' + url
                        if self._is_valid_stream_url(url):
                            return url

        if 'data' in data and isinstance(data['data'], dict):
            if 'downloads' in data['data']:
                downloads = data['data']['downloads']
                if isinstance(downloads, list) and downloads:
                    best = None
                    best_res = 0
                    for dl in downloads:
                        if isinstance(dl, dict) and dl.get('url'):
                            res = dl.get('resolution', 0)
                            if res > best_res:
                                best_res = res
                                best = dl
                    if best and best.get('url'):
                        url = best['url']
                        if url.startswith('//'):
                            url = 'https:' + url
                        if self._is_valid_stream_url(url):
                            return url

        if 'url' in data and data['url']:
            url = data['url']
            if url.startswith('//'):
                url = 'https:' + url
            if self._is_valid_stream_url(url):
                return url

        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, str) and (value.startswith('http') or value.startswith('//')):
                    if any(ext in value.lower() for ext in ['.m3u8', '.mp4', '.mkv', '.ts', '.webm']):
                        if value.startswith('//'):
                            value = 'https:' + value
                        return value

        return None

    def _is_valid_stream_url(self, url):
        if not url:
            return False
        valid_extensions = ['.m3u8', '.mp4', '.mkv', '.ts', '.webm']
        if any(ext in url.lower() for ext in valid_extensions):
            return True
        if any(domain in url.lower() for domain in ['video', 'stream', 'cdn']):
            return True
        if url.startswith(('http://', 'https://')):
            return True
        return False

    def _build_json_response(self, results):
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]

        response = {
            'status': 'success' if successful else 'error',
            'total_backends': len(results),
            'successful_backends': len(successful),
            'failed_backends': len(failed),
            'results': [],
            'playable_urls': []
        }

        for result in results:
            result_data = {
                'backend': result['backend'],
                'path': result['path'],
                'success': result['success'],
                'response_time': round(result['response_time'], 3),
                'error': result.get('error')
            }

            if result['success'] and result['url']:
                headers = result.get('headers', {})
                result_data['url'] = result['url']  # raw URL only
                result_data['headers'] = headers

                # Add to playable URLs
                response['playable_urls'].append({
                    'backend': result['backend'],
                    'url': result['url'],  # raw URL only
                    'headers': headers
                })

            response['results'].append(result_data)

        # Sort playable URLs by quality preference (MP4 first, then M3U8)
        def url_priority(item):
            url = item['url'].lower()
            if '.mp4' in url:
                return 3
            elif '.m3u8' in url:
                return 2
            else:
                return 1

        response['playable_urls'].sort(key=url_priority, reverse=True)

        return response

    def _log_results_summary(self, results):
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]

        self.log("=" * 80)
        self.log("BACKEND RESULTS SUMMARY:")
        self.log(f"Successful backends: {len(successful)}")
        for r in successful:
            url_preview = r['url'][:100] + '...' if len(r['url']) > 100 else r['url']
            self.log(f"  ✓ {r['backend']}: {url_preview} ({r['response_time']:.2f}s)")

        self.log(f"Failed backends: {len(failed)}")
        for r in failed:
            self.log(f"  ✗ {r['backend']}: {r.get('error', 'Unknown error')} ({r['response_time']:.2f}s)")
        self.log("=" * 80)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='VidNest Resolver')
    parser.add_argument('url_or_id', help='VidNest URL or media ID')
    parser.add_argument('--tv', action='store_true', help='Treat as TV show')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON output')

    args = parser.parse_args()

    resolver = VidNestResolver(debug=args.debug)
    result_json = resolver.resolve(args.url_or_id, args.tv)

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