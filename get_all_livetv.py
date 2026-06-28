#!/usr/bin/env python3
"""
Aggregate live TV - fetches all live TV playlists and combines into a single JSON output.
"""

import json
import importlib
import os
import sys

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'providers'))

LIVETV = [
    'livetv.xumo',
    'livetv.tubi',
    'livetv.yupptv',
    'livetv.us_local',
    'livetv.samsung',
    'livetv.roku',
    'livetv.lgtv',
    'livetv.iptv_org',
    'livetv.plutotv',
]


def main():
    aggregated = {'sources': {}}

    for module_path in LIVETV:
        key = module_path.split('.')[-1]
        sys.stderr.write(f"[{key}] Fetching...\n")
        try:
            module = importlib.import_module(module_path)
            data = module.get_data()
            aggregated['sources'][key] = data
            sys.stderr.write(f"[{key}] OK - {data.get('total', 0)} channels\n")
        except Exception as e:
            aggregated['sources'][key] = {'source': key, 'error': str(e)}
            sys.stderr.write(f"[{key}] Error: {e}\n")

    print(json.dumps(aggregated, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
