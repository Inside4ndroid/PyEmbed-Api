#!/usr/bin/env python3
"""
3EyedRaven resolver (ported from VyseTV's film_sources/scrapers.dart, 3eyedraven.js).
Requires: requests
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (UA, cli, dig, fail, fetch_raw, id_from_input, ok, slugify,
                    stream, tmdb_meta)

BASE = "https://3eyedraven.watch"
API = f"{BASE}/api"


class ThreeEyedRavenResolver:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    @staticmethod
    def _absolute(url):
        if not url:
            return ""
        if re.match(r"^https?://", url):
            return url
        return f"{BASE}{'' if url.startswith('/') else '/'}{url}"

    def resolve(self, url_or_id, media_type="movie", season=None, episode=None):
        tmdb_id = id_from_input(url_or_id)
        if not tmdb_id:
            return fail("Could not extract TMDB ID")
        is_tv = media_type == "tv" and season is not None and episode is not None
        try:
            meta = tmdb_meta(tmdb_id, is_tv)
            if not meta["title"]:
                return fail("TMDB metadata unavailable")
            identifier = f"{slugify(meta['title'])}-{tmdb_id}"
            if is_tv:
                url = f"{API}/stream/{identifier}?season={season}&episode={episode}"
            else:
                url = f"{API}/stream/{identifier}"
            headers = {
                "User-Agent": UA,
                "Accept": "application/json",
                "Referer": f"{BASE}/",
                "Origin": BASE,
            }
            res = fetch_raw(url, headers=headers, timeout=15)
            if res.status_code >= 300:
                return fail(f"3EyedRaven HTTP {res.status_code}")
            payload = res.json()
            stream_obj = dig(payload, ["stream"])
            raw_url = dig(stream_obj, ["url"])
            if not isinstance(raw_url, str) or not raw_url:
                return fail("3EyedRaven returned no stream")
            stream_url = self._absolute(raw_url)
            if not re.match(r"^https?://", stream_url):
                return fail("3EyedRaven returned an invalid URL")
            built = stream(
                stream_url,
                "3eyedraven",
                quality="1080p",
                type="hls" if dig(stream_obj, ["format"]) == "hls" else "mp4",
                headers=headers,
            )
            if not built:
                return fail("3EyedRaven returned an invalid URL")
            return ok(tmdb_id, [built])
        except Exception as exc:
            self.log(f"3EyedRaven error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(ThreeEyedRavenResolver)
