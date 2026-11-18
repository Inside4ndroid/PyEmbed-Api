#!/usr/bin/env python3
"""
RiveStream resolver (ported from VyseTV's film_sources/scrapers.dart, rivestream.js).
The site signs requests with a custom secret key; the 32-bit integer maths is kept exactly.

Requires: requests
"""

import base64
import os
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import UA, cli, dig, fail, fetch_json, first_truthy, id_from_input, ok, stream, truthy

BASE = "https://www.rivestream.app"
DEFAULTS = [
    "apex", "pulse", "solstice", "quasar", "horizon", "primevids",
    "flowcast", "asiacloud", "citadel", "hindicast", "guru",
]
# The live service list is long and each call can take ~30s; ask the ones that
# answer first, then stop. `pulse` is usually the quickest working server.
PREFERRED = [
    "pulse", "primevids", "citadel", "apollo", "lumen", "prometheus",
    "mirage", "sentinel", "valiant", "rift", "apogee", "borealis",
]
MAX_SERVICES = 6
C_ARRAY = [
    "4Z7lUo", "gwIVSMD", "PLmz2elE2v", "Z4OFV0", "SZ6RZq6Zc", "zhJEFYxrz8", "FOm7b0", "axHS3q4KDq",
    "o9zuXQ", "4Aebt", "wgjjWwKKx", "rY4VIxqSN", "kfjbnSo", "2DyrFA1M", "YUixDM9B", "JQvgEj0",
    "mcuFx6JIek", "eoTKe26gL", "qaI9EVO1rB", "0xl33btZL", "1fszuAU", "a7jnHzst6P", "wQuJkX",
    "cBNhTJlEOf", "KNcFWhDvgT", "XipDGjST", "PCZJlbHoyt", "2AYnMZkqd", "HIpJh", "KH0C3iztrG",
    "W81hjts92", "rJhAT", "NON7LKoMQ", "NMdY3nsKzI", "t4En5v", "Qq5cOQ9H", "Y9nwrp", "VX5FYVfsf",
    "cE5SJG", "x1vj1", "HegbLe", "zJ3nmt4OA", "gt7rxW57dq", "clIE9b", "jyJ9g", "B5jXjMCSx",
    "cOzZBZTV", "FTXGy", "Dfh1q1", "ny9jqZ2POI", "X2NnMn", "MBtoyD", "qz4Ilys7wB", "68lbOMye",
    "3YUJnmxp", "1fv5Imona", "PlfvvXD7mA", "ZarKfHCaPR", "owORnX", "dQP1YU", "dVdkx", "qgiK0E",
    "cx9wQ", "5F9bGa", "7UjkKrp", "Yvhrj", "wYXez5Dg3", "pG4GMU", "MwMAu", "rFRD5wlM",
]


def _i32(value):
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def _u32(value):
    return value & 0xFFFFFFFF


def _shl(a, b):
    return _i32((a & 0xFFFFFFFF) << (b & 31))


def _ushr(a, b):
    return (a & 0xFFFFFFFF) >> (b & 31)


def _hex8(value):
    return format(_i32(value), "x").rjust(8, "0")


def _rive_inner(text):
    t = 0
    for n, char in enumerate(text):
        r = ord(char)
        t = _u32(r + _shl(t, 6) + _shl(t, 16) - t)
        i = _u32(_shl(t, n % 5) | _ushr(t, 32 - (n % 5)))
        t = _i32(t ^ _u32(i ^ (_shl(r, n % 7) | _ushr(r, 8 - (n % 7)))))
        t = _u32(t + _i32(_ushr(t, 11) ^ _shl(t, 3)))
    t = _i32(t ^ _ushr(t, 15))
    t = _u32((65535 & t) * 49842 + _shl((_ushr(t, 16) * 49842) & 65535, 16))
    t = _i32(t ^ _ushr(t, 13))
    t = _u32((65535 & t) * 40503 + _shl((_ushr(t, 16) * 40503) & 65535, 16))
    t = _i32(t ^ _ushr(t, 16))
    return _hex8(t)


def _rive_outer(text):
    n = _i32(3735928559 ^ len(text))
    for index, char in enumerate(text):
        r = ord(char)
        r_xor = (_i32(131 * index + 89) ^ _shl(r, index % 5)) & 255
        r2 = r ^ r_xor
        n = _i32(_u32(_shl(n, 7) | _ushr(n, 25)) ^ r2)
        idx = (65535 & n) * 60205
        o2 = _shl(_ushr(n, 16) * 60205, 16)
        n = _u32(idx + o2)
        n = _i32(n ^ _ushr(n, 11))
    n = _i32(n ^ _ushr(n, 15))
    n = _u32((65535 & n) * 49842 + _shl((_ushr(n, 16) * 49842) & 65535, 16))
    n = _i32(n ^ _ushr(n, 13))
    n = _u32((65535 & n) * 40503 + _shl((_ushr(n, 16) * 40503) & 65535, 16))
    n = _i32(n ^ _ushr(n, 16))
    n = _u32((65535 & n) * 10196 + _shl((_ushr(n, 16) * 10196) & 65535, 16))
    return _hex8(_i32(n ^ _ushr(n, 15)))


