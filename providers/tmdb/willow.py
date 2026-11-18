#!/usr/bin/env python3
"""
Willow resolver (ported from VyseTV's film_sources/scrapers.dart, willow.js).
Requires: requests
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (UA, cli, dig, fail, fetch_raw, first_truthy, id_from_input, ok,
                    quality_label, stream, truthy)

BASE = "https://willowmovies.com"
HEADERS = {
    "User-Agent": UA,
    "Referer": f"{BASE}/",
    "Origin": BASE,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}
PLAYBACK = {"User-Agent": UA, "Referer": f"{BASE}/", "Origin": BASE}


class WillowResolver:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    @staticmethod
    def _kind(given, url):
        text = str(given or "").lower()
        if text:
            if text in ("hls", "m3u8"):
                return "hls"
            if text in ("dash", "mpd"):
                return "dash"
            return text
        low = url.lower()
        if ".m3u8" in low:
            return "hls"
        if ".mpd" in low:
            return "dash"
        if ".mkv" in low:
            return "mkv"
        return "mp4"

    def _extract(self, data, fallback=None):
        out = []
        if not isinstance(data, dict):
            return out
        name = first_truthy(dig(data, ["source", "name"]), dig(data, ["source", "id"]), fallback, "Default")
        qualities = data.get("qualities")
        if isinstance(qualities, list):
            for item in qualities:
                if not isinstance(item, dict):
                    continue
                url = item.get("url")
                if not isinstance(url, str) or not url:
                    continue
                quality = str(item.get("quality") or "Auto").strip()
                if quality == "0p":
                    quality = "Auto"
                elif quality.isdigit():
                    quality = f"{quality}p"
                built = stream(
                    url,
                    f"Willow - {name}",
                    quality=quality,
                    type=self._kind(item.get("type"), url),
                    headers=PLAYBACK,
                )
                if built:
                    out.append(built)
        src = data.get("src")
        if isinstance(src, str) and src:
            built = stream(
                src,
                f"Willow - {name}",
                type=self._kind(data.get("type"), src),
                headers=PLAYBACK,
            )
            if built:
                out.append(built)
        return out

    def resolve(self, url_or_id, media_type="movie", season=None, episode=None):
        tmdb_id = id_from_input(url_or_id)
        if not tmdb_id:
            return fail("Could not extract TMDB ID")
        is_tv = media_type == "tv" and season is not None and episode is not None
        try:
            if is_tv:
                query = f"id={tmdb_id}&type=tv&s={season}&e={episode}"
            else:
                query = f"id={tmdb_id}&type=movie"
            res = fetch_raw(f"{BASE}/api/stream?{query}", headers=HEADERS, timeout=30)
            if res.status_code >= 300:
                return fail(f"Willow HTTP {res.status_code}")
            try:
                initial = res.json()
            except Exception:
                return fail("Willow returned invalid JSON")

            out = []
            seen = set()
            for item in self._extract(initial):
                if item["url"] not in seen:
                    seen.add(item["url"])
                    out.append(item)

            current = dig(initial, ["source", "id"])
            extra = initial.get("sources") if isinstance(initial.get("sources"), list) else []
            for src in extra:
                if not isinstance(src, dict) or not truthy(src.get("id")) or src.get("id") == current:
                    continue
                try:
                    r = fetch_raw(
                        f"{BASE}/api/stream?{query}&source={src['id']}",
                        headers=HEADERS,
                        timeout=8,
                    )
                    if r.status_code >= 300:
                        continue
                    for item in self._extract(r.json(), first_truthy(src.get("name"), src.get("id"))):
                        if item["url"] not in seen:
                            seen.add(item["url"])
                            out.append(item)
                except Exception:
                    pass

            if not out:
                return fail("Willow found no playable streams")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"Willow error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(WillowResolver)
