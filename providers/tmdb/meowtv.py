#!/usr/bin/env python3
"""
MeowTV resolver (ported from VyseTV's film_sources/scrapers.dart, meowtv.js).
A stream ticket, then each server's answer decrypted by enc-dec.app.

Requires: requests
"""

import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import UA, cli, dig, fail, fetch_raw, first_truthy, id_from_input, ok, stream, truthy

BASE = "https://api.meowtv.ru"
DEC_API = "https://enc-dec.app/api"
HEADERS = {
    "User-Agent": UA,
    "Origin": "https://meowtv.ru",
    "Referer": "https://meowtv.ru/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}
SERVERS = [
    ("acme", "Acme", False),
    ("dcloud", "Dcloud", False),
    ("tik", "TCloud", False),
    ("ipcloud", "IPcloud", False),
    ("turkce", "Türkçe", True),
    ("hindi", "Hindi", False),
    ("english", "English", False),
]


class MeowtvResolver:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    @staticmethod
    def _extract(result):
        out = []
        kind = lambda given, url: str(given) if truthy(given) else ("hls" if ".m3u8" in url else "mp4")
        if isinstance(result, str) and result.startswith("http"):
            out.append(("Auto", result, kind(None, result)))
        elif isinstance(result, dict) and isinstance(result.get("url"), str):
            out.append((str(result.get("quality") or "Auto"), result["url"], kind(result.get("type"), result["url"])))
        elif isinstance(result, dict) and isinstance(result.get("sources"), list):
            for source in result["sources"]:
                if isinstance(source, dict) and isinstance(source.get("url"), str) and source["url"]:
                    out.append((
                        str(source.get("quality") or "Auto"),
                        source["url"],
                        kind(source.get("type"), source["url"]),
                    ))
        elif isinstance(result, dict) and truthy(result.get("stream")):
            value = result["stream"]
            url = value if isinstance(value, str) else dig(value, ["url"])
            if isinstance(url, str) and url:
                quality = first_truthy(dig(value, ["quality"]) if isinstance(value, dict) else None, "Auto")
                out.append((str(quality), url, kind(None, url)))
        return out

    def _one(self, server_id, label, movie_only, tmdb_id, is_tv, season, episode, headers):
        if is_tv and movie_only:
            return []
        try:
            if is_tv:
                url = f"{BASE}/streams/tv/{tmdb_id}/{season}/{episode}?s={server_id}"
            else:
                url = f"{BASE}/streams/movie/{tmdb_id}?s={server_id}"
            res = fetch_raw(url, headers=headers, timeout=10)
            if res.status_code >= 300:
                return []
            data = res.json()
            dec = fetch_raw(
                f"{DEC_API}/dec-meowtv",
                method="POST",
                headers={"Content-Type": "application/json", "User-Agent": UA},
                body={"data": data},
                timeout=10,
            )
            if dec.status_code >= 300:
                return []
            payload = dec.json()
            if dig(payload, ["status"]) != 200:
                return []
            out = []
            for quality, stream_url, stream_type in self._extract(payload.get("result")):
                built = stream(
                    stream_url,
                    f"MeowTV - {label}",
                    quality=quality,
                    type=stream_type,
                    headers={"Referer": "https://meowtv.ru/", "Origin": "https://meowtv.ru", "User-Agent": UA},
                )
                if built:
                    out.append(built)
            return out
        except Exception:
            return []

    def resolve(self, url_or_id, media_type="movie", season=None, episode=None):
        tmdb_id = id_from_input(url_or_id)
        if not tmdb_id:
            return fail("Could not extract TMDB ID")
        is_tv = media_type == "tv" and season is not None and episode is not None
        try:
            ticket_res = fetch_raw(f"{BASE}/streams/ticket", method="POST", headers=HEADERS, timeout=10)
            ticket = dig(ticket_res.json(), ["ticket"]) if ticket_res.status_code < 300 else None
            if not truthy(ticket):
                return fail("MeowTV ticket unavailable")
            headers = {**HEADERS, "X-Stream-Ticket": str(ticket)}

            with ThreadPoolExecutor(max_workers=7) as pool:
                results = list(
                    pool.map(
                        lambda server: self._one(server[0], server[1], server[2], tmdb_id, is_tv, season, episode, headers),
                        SERVERS,
                    )
                )

            seen = set()
            out = []
            for group in results:
                for item in group:
                    if item["url"] not in seen:
                        seen.add(item["url"])
                        out.append(item)
            if not out:
                return fail("MeowTV found no playable streams")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"MeowTV error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(MeowtvResolver)
