#!/usr/bin/env python3
"""
ThugTV resolver (ported from VyseTV's film_sources/scrapers.dart, thugtv.js).
Requires: requests
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (UA, cli, dig, fail, fetch_json, id_from_input, ok, stream,
                    truthy)

BASE = "https://thugtv.online"
API = "https://api.thugtv.online/api"
HEADERS = {
    "Accept": "application/json",
    "Referer": f"{BASE}/",
    "Origin": BASE,
    "User-Agent": UA,
}
PLAY = {"Referer": f"{BASE}/", "Origin": BASE}


class ThugtvResolver:
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
                path = f"/stream/tv/{tmdb_id}/{season}/{episode}"
            else:
                path = f"/stream/movie/{tmdb_id}"
            payload = fetch_json(f"{API}{path}", headers=HEADERS, timeout=15)
            sources = dig(payload, ["sources"])
            if not isinstance(sources, list) or not sources:
                return fail("ThugTV returned no sources")

            out = []
            for src in sources:
                if not isinstance(src, dict) or src.get("type") == "embed":
                    continue
                url = src.get("url")
                if isinstance(url, str) and url.startswith("http"):
                    server = f"ThugTV - {src.get('name') or src.get('label') or 'Direct'} ({src.get('quality') or 'Auto'})"
                    built = stream(url, server, quality=str(src.get("quality") or "Auto"), headers=PLAY)
                    if built:
                        out.append(built)
                    continue

                resolve_path = src.get("resolvePath")
                if isinstance(resolve_path, str) and resolve_path:
                    clean = resolve_path if resolve_path.startswith("/") else f"/{resolve_path}"
                    try:
                        resolved = fetch_json(f"{BASE}/api{clean}", headers=HEADERS, timeout=15)
                        direct = dig(resolved, ["source", "url"])
                        if isinstance(direct, str) and direct.startswith("http"):
                            source = resolved.get("source") or {}
                            built = stream(
                                direct,
                                f"ThugTV - {source.get('name') or source.get('label') or src.get('name') or 'Direct'}",
                                quality=str(source.get("quality") or src.get("quality") or "Auto"),
                                headers=PLAY,
                            )
                            if built:
                                out.append(built)
                    except Exception:
                        pass

            if not out:
                return fail("ThugTV found no playable streams")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"ThugTV error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(ThugtvResolver)
