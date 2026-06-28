#!/usr/bin/env python3
"""
EasyNews Provider – Searches Usenet via members.easynews.com API.
Requires EasyNews username and password.
Returns direct-playable video URLs (no torrents/magnets).
"""

import re
import json
import sys
import base64
import urllib.request
import urllib.error
import ssl
from urllib.parse import urlencode

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

SOURCE = "easynews"
BASE_URL = "https://members.easynews.com"
SEARCH_PATH = "/2.0/search/solr-search/advanced"
FILE_EXTENSIONS = "m4v,3gp,mov,divx,xvid,wmv,avi,mpg,mpeg,mp4,mkv,avc,flv,webm"
MAX_RESULTS = 15

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


def fetch_json(url, headers=None):
    return json.loads(fetch_url(url, headers))


def get_tmdb_details(tmdb_id, media_type):
    url = f"https://api.themoviedb.org/3/{'tv' if media_type == 'tv' else 'movie'}/{tmdb_id}?api_key={TMDB_API_KEY}"
    data = fetch_json(url)
    title = data.get('title') or data.get('name') or data.get('original_title', '')
    year = None
    date = data.get('release_date') or data.get('first_air_date')
    if date:
        year = date.split('-')[0]
    return {'title': title, 'year': year}


def sanitize_title(t):
    t = t.replace('&', 'and')
    t = re.sub(r'[.\-_:]+', ' ', t)
    t = re.sub(r'[^\w\s\xC0-\xFF]', '', t)
    return t.lower().strip()


def matches_query(post_title, query):
    sq = sanitize_title(query)
    st = sanitize_title(post_title)
    try:
        return bool(re.search(r'\b' + re.escape(sq) + r'\b', st, re.I))
    except Exception:
        return sq in st


def detect_quality(title, fallback_res):
    m = re.search(r'(4320p|2160p|1080p|1080i|720p|720i|576p|576i|480p|480i|360p)', title, re.I)
    if m:
        return m.group(1).lower()
    if fallback_res:
        return fallback_res
    return None


def is_bad_video(f):
    if f.get('passwd') or f.get('virus'):
        return True
    if f.get('type', '').upper() != 'VIDEO':
        return True
    duration = f.get('14', '')
    if re.match(r'^\d+s', duration):
        return True
    if re.match(r'^[0-5]m', duration):
        return True
    return False


def get_data(tmdb_id=None, media_type='movie', season=None, episode=None,
             username=None, password=None):
    if not tmdb_id:
        return {'source': SOURCE, 'error': 'tmdb_id required'}
    if not username or not password:
        return {'source': SOURCE, 'error': 'EasyNews username and password required (--username, --password)'}

    details = get_tmdb_details(tmdb_id, media_type)
    title = details['title']
    year = details['year']

    if media_type == 'tv' and season is not None and episode is not None:
        query = f"{title} S{season:02d}E{episode:02d}"
    else:
        query = f"{title} {year}" if year else title

    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    auth_header = f"Basic {auth}"

    encoded_query = urlencode({'': query})[1:]
    search_url = (
        f"{BASE_URL}{SEARCH_PATH}?st=adv&sb=1"
        f"&fex={FILE_EXTENSIONS}&fty[]=VIDEO"
        f"&spamf=1&u=1&gx=1&pno=1&sS=3"
        f"&s1=dsize&s1d=-&s2=relevance&s2d=-&s3=dtime&s3d=-"
        f"&pby=50&safeO=0&gps={encoded_query}"
    )

    try:
        resp = fetch_json(search_url, headers={'Authorization': auth_header})
    except urllib.error.HTTPError as e:
        return {'source': SOURCE, 'error': f"HTTP {e.code}"}

    down_url = resp.get('downURL', '').rstrip('/')
    dl_farm = resp.get('dlFarm', '')
    dl_port = resp.get('dlPort', '')
    data = resp.get('data', [])

    if not down_url or not dl_farm or not dl_port:
        return {'source': SOURCE, 'total': 0, 'streams': []}

    streams = []
    for f in data:
        if is_bad_video(f):
            continue

        post_hash = f.get('0', '')
        post_title = f.get('10', '')
        ext = f.get('11', '')
        size_str = f.get('4', '')
        full_res = f.get('fullres', '')

        if not post_hash or not post_title:
            continue
        if not matches_query(post_title, query):
            continue

        quality = detect_quality(post_title, full_res)
        stream_url = f"{down_url}/{dl_farm}/{dl_port}/{post_hash}{ext}/{post_title}{ext}"

        streams.append({
            'name': f"EasyNews {quality}" if quality else "EasyNews",
            'url': stream_url,
            'quality': quality,
            'type': 'direct',
            'size': size_str or None,
        })

        if len(streams) >= MAX_RESULTS:
            break

    return {
        'source': SOURCE,
        'query': query,
        'total': len(streams),
        'streams': streams,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description='EasyNews Provider')
    parser.add_argument('tmdb_id', help='TMDB ID')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie')
    parser.add_argument('--season', type=int)
    parser.add_argument('--episode', type=int)
    parser.add_argument('--username', help='EasyNews username')
    parser.add_argument('--password', help='EasyNews password')
    args = parser.parse_args()

    try:
        result = get_data(args.tmdb_id, args.type, args.season, args.episode,
                          args.username, args.password)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'source': SOURCE, 'error': str(e)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
