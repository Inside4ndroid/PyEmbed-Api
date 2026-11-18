#!/usr/bin/env python3
"""
WatchOut resolver (ported from VyseTV's film_sources/scrapers.dart, watchout.js).
Reads the WatchOut GitHub JSON feed.

Requires: requests
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import cli, fail, fetch_json, fetch_text, id_from_input, ok, stream

API = "https://raw.githubusercontent.com/Watchout2025/api/refs/heads/main/hls/"
HEADERS = {"Origin": "https://vidout.pages.dev", "Referer": "https://vidout.pages.dev"}


class WatchoutResolver:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    @staticmethod
    def _is_hls(url):
        low = url.lower()
        return ".m3u8" in low or url.endswith(".txt") or "master" in low or ".mp4" not in low

    def resolve(self, url_or_id, media_type="movie", season=None, episode=None):
        tmdb_id = id_from_input(url_or_id)
        if not tmdb_id:
            return fail("Could not extract TMDB ID")
        is_tv = media_type == "tv" and season is not None and episode is not None
        try:
            if not is_tv:
                text = fetch_text(f"{API}movie/{tmdb_id}", timeout=15).strip()
                if "://" not in text:
                    return fail("WatchOut has no stream for this title")
                stream_url = text
            else:
                data = None
                for name in (f"S{season}.json", f"s{season}.json"):
                    try:
                        data = fetch_json(f"{API}tv/{tmdb_id}/{name}", timeout=15)
                        break
                    except Exception:
                        continue
                value = data.get(str(episode)) if isinstance(data, dict) else None
                if not value:
                    return fail("WatchOut has no stream for this episode")
                stream_url = str(value)

            built = stream(
                stream_url,
                "Watchout - Direct",
                type="hls" if self._is_hls(stream_url) else "mp4",
                headers=HEADERS,
            )
            if not built:
                return fail("WatchOut returned an invalid URL")
            return ok(tmdb_id, [built])
        except Exception as exc:
            self.log(f"WatchOut error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(WatchoutResolver)