def rive_secret_key(value):
    if value is None:
        return "rive"
    try:
        text = str(value)
        numeric = None
        stripped = text.strip()
        if stripped and (stripped.lstrip("+-").isdigit()):
            numeric = int(stripped)
        elif stripped and _is_float(stripped):
            numeric = int(float(stripped))
        if numeric is None:
            total = sum(ord(ch) for ch in text)
            chosen = C_ARRAY[total % len(C_ARRAY)]
            index = (total % len(text)) // 2
        else:
            chosen = C_ARRAY[numeric % len(C_ARRAY)]
            index = (numeric % len(text)) // 2
        mixed = text[:index] + chosen + text[index:]
        return base64.b64encode((_rive_outer(_rive_inner(mixed))).encode("utf-8")).decode("ascii")
    except Exception:
        return "topSecret"


def _is_float(text):
    try:
        float(text)
        return True
    except Exception:
        return False


class RivestreamResolver:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    def _service(self, service, tmdb_id, is_tv, season, episode, key, referer):
        try:
            cb = ""
            if service in ("primevids", "citadel"):
                cb = f"&cb={int(__import__('time').time() * 1000) // 3000000}"
            if is_tv:
                params = (
                    f"requestID=tvVideoProvider&id={tmdb_id}&season={season}&episode={episode}"
                    f"&service={service}{cb}&secretKey={urllib.parse.quote(key, safe='')}"
                )
            else:
                params = (
                    f"requestID=movieVideoProvider&id={tmdb_id}&service={service}{cb}"
                    f"&secretKey={urllib.parse.quote(key, safe='')}"
                )
            payload = fetch_json(
                f"{BASE}/api/backendfetch?{params}",
                headers={
                    "User-Agent": UA,
                    "Referer": referer,
                    "Accept": "application/json, text/plain, */*",
                },
                timeout=30,
            )
            sources = dig(payload, ["data", "sources"])
            if not isinstance(sources, list):
                return []
            out = []
            for item in sources:
                if not isinstance(item, dict) or not truthy(item.get("url")):
                    continue
                url = str(item["url"])
                fmt = str(item.get("format") or "").lower()
                is_hls = fmt in ("hls", "m3u8") or ".m3u8" in url.lower() or ".txt" in url.lower()
                quality = str(item.get("quality") or "Auto")
                if quality.upper() in ("HLS", "DASH", "MP4"):
                    quality = "Auto"
                built = stream(
                    url,
                    f"Rive ({item.get('source') or service})",
                    quality=quality,
                    type="hls" if is_hls else "mp4",
                    headers={"User-Agent": UA, "Referer": referer},
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
            key = rive_secret_key(tmdb_id)
            if is_tv:
                referer = f"{BASE}/watch?type=tv&id={tmdb_id}&season={season}&episode={episode}"
            else:
                referer = f"{BASE}/watch?type=movie&id={tmdb_id}"

            try:
                services_payload = fetch_json(
                    f"{BASE}/api/backendfetch?requestID=VideoProviderServices"
                    f"&secretKey={urllib.parse.quote(rive_secret_key(None), safe='')}",
                    headers={
                        "User-Agent": UA,
                        "Referer": f"{BASE}/",
                        "Accept": "application/json, text/plain, */*",
                    },
                    timeout=6,
                )
                data = dig(services_payload, ["data"])
                services = data if isinstance(data, list) and data else DEFAULTS
            except Exception:
                services = DEFAULTS

            # Keep preferred servers first, then any live ones, capped.
            ordered = []
            for name in PREFERRED + list(services) + DEFAULTS:
                if name not in ordered:
                    ordered.append(name)
            services = ordered[:MAX_SERVICES]

            with ThreadPoolExecutor(max_workers=6) as pool:
                groups = list(
                    pool.map(
                        lambda service: self._service(service, tmdb_id, is_tv, season, episode, key, referer),
                        services,
                    )
                )

            out = [item for group in groups for item in group]
            if not out:
                return fail("RiveStream found no playable streams")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"RiveStream error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(RivestreamResolver)
