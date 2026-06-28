#!/usr/bin/env python3
"""
TorrentDL Provider – Fetches torrent streams from torrentdownload.info RSS feed.
Uses TMDB title + year for movies, title + S01E01 for TV.
"""

import re
import json
import sys
import urllib.request
import urllib.error
import ssl
from urllib.parse import urlencode

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

SOURCE = "torrentdl"
FEED_URL = "https://www.torrentdownload.info/feed"

TMDB_API_KEY = "1865f43a0549ca50d341dd9ab8b29f49"


def fetch_url(url, headers=None):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req_headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    resp = urllib.request.urlopen(req, context=ctx, timeout=30)
    return resp.read().decode('utf-8', errors='replace')


def fetch_json(url):
    return json.loads(fetch_url(url))


def get_tmdb_details(tmdb_id, media_type):
    url = f"https://api.themoviedb.org/3/{'tv' if media_type == 'tv' else 'movie'}/{tmdb_id}?api_key={TMDB_API_KEY}"
    data = fetch_json(url)
    title = data.get('title') or data.get('name') or data.get('original_title', '')
    year = None
    date = data.get('release_date') or data.get('first_air_date')
    if date:
        year = date.split('-')[0]
    return {'title': title, 'year': year}


def parse_rss(xml):
    results = []
    for m in re.finditer(r'<item>([\s\S]*?)</item>', xml, re.I):
        item = m.group(1)

        title_m = re.search(r'<title>([\s\S]*?)</title>', item)
        if not title_m:
            continue
        title = re.sub(r'<!\[CDATA\[|]]>', '', title_m.group(1))
        title = title.replace('&amp;', '&').strip()

        desc_m = re.search(r'<description>([\s\S]*?)</description>', item)
        desc = re.sub(r'<!\[CDATA\[|]]>', '', desc_m.group(1)).strip() if desc_m else ''

        link_m = re.search(r'<link>([\s\S]*?)</link>', item)
        link = link_m.group(1).strip() if link_m else ''

        infohash = link.rstrip('/').split('/')[-1]
        if not re.match(r'^[a-fA-F0-9]{40}$', infohash):
            hash_m = re.search(r'Hash:\s*([a-fA-F0-9]{40})', desc, re.I)
            infohash = hash_m.group(1) if hash_m else None
        if not infohash:
            continue

        seeders_m = re.search(r'Seeds:\s*(\d+)', desc)
        seeders = int(seeders_m.group(1)) if seeders_m else 0

        size_m = re.search(r'Size:\s*([\d.]+\s*[KMGT]B)', desc, re.I)
        size = size_m.group(1) if size_m else ''

        quality = 'Unknown'
        lower = title.lower()
        if '2160p' in lower or '4k' in lower:
            quality = '2160p'
        elif '1080p' in lower:
            quality = '1080p'
        elif '720p' in lower:
            quality = '720p'
        elif '480p' in lower:
            quality = '480p'

        results.append({
            'title': title,
            'infoHash': infohash,
            'seeders': seeders,
            'size': size,
            'quality': quality,
            'magnet': f'magnet:?xt=urn:btih:{infohash}',
        })

    return results


def get_data(tmdb_id=None, media_type='movie', season=None, episode=None):
    if not tmdb_id:
        return {'source': SOURCE, 'error': 'tmdb_id required'}

    details = get_tmdb_details(tmdb_id, media_type)
    title = details['title']
    year = details['year']

    if media_type == 'tv' and season is not None and episode is not None:
        query = f"{title} s{season:02d}e{episode:02d}"
    else:
        query = f"{title} {year}" if year else title

    url = f"{FEED_URL}?q={urlencode({'': query})[1:]}"
    xml = fetch_url(url)
    items = parse_rss(xml)

    items = [i for i in items if i['seeders'] > 1]
    items.sort(key=lambda x: x['seeders'], reverse=True)
    items = items[:15]

    return {
        'source': SOURCE,
        'query': query,
        'total': len(items),
        'torrents': items,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description='TorrentDL Provider')
    parser.add_argument('tmdb_id', help='TMDB ID')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie')
    parser.add_argument('--season', type=int)
    parser.add_argument('--episode', type=int)
    args = parser.parse_args()

    try:
        result = get_data(args.tmdb_id, args.type, args.season, args.episode)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'source': SOURCE, 'error': str(e)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
