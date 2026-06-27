#!/usr/bin/env python3
"""
Aggregate resolver - runs all resolvers and combines valid results into a single JSON output.
"""

import json
import argparse
import importlib
import os
import sys
import traceback

RESOLVER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'script.module.resolveurl')
sys.path.insert(0, RESOLVER_DIR)

RESOLVERS = [
    ('castle', 'CastleResolver'),
    ('fsharetv', 'FshareTvResolver'),
    ('hdhub', 'HdHubResolver'),
    ('movieblast', 'MovieBlastResolver'),
    ('moviesdrive', 'MoviesDriveResolver'),
    ('netmirror', 'NetMirrorResolver'),
    ('showbox', 'ShowBoxResolver'),
    ('streamflix', 'StreamFlixResolver'),
    ('vidapi', 'VidApiResolver'),
    ('vidlink', 'VidlinkResolver'),
    ('vidnest', 'VidNestResolver'),
    ('vidrock', 'VidrockResolver'),
    ('vidzee', 'VidzeeResolver'),
    ('vixsrc', 'VixSrcResolver'),
]


def main():
    parser = argparse.ArgumentParser(
        description='Aggregate resolver - runs all resolvers and combines results'
    )
    parser.add_argument('url_or_id', help='TMDB ID or URL')
    parser.add_argument('--type', choices=['movie', 'tv'], default='movie',
                        help='Media type (default: movie)')
    parser.add_argument('--season', type=int, help='Season number (for TV)')
    parser.add_argument('--episode', type=int, help='Episode number (for TV)')
    parser.add_argument('--ui-cookie', help='FebBox UI token (required for ShowBox)')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON output')

    args = parser.parse_args()

    aggregated = {
        'status': 'success',
        'input': {
            'url_or_id': args.url_or_id,
            'media_type': args.type,
            'season': args.season,
            'episode': args.episode,
        },
        'resolvers': {},
        'total_playable_urls': 0,
    }

    for module_name, class_name in RESOLVERS:
        resolver_key = module_name
        sys.stderr.write(f"[{resolver_key}] Running...\n")

        try:
            module = importlib.import_module(module_name)
            ResolverClass = getattr(module, class_name)

            resolver_args = {'debug': args.debug}

            # Special handling: showbox needs ui-cookie in constructor
            if module_name == 'showbox':
                if not args.ui_cookie:
                    aggregated['resolvers'][resolver_key] = {
                        'status': 'skipped',
                        'message': '--ui-cookie required for ShowBox resolver'
                    }
                    sys.stderr.write(f"[{resolver_key}] Skipped (no --ui-cookie)\n")
                    continue
                resolver_args['ui_cookie'] = args.ui_cookie

            resolver = ResolverClass(**resolver_args)

            # moviesdrive uses tmdb_id instead of url_or_id
            if module_name == 'moviesdrive':
                resolve_kwargs = {
                    'tmdb_id': args.url_or_id,
                    'media_type': args.type,
                    'season': args.season,
                    'episode': args.episode,
                }
            else:
                resolve_kwargs = {
                    'url_or_id': args.url_or_id,
                    'media_type': args.type,
                    'season': args.season,
                    'episode': args.episode,
                }

            result_json = resolver.resolve(**resolve_kwargs)
            result = json.loads(result_json)

            aggregated['resolvers'][resolver_key] = result

            playable = result.get('playable_urls', [])
            if result.get('status') == 'success' and playable:
                aggregated['total_playable_urls'] += len(playable)
                sys.stderr.write(
                    f"[{resolver_key}] OK - {len(playable)} URL(s)\n"
                )
            else:
                msg = result.get('message', 'No playable URLs')
                sys.stderr.write(f"[{resolver_key}] {msg}\n")

        except Exception as e:
            aggregated['resolvers'][resolver_key] = {
                'status': 'error',
                'message': str(e),
            }
            if args.debug:
                sys.stderr.write(
                    f"[{resolver_key}] Error: {e}\n"
                    f"{traceback.format_exc()}\n"
                )
            else:
                sys.stderr.write(f"[{resolver_key}] Error: {e}\n")

    output = json.dumps(aggregated, indent=2 if args.pretty else None)
    print(output)


if __name__ == '__main__':
    main()
