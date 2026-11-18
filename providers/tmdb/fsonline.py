#!/usr/bin/env python3
"""
FSOnline resolver (ported from VyseTV's film_sources/scrapers.dart, fsonline.js).
Requires: requests
"""

import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import UA, cli, fail, fetch_text, id_from_input, ok, stream, tmdb_meta

ORIGIN = "https://www3.fsonline.app"
AJAX = f"{ORIGIN}/wp-admin/admin-ajax.php"
HEADERS = {"User-Agent": UA, "Origin": ORIGIN, "Referer": f"{ORIGIN}/"}


class FsonlineResolver:
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
            query = meta["titles"][0] + (f" {meta['year']}" if meta["year"] else "")
            search_html = fetch_text(
                f"{ORIGIN}/?s={urllib.parse.quote(query, safe='')}",
                headers=HEADERS,
                timeout=15,
            )
            folder = "seriale" if is_tv else "film"
            link = re.search(
                rf'href=["\'](https?://www3\.fsonline\.app/{folder}/([^"\'/]+)/)["\']',
                search_html,
                re.I,
            )
            if not link:
                return fail("FSOnline search found no title")

            if is_tv:
                slug = re.sub(r"-\d{4}$", "", link.group(2))
                target = f"{ORIGIN}/episoade/{slug}-sezonul-{season}-episodul-{episode}/"
            else:
                target = link.group(1)

            page_html = fetch_text(target, headers=HEADERS, timeout=15)
            movie_id = None
            m = re.search(r"""movie-id=['"]([^'"]+)['"]""", page_html) or re.search(r"movie-id=([^ >]+)", page_html)
            if m:
                movie_id = m.group(1)
            if not movie_id:
                return fail("FSOnline movie id not found")

            ajax_html = fetch_text(
                AJAX,
                method="POST",
                headers={
                    **HEADERS,
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": target,
                },
                body=f"action=lazy_player&movieID={movie_id}",
                timeout=15,
            )

            out = []
            index = 0
            while True:
                index = ajax_html.find('data-vs="', index)
                if index == -1:
                    break
                embed_start = index + 9
                embed_end = ajax_html.find('"', embed_start)
                if embed_end == -1:
                    break
                embed_url = ajax_html[embed_start:embed_end]
                span_start = ajax_html.find("<span>", embed_end)
                span_end = ajax_html.find("</span>", span_start)
                if span_start < 0 or span_end < 0:
                    break
                label = ajax_html[span_start + 6:span_end].strip().lower()
                if "filesun" in label:
                    try:
                        player_html = fetch_text(
                            embed_url,
                            headers={"Referer": ORIGIN, "User-Agent": UA},
                            timeout=15,
                        )
                        match = re.search(r"""file:\s*["'](https?://[^"']+\.m3u8[^"']*)["']""", player_html) or re.search(
                            r"""["']?file["']?:\s*["'](https?://[^"']+)["']""", player_html
                        )
                        if match:
                            built = stream(
                                match.group(1).replace("\\/", "/"),
                                "FSOnline - FileSuN",
                                type="hls",
                                headers={
                                    "Referer": embed_url,
                                    "Origin": "https://player.fsonline.app",
                                    "User-Agent": UA,
                                },
                            )
                            if built:
                                out.append(built)
                    except Exception:
                        pass
                index = span_end

            if not out:
                return fail("FSOnline found no FileSuN stream")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"FSOnline error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(FsonlineResolver)
