#!/usr/bin/env python3
"""
TrendiMovies resolver (ported from VyseTV's film_sources/scrapers.dart, trendimovies.js).
Reads download links from the page's Astro island props.

Requires: requests
"""

import html as html_module
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (UA, cli, dig, fail, fetch_text, first_truthy, id_from_input,
                    ok, quality_rank, stream, truthy)

BASE = "https://trendimovies.com"
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": f"{BASE}/",
}
PLAYBACK = {"User-Agent": UA, "Referer": f"{BASE}/"}


class TrendimoviesResolver:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    @staticmethod
    def _unwrap(value):
        if isinstance(value, list):
            if len(value) == 2 and value[0] in (0, 1):
                return TrendimoviesResolver._unwrap(value[1])
            return [TrendimoviesResolver._unwrap(v) for v in value]
        if isinstance(value, dict):
            return {k: TrendimoviesResolver._unwrap(v) for k, v in value.items()}
        return value

    @staticmethod
    def _file_type(url, item):
        ext = first_truthy(item.get("format"), item.get("extension"), item.get("ext"), item.get("type"))
        if ext is not None:
            return str(ext).lower().lstrip(".")
        low = url.lower()
        if ".m3u8" in low:
            return "hls"
        if ".mpd" in low:
            return "dash"
        if ".mp4" in low:
            return "mp4"
        if ".avi" in low:
            return "avi"
        return "mkv"

    def _links(self, raw):
        if not isinstance(raw, list):
            return []
        seen = set()
        out = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            url = first_truthy(item.get("url"), item.get("file_url"), item.get("link"))
            if not isinstance(url, str) or not url.startswith("http") or url in seen:
                continue
            seen.add(url)
            quality = str(first_truthy(item.get("quality"), item.get("resolution"), "Auto"))
            if quality.strip().isdigit():
                quality = f"{quality}p"
            size = first_truthy(item.get("file_size"), item.get("size"))
            language = item.get("language")
            label = f"TrendiMovies - {quality}"
            if truthy(language):
                label += f" ({language})"
            if truthy(size):
                label += f" [{size}]"
            built = stream(
                url,
                label,
                quality=quality,
                type=self._file_type(url, item),
                headers=PLAYBACK,
                audio=language,
            )
            if built:
                out.append(built)
        return out

    @staticmethod
    def _islands(page):
        out = []
        for match in re.finditer(r'<astro-island[^>]*props="([^"]+)"', page):
            try:
                decoded = html_module.unescape(match.group(1))
                out.append(TrendimoviesResolver._unwrap(json.loads(decoded)))
            except Exception:
                pass
        return out

    def resolve(self, url_or_id, media_type="movie", season=None, episode=None):
        tmdb_id = id_from_input(url_or_id)
        if not tmdb_id:
            return fail("Could not extract TMDB ID")
        is_tv = media_type == "tv" and season is not None and episode is not None
        try:
            all_links = []
            if not is_tv:
                page = fetch_text(f"{BASE}/movie/{tmdb_id}", headers=HEADERS, timeout=25)
                for island in self._islands(page):
                    raw = (
                        dig(island, ["links"])
                        or dig(island, ["movie", "downloads"])
                        or dig(island, ["downloads"])
                        or dig(island, ["movie", "links"])
                    )
                    found = self._links(raw)
                    if found:
                        all_links = found
                        break
            else:
                page = None
                for path in (f"/tv/{tmdb_id}", f"/show/{tmdb_id}"):
                    try:
                        page = fetch_text(f"{BASE}{path}", headers=HEADERS, timeout=25)
                        break
                    except Exception:
                        continue
                if page:
                    by_season = None
                    by_episode = None
                    for island in self._islands(page):
                        by_season = (
                            dig(island, ["episodesBySeason"])
                            or dig(island, ["show", "episodes"])
                            or dig(island, ["episodes"])
                            or by_season
                        )
                        by_episode = (
                            dig(island, ["downloadsByEpisode"])
                            or dig(island, ["downloads"])
                            or by_episode
                        )
                        if by_season is not None and by_episode is not None:
                            break
                    episodes = dig(by_season, [str(season)]) if isinstance(by_season, dict) else None
                    if isinstance(episodes, list) and by_episode is not None:
                        target = next(
                            (ep for ep in episodes if isinstance(ep, dict) and str(dig(ep, ["episode_number"])) == str(episode)),
                            None,
                        )
                        if target and target.get("id") is not None:
                            all_links = self._links(dig(by_episode, [str(target["id"])]))

            all_links.sort(key=lambda s: quality_rank(s.get("quality")), reverse=True)
            if not all_links:
                return fail("TrendiMovies found no download links")
            return ok(tmdb_id, all_links)
        except Exception as exc:
            self.log(f"TrendiMovies error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(TrendimoviesResolver)
