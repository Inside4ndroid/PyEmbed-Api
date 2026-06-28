#!/usr/bin/env python3
"""
Torrentio Provider – Fetches torrent streams from torrentio.strem.fun Stremio addon.
Requires TMDB ID (resolved to IMDB ID internally).
"""

import re
import json
import sys
import urllib.request
import urllib.error
import ssl

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

SOURCE = "torrentio"
BASE_URL = "https://torrentio.strem.fun/sort=seeders/stream"

TMDB_API_KEY = "1865f43a0549ca50d341dd9ab8b29f49"


def fetch_url(url, headers=None):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req_headers = {'User-Agent': 'Mozilla/5.0'}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    resp = urllib.request.urlopen(req, context=ctx, timeout=30)
    return resp.read().decode('utf-8', errors='replace')


def fetch_json(url):
    return json.loads(fetch_url(url))


def get_imdb_id(tmdb_id, media_type):
    url = f"https://api.themoviedb.org/3/{'tv' if media_type == 'tv' else 'movie'}/{tmdb_id}/external_ids?api_key={TMDB_API_KEY}"
    data = fetch_json(url)
    return data.get('imdb_id')


def parse_seeders(title):
    m = re.search(r'[\U0001F464]\s*(\d+)', title)
    return int(m.group(1)) if m else 0


def parse_quality(name):
    lower = name.lower()
    if '2160p' in lower or '4k' in lower:
        return '2160p'
    if '1080p' in lower:
        return '1080p'
    if '720p' in lower:
        return '720p'
    if '480p' in lower:
        return '480p'
    return 'Unknown'


def parse_size(title):
    m = re.search(r'[\U0001F4BE]\s*([\d.]+\s*[KMGT]B)', title, re.I)
    return m.group(1) if m else ''


def get_data(tmdb_id=None, media_type='movie', season=None, episode=None):
    if not tmdb_id:
        return {'source': SOURCE, 'error': 'tmdb_id required'}

    imdb_id = get_imdb_id(tmdb_id, media_type)
    if not imdb_id:
        return {'source': SOURCE, 'error': f'Could not resolve IMDB ID for tmdbId={tmdb_id}'}

    if media_type == 'tv' and season is not None and episode is not None:
        api_url = f"{BASE_URL}/series/{imdb_id}:{season}:{episode}.json"
    else:
        api_url = f"{BASE_URL}/movie/{imdb_id}.json"

    try:
        text = fetch_url(api_url)
    except urllib.error.HTTPError:
        return {'source': SOURCE, 'imdb_id': imdb_id, 'total': 0, 'torrents': []}

    data = json.loads(text)
    raw_streams = data.get('streams', [])

    torrents = []
    for s in raw_streams:
        info_hash = s.get('infoHash')
        if not info_hash:
            continue
        title = s.get('title', '')
        name = s.get('name', '')

        seeders = parse_seeders(title)
        if seeders <= 1:
            continue

        quality = parse_quality(name)
        size = parse_size(title)

        torrents.append({
            'name': f"[DEBRID] Torrentio - {quality}",
            'quality': quality,
            'infoHash': info_hash,
            'seeders': seeders,
            'size': size or None,
            'magnet': f"magnet:?xt=urn:btih:{info_hash}",
            'fileIdx': s.get('fileIdx', 0),
        })

    torrents.sort(key=lambda x: x['seeders'], reverse=True)
    torrents = torrents[:5]

    return {
        'source': SOURCE,
        'imdb_id': imdb_id,
        'total': len(torrents),
        'torrents': torrents,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Torrentio Provider')
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
