#!/usr/bin/env python3
"""
111477 resolver (ported from VyseTV's film_sources/scrapers.dart, 111477.js).
111477 is a Stremio addon that serves very large (often 4K remux) files.

Requires: requests
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (UA, b64url, cli, dig, fail, fetch_raw, id_from_input, ok,
                    resolve_imdb_id, stream)

ORIGIN = "https://st.111477.xyz"
CONFIG = "https://a.111477.xyz/::sort=file-desc::limit=3"
HEADERS = {"User-Agent": UA, "Accept": "application/json, text/plain, */*"}


class S111477Resolver:
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
            imdb = resolve_imdb_id(tmdb_id, is_tv)
            targets = []
            if imdb.startswith("tt"):
                targets.append(imdb)
            targets.append(f"tmdb:{tmdb_id}")

            addon_base = f"{ORIGIN}/config/{b64url(CONFIG)}"
            out = []
            seen = set()
            for target in targets:
                if is_tv:
                    endpoint = f"{addon_base}/stream/series/{target}:{season}:{episode}.json"
                else:
                    endpoint = f"{addon_base}/stream/movie/{target}.json"
                try:
                    res = fetch_raw(endpoint, headers=HEADERS, timeout=12)
                except Exception:
                    continue
                if res.status_code >= 300:
                    continue
                try:
                    payload = res.json()
                except Exception:
                    continue
                items = dig(payload, ["streams"])
                if not isinstance(items, list) or not items:
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    url = str(item.get("url") or "").strip()
                    if not url.startswith("http") or url in seen:
                        continue
                    seen.add(url)
                    label = str(item.get("title") or "").strip() or str(item.get("name") or "111477").strip()
                    built = stream(url, label, headers=HEADERS)
                    if built:
                        out.append(built)
                if out:
                    break

            if not out:
                return fail("111477 found no playable streams")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"111477 error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(S111477Resolver)
