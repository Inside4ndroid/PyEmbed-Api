#!/usr/bin/env python3
"""
CNO resolver (ported from VyseTV's film_sources/scrapers.dart, cno.js).
Asks its numbered servers in parallel.

Requires: requests
"""

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (UA, cli, fail, fetch_text, first_truthy, id_from_input, ok,
                    quality_label, stream)

BASE = "https://cno.to"
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": f"{BASE}/",
    "Origin": BASE,
    "User-Agent": UA,
}
PLAY = {"Referer": f"{BASE}/", "Origin": BASE}
SERVER_COUNT = 50
MAX_WORKERS = 10


class CnoResolver:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    def _one(self, number, tmdb_id, is_tv, season, episode):
        if is_tv:
            url = f"{BASE}/api/s/{number}/tv/{tmdb_id}/{season}/{episode}"
        else:
            url = f"{BASE}/api/s/{number}/movie/{tmdb_id}?v=3"
        try:
            raw = fetch_text(url, headers=HEADERS, timeout=12)
            if not raw or '"error":' in raw:
                return None

            if "#EXTM3U" in raw:
                lines = [line.strip() for line in raw.splitlines()]
                stream_url = None
                quality = "Auto"
                for index, line in enumerate(lines):
                    if not line.startswith("#EXT-X-STREAM-INF:"):
                        continue
                    match = re.search(r"RESOLUTION=(\d+x\d+)", line)
                    if match:
                        quality = match.group(1)
                    nxt = lines[index + 1] if index + 1 < len(lines) else ""
                    if nxt and not nxt.startswith("#"):
                        stream_url = nxt
                        break
                if stream_url is None:
                    stream_url = next((l for l in lines if l and not l.startswith("#")), None)
                if stream_url:
                    if stream_url.startswith("/"):
                        stream_url = f"{BASE}{stream_url}"
                    return stream(
                        stream_url,
                        f"Cno - Server {number} ({quality_label(quality)})",
                        quality=quality,
                        type="hls",
                        headers=PLAY,
                    )

            try:
                data = json.loads(raw)
            except Exception:
                return None
            url_value = first_truthy(data.get("url"), data.get("file"), data.get("stream")) if isinstance(data, dict) else None
            if isinstance(url_value, str) and url_value.startswith("http"):
                quality = str(first_truthy(data.get("quality"), "Auto"))
                return stream(
                    url_value,
                    f"Cno - Server {number} ({quality})",
                    quality=quality,
                    headers=PLAY,
                )
        except Exception:
            return None
        return None

    def resolve(self, url_or_id, media_type="movie", season=None, episode=None):
        tmdb_id = id_from_input(url_or_id)
        if not tmdb_id:
            return fail("Could not extract TMDB ID")
        is_tv = media_type == "tv" and season is not None and episode is not None
        try:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                results = list(
                    pool.map(
                        lambda number: self._one(number, tmdb_id, is_tv, season, episode),
                        range(1, SERVER_COUNT + 1),
                    )
                )
            out = [item for item in results if item]
            if not out:
                return fail("CNO found no playable streams")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"CNO error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(CnoResolver)
