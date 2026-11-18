#!/usr/bin/env python3
"""
VidQueen resolver (ported from VyseTV's film_sources/scrapers.dart, vidqueen.js).
Requires: requests
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (UA, cli, dig, fail, fetch_raw, id_from_input, ok, quality_label,
                    stream, truthy)

BASE = "https://api.vidqueen.st"
ORIGIN = "https://vidqueen.st"
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": ORIGIN,
    "Referer": f"{ORIGIN}/",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "sec-ch-ua": '"Not-A.Brand";v="99", "Google Chrome";v="157", "Chromium";v="157"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}
PLAYBACK = {"User-Agent": UA, "Origin": ORIGIN, "Referer": f"{ORIGIN}/"}
SERVERS = [
    ("Bloodstone", "sources=s1&hevc=1"),
    ("Garnet", "sources=s2&hevc=1&vh=1"),
    ("Ruby", "sources=s3&hevc=1&vh=1"),
    ("Obsidian", "sources=s4&sw=1"),
    ("Jet", "sources=s5&hevc=1&vh=1"),
]


class VidqueenResolver:
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
                prefix = f"tv?id={tmdb_id}&season={season}&episode={episode}&mode=json"
            else:
                prefix = f"movie?id={tmdb_id}&mode=json"

            out = []
            seen = set()
            for label, suffix in SERVERS:
                try:
                    res = fetch_raw(f"{BASE}/{prefix}&{suffix}", headers=HEADERS, timeout=10)
                except Exception:
                    continue
                if res.status_code >= 300:
                    continue
                try:
                    data = res.json()
                except Exception:
                    continue
                source = data.get("source")
                if not truthy(source) or not isinstance(source, dict):
                    continue

                source_label = str(source.get("label") or label)
                manifest = source.get("manifest")
                if isinstance(manifest, str) and manifest:
                    lines = [line.strip() for line in manifest.splitlines()]
                    for index, line in enumerate(lines):
                        if not line.startswith("#EXT-X-STREAM-INF"):
                            continue
                        nxt = lines[index + 1] if index + 1 < len(lines) else ""
                        if not nxt.startswith("http") or nxt in seen:
                            continue
                        seen.add(nxt)
                        match = re.search(r"RESOLUTION=\d+x(\d+)", line, re.I)
                        built = stream(
                            nxt,
                            f"Vidqueen - {source_label}",
                            quality=f"{match.group(1)}p" if match else "1080p",
                            type="hls",
                            headers=PLAYBACK,
                        )
                        if built:
                            out.append(built)

                qualities = source.get("qualities")
                has_mp4 = isinstance(qualities, list) and any(dig(x, ["type"]) == "mp4" for x in qualities)
                if has_mp4:
                    for item in qualities:
                        url = dig(item, ["url"])
                        if not isinstance(url, str) or not url or url in seen:
                            continue
                        seen.add(url)
                        built = stream(
                            url,
                            f"Vidqueen - {source_label}",
                            quality=str(item.get("quality") or "Auto"),
                            type="mp4",
                            headers=PLAYBACK,
                        )
                        if built:
                            out.append(built)

                url = source.get("url")
                if truthy(url) and not has_mp4 and not truthy(manifest) and str(url) not in seen:
                    seen.add(str(url))
                    raw = "1080p"
                    if truthy(source.get("h")):
                        raw = f"{source['h']}p"
                    elif truthy(dig(qualities, [0, "quality"])) and dig(qualities, [0, "quality"]) != "Auto":
                        raw = str(dig(qualities, [0, "quality"]))
                    built = stream(
                        str(url),
                        f"Vidqueen - {source_label}",
                        quality=raw,
                        headers=PLAYBACK,
                    )
                    if built:
                        out.append(built)

            if not out:
                return fail("VidQueen found no playable streams")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"VidQueen error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(VidqueenResolver)
