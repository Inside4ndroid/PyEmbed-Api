#!/usr/bin/env python3
"""
PurStream resolver (ported from VyseTV's film_sources/scrapers.dart, purstream.js).
Requires: requests
"""

import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (UA, cli, dig, fail, fetch_json, id_from_input, ok, stream,
                    tmdb_meta, truthy)

DOMAIN = "https://purstream.ad"
API = "https://api.purstream.ad/api/v1"
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Referer": f"{DOMAIN}/",
    "Origin": DOMAIN,
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}


class PurstreamResolver:
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
            meta = tmdb_meta(tmdb_id, is_tv)
            if not meta["titles"]:
                return fail("TMDB metadata unavailable")
            title = meta["titles"][0]
            search = fetch_json(
                f"{API}/search-bar/search/{urllib.parse.quote(title, safe='')}",
                headers=HEADERS,
                timeout=10,
            )
            items = dig(search, ["data", "items", "movies", "items"]) or []
            if not isinstance(items, list):
                return fail("PurStream search returned no items")

            wanted_type = "tv" if is_tv else "movie"
            lower = title.lower()
            match = None
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_title = dig(item, ["title"])
                release = dig(item, ["release_date"])
                if (
                    dig(item, ["type"]) == wanted_type
                    and isinstance(item_title, str)
                    and item_title.lower() == lower
                    and (meta["year"] is None or (isinstance(release, str) and release.startswith(str(meta["year"]))))
                ):
                    match = item
                    break
            if match is None:
                for item in items:
                    if isinstance(item, dict) and dig(item, ["type"]) == wanted_type:
                        match = item
                        break
            if not truthy(dig(match, ["id"])):
                return fail("PurStream found no matching title")

            item_id = match["id"]
            if is_tv:
                url = f"{API}/stream/{item_id}/episode?season={season}&episode={episode}"
            else:
                url = f"{API}/stream/{item_id}"
            payload = fetch_json(url, headers=HEADERS, timeout=10)
            sources = dig(payload, ["data", "items", "sources"])
            if dig(payload, ["type"]) != "success" or not isinstance(sources, list) or not sources:
                return fail("PurStream returned no sources")
            chosen = next((s for s in sources if isinstance(s, dict) and truthy(dig(s, ["stream_url"]))), None)
            if chosen is None:
                return fail("PurStream returned no playable stream")

            built = stream(
                chosen["stream_url"],
                "purstream",
                quality=str(chosen.get("source_name") or "Auto"),
                type=chosen.get("format") or "hls",
                headers={"User-Agent": UA, "Referer": f"{DOMAIN}/"},
            )
            if not built:
                return fail("PurStream returned an invalid URL")
            return ok(tmdb_id, [built])
        except Exception as exc:
            self.log(f"PurStream error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(PurstreamResolver)
