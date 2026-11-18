#!/usr/bin/env python3
"""
YaStream resolver (ported from VyseTV's film_sources/scrapers.dart, yastream.js).
YaStream is a Stremio addon, so this is a plain JSON lookup.

Requires: requests
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import cli, fail, fetch_json, id_from_input, ok, stream

BASE = "https://yastream.tamthai.de"


class YastreamResolver:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    def resolve(self, url_or_id, media_type="movie", season=None, episode=None):
        tmdb_id = id_from_input(url_or_id)
        if not tmdb_id:
            return fail("Could not extract TMDB ID")
        is_tv = media_type == "tv" and season is not None and episode is not None
        try:
            if is_tv:
                path = f"/stream/series/tmdb:{tmdb_id}:{season}:{episode}.json"
            else:
                path = f"/stream/movie/tmdb:{tmdb_id}.json"
            data = fetch_json(f"{BASE}{path}", timeout=15)
            items = data.get("streams") if isinstance(data, dict) else None
            if not isinstance(items, list) or not items:
                return fail("YaStream returned no streams")

            out = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                url = item.get("url")
                if not isinstance(url, str) or not url.startswith("http"):
                    continue
                name = item.get("name")
                name = name.replace("\n", " ").strip() if isinstance(name, str) and name else "Server"
                headers = {}
                proxy = (item.get("behaviorHints") or {}).get("proxyHeaders") or {}
                if isinstance(proxy.get("request"), dict):
                    headers = {str(k): str(v) for k, v in proxy["request"].items()}
                built = stream(url, f"YaStream - {name}", headers=headers)
                if built:
                    out.append(built)

            if not out:
                return fail("YaStream found no playable streams")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"YaStream error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(YastreamResolver)
