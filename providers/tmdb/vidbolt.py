#!/usr/bin/env python3
"""
VidBolt resolver (ported from VyseTV's film_sources/scrapers.dart, vidbolt.js).
Returns JSON in PyEmbed-Api's unified format.

Requires: requests
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (cli, dig, fail, fetch_raw, first_truthy, id_from_input, ok,
                    quality_label, stream)

BASE = "https://vidbolt.xyz"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36")
API_HEADERS = {
    "User-Agent": UA,
    "Referer": f"{BASE}/",
    "Origin": BASE,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}
PLAYBACK_HEADERS = {"User-Agent": UA, "Referer": f"{BASE}/", "Origin": BASE}


class VidboltResolver:
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
                target = f"{BASE}/api/resolve?type=tv&id={tmdb_id}&season={season}&episode={episode}"
            else:
                target = f"{BASE}/api/resolve?type=movie&id={tmdb_id}"

            res = fetch_raw(target, headers=API_HEADERS, timeout=25)
            if res.status_code >= 300:
                return fail(f"VidBolt HTTP {res.status_code}")
            try:
                data = res.json()
            except Exception:
                return fail("VidBolt returned invalid JSON")

            stream_obj = dig(data, ["stream"])
            if not isinstance(stream_obj, dict):
                return fail("VidBolt returned no stream")

            server = stream_obj.get("server")
            name = (server[0].upper() + server[1:]) if isinstance(server, str) and server else "Direct"
            out = []
            seen = set()

            for item in stream_obj.get("sources") or []:
                if not isinstance(item, dict):
                    continue
                url = item.get("url")
                if not isinstance(url, str) or not url or url in seen:
                    continue
                seen.add(url)
                quality = str(item.get("quality") or "Auto").strip()
                if quality.isdigit():
                    quality = f"{quality}p"
                built = stream(
                    url,
                    f"VidBolt - {name}",
                    quality=quality,
                    type=item.get("kind"),
                    headers=PLAYBACK_HEADERS,
                    audio=item.get("language"),
                )
                if built:
                    out.append(built)

            url = stream_obj.get("url")
            if isinstance(url, str) and url and url not in seen:
                quality = str(first_truthy(stream_obj.get("quality"), "Auto"))
                built = stream(
                    url,
                    f"VidBolt - {name}",
                    quality=quality,
                    type=stream_obj.get("kind"),
                    headers=PLAYBACK_HEADERS,
                    audio=stream_obj.get("language"),
                )
                if built:
                    out.append(built)

            if not out:
                return fail("VidBolt found no playable streams")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"VidBolt error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(VidboltResolver)
