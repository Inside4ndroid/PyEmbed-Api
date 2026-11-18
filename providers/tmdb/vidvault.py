#!/usr/bin/env python3
"""
VidVault resolver (ported from VyseTV's film_sources/scrapers.dart, vidvault.js).
Download pages; starts a conversion job when a quality isn't ready.

Requires: requests
"""

import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import UA, cli, dig, fail, fetch_raw, id_from_input, ok, quality_rank, stream, truthy

BASE = "https://vidvault.to"
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{BASE}/",
}
PLAYBACK = {"User-Agent": UA, "Referer": f"{BASE}/"}


class VidvaultResolver:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    @staticmethod
    def _path(is_tv, tmdb_id, season, episode, kind, quality):
        if is_tv:
            return f"{BASE}/{kind}/tv/{tmdb_id}/{season}/{episode}/{quality}"
        return f"{BASE}/{kind}/movie/{tmdb_id}/{quality}"

    def _download(self, is_tv, tmdb_id, season, episode, quality):
        try:
            res = fetch_raw(
                self._path(is_tv, tmdb_id, season, episode, "download-link", quality),
                headers={**HEADERS, "Accept": "application/json"},
                timeout=4,
            )
            if res.status_code >= 300:
                return None
            url = dig(res.json(), ["url"])
            if not truthy(url):
                return None
            clean = str(url).split("?")[0].split("#")[0]
            if not clean.endswith(".mkv") and not clean.endswith(".mp4"):
                clean += ".mkv"
            return clean
        except Exception:
            return None

    def _poll(self, job_id):
        started = time.time()
        while time.time() - started < 12:
            try:
                res = fetch_raw(
                    f"{BASE}/job/{job_id}?t={int(time.time() * 1000)}",
                    headers=HEADERS,
                    timeout=3,
                )
                if res.status_code < 300:
                    status = dig(res.json(), ["status"])
                    if status == "done":
                        return True
                    if status == "error":
                        return False
            except Exception:
                pass
            time.sleep(0.6)
        return False

    def _prepare(self, is_tv, tmdb_id, season, episode, quality):
        url = self._download(is_tv, tmdb_id, season, episode, quality)
        if url:
            return url
        try:
            res = fetch_raw(
                self._path(is_tv, tmdb_id, season, episode, "start-conversion", quality),
                method="POST",
                headers=HEADERS,
                timeout=6,
            )
            if res.status_code < 300:
                job = dig(res.json(), ["jobId"])
                if job == "existing":
                    return self._download(is_tv, tmdb_id, season, episode, quality)
                if truthy(job) and self._poll(str(job)):
                    return self._download(is_tv, tmdb_id, season, episode, quality)
        except Exception:
            pass
        return None

    def resolve(self, url_or_id, media_type="movie", season=None, episode=None):
        tmdb_id = id_from_input(url_or_id)
        if not tmdb_id:
            return fail("Could not extract TMDB ID")
        is_tv = media_type == "tv" and season is not None and episode is not None
        try:
            if is_tv:
                page_url = f"{BASE}/tv/{tmdb_id}/{season}/{episode}"
            else:
                page_url = f"{BASE}/movie/{tmdb_id}"
            res = fetch_raw(page_url, headers=HEADERS, timeout=35)
            if res.status_code >= 300:
                return fail(f"VidVault HTTP {res.status_code}")
            page = res.text

            out = []
            seen = set()
            for match in re.finditer(
                r"""<div[^>]*class=["'][^"']*quality-item[^"']*["'][^>]*>([\s\S]*?)</div>""",
                page,
                re.I,
            ):
                block = match.group(1)
                jump = re.search(r"""window\.location\.href\s*=\s*['"]([^'"]+)['"]""", block, re.I)
                if not jump:
                    continue
                url = jump.group(1).strip()
                if url in seen:
                    continue
                seen.add(url)
                quality_match = re.search(r"Download\s*([0-9a-zA-Z]+)", block, re.I)
                quality = quality_match.group(1).strip() if quality_match else "Auto"
                size_match = re.search(r"<small>\(([^)]+)\)</small>", block, re.I)
                size = size_match.group(1).strip() if size_match else ""
                label = f"VidVault - {quality.upper()}" + (f" ({size})" if size else "")
                built = stream(url, label, quality=quality, type="mkv", headers=PLAYBACK)
                if built:
                    out.append(built)

            if out:
                out.sort(key=lambda s: quality_rank(s.get("quality")), reverse=True)
                return ok(tmdb_id, out)

            qualities = [m.group(1) for m in re.finditer(r"""id=["']item-([0-9a-zA-Z]+)["']""", page, re.I)]
            if not qualities:
                qualities = ["1080p", "720p", "360p"]

            with ThreadPoolExecutor(max_workers=3) as pool:
                urls = list(
                    pool.map(
                        lambda quality: (quality, self._prepare(is_tv, tmdb_id, season, episode, quality)),
                        qualities,
                    )
                )

            for quality, url in urls:
                if not url or url in seen:
                    continue
                seen.add(url)
                built = stream(
                    url,
                    f"VidVault - {quality.upper()}",
                    quality=quality,
                    type="mkv",
                    headers=PLAYBACK,
                )
                if built:
                    out.append(built)

            out.sort(key=lambda s: quality_rank(s.get("quality")), reverse=True)
            if not out:
                return fail("VidVault found no download links")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"VidVault error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(VidvaultResolver)
