#!/usr/bin/env python3
"""
FrameXTV resolver (ported from VyseTV's film_sources/scrapers.dart, framextv.js).
Uses the FrameX API; StreamOS' slow relay probing is deliberately not used.

Requires: requests
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (UA, cli, dig, fail, fetch_raw, id_from_input, ok, stream,
                    truthy)

FRAMEX = "https://api.framextv.cc"
FRAMEX_HEADERS = {
    "User-Agent": UA,
    "Referer": "https://framextv.cc/",
    "Origin": "https://framextv.cc",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


class FramextvResolver:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    def _framex(self, url):
        try:
            res = fetch_raw(url, headers=FRAMEX_HEADERS, timeout=10)
            return res.json() if res.status_code < 300 else None
        except Exception:
            return None

    def resolve(self, url_or_id, media_type="movie", season=None, episode=None):
        tmdb_id = id_from_input(url_or_id)
        if not tmdb_id:
            return fail("Could not extract TMDB ID")
        is_tv = media_type == "tv" and season is not None and episode is not None
        try:
            if is_tv:
                fq = f"type=tv&id={tmdb_id}&season={season}&episode={episode}&codecs=hevc"
            else:
                fq = f"type=movie&id={tmdb_id}&codecs=hevc"

            framex_urls = [
                f"{FRAMEX}/api/stream?{fq}",
                f"{FRAMEX}/api/stream?{fq}&provider=sparky",
                f"{FRAMEX}/api/stream?{fq}&provider=titan",
            ]

            with ThreadPoolExecutor(max_workers=3) as pool:
                framex_results = list(pool.map(self._framex, framex_urls))

            out = []
            seen = set()
            for data in framex_results:
                if not truthy(dig(data, ["success"])) or not isinstance(data.get("sources"), list):
                    continue
                for src in data["sources"]:
                    url = dig(src, ["url"])
                    if not isinstance(url, str) or not url or url in seen:
                        continue
                    seen.add(url)
                    built = stream(
                        url,
                        f"FrameX - {src.get('server') or data.get('provider') or 'Direct'}",
                        quality=str(src.get("quality") or "Auto"),
                        type=src.get("type"),
                        headers={
                            "User-Agent": UA,
                            "Referer": "https://framextv.cc/",
                            "Origin": "https://framextv.cc",
                        },
                    )
                    if built:
                        out.append(built)

            if not out:
                return fail("FrameXTV found no playable streams")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"FrameXTV error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(FramextvResolver)
