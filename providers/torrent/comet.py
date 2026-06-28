#!/usr/bin/env python3
"""
Comet Provider – Fetches debrid-resolved streams from comet.elfhosted.com.
Requires debrid API keys passed via command line.
"""

import re
import json
import sys
import base64
import urllib.request
import urllib.error
import ssl

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

SOURCE = "comet"
BASE_URL = "https://comet.elfhosted.com"

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


def get_imdb_id(tmdb_id, media_type):
    url = f"https://api.themoviedb.org/3/{'tv' if media_type == 'tv' else 'movie'}/{tmdb_id}/external_ids?api_key={TMDB_API_KEY}"
    data = fetch_json(url)
    return data.get('imdb_id')


def get_data(tmdb_id=None, media_type='movie', season=None, episode=None,
             realdebrid=None, torbox=None, premiumize=None, alldebrid=None):
    if not tmdb_id:
        return {'source': SOURCE, 'error': 'tmdb_id required'}

    debrid_services = []
    if realdebrid:
        debrid_services.append({'service': 'realdebrid', 'apiKey': realdebrid})
    if torbox:
        debrid_services.append({'service': 'torbox', 'apiKey': torbox})
    if premiumize:
        debrid_services.append({'service': 'premiumize', 'apiKey': premiumize})
    if alldebrid:
        debrid_services.append({'service': 'alldebrid', 'apiKey': alldebrid})

    if not debrid_services:
        return {'source': SOURCE, 'error': 'At least one debrid API key required (--realdebrid, --torbox, --premiumize, --alldebrid)'}

    config = {
        'maxResultsPerResolution': 0,
        'maxSize': 0,
        'cachedOnly': True,
        'sortCachedUncachedTogether': False,
        'removeTrash': True,
        'resultFormat': ['all'],
        'debridServices': debrid_services,
        'enableTorrent': False,
        'deduplicateStreams': False,
        'scrapeDebridAccountTorrents': False,
        'debridStreamProxyPassword': '',
        'languages': {
            'required': [],
            'allowed': [],
            'exclude': [],
            'preferred': [],
        },
        'resolutions': {
            'unknown': False,
        },
        'options': {
            'remove_ranks_under': -10000000000,
            'allow_english_in_languages': False,
            'remove_unknown_languages': False,
        },
    }

    config_b64 = base64.urlsafe_b64encode(json.dumps(config).encode()).decode()

    imdb_id = get_imdb_id(tmdb_id, media_type)
    if not imdb_id:
        return {'source': SOURCE, 'error': f'Could not resolve IMDB ID for tmdbId={tmdb_id}'}

    if media_type == 'tv' and season is not None and episode is not None:
        path = f"stream/series/{imdb_id}:{season}:{episode}.json"
    else:
        path = f"stream/movie/{imdb_id}.json"

    url = f"{BASE_URL}/{config_b64}/{path}"
    try:
        text = fetch_url(url)
    except urllib.error.HTTPError as e:
        return {'source': SOURCE, 'error': f"HTTP {e.code}"}

    data = json.loads(text)
    raw_streams = data.get('streams', [])

    streams = []
    for s in raw_streams:
        stream_url = s.get('url')
        if not stream_url:
            continue
        name = s.get('name', 'Comet')
        desc = s.get('description', '')
        desc_lines = desc.split('\n')
        subtitle = ' | '.join(desc_lines[1:]) if len(desc_lines) > 1 else desc

        seeders_m = re.search(r'[\U0001F464]\s*(\d+)', desc)
        seeders = int(seeders_m.group(1)) if seeders_m else 0

        stream_type = 'hls' if '.m3u8' in stream_url else 'direct'

        streams.append({
            'name': name,
            'url': stream_url,
            'type': stream_type,
            'seeders': seeders,
            'description': subtitle or None,
        })

    streams.sort(key=lambda x: x['seeders'], reverse=True)
    streams = streams[:15]

    return {
        'source': SOURCE,
        'imdb_id': imdb_id,
        'total': len(streams),
        'streams': streams,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Comet Provider')
    parser.add_argument('tmdb_id', help='TMDB ID')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie')
    parser.add_argument('--season', type=int)
    parser.add_argument('--episode', type=int)
    parser.add_argument('--realdebrid', help='RealDebrid API key')
    parser.add_argument('--torbox', help='TorBox API key')
    parser.add_argument('--premiumize', help='Premiumize API key')
    parser.add_argument('--alldebrid', help='AllDebrid API key')
    args = parser.parse_args()

    try:
        result = get_data(args.tmdb_id, args.type, args.season, args.episode,
                          args.realdebrid, args.torbox, args.premiumize, args.alldebrid)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'source': SOURCE, 'error': str(e)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
