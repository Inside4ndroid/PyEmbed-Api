#!/usr/bin/env python3
"""
LookMovie resolver (ported from VyseTV's film_sources/scrapers.dart, lookmovie.js).
Requires: requests
"""

import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (TMDB_API_KEY, UA, cli, dig, fail, fetch_json, fetch_text,
                    first_truthy, id_from_input, ok, stream, truthy)

DOMAINS = ["https://www.lookmovie2.to", "https://lookmovie2.to", "https://lookmovie.foundation"]
BASE_HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
STORAGE_RE = re.compile(r"""window\[['"](?:movie|show)_storage['"]\]\s*=\s*\{([^}]+)\}""", re.S)
ID_MOVIE_RE = re.compile(r"""['"]?(?:id_movie|movieId)['"]?\s*[:=]\s*['"]?(\d+)['"]?""", re.I)
SEASONS_RE = re.compile(r"seasons\s*:\s*(\[[\s\S]+?\])\s*[,}]")


class LookmovieResolver:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    @staticmethod
    def _episode_id(page, season, episode):
        storage = STORAGE_RE.search(page)
        if storage:
            seasons_match = SEASONS_RE.search(storage.group(1))
            if seasons_match:
                try:
                    seasons = json.loads(seasons_match.group(1))
                    target = next(
                        (
                            item for item in seasons
                            if str(dig(item, ["season"]) if dig(item, ["season"]) is not None else dig(item, ["meta", "season"])) == str(season)
                        ),
                        None,
                    )
                    if target is not None:
                        eps = target.get("episodes")
                        found = None
                        if isinstance(eps, list):
                            found = next((e for e in eps if str(dig(e, ["episode"])) == str(episode)), None)
                        elif isinstance(eps, dict):
                            found = eps.get(str(episode)) or next(
                                (e for e in eps.values() if str(dig(e, ["episode"])) == str(episode)),
                                None,
                            )
                        if found is not None:
                            return str(found.get("id_episode") or found.get("id"))
                except Exception:
                    pass

        split_re = re.compile(r"""id_episode['"]?\s*[:=]\s*['"]?(\d+)['"]?""", re.I)
        matches = list(split_re.finditer(page))
        for index, match in enumerate(matches):
            before = page[0 if index == 0 else matches[index - 1].end():match.start()]
            after = page[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(page)]
            context = (before[-300:] if len(before) > 300 else before) + (after[:300] if len(after) > 300 else after)
            if re.search(rf"""['"]?episode['"]?\s*[:=]\s*['"]?{episode}['"]?""", context, re.I) and re.search(
                rf"""['"]?season['"]?\s*[:=]\s*['"]?{season}['"]?""", context, re.I
            ):
                return match.group(1)

        match = re.search(
            rf"""data-season=["']{season}["'][^>]*?data-episode=["']{episode}["'][^>]*?data-id=["'](\d+)["']""",
            page,
            re.I,
        ) or re.search(
            rf"""data-episode=["']{episode}["'][^>]*?data-season=["']{season}["'][^>]*?data-id=["'](\d+)["']""",
            page,
            re.I,
        )
        return match.group(1) if match else None

    def resolve(self, url_or_id, media_type="movie", season=None, episode=None):
        tmdb_id = id_from_input(url_or_id)
        if not tmdb_id:
            return fail("Could not extract TMDB ID")
        is_tv = media_type == "tv" and season is not None and episode is not None
        try:
            meta = fetch_json(
                f"https://api.themoviedb.org/3/{'tv' if is_tv else 'movie'}/{tmdb_id}?api_key={TMDB_API_KEY}",
                timeout=3,
            )
            title = first_truthy(dig(meta, ["title"]), dig(meta, ["name"])) or ""
            date = str(first_truthy(dig(meta, ["first_air_date"]), dig(meta, ["release_date"])) or "")
            year = date[:4]
            if not title:
                return fail("TMDB metadata unavailable")

            match = None
            base = None
            type_segment = "shows" if is_tv else "movies"
            for domain in DOMAINS:
                try:
                    headers = {
                        **BASE_HEADERS,
                        "Accept": "application/json",
                        "Referer": f"{domain}/",
                        "X-Requested-With": "XMLHttpRequest",
                    }
                    data = fetch_json(
                        f"{domain}/api/v1/{type_segment}/do-search/?q={urllib.parse.quote(title, safe='')}",
                        headers=headers,
                        timeout=4,
                    )
                    results = dig(data, ["result"])
                    if isinstance(results, list) and results:
                        match = next((r for r in results if str(dig(r, ["year"])) == year), None)
                        match = match or next(
                            (r for r in results if isinstance(dig(r, ["title"]), str) and dig(r, ["title"]).lower() == title.lower()),
                            None,
                        )
                        match = match or results[0]
                        if match is not None:
                            base = domain
                            break
                except Exception:
                    continue

            if match is None or base is None or not truthy(match.get("slug")):
                return fail("LookMovie found no matching title")

            page_headers = {**BASE_HEADERS, "Accept": "text/html", "Referer": f"{base}/"}
            page = fetch_text(f"{base}/{type_segment}/play/{match['slug']}", headers=page_headers, timeout=8)
            storage = STORAGE_RE.search(page)
            if not storage:
                return fail("LookMovie storage block not found")
            hash_match = re.search(r"""hash\s*:\s*['"]([^'"]+)['"]""", storage.group(1))
            expires_match = re.search(r"expires\s*:\s*(\d+)", storage.group(1))
            if not hash_match or not expires_match:
                return fail("LookMovie security token not found")

            stream_id = (
                self._episode_id(page, season, episode)
                if is_tv
                else first_truthy(match.get("id_movie"), match.get("id"))
            )
            if isinstance(stream_id, str) and not stream_id.isdigit():
                id_match = ID_MOVIE_RE.search(page)
                stream_id = id_match.group(1) if id_match else None
            if stream_id is None:
                return fail("LookMovie stream id not found")

            access_headers = {
                **BASE_HEADERS,
                "Accept": "application/json",
                "Referer": f"{base}/",
                "X-Requested-With": "XMLHttpRequest",
            }
            kind = "episode" if is_tv else "movie"
            data = fetch_json(
                f"{base}/api/v1/security/{kind}-access?id_{kind}={stream_id}"
                f"&hash={hash_match.group(1)}&expires={expires_match.group(1)}",
                headers=access_headers,
                timeout=8,
            )
            streams = (
                dig(data, ["streams"])
                or dig(data, ["result", "streams"])
                or dig(data, ["data", "streams"])
                or data
            )
            if not isinstance(streams, dict):
                return fail("LookMovie returned no streams")

            out = []
            for key, value in streams.items():
                if isinstance(value, str) and ".m3u8" in value:
                    built = stream(
                        value,
                        f"LookMovie - {key}",
                        quality=str(key),
                        type="hls",
                        headers=access_headers,
                    )
                    if built:
                        out.append(built)
            if not out:
                return fail("LookMovie found no playable streams")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"LookMovie error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(LookmovieResolver)
