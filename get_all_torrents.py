#!/usr/bin/env python3
"""
Aggregate torrent - runs all torrent providers and combines results into a single JSON output.
"""

import json
import argparse
import importlib
import os
import sys

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'providers'))

TORRENT_PROVIDERS = [
    'torrent.torrentdl',
    'torrent.torrentio',
    'torrent.comet',
    'torrent.easynews',
]


def main():
    parser = argparse.ArgumentParser(
        description='Aggregate torrent providers'
    )
    parser.add_argument('tmdb_id', help='TMDB ID')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie')
    parser.add_argument('--season', type=int)
    parser.add_argument('--episode', type=int)
    parser.add_argument('--realdebrid', help='RealDebrid API key (for Comet)')
    parser.add_argument('--torbox', help='TorBox API key (for Comet)')
    parser.add_argument('--premiumize', help='Premiumize API key (for Comet)')
    parser.add_argument('--alldebrid', help='AllDebrid API key (for Comet)')
    parser.add_argument('--username', help='EasyNews username')
    parser.add_argument('--password', help='EasyNews password')
    args = parser.parse_args()

    aggregated = {
        'input': {
            'tmdb_id': args.tmdb_id,
            'media_type': args.type,
            'season': args.season,
            'episode': args.episode,
        },
        'providers': {},
    }

    for module_path in TORRENT_PROVIDERS:
        key = module_path.split('.')[-1]
        sys.stderr.write(f"[{key}] Running...\n")
        try:
            module = importlib.import_module(module_path)

            kwargs = {
                'tmdb_id': args.tmdb_id,
                'media_type': args.type,
                'season': args.season,
                'episode': args.episode,
            }

            if key == 'comet':
                kwargs.update({
                    'realdebrid': args.realdebrid,
                    'torbox': args.torbox,
                    'premiumize': args.premiumize,
                    'alldebrid': args.alldebrid,
                })
            elif key == 'easynews':
                kwargs.update({
                    'username': args.username,
                    'password': args.password,
                })

            data = module.get_data(**kwargs)
            aggregated['providers'][key] = data
            items = data.get('torrents') or data.get('streams') or []
            sys.stderr.write(f"[{key}] OK - {len(items)} result(s)\n")

        except Exception as e:
            aggregated['providers'][key] = {'source': key, 'error': str(e)}
            sys.stderr.write(f"[{key}] Error: {e}\n")

    print(json.dumps(aggregated, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
