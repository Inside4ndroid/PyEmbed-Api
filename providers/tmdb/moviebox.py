#!/usr/bin/env python3
"""
MovieBox resolver (ported from VyseTV's film_sources/scrapers.dart, moviebox.js).
Uses the net79.cc API and plays with an mzfi.me referer.

Requires: requests
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (UA, cli, dig, fail, fetch_json, format_size, id_from_input,
                    ok, stream, truthy)

BASE = "https://net79.cc"
HEADERS = {
    "Accept": "application/json",
    "Referer": f"{BASE}/",
    "Origin": BASE,
    "User-Agent": UA,
}
PLAYBACK = {"Referer": "https://mzfi.me/"}


class MovieboxResolver:
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
                url = f"{BASE}/api/embed-tmdb/{tmdb_id}?type=tv&se={season}&ep={episode}"
            else:
                url = f"{BASE}/api/embed-tmdb/{tmdb_id}?type=movie"

            payload = fetch_json(url, headers=HEADERS, timeout=8)
            if not truthy(dig(payload, ["ok"])) or truthy(payload.get("noSource")):
                return fail("MovieBox has no stream for this title")

            items = []
            if isinstance(payload.get("streams"), list) and payload["streams"]:
                items = payload["streams"]
            elif truthy(payload.get("mp4")):
                items = [{
                    "url": payload.get("mp4"),
                    "resolution": payload.get("resolution") or 720,
                }]

            out = []
            seen = set()
            for item in items:
                if not isinstance(item, dict):
                    continue
                stream_url = dig(item, ["url"])
                if not isinstance(stream_url, str) or not stream_url.startswith("http") or stream_url in seen:
                    continue
                seen.add(stream_url)
                resolution = f"{item['resolution']}p" if truthy(item.get("resolution")) else "720p"
                size = format_size(item.get("size")) if truthy(item.get("size")) else ""
                built = stream(
                    stream_url,
                    f"MovieBox {resolution}{f' [{size}]' if size else ''}",
                    quality=resolution,
                    headers=PLAYBACK,
                )
                if built:
                    out.append(built)

            if not out:
                return fail("MovieBox found no playable streams")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"MovieBox error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(MovieboxResolver)
