#!/usr/bin/env python3
"""
VidSpark resolver (ported from VyseTV's film_sources/scrapers.dart, vidspark.js).
Shows only in the original port; kept general.

Requires: requests
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (UA, cli, dig, fail, fetch_json, hls_variants, id_from_input,
                    ok, quality_rank, stream)

BASE = "https://vidspark.to"
PLAYER_KEY = "3a67e8866ae1d2bb9e81fe7f73315a56eb3bdf5e3e755c7554c8be6910aa6b13"
PLAYBACK = {"User-Agent": UA, "Referer": f"{BASE}/", "Origin": BASE}


class VidsparkResolver:
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
                target = f"{BASE}/api/vidora/v1/tv/{tmdb_id}/{season}/{episode}"
                referer = f"{BASE}/tv/{tmdb_id}/{season}/{episode}"
            else:
                target = f"{BASE}/api/vidora/v1/movie/{tmdb_id}"
                referer = f"{BASE}/movie/{tmdb_id}"

            headers = {
                "User-Agent": UA,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": referer,
                "Origin": BASE,
                "x-player-key": PLAYER_KEY,
            }
            data = fetch_json(target, headers=headers, timeout=25)
            if not dig(data, ["result"]):
                return fail("VidSpark returned no result")
            sources = dig(data, ["sources"])
            if not isinstance(sources, list) or not sources:
                return fail("VidSpark returned no sources")

            out = []
            seen = set()
            for item in sources:
                if not isinstance(item, dict):
                    continue
                url = dig(item, ["url"])
                if not isinstance(url, str) or not url.startswith("http"):
                    continue
                source = item.get("source")
                label = (source[0].upper() + source[1:]) if isinstance(source, str) and source else "Direct"

                if ".m3u8" in url:
                    for variant in hls_variants(url, headers=PLAYBACK, timeout=5) or []:
                        if variant["url"] in seen:
                            continue
                        seen.add(variant["url"])
                        built = stream(
                            variant["url"],
                            f"VidSpark - {label} ({variant['quality']})",
                            quality=variant["quality"],
                            type="hls",
                            headers=PLAYBACK,
                        )
                        if built:
                            out.append(built)

                if url not in seen:
                    seen.add(url)
                    built = stream(url, f"VidSpark - {label}", headers=PLAYBACK)
                    if built:
                        out.append(built)

            out.sort(key=lambda s: quality_rank(s.get("quality")), reverse=True)
            if not out:
                return fail("VidSpark found no playable streams")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"VidSpark error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(VidsparkResolver)
