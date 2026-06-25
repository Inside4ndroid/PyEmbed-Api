"""
    ResolveURL
    Copyright (C) 2023 gujal

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import re
import json
import time
from resolveurl import common
from resolveurl.resolver import ResolveUrl, ResolverError

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

# Define logging levels if they don't exist in common
if not hasattr(common, 'LOGERROR'):
    common.LOGERROR = 4
if not hasattr(common, 'LOGWARNING'):
    common.LOGWARNING = 2
if not hasattr(common, 'LOGINFO'):
    common.LOGINFO = 1
if not hasattr(common, 'LOGDEBUG'):
    common.LOGDEBUG = 0


class VidNestResolver(ResolveUrl):
    name = "vidnest"
    domains = ["vidnest.fun", "new.vidnest.fun"]
    pattern = r'(?://|\.)(vidnest\.fun)/(?:embed/|movie/|tv/)?([0-9a-zA-Z]+)'

    def get_media_url(self, host, media_id):
        """
        Main method to get media URL from vidnest
        """
        common.logger.log('=' * 80, common.LOGINFO)
        common.logger.log('VidNest Resolver Started', common.LOGINFO)
        common.logger.log('Host: %s, Media ID: %s' % (host, media_id), common.LOGINFO)
        
        web_url = self.get_url(host, media_id)
        common.logger.log('Web URL: %s' % web_url, common.LOGINFO)
        
        # Common headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Origin': 'https://vidnest.fun',
            'Referer': 'https://vidnest.fun/',
            'Accept': 'application/json, */*',
        }

        try:
            # First try to get the webpage to find available servers
            common.logger.log('Fetching webpage: %s' % web_url, common.LOGINFO)
            start_time = time.time()
            
            html = self.net.http_GET(web_url, headers=headers).content
            if isinstance(html, bytes):
                html = html.decode('utf-8', errors='ignore')
            
            elapsed = time.time() - start_time
            common.logger.log('Webpage fetched in %.2f seconds' % elapsed, common.LOGINFO)
            
            # Log first 500 chars of HTML for debugging
            common.logger.log('HTML Preview: %s...' % html[:500], common.LOGDEBUG)
            
            # Check if it's a TV show or movie
            is_tv = '/tv/' in web_url
            common.logger.log('Content Type: %s' % ('TV Show' if is_tv else 'Movie'), common.LOGINFO)
            
            # Extract TMDB ID
            tmdb_id = self._extract_tmdb_id(html, media_id)
            if not tmdb_id:
                common.logger.log('ERROR: Could not extract TMDB ID', common.LOGERROR)
                raise ResolverError('Could not extract TMDB ID')
            
            common.logger.log('TMDB ID: %s' % tmdb_id, common.LOGINFO)

            # Try each backend in sequence with detailed logging
            successful_backends = []
            failed_backends = []
            
            common.logger.log('Starting backend resolution...', common.LOGINFO)
            common.logger.log('Total backends to try: %d' % len(BACKENDS), common.LOGINFO)
            
            for idx, backend in enumerate(BACKENDS, 1):
                common.logger.log('-' * 40, common.LOGINFO)
                common.logger.log('[%d/%d] Trying backend: %s' % (idx, len(BACKENDS), backend['name']), common.LOGINFO)
                common.logger.log('Backend path: %s' % backend['path'], common.LOGDEBUG)
                
                try:
                    start_time = time.time()
                    stream_url = self._try_backend(tmdb_id, backend, is_tv)
                    elapsed = time.time() - start_time
                    
                    if stream_url:
                        common.logger.log('✓ Backend %s returned a URL in %.2f seconds' % (backend['name'], elapsed), common.LOGINFO)
                        common.logger.log('Stream URL: %s' % stream_url, common.LOGINFO)
                        
                        # Verify the stream is accessible
                        common.logger.log('Verifying stream URL...', common.LOGDEBUG)
                        if self._verify_stream(stream_url):
                            common.logger.log('✓ Stream URL verified successfully', common.LOGINFO)
                            successful_backends.append({'name': backend['name'], 'url': stream_url})
                            
                            # Return the stream URL with any necessary headers
                            final_url = stream_url + '|User-Agent=' + headers['User-Agent'] + '&Referer=' + headers['Referer']
                            common.logger.log('=' * 80, common.LOGINFO)
                            common.logger.log('SUCCESS! Final URL: %s' % final_url, common.LOGINFO)
                            common.logger.log('=' * 80, common.LOGINFO)
                            return final_url
                        else:
                            common.logger.log('✗ Stream URL verification failed', common.LOGWARNING)
                            failed_backends.append({'name': backend['name'], 'error': 'Verification failed'})
                    else:
                        common.logger.log('✗ Backend %s returned no URL in %.2f seconds' % (backend['name'], elapsed), common.LOGWARNING)
                        failed_backends.append({'name': backend['name'], 'error': 'No URL returned'})
                        
                except Exception as e:
                    common.logger.log('✗ Backend %s error: %s' % (backend['name'], str(e)), common.LOGWARNING)
                    failed_backends.append({'name': backend['name'], 'error': str(e)})
                    continue

            # Log summary of all backends tried
            common.logger.log('=' * 80, common.LOGINFO)
            common.logger.log('RESOLUTION SUMMARY:', common.LOGINFO)
            common.logger.log('Successful backends: %d' % len(successful_backends), common.LOGINFO)
            for b in successful_backends:
                common.logger.log('  - %s: %s' % (b['name'], b['url'][:100] + '...'), common.LOGINFO)
            
            common.logger.log('Failed backends: %d' % len(failed_backends), common.LOGINFO)
            for b in failed_backends:
                common.logger.log('  - %s: %s' % (b['name'], b['error']), common.LOGINFO)
            
            common.logger.log('=' * 80, common.LOGINFO)
            raise ResolverError('No working streams found from any backend')
            
        except Exception as e:
            common.logger.log('VidNest fatal error: %s' % str(e), common.LOGERROR)
            raise ResolverError('Failed to resolve VidNest URL: %s' % str(e))

    def _extract_tmdb_id(self, html, media_id):
        """
        Extract TMDB ID from the page or use the provided ID
        """
        common.logger.log('Extracting TMDB ID...', common.LOGDEBUG)
        
        if not html:
            common.logger.log('HTML is empty, using media_id: %s' % media_id, common.LOGWARNING)
            return media_id if media_id.isdigit() else None
            
        # Try to find TMDB ID in the page
        patterns = [
            r'data-tmdbid=["\']?(\d+)["\']?',
            r'data-id=["\']?(\d+)["\']?',
            r'{"tmdb":(\d+)}',
            r'/movie/(\d+)',
            r'tmdb_id=(\d+)',
            r'tmdb=(\d+)',
            r'video_id=(\d+)',
        ]
        
        for pattern in patterns:
            tmdb_match = re.search(pattern, html, re.I)
            if tmdb_match:
                tmdb_id = tmdb_match.group(1)
                common.logger.log('TMDB ID found using pattern "%s": %s' % (pattern, tmdb_id), common.LOGDEBUG)
                return tmdb_id
        
        # If media_id looks like a TMDB ID, use it directly
        if media_id.isdigit():
            common.logger.log('Using media_id as TMDB ID: %s' % media_id, common.LOGWARNING)
            return media_id
        
        common.logger.log('No TMDB ID found in HTML or media_id', common.LOGWARNING)
        return None

    def _try_backend(self, tmdb_id, backend, is_tv=False):
        """
        Try to get stream from a specific backend
        """
        # Build API URL
        if is_tv:
            api_url = 'https://new.vidnest.fun/%s/tv/%s/1/1' % (backend['path'], tmdb_id)
        else:
            api_url = 'https://new.vidnest.fun/%s/movie/%s' % (backend['path'], tmdb_id)

        common.logger.log('API URL: %s' % api_url, common.LOGDEBUG)

        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Accept': 'application/json, */*',
            'Origin': 'https://vidnest.fun',
            'Referer': 'https://vidnest.fun/',
        }

        try:
            start_time = time.time()
            response = self.net.http_GET(api_url, headers=headers)
            elapsed = time.time() - start_time
            common.logger.log('API response received in %.2f seconds' % elapsed, common.LOGDEBUG)
            
            response_content = response.content
            if isinstance(response_content, bytes):
                response_content = response_content.decode('utf-8', errors='ignore')
            
            common.logger.log('Response content length: %d chars' % len(response_content), common.LOGDEBUG)
            common.logger.log('Response preview: %s...' % response_content[:200], common.LOGDEBUG)
            
            response_data = json.loads(response_content)
            common.logger.log('Response parsed as JSON successfully', common.LOGDEBUG)
            
            # Check if data is encrypted
            if response_data.get('encrypted', False):
                common.logger.log('Response is encrypted, decrypting...', common.LOGDEBUG)
                encrypted_data = response_data.get('data', '')
                common.logger.log('Encrypted data length: %d' % len(encrypted_data), common.LOGDEBUG)
                
                decrypted_data = self._decrypt_vidnest(encrypted_data)
                if decrypted_data:
                    common.logger.log('Decryption successful', common.LOGDEBUG)
                    if isinstance(decrypted_data, dict):
                        common.logger.log('Decrypted data keys: %s' % list(decrypted_data.keys()), common.LOGDEBUG)
                        common.logger.log('Decrypted data preview: %s' % str(decrypted_data)[:200], common.LOGDEBUG)
                    else:
                        common.logger.log('Decrypted data preview: %s...' % str(decrypted_data)[:200], common.LOGDEBUG)
                    return self._parse_stream_data(decrypted_data)
                else:
                    common.logger.log('Decryption failed', common.LOGWARNING)
            else:
                common.logger.log('Response is not encrypted, parsing directly', common.LOGDEBUG)
                common.logger.log('Response keys: %s' % list(response_data.keys()), common.LOGDEBUG)
                common.logger.log('Response preview: %s' % str(response_data)[:200], common.LOGDEBUG)
                return self._parse_stream_data(response_data)
                
        except json.JSONDecodeError as e:
            common.logger.log('JSON decode error: %s' % str(e), common.LOGWARNING)
            common.logger.log('Raw response: %s' % response_content[:500], common.LOGDEBUG)
        except Exception as e:
            common.logger.log('Backend error: %s' % str(e), common.LOGWARNING)
            
        return None

    def _decrypt_vidnest(self, data):
        """
        Decrypt VidNest's custom base64 encoding
        """
        if not data:
            common.logger.log('No data to decrypt', common.LOGWARNING)
            return None

        try:
            common.logger.log('Starting decryption...', common.LOGDEBUG)
            start_time = time.time()
            
            # Build lookup table
            lookup = {char: idx for idx, char in enumerate(VIDNEST_ALPHABET)}
            common.logger.log('Lookup table built with %d entries' % len(lookup), common.LOGDEBUG)
            
            result = bytearray()
            i = 0
            while i < len(data):
                chunk = data[i:i+4]
                # Pad chunk if necessary
                while len(chunk) < 4:
                    chunk += '='
                
                vals = []
                for char in chunk:
                    if char in lookup:
                        vals.append(lookup[char])
                    else:
                        vals.append(64)
                
                # Decode 4 chars into 3 bytes
                if len(vals) >= 4:
                    result.append((vals[0] << 2) | (vals[1] >> 4))
                    if vals[2] != 64:
                        result.append(((vals[1] & 15) << 4) | (vals[2] >> 2))
                    if vals[3] != 64:
                        result.append(((vals[2] & 3) << 6) | vals[3])
                
                i += 4
            
            elapsed = time.time() - start_time
            common.logger.log('Decryption completed in %.3f seconds, result length: %d bytes' % (elapsed, len(result)), common.LOGDEBUG)
            
            # Try to parse as JSON
            try:
                decoded = result.decode('utf-8')
                common.logger.log('Decoded string length: %d chars' % len(decoded), common.LOGDEBUG)
                common.logger.log('Decoded preview: %s...' % decoded[:200], common.LOGDEBUG)
                return json.loads(decoded)
            except Exception as e:
                common.logger.log('Failed to parse as JSON: %s' % str(e), common.LOGWARNING)
                
                # If not valid JSON, try to parse as string
                result_str = result.decode('utf-8', errors='ignore')
                common.logger.log('Result string preview: %s...' % result_str[:200], common.LOGDEBUG)
                
                # Try to find JSON in the string
                json_match = re.search(r'\{.*\}', result_str, re.DOTALL)
                if json_match:
                    try:
                        json_str = json_match.group(0)
                        common.logger.log('Found JSON in string: %s...' % json_str[:200], common.LOGDEBUG)
                        return json.loads(json_str)
                    except Exception as e2:
                        common.logger.log('Failed to parse extracted JSON: %s' % str(e2), common.LOGWARNING)
                
                common.logger.log('Returning as raw string', common.LOGDEBUG)
                return result_str
                
        except Exception as e:
            common.logger.log('Decryption error: %s' % str(e), common.LOGERROR)
            return None

    def _parse_stream_data(self, data):
        """
        Parse the decrypted stream data
        """
        common.logger.log('Parsing stream data...', common.LOGDEBUG)
        
        if isinstance(data, str):
            common.logger.log('Data is string, attempting JSON parse...', common.LOGDEBUG)
            try:
                data = json.loads(data)
                common.logger.log('String parsed to JSON successfully', common.LOGDEBUG)
            except:
                # Try to extract JSON from the string
                json_match = re.search(r'\{.*\}', data, re.DOTALL)
                if json_match:
                    try:
                        data = json.loads(json_match.group(0))
                        common.logger.log('JSON extracted from string', common.LOGDEBUG)
                    except:
                        common.logger.log('Failed to parse string as JSON', common.LOGWARNING)
                        return None
                else:
                    common.logger.log('No JSON found in string', common.LOGWARNING)
                    return None

        if not isinstance(data, dict):
            common.logger.log('Data is not a dictionary: %s' % type(data), common.LOGWARNING)
            return None

        common.logger.log('Data keys: %s' % list(data.keys()), common.LOGDEBUG)

        # Try sources format (moviesapi, hollymoviehd, vidlink, klikxxi)
        if 'sources' in data and data['sources']:
            sources = data['sources']
            common.logger.log('Found sources: %d items' % len(sources), common.LOGDEBUG)
            
            if isinstance(sources, list) and sources:
                # Prefer higher quality
                for idx, source in enumerate(sources):
                    if isinstance(source, dict) and source.get('url'):
                        url = source['url']
                        quality = source.get('quality', 'unknown')
                        common.logger.log('Source %d quality: %s, URL: %s' % (idx+1, quality, url[:100]), common.LOGDEBUG)
                        
                        if url.startswith('//'):
                            url = 'https:' + url
                        
                        if self._is_valid_stream_url(url):
                            common.logger.log('✓ Valid source URL found: %s' % url, common.LOGDEBUG)
                            return url

        # Try streams format (allmovies)
        if 'streams' in data and data['streams']:
            streams = data['streams']
            common.logger.log('Found streams: %d items' % len(streams), common.LOGDEBUG)
            
            if isinstance(streams, list) and streams:
                for idx, stream in enumerate(streams):
                    if isinstance(stream, dict) and stream.get('url'):
                        url = stream['url']
                        common.logger.log('Stream %d URL: %s' % (idx+1, url[:100]), common.LOGDEBUG)
                        
                        if url.startswith('//'):
                            url = 'https:' + url
                        
                        if self._is_valid_stream_url(url):
                            common.logger.log('✓ Valid stream URL found: %s' % url, common.LOGDEBUG)
                            return url

        # Try downloads format (movies4f)
        if 'data' in data and isinstance(data['data'], dict):
            common.logger.log('Checking data.downloads...', common.LOGDEBUG)
            
            if 'downloads' in data['data']:
                downloads = data['data']['downloads']
                common.logger.log('Found downloads: %d items' % len(downloads), common.LOGDEBUG)
                
                if isinstance(downloads, list) and downloads:
                    # Pick highest resolution
                    best = None
                    best_res = 0
                    for dl in downloads:
                        if isinstance(dl, dict) and dl.get('url'):
                            res = dl.get('resolution', 0)
                            common.logger.log('Download resolution: %d, URL: %s' % (res, dl['url'][:100]), common.LOGDEBUG)
                            if res > best_res:
                                best_res = res
                                best = dl
                    
                    if best and best.get('url'):
                        url = best['url']
                        common.logger.log('Best download resolution: %d' % best_res, common.LOGDEBUG)
                        
                        if url.startswith('//'):
                            url = 'https:' + url
                        
                        if self._is_valid_stream_url(url):
                            common.logger.log('✓ Valid download URL found: %s' % url, common.LOGDEBUG)
                            return url

        # Try direct URL
        if 'url' in data and data['url']:
            url = data['url']
            common.logger.log('Direct URL found: %s' % url[:100], common.LOGDEBUG)
            
            if url.startswith('//'):
                url = 'https:' + url
            
            if self._is_valid_stream_url(url):
                common.logger.log('✓ Valid direct URL found: %s' % url, common.LOGDEBUG)
                return url

        # Try to find any URL in the data
        if isinstance(data, dict):
            common.logger.log('Searching for any URL in data...', common.LOGDEBUG)
            
            for key, value in data.items():
                if isinstance(value, str) and (value.startswith('http') or value.startswith('//')):
                    common.logger.log('Found URL in key "%s": %s' % (key, value[:100]), common.LOGDEBUG)
                    
                    if any(ext in value.lower() for ext in ['.m3u8', '.mp4', '.mkv', '.ts', '.webm']):
                        if value.startswith('//'):
                            value = 'https:' + value
                        common.logger.log('✓ Found valid media URL: %s' % value, common.LOGDEBUG)
                        return value

        common.logger.log('No valid stream URL found in data', common.LOGWARNING)
        return None

    def _is_valid_stream_url(self, url):
        """
        Check if a URL looks like a valid stream URL
        """
        if not url:
            return False
        
        # Check if it's a valid URL
        valid_extensions = ['.m3u8', '.mp4', '.mkv', '.ts', '.webm']
        if any(ext in url.lower() for ext in valid_extensions):
            common.logger.log('URL has valid media extension', common.LOGDEBUG)
            return True
        
        # Check if it's an iframe URL that might contain a stream
        if 'embed' in url.lower() or 'player' in url.lower():
            common.logger.log('URL looks like an embed/player URL', common.LOGDEBUG)
            return True
            
        # Check if it's a streaming domain
        if any(domain in url.lower() for domain in ['video', 'stream', 'cdn', 'cloudfront', 'akamai']):
            common.logger.log('URL looks like a streaming domain', common.LOGDEBUG)
            return True
            
        # If it's a URL with http/https, it might work
        if url.startswith(('http://', 'https://')):
            common.logger.log('URL is a valid HTTP/HTTPS URL', common.LOGDEBUG)
            return True
            
        common.logger.log('URL does not look like a valid stream URL', common.LOGWARNING)
        return False

    def _verify_stream(self, url):
        """
        Verify that the stream URL is accessible
        """
        common.logger.log('Verifying stream URL: %s' % url[:100], common.LOGDEBUG)
        
        try:
            # Try a HEAD request to verify the URL exists
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://vidnest.fun/',
                'Range': 'bytes=0-1024'
            }
            
            start_time = time.time()
            response = self.net.http_HEAD(url, headers=headers)
            elapsed = time.time() - start_time
            
            common.logger.log('Verification response status: %d (took %.2f seconds)' % (response.status_code, elapsed), common.LOGDEBUG)
            
            if response.status_code < 400:
                common.logger.log('Stream URL verification successful', common.LOGDEBUG)
                return True
            else:
                common.logger.log('Stream URL verification failed with status: %d' % response.status_code, common.LOGWARNING)
                return False
                
        except Exception as e:
            common.logger.log('Stream URL verification error: %s' % str(e), common.LOGWARNING)
            # If we can't verify, assume it's working
            common.logger.log('Assuming URL is valid despite verification error', common.LOGDEBUG)
            return True

    def get_url(self, host, media_id):
        """
        Get the full URL for the media
        """
        return 'https://%s/movie/%s' % (host, media_id)

    def get_host_and_id(self, url):
        """
        Extract host and media ID from URL
        """
        r = re.search(self.pattern, url, re.I)
        if r:
            return r.groups()
        else:
            return False

    def valid_url(self, url, host):
        """
        Check if the URL is valid for this resolver
        """
        return re.search(self.pattern, url, re.I) is not None