#!/usr/bin/env python3
"""
BraFlix resolver (ported from VyseTV's film_sources/scrapers.dart, braflix.js).
Returns a DASH manifest; the app has Media3 DASH support.

Requires: requests
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import UA, cli, dig, fail, fetch_raw, first_truthy, id_from_input, ok, stream

BASE = "https://braflix.dev"
HEADERS = {
    "Origin": BASE,
    "Referer": f"{BASE}/",
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
}
PLAYBACK = {"Origin": BASE, "Referer": f"{BASE}/"}


class BraflixResolver:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    @staticmethod
    def _quality_summary(raw):
        parts = [part.strip() for part in str(raw or "").split(",") if part.strip()]
        heights = []
        for part in parts:
            digits = "".join(ch for ch in part if ch.isdigit())
            if digits:
                heights.append(int(digits))
        summary = "/".join(f"{part}p" for part in parts) if parts else "DASH"
        return (max(heights) if heights else 0), summary

    def resolve(self, url_or_id, media_type="movie", season=None, episode=None):
        tmdb_id = id_from_input(url_or_id)
        if not tmdb_id:
            return fail("Could not extract TMDB ID")
        is_tv = media_type == "tv" and season is not None and episode is not None
        try:
            if is_tv:
                path = f"/api/play/tv/{tmdb_id}/{season}/{episode}"
            else:
                path = f"/api/play/movie/{tmdb_id}"
            res = fetch_raw(f"{BASE}{path}", headers=HEADERS, timeout=10)
            if res.status_code >= 300:
                return fail(f"BraFlix HTTP {res.status_code}")
            data = res.json()
            raw = dig(data, ["result", "file", "stream"])
            if data.get("status") != "ready" or not isinstance(raw, str) or not raw:
                return fail("BraFlix has no stream for this title")
            full = raw if raw.startswith("http") else f"{BASE}{raw}"
            max_height, summary = self._quality_summary(
                first_truthy(dig(data, ["result", "source", "quality"]), "1080,720,480")
            )
            built = stream(
                full,
                f"Braflix - DASH ({summary})",
                quality=f"{max_height}p" if max_height else "Auto",
                type="dash",
                headers=PLAYBACK,
            )
            if not built:
                return fail("BraFlix returned an invalid URL")
            return ok(tmdb_id, [built])
        except Exception as exc:
            self.log(f"BraFlix error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(BraflixResolver)
