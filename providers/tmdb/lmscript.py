#!/usr/bin/env python3
"""
LMScript resolver (ported from VyseTV's film_sources/scrapers.dart, lmscript.js).
Films only.

Requires: requests
"""

import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import UA, cli, dig, fail, fetch_json, id_from_input, ok, stream, tmdb_meta

BASE = "https://lmscript.xyz"
REFERER = "https://lookmovie2.to/"
ORDER = ["1080p", "720p", "480p", "360p"]


class LmscriptResolver:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    def resolve(self, url_or_id, media_type="movie", season=None, episode=None):
        tmdb_id = id_from_input(url_or_id)
        if not tmdb_id:
            return fail("Could not extract TMDB ID")
        if media_type == "tv" and season is not None and episode is not None:
            return fail("LMScript is films only")
        try:
            meta = tmdb_meta(tmdb_id, False)
            if not meta["titles"]:
                return fail("TMDB metadata unavailable")

            movie = None
            for title in meta["titles"]:
                data = fetch_json(
                    f"{BASE}/v1/movies?filters[q]={urllib.parse.quote(title, safe='')}&expand=streams",
                    timeout=15,
                )
                items = dig(data, ["items"])
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    if (
                        str(item.get("tmdb_prefix")) == tmdb_id
                        or str(item.get("tmdb_id")) == tmdb_id
                        or (isinstance(item.get("title"), str) and item["title"].lower() == title.lower())
                    ):
                        movie = item
                        break
                if movie:
                    break

            if not movie:
                return fail("LMScript found no matching title")
            streams = movie.get("streams") if isinstance(movie.get("streams"), dict) else {}
            keys = list(streams.keys())
            keys.sort(key=lambda key: ORDER.index(key) if key in ORDER else len(ORDER))
            out = []
            for quality in keys:
                url = streams[quality]
                built = stream(
                    str(url),
                    f"LookMovie - {quality}",
                    quality=quality,
                    headers={"Referer": REFERER, "User-Agent": UA},
                )
                if built:
                    out.append(built)
            if not out:
                return fail("LMScript returned no streams")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"LMScript error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(LmscriptResolver)
