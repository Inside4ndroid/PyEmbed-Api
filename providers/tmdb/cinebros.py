#!/usr/bin/env python3
"""
CineBros resolver (ported from VyseTV's film_sources/scrapers.dart, cinebros.js).
Requires: requests
"""

import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (UA, cli, dig, fail, fetch_raw, first_truthy, id_from_input,
                    ok, stream, tmdb_meta, truthy)

BASE = "https://cinebros.net"
HEADERS = {
    "User-Agent": UA,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": BASE,
    "Referer": f"{BASE}/",
}
PLAYBACK = {"User-Agent": UA, "Referer": f"{BASE}/", "Origin": BASE}


class CinebrosResolver:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    @staticmethod
    def _parse_objects(text):
        items = []
        depth = 0
        start = -1
        in_string = False
        escape = False
        for index, char in enumerate(text):
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                if depth == 0:
                    start = index
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0 and start != -1:
                    try:
                        items.append(json.loads(text[start:index + 1]))
                    except Exception:
                        pass
                    start = -1
        return items

    @staticmethod
    def _score(item):
        score = 0
        match = re.search(r"\d+", item.get("quality") or "")
        if match:
            score += int(match.group(0))
        if "/stream/" in item.get("url", ""):
            score += 10000
        if "blob=" in item.get("url", ""):
            score -= 5000
        return score

    def resolve(self, url_or_id, media_type="movie", season=None, episode=None):
        tmdb_id = id_from_input(url_or_id)
        if not tmdb_id:
            return fail("Could not extract TMDB ID")
        is_tv = media_type == "tv" and season is not None and episode is not None
        try:
            meta = tmdb_meta(tmdb_id, is_tv)
            runtime = str(meta["runtime"] or (24 if is_tv else 90))
            params = {
                "tmdbId": tmdb_id,
                "type": "tv" if is_tv else "movie",
                "title": meta["title"] or tmdb_id,
            }
            if is_tv:
                params["seasonId"] = str(season)
                params["episodeId"] = str(episode)
            if meta["year"] is not None:
                params["year"] = str(meta["year"])
            params["runtime"] = runtime

            referer = (
                f"{BASE}/watch/tv/{tmdb_id}/{season}/{episode}"
                if is_tv
                else f"{BASE}/watch/movie/{tmdb_id}"
            )
            url = f"{BASE}/api/streams?{urllib.parse.urlencode(params)}"
            res = fetch_raw(url, headers={**HEADERS, "Referer": referer}, timeout=25)
            if res.status_code >= 300:
                return fail(f"CineBros HTTP {res.status_code}")

            out = []
            seen = set()
            for item in self._parse_objects(res.text):
                if not isinstance(item, dict):
                    continue
                stream_url = item.get("url")
                if not isinstance(stream_url, str) or not stream_url.startswith("http") or stream_url in seen:
                    continue
                seen.add(stream_url)
                quality = str(item.get("quality") or "Auto").strip()
                if quality.isdigit():
                    quality = f"{quality}p"
                label = f"CineBros - {item.get('name')}" if truthy(item.get("name")) else f"CineBros ({quality})"
                built = stream(
                    stream_url,
                    label,
                    quality=quality,
                    type=item.get("type") or (
                        "hls" if (".m3u8" in stream_url or "/stream/" in stream_url) else
                        ("dash" if ".mpd" in stream_url else "mp4")
                    ),
                    headers=PLAYBACK,
                )
                if built:
                    out.append(built)

            out.sort(key=self._score, reverse=True)
            if not out:
                return fail("CineBros found no playable streams")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"CineBros error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(CinebrosResolver)
