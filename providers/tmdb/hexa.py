#!/usr/bin/env python3
"""
Hexa resolver (ported from VyseTV's film_sources/scrapers.dart, hexa.js).
Challenge solving and decryption are delegated to enc-dec.app.

Requires: requests
"""

import os
import re
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import UA, cli, dig, fail, fetch_json, fetch_raw, id_from_input, ok, stream, truthy

BASE = "https://theemoviedb.hexa.su"
CAP_URL = "https://cap.hexa.su/15d2cf0395"
DEC_API = "https://enc-dec.app/api"
CHALLENGE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8,fr;q=0.7,bg;q=0.6,pl;q=0.5,id;q=0.4,zh-CN;q=0.3,zh;q=0.2,ja;q=0.1,es;q=0.1",
    "Origin": "https://hexa.su",
    "Referer": "https://hexa.su/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 OPR/129.0.0.0 (Edition std-2)",
}
PLAYBACK = {"User-Agent": UA, "Referer": "https://hexa.su/", "Origin": "https://hexa.su"}

_cached_cap_token = None
_token_use_count = 0


class HexaResolver:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    def _cap_token(self):
        global _cached_cap_token, _token_use_count
        if _cached_cap_token is not None and _token_use_count < 18:
            _token_use_count += 1
            return _cached_cap_token
        try:
            challenge = fetch_json(
                f"{CAP_URL}/challenge",
                method="POST",
                headers=CHALLENGE_HEADERS,
                body={},
                timeout=8,
            )
            encoded = fetch_json(
                f"{DEC_API}/enc-hexa",
                method="POST",
                headers={"Content-Type": "application/json", "User-Agent": UA},
                body={"challenge_data": challenge},
                timeout=8,
            )
            if dig(encoded, ["status"]) != 200 or not truthy(dig(encoded, ["result"])):
                return None
            redeemed = fetch_json(
                f"{CAP_URL}/redeem",
                method="POST",
                headers=CHALLENGE_HEADERS,
                body=encoded["result"],
                timeout=8,
            )
            token = dig(redeemed, ["token"])
            if isinstance(token, str) and token:
                _cached_cap_token = token
                _token_use_count = 1
                return token
        except Exception:
            _cached_cap_token = None
        return None

    @staticmethod
    def _extract(result):
        if result is None:
            return []
        data = result
        if isinstance(data, str):
            if data.startswith("{") or data.startswith("["):
                try:
                    import json
                    data = json.loads(data)
                except Exception:
                    pass
        if isinstance(data, str) and data.startswith("http"):
            return [(data, "Hexa - Direct", "Auto")]

        raw_sources = (
            data if isinstance(data, list)
            else (data.get("sources") if isinstance(data, dict) and isinstance(data.get("sources"), list)
                  else (data.get("streams") if isinstance(data, dict) and isinstance(data.get("streams"), list) else []))
        )
        out = []
        for item in raw_sources:
            if isinstance(item, dict):
                url = item.get("url") or item.get("file") or item.get("src")
                quality = item.get("quality") or item.get("label") or "Auto"
                name = item.get("server") or item.get("name") or "Direct"
                stream_type = item.get("type")
            elif isinstance(item, str):
                url, quality, name, stream_type = item, "Auto", "Direct", None
            else:
                continue
            if not isinstance(url, str) or not url.startswith("http"):
                continue
            if str(quality).isdigit():
                quality = f"{quality}p"
            out.append((url, f"Hexa - {name}", str(quality), stream_type))

        if isinstance(data, dict) and isinstance(data.get("url"), str) and data["url"].startswith("http"):
            url = data["url"]
            quality = str(data.get("quality") or "Auto")
            if quality.isdigit():
                quality = f"{quality}p"
            out.append((url, f"Hexa - {data.get('server') or 'Direct'}", quality, data.get("type")))
        return out

    def resolve(self, url_or_id, media_type="movie", season=None, episode=None):
        tmdb_id = id_from_input(url_or_id)
        if not tmdb_id:
            return fail("Could not extract TMDB ID")
        is_tv = media_type == "tv" and season is not None and episode is not None
        try:
            if is_tv:
                path = f"/api/tmdb/tv/{tmdb_id}/season/{season}/episode/{episode}/images"
            else:
                path = f"/api/tmdb/movie/{tmdb_id}/images"

            cap_token = self._cap_token()
            if not cap_token:
                return fail("Hexa challenge token unavailable")
            key = secrets.token_hex(32)
            headers = {
                "User-Agent": UA,
                "Referer": "https://hexa.su/",
                "Origin": "https://hexa.su",
                "Accept": "text/plain",
                "X-Fingerprint-Lite": "e9136c41504646444",
                "X-Cap-Token": cap_token,
                "X-Api-Key": key,
            }
            res = fetch_raw(f"{BASE}{path}", headers=headers, timeout=12)
            if res.status_code >= 300:
                global _cached_cap_token
                _cached_cap_token = None
                return fail(f"Hexa HTTP {res.status_code}")
            encrypted = res.text.strip()
            if not encrypted:
                return fail("Hexa returned an empty response")

            decrypted = fetch_json(
                f"{DEC_API}/dec-hexa",
                method="POST",
                headers={"Content-Type": "application/json", "User-Agent": UA},
                body={"text": encrypted, "key": key},
                timeout=10,
            )
            if dig(decrypted, ["status"]) != 200 or not truthy(dig(decrypted, ["result"])):
                return fail("Hexa decryption failed")

            out = []
            seen = set()
            for stream_url, server, quality, stream_type in self._extract(decrypted["result"]):
                if stream_url in seen:
                    continue
                seen.add(stream_url)
                built = stream(
                    stream_url,
                    server,
                    quality=quality,
                    type=stream_type,
                    headers=PLAYBACK,
                )
                if built:
                    out.append(built)
            if not out:
                return fail("Hexa found no playable streams")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"Hexa error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(HexaResolver)
