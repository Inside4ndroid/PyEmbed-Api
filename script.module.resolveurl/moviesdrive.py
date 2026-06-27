#!/usr/bin/env python3
"""
MoviesDrive Resolver - Standalone Version
Returns JSON with stream URL and headers separated
Based on index.js, utils.js, constants.js from MoviesDrive provider
"""

import re
import json
import time
import urllib.request
import urllib.error
import ssl
from urllib.parse import urljoin, urlencode, urlparse
from bs4 import BeautifulSoup
import requests

__version__ = "1.0.2"

DOMAINS_URL = "https://raw.githubusercontent.com/phisher98/TVVVV/refs/heads/main/domains.json"
TMDB_API_KEY = "f3c627493095a7e40ceca68355c94c6d"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive"
}


class MoviesDriveResolver:
    def __init__(self, debug=False):
        self.debug = debug
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.main_url = None
        self.cache_main_url = None

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    def get_main_url(self):
        """Fetch dynamic main URL from GitHub, cache it."""
        if self.cache_main_url:
            return self.cache_main_url
        try:
            resp = requests.get(DOMAINS_URL, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                domain = data.get("moviesdrive") or data.get("Moviesdrive")
                if domain:
                    if not domain.startswith("http"):
                        domain = "https://" + domain
                    self.cache_main_url = domain.rstrip('/')
                    self.log(f"Main URL: {self.cache_main_url}")
                    return self.cache_main_url
        except Exception as e:
            self.log(f"Error fetching domains: {e}", "ERROR")
        # fallback
        self.cache_main_url = "https://new3.moviesdrives.my"
        self.log(f"Using fallback main URL: {self.cache_main_url}")
        return self.cache_main_url

    def _fetch_url(self, url, headers=None, timeout=15, method='GET', data=None, json_data=None, allow_redirects=True):
        """Fetch URL and return (success, content, error)."""
        if headers is None:
            headers = HEADERS.copy()
        if json_data:
            data = json.dumps(json_data)
            headers['Content-Type'] = 'application/json'
            method = 'POST'
        try:
            if method == 'GET':
                resp = self.session.get(url, headers=headers, timeout=timeout, allow_redirects=allow_redirects)
            else:
                resp = self.session.post(url, headers=headers, data=data, timeout=timeout, allow_redirects=allow_redirects)
            if resp.status_code >= 400:
                return False, None, f"HTTP Error {resp.status_code}"
            return True, resp.text, None
        except Exception as e:
            return False, None, str(e)

    def _get_tmdb_details(self, tmdb_id, media_type):
        """Get IMDB ID and title from TMDB."""
        url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}?api_key={TMDB_API_KEY}&append_to_response=external_ids"
        try:
            resp = requests.get(url, headers={'User-Agent': HEADERS['User-Agent']}, timeout=10)
            if resp.status_code != 200:
                self.log(f"TMDB API error: {resp.status_code}", "ERROR")
                return None, None, None
            data = resp.json()
            imdb_id = data.get('external_ids', {}).get('imdb_id')
            title = data.get('title') or data.get('name')
            year = data.get('release_date', '')[:4] if data.get('release_date') else data.get('first_air_date', '')[:4]
            return imdb_id, title, year
        except Exception as e:
            self.log(f"TMDB fetch error: {e}", "ERROR")
            return None, None, None

    def _extract_mdrive_links(self, url):
        """
        Extract server links from a modpro/search-recover page.
        Returns list of URLs (hubcloud, gdflix, gdlink, etc.).
        """
        self.log(f"Extracting from mdrive: {url}")
        success, html, err = self._fetch_url(url, headers=HEADERS)
        if not success:
            self.log(f"Failed to fetch mdrive: {err}", "ERROR")
            return []

        # Check if it's a search-recover.php page
        if "search-recover.php" in url:
            q_match = re.search(r'const Q_INITIAL\s*=\s*"([^"]+)"', html)
            token_match = re.search(r'const FROM_AC_TOKEN\s*=\s*"([^"]+)"', html)
            if q_match and token_match:
                api_base = url.split('?')[0]
                params = {
                    'api': 'search',
                    'q': q_match.group(1),
                    'page': '1',
                    'from_ac': token_match.group(1)
                }
                api_url = f"{api_base}?{urlencode(params)}"
                self.log(f"Search API: {api_url}")
                success2, api_data, err2 = self._fetch_url(api_url, headers={**HEADERS, 'Accept': 'application/json'})
                if success2:
                    try:
                        data = json.loads(api_data)
                        if data.get('hits'):
                            urls = [h.get('url') for h in data['hits'] if h.get('url')]
                            self.log(f"Found {len(urls)} links from API")
                            return urls
                    except:
                        pass

        # Regular page: find anchor links containing hubcloud, gdflix, gdlink
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        pattern = re.compile(r'hubcloud|gdflix|gdlink', re.I)
        for a in soup.find_all('a', href=True):
            href = a['href']
            if pattern.search(href):
                links.append(href)
        self.log(f"Found {len(links)} server links from page")
        return links

    def _hubcloud_extractor(self, url, referer):
        """
        Extract final download links from a hubcloud page.
        Returns list of dicts: {name, quality, url, size}
        """
        self.log(f"HubCloud extracting: {url}")
        try:
            # Replace hubcloud.ink with hubcloud.dad (as in JS)
            current_url = url.replace("hubcloud.ink", "hubcloud.dad")
            headers = {**HEADERS, 'Referer': referer}
            success, page_data, err = self._fetch_url(current_url, headers=headers)
            if not success:
                self.log(f"HubCloud fetch failed: {err}", "ERROR")
                return []

            # Check if we need to redirect to another page
            if "hubcloud.php" not in current_url:
                soup = BeautifulSoup(page_data, 'html.parser')
                next_href = None
                # Try #download button
                download_btn = soup.find(id="download")
                if download_btn and download_btn.get('href'):
                    next_href = download_btn['href']
                else:
                    # Try var url = '...'
                    match = re.search(r"var url = '([^']*)'", page_data)
                    if match:
                        next_href = match.group(1)
                if next_href:
                    if not next_href.startswith('http'):
                        parsed = urlparse(current_url)
                        base = f"{parsed.scheme}://{parsed.netloc}"
                        next_href = urljoin(base, next_href)
                    self.log(f"HubCloud next URL: {next_href}")
                    current_url = next_href
                    # Fetch the second page
                    success2, page_data2, err2 = self._fetch_url(current_url, headers={**HEADERS, 'Referer': current_url})
                    if success2:
                        page_data = page_data2

            # Parse final page
            soup = BeautifulSoup(page_data, 'html.parser')
            # Get quality from header or size
            size = ""
            size_elem = soup.find(id="size")
            if size_elem:
                size = size_elem.get_text(strip=True)
            header_elem = soup.find("div", class_="card-header")
            quality = 1080
            if header_elem:
                header_text = header_elem.get_text(strip=True)
                q_match = re.search(r'(\d{3,4})[pP]', header_text)
                if q_match:
                    quality = int(q_match.group(1))

            # Collect all .btn anchors
            results = []
            for a in soup.select("a.btn"):
                link = a.get('href')
                text = a.get_text(strip=True).lower()
                if not link:
                    continue
                # Filter conditions from JS
                if ("download file" in text or
                    "fsl server" in text or
                    "s3 server" in text or
                    "fslv2" in text or
                    "mega server" in text or
                    (link and "r2.dev" in link)):
                    label = "HubCloud"
                    if link and "r2.dev" in link:
                        label = "Direct R2"
                    elif link and "workers.dev" in link:
                        label = "ZipDisk Server"
                    elif "fsl server" in text:
                        label = "HubCloud - FSL"
                    elif "s3 server" in text:
                        label = "HubCloud - S3"
                    elif "fslv2" in text:
                        label = "HubCloud - FSLv2"
                    elif "mega server" in text:
                        label = "HubCloud - Mega"
                    results.append({
                        'name': label,
                        'quality': quality,
                        'url': link,
                        'size': size
                    })
            self.log(f"HubCloud found {len(results)} links")
            return results
        except Exception as e:
            self.log(f"HubCloud extract error: {e}", "ERROR")
            return []

    def _load_extractor(self, url, referer):
        """
        Choose extractor based on hostname.
        Returns list of stream dicts {name, quality, url, size?}
        """
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if "hubcloud" in hostname:
            return self._hubcloud_extractor(url, referer)
        if "gdflix" in hostname or "gdlink" in hostname:
            # For gdflix/gdlink, we treat as direct link (no further extraction)
            return [{"name": "Google Drive", "quality": 1080, "url": url, "size": None}]
        # fallback
        return []

    def resolve(self, tmdb_id, media_type='movie', season=None, episode=None):
        """
        Main resolve method.
        Returns JSON string with status and playable_urls.
        """
        self.log("=" * 80)
        self.log(f"MoviesDrive Resolver - {media_type} ID: {tmdb_id}")
        if media_type == 'tv' and season is not None and episode is not None:
            self.log(f"Season: {season}, Episode: {episode}")

        # Get IMDB ID from TMDB
        imdb_id, title, year = self._get_tmdb_details(tmdb_id, media_type)
        if not imdb_id:
            return json.dumps({
                'status': 'error',
                'message': 'Failed to get IMDB ID from TMDB'
            })
        self.log(f"IMDB ID: {imdb_id}, Title: {title}, Year: {year}")

        main_url = self.get_main_url()

        # --- Step 1: Search by IMDB ID ---
        search_url = f"{main_url}/search.php?q={imdb_id}"
        self.log(f"Search URL (IMDB): {search_url}")
        success, search_data, err = self._fetch_url(search_url, headers=HEADERS)
        if not success:
            return json.dumps({
                'status': 'error',
                'message': f'Search request failed: {err}'
            })

        try:
            search_json = json.loads(search_data)
        except:
            return json.dumps({
                'status': 'error',
                'message': 'Invalid search response JSON'
            })

        if self.debug:
            self.log(f"Search response: {json.dumps(search_json, indent=2)}", "DEBUG")

        hits = search_json.get('hits', [])
        match = None

        # Try exact imdb_id match first
        for hit in hits:
            doc = hit.get('document')
            if doc:
                doc_imdb = doc.get('imdb_id') or doc.get('imdb')
                if doc_imdb == imdb_id:
                    match = doc
                    self.log(f"Exact IMDB match found: {doc.get('post_title')}")
                    break

        # --- Fallback 1: title/year matching on current results ---
        if not match and title:
            self.log("No exact IMDB match, trying title/year fallback on current results")
            for hit in hits:
                doc = hit.get('document')
                if not doc:
                    continue
                post_title = doc.get('post_title', '')
                post_date = doc.get('post_date', '')
                # Extract year from post_title (look for 4-digit year)
                title_year_match = re.search(r'\b(19|20)\d{2}\b', post_title)
                doc_year = title_year_match.group(0) if title_year_match else None
                if not doc_year:
                    # Try from post_date (e.g., "April 1, 2026")
                    date_match = re.search(r'(\d{4})', post_date)
                    if date_match:
                        doc_year = date_match.group(1)
                # Check if our title appears in post_title (case-insensitive)
                if title.lower() in post_title.lower():
                    # Check year if we have it and doc_year matches
                    if year and doc_year and doc_year == year:
                        match = doc
                        self.log(f"Title/year match found: {post_title} ({doc_year})")
                        break
                    elif not year:
                        # If no year, just title match is enough
                        match = doc
                        self.log(f"Title match found (no year check): {post_title}")
                        break

        # --- Fallback 2: Search using title ---
        if not match and title:
            self.log(f"No match in IMDB search results, trying title search: {title}")
            search_url_title = f"{main_url}/search.php?q={title.replace(' ', '+')}"
            success2, search_data2, err2 = self._fetch_url(search_url_title, headers=HEADERS)
            if success2:
                try:
                    search_json2 = json.loads(search_data2)
                    hits2 = search_json2.get('hits', [])
                    for hit in hits2:
                        doc = hit.get('document')
                        if not doc:
                            continue
                        post_title = doc.get('post_title', '')
                        post_date = doc.get('post_date', '')
                        doc_imdb = doc.get('imdb_id') or doc.get('imdb')
                        # Prefer match with imdb_id if available
                        if doc_imdb == imdb_id:
                            match = doc
                            self.log(f"Title search found exact IMDB match: {post_title}")
                            break
                        # Otherwise fallback to title/year match
                        title_year_match = re.search(r'\b(19|20)\d{2}\b', post_title)
                        doc_year = title_year_match.group(0) if title_year_match else None
                        if not doc_year:
                            date_match = re.search(r'(\d{4})', post_date)
                            if date_match:
                                doc_year = date_match.group(1)
                        if title.lower() in post_title.lower():
                            if year and doc_year and doc_year == year:
                                match = doc
                                self.log(f"Title search found title/year match: {post_title}")
                                break
                            elif not year:
                                match = doc
                                self.log(f"Title search found title match: {post_title}")
                                break
                except:
                    pass

        if not match:
            if self.debug:
                self.log("Available documents from last search:")
                for hit in hits:
                    doc = hit.get('document')
                    if doc:
                        self.log(f"  {doc.get('post_title')} ({doc.get('post_date')}) - IMDB: {doc.get('imdb_id')}")
            return json.dumps({
                'status': 'error',
                'message': 'No matching document found'
            })

        permalink = match.get('permalink')
        if not permalink:
            return json.dumps({
                'status': 'error',
                'message': 'No permalink in match'
            })

        if not permalink.startswith('http'):
            permalink = urljoin(main_url, permalink)
        self.log(f"Content page: {permalink}")

        # Fetch content page
        success, page_html, err = self._fetch_url(permalink, headers=HEADERS)
        if not success:
            return json.dumps({
                'status': 'error',
                'message': f'Failed to fetch content page: {err}'
            })

        soup = BeautifulSoup(page_html, 'html.parser')
        all_streams = []  # list of final stream dicts

        if media_type == 'movie':
            # Get all h5 > a links (download links)
            download_links = []
            for h5 in soup.find_all('h5'):
                a = h5.find('a')
                if a and a.get('href'):
                    download_links.append(a['href'])
            download_links = list(set(download_links))
            self.log(f"Found {len(download_links)} download links")

            for dlink in download_links:
                if not dlink.startswith('http'):
                    dlink = urljoin(main_url, dlink)
                # Extract server links from that mdrive page
                server_links = self._extract_mdrive_links(dlink)
                self.log(f"Server links from {dlink}: {len(server_links)}")
                for server_url in server_links:
                    # Use loadExtractor on each server URL
                    streams = self._load_extractor(server_url, referer=permalink)
                    for s in streams:
                        final_url = s['url']
                        quality = f"{s['quality']}p" if s['quality'] else "Auto"
                        headers = {
                            'User-Agent': HEADERS['User-Agent'],
                            'Referer': permalink,
                        }
                        all_streams.append({
                            'url': final_url,
                            'quality': quality,
                            'headers': headers,
                            'server': s.get('name', 'MoviesDrive'),
                            'size': s.get('size'),
                        })
        else:
            # TV Series
            stag = f"Season {season}" if season else "Season"
            sep_pattern = f"Ep{episode:02d}|Ep{episode}" if episode else ""
            # Find h5 elements that contain season text
            season_h5s = []
            for h5 in soup.find_all('h5'):
                text = h5.get_text(strip=True)
                if re.search(stag, text, re.I):
                    season_h5s.append(h5)
            self.log(f"Found {len(season_h5s)} season h5 entries")

            for h5 in season_h5s:
                # The next sibling may contain links; but JS uses .next() and .next().find('a')
                # We'll traverse siblings
                next_sib = h5.find_next_sibling()
                if not next_sib:
                    continue
                # Find first a inside next sibling
                a = next_sib.find('a')
                if not a or not a.get('href'):
                    continue
                ep_page_url = a['href']
                if not ep_page_url.startswith('http'):
                    ep_page_url = urljoin(main_url, ep_page_url)
                self.log(f"Episode page: {ep_page_url}")

                # Fetch episode page
                success_ep, ep_html, err_ep = self._fetch_url(ep_page_url, headers=HEADERS)
                if not success_ep:
                    self.log(f"Failed to fetch episode page: {err_ep}", "ERROR")
                    continue
                soup_ep = BeautifulSoup(ep_html, 'html.parser')
                # Find h5 with episode pattern
                for h5_ep in soup_ep.find_all('h5'):
                    text_ep = h5_ep.get_text(strip=True)
                    if sep_pattern and re.search(sep_pattern, text_ep, re.I):
                        # Get links from next siblings
                        next_sib2 = h5_ep.find_next_sibling()
                        if not next_sib2:
                            continue
                        # Get first a
                        a1 = next_sib2.find('a')
                        # Also check next next sibling (as JS does .next().next().find('a'))
                        next_sib3 = next_sib2.find_next_sibling()
                        a2 = next_sib3.find('a') if next_sib3 else None
                        ep_links = []
                        if a1 and a1.get('href'):
                            ep_links.append(a1['href'])
                        if a2 and a2.get('href'):
                            ep_links.append(a2['href'])
                        ep_links = list(set(ep_links))
                        self.log(f"Found {len(ep_links)} episode download links")

                        for ep_link in ep_links:
                            if not ep_link.startswith('http'):
                                ep_link = urljoin(main_url, ep_link)
                            # Extract server links from mdrive
                            server_links = self._extract_mdrive_links(ep_link)
                            for server_url in server_links:
                                streams = self._load_extractor(server_url, referer=ep_page_url)
                                for s in streams:
                                    final_url = s['url']
                                    quality = f"{s['quality']}p" if s['quality'] else "Auto"
                                    headers = {
                                        'User-Agent': HEADERS['User-Agent'],
                                        'Referer': ep_page_url,
                                    }
                                    all_streams.append({
                                        'url': final_url,
                                        'quality': quality,
                                        'headers': headers,
                                        'server': s.get('name', 'MoviesDrive'),
                                        'size': s.get('size'),
                                    })

        if not all_streams:
            return json.dumps({
                'status': 'error',
                'message': 'No playable streams found'
            })

        # Build final response
        response = {
            'status': 'success',
            'tmdb_id': tmdb_id,
            'playable_urls': all_streams
        }
        self.log(f"Total streams: {len(all_streams)}")
        self.log("=" * 80)
        return json.dumps(response, indent=2)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='MoviesDrive Resolver')
    parser.add_argument('tmdb_id', help='TMDB ID')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie', help='Media type')
    parser.add_argument('--season', type=int, help='Season number (for TV)')
    parser.add_argument('--episode', type=int, help='Episode number (for TV)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON output')

    args = parser.parse_args()

    resolver = MoviesDriveResolver(debug=args.debug)
    result_json = resolver.resolve(args.tmdb_id, args.type, args.season, args.episode)

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