#!/usr/bin/env python3
"""
Fetch PlutoTV channels via their public API.
Binds per-region with spoofed X-Forwarded-For.
"""

import re
import json
import sys
import uuid
import urllib.request
import urllib.error
import ssl
from datetime import datetime, timezone

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)

SOURCE = "plutotv"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15"

REGIONS = {
    "us": "45.50.96.71",
    "gb": "178.238.11.6",
    "ca": "99.224.0.1",
    "de": "85.214.132.117",
    "fr": "212.27.48.10",
    "it": "5.170.0.1",
    "es": "88.0.0.1",
}


def fetch_url(url, extra_headers=None):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    headers = {'User-Agent': UA}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    resp = urllib.request.urlopen(req, context=ctx, timeout=30)
    return resp.read().decode('utf-8', errors='replace')


def boot():
    client_id = str(uuid.uuid4())
    client_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    url = (
        f"https://boot.pluto.tv/v4/start"
        f"?appName=web&appVersion=9.9.1"
        f"&deviceVersion=130.0.0&deviceModel=web&deviceMake=Firefox&deviceType=web"
        f"&clientID={client_id}&clientModelNumber=1.0.0&serverSideAds=false"
        f"&constraints=&drmCapabilities=&blockingMode=&clientTime={client_time}"
    )
    text = fetch_url(url)
    data = json.loads(text)
    jwt = data.get('sessionToken')
    stitcher = (data.get('servers') or {}).get('stitcher')
    stitcher_params = data.get('stitcherParams', '')
    return jwt, stitcher, stitcher_params


def fetch_region_channels(region, xff, jwt, stitcher, stitcher_params):
    headers = {
        'Authorization': f'Bearer {jwt}',
        'X-Forwarded-For': xff,
    }

    channels_text = fetch_url(
        "https://service-channels.clusters.pluto.tv/v2/guide/channels"
        "?channelIds=&offset=0&limit=1000&sort=number%3Aasc",
        headers,
    )
    channels_data = json.loads(channels_text)
    channels = channels_data.get('data', [])

    categories_text = fetch_url(
        "https://service-channels.clusters.pluto.tv/v2/guide/categories",
        headers,
    )
    categories_data = json.loads(categories_text)
    categories = categories_data.get('data', [])
    cat_map = {c.get('id', ''): c.get('name', 'Uncategorized') for c in categories}

    result = []
    for ch in channels:
        name = ch.get('name')
        stitched = ch.get('stitched') or {}
        path = stitched.get('path')
        if not name or not path:
            continue

        cat_id = (ch.get('categoryIDs') or [None])[0]
        group_name = cat_map.get(cat_id, 'Uncategorized')
        logo = None
        images = ch.get('images')
        if images:
            logo = images[0].get('url')

        stream_url = f"{stitcher}/v2{path}?{stitcher_params}&jwt={jwt}&masterJWTPassthrough=true"

        result.append({
            'name': name,
            'tvg_id': ch.get('id', ''),
            'logo': logo or '',
            'group': f"{region.upper()} - {group_name}",
            'url': stream_url,
        })

    return result


def get_data():
    jwt, stitcher, stitcher_params = boot()
    if not jwt or not stitcher:
        raise Exception("Boot failed: no JWT or stitcher server")

    all_channels = []
    for region, xff in REGIONS.items():
        try:
            channels = fetch_region_channels(region, xff, jwt, stitcher, stitcher_params)
            all_channels.extend(channels)
        except Exception as e:
            sys.stderr.write(f"[plutotv] Region {region} failed: {e}\n")

    return {
        'source': SOURCE,
        'url': 'https://pluto.tv',
        'total': len(all_channels),
        'channels': all_channels,
    }


def main():
    try:
        result = get_data()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({'source': SOURCE, 'error': str(e)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
