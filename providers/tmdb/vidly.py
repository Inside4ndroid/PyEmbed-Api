#!/usr/bin/env python3
"""
Vidly resolver (ported from VyseTV's film_sources/scrapers.dart, vidly.js).
Payloads use a custom `v1.` stream cipher.

Requires: requests
"""

import base64
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (UA, audio_of, cli, dig, fail, fetch_text, first_truthy,
                    hls_variants, id_from_input, ok, quality_rank, stream, truthy)

BASE = "https://vidly.pro"
SECRET = r"vY7#qL2!mZ9@wK4$"
HEADERS = {
    "User-Agent": UA,
    "Referer": f"{BASE}/",
    "Origin": BASE,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
PLAYBACK = {"User-Agent": UA, "Referer": f"{BASE}/", "Origin": BASE}


def _u32(value):
    return value & 0xFFFFFFFF


def _i32(value):
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def _vidly_decrypt(sealed):
    if not sealed.startswith("v1."):
        return None
    try:
        b64 = sealed[3:].replace("-", "+").replace("_", "/")
        while len(b64) % 4:
            b64 += "="
        raw = base64.b64decode(b64)
        salt = raw[:12]
        payload = bytearray(raw[12:])

        keys = []
        for stage in range(4):
            n = _u32(0x811C9DC5 ^ _u32(0x9E3779B9 * stage))
            for ch in SECRET:
                n = _u32((n ^ ord(ch)) * 0x1000193)
            for byte in salt:
                n = _u32((n ^ byte) * 0x1000193)
            keys.append(n)

        s_key, n_key, l_key, a_key = keys
        r = 0
        for index in range(len(payload)):
            if (3 & index) == 0:
                l_key = _u32(l_key)
                a_key = _u32(a_key)
                s_key = _u32(s_key)
                n_key = _u32(n_key)
                e = _i32(s_key + n_key)
                s_key = _i32(n_key ^ (n_key >> 9))
                n_key = _i32(l_key + _i32(l_key << 3))
                a_key = _i32(a_key + 1)
                e = _i32(e + a_key)
                l_key = _i32(_i32(_i32(l_key << 21) | (l_key >> 11)) + e)
                r = _u32(e)
            payload[index] ^= (r >> ((3 & index) * 8)) & 255
        return json.loads(bytes(payload).decode("utf-8", "replace"))
    except Exception:
        return None


class VidlyResolver:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    @staticmethod
    def _invalid(url):
        return not url or bool(re.search(r"tiles|thumbs?|sprite", url, re.I))

    def resolve(self, url_or_id, media_type="movie", season=None, episode=None):
        tmdb_id = id_from_input(url_or_id)
        if not tmdb_id:
            return fail("Could not extract TMDB ID")
        is_tv = media_type == "tv" and season is not None and episode is not None
        try:
            if is_tv:
                target = f"{BASE}/tv/{tmdb_id}/{season}/{episode}?preview=1"
            else:
                target = f"{BASE}/movie/{tmdb_id}?preview=1"
            page = fetch_text(target, headers=HEADERS, timeout=10)

            out = []
            seen = set()
            sealed_match = re.search(r"v1\.[a-zA-Z0-9_-]{100,}", page)
            if sealed_match:
                data = _vidly_decrypt(sealed_match.group(0))
                streams = dig(data, ["streams"])
                if isinstance(streams, list):
                    label = str(first_truthy(dig(data, ["provider", "label"]), "Vidly"))
                    for item in streams:
                        if not isinstance(item, dict):
                            continue
                        url = item.get("url")
                        if not isinstance(url, str) or not url.startswith("http") or self._invalid(url):
                            continue
                        if ".m3u8" in url:
                            variants = hls_variants(
                                url, headers=PLAYBACK, timeout=6, bandwidth=True, skip=self._invalid
                            )
                            if variants:
                                for variant in variants:
                                    if self._invalid(variant["url"]) or variant["url"] in seen:
                                        continue
                                    seen.add(variant["url"])
                                    built = stream(
                                        variant["url"],
                                        f"Vidly - {label} ({variant['quality']})",
                                        quality=variant["quality"],
                                        type="hls",
                                        headers=PLAYBACK,
                                        audio=audio_of(item.get("language")),
                                    )
                                    if built:
                                        out.append(built)
                                continue
                        if url in seen:
                            continue
                        seen.add(url)
                        quality = str(item.get("quality") or "Auto").strip()
                        if quality.isdigit():
                            quality = f"{quality}p"
                        built = stream(
                            url,
                            f"Vidly - {label}" + (f" ({item['language']})" if truthy(item.get("language")) else ""),
                            quality=quality,
                            type=item.get("type"),
                            headers=PLAYBACK,
                            audio=audio_of(item.get("language")),
                        )
                        if built:
                            out.append(built)

            if not out:
                match = re.search(
                    r"""https?://[^"'\\<>\s]+/media/([a-zA-Z0-9_-]+)/thumbs""",
                    page,
                    re.I,
                )
                if match:
                    master = match.group(0).split("/media/")[0] + f"/media/{match.group(1)}/index.m3u8"
                    variants = hls_variants(master, headers=PLAYBACK, timeout=6, bandwidth=True, skip=self._invalid)
                    if variants:
                        for variant in variants:
                            if self._invalid(variant["url"]) or variant["url"] in seen:
                                continue
                            seen.add(variant["url"])
                            built = stream(
                                variant["url"],
                                f"Vidly - Direct ({variant['quality']})",
                                quality=variant["quality"],
                                type="hls",
                                headers=PLAYBACK,
                            )
                            if built:
                                out.append(built)
                    elif not self._invalid(master) and master not in seen:
                        seen.add(master)
                        built = stream(master, "Vidly - Direct", type="hls", headers=PLAYBACK)
                        if built:
                            out.append(built)

            out.sort(key=lambda s: quality_rank(s.get("quality")), reverse=True)
            if not out:
                return fail("Vidly found no playable streams")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"Vidly error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(VidlyResolver)
