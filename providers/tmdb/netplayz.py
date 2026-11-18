#!/usr/bin/env python3
"""
NetPlayz resolver (ported from VyseTV's film_sources/scrapers.dart, netplayz.js).
Castle-family API with AES-CBC encrypted JSON.

Requires: requests, pycryptodome
"""

import base64
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import UA, cli, dig, fail, fetch_raw, first_truthy, id_from_input, ok, stream, truthy

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
except ImportError:
    raise ImportError("Please install pycryptodome: pip install pycryptodome")

API = "https://api.hwnou.com"
KEY = b"fJATm*kgfJT!BgJB"
OKHTTP = "okhttp/3.2.0"
APK_SIGN_KEY = "ED0955EB04E67A1D9F3305B95454FED485261475"
STREAM_HEADERS = {"User-Agent": UA, "Referer": "https://thugtv.online/", "Origin": "https://thugtv.online"}


class NetplayzResolver:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    @staticmethod
    def _aes_decrypt(ciphertext):
        raw = base64.b64decode(ciphertext.strip())
        cipher = AES.new(KEY, AES.MODE_CBC, KEY)
        return unpad(cipher.decrypt(raw), AES.block_size).decode("utf-8", "ignore").strip()

    def _hwnou(self, url, method="GET", body=None):
        try:
            headers = {
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "User-Agent": OKHTTP,
            }
            if body is not None:
                headers["Content-Type"] = "application/json;charset=utf-8"
            res = fetch_raw(url, method=method, headers=headers, body=body, timeout=20)
            if res.status_code >= 300 or not res.text:
                return None
            return json.loads(self._aes_decrypt(res.text))
        except Exception:
            return None

    def resolve(self, url_or_id, media_type="movie", season=None, episode=None):
        tmdb_id = id_from_input(url_or_id)
        if not tmdb_id:
            return fail("Could not extract TMDB ID")
        is_tv = media_type == "tv" and season is not None and episode is not None
        episode_number = (episode or 1) if is_tv else 1
        try:
            from common import tmdb_meta

            meta = tmdb_meta(tmdb_id, is_tv)
            title = meta["title"]
            if not title:
                return fail("TMDB metadata unavailable")

            keyword = urllib.parse.quote(title.lower().replace(" ", "+"), safe="")
            search = self._hwnou(
                f"{API}/film-api/v2.1.2/movie/searchByKeyword?keyword={keyword}&page=1&size=20&mode=1"
                "&secure=0&channel=IndiaA&appMarket=GuanWang&packageName=com.external.castle&clientType=1"
            )
            rows = dig(search, ["data", "rows"]) if search else []
            if not isinstance(rows, list):
                return fail("NetPlayz search failed")

            candidates = [r for r in rows if isinstance(r, dict) and (dig(r, ["movieType"]) == 2) == (not is_tv)]
            if not candidates:
                return fail("NetPlayz found no matching title")
            match = next(
                (r for r in candidates if str(dig(r, ["title"]) or "").lower() == title.lower()),
                candidates[0],
            )
            movie_id = match.get("id")
            if movie_id is None:
                return fail("NetPlayz movie id missing")

            details = self._hwnou(
                f"{API}/film-api/v2.1.2/movie?movieId={movie_id}&packageName=com.external.castle&clientType=1"
            )
            episodes = dig(details, ["data", "episodes"]) if details else []
            if not isinstance(episodes, list) or not episodes:
                return fail("NetPlayz returned no episodes")

            if is_tv:
                target_ep = next(
                    (e for e in episodes if str(dig(e, ["number"])) == str(episode_number)),
                    episodes[0],
                )
            else:
                target_ep = episodes[0]

            videos = dig(target_ep, ["videos"]) or []
            free = [v for v in videos if isinstance(v, dict) and v.get("premiumProPermission") is False]
            free.sort(key=lambda v: v.get("resolution") or 0, reverse=True)
            video = free[0] if free else (videos[0] if videos else None)
            if not isinstance(video, dict):
                return fail("NetPlayz returned no video")

            tracks = dig(target_ep, ["tracks"]) or []
            preferred = next(
                (t for t in tracks if dig(t, ["languageId"]) == 1003),
                tracks[0] if tracks else None,
            )
            language_id = dig(preferred, ["languageId"])

            body = json.dumps(
                {
                    "appMarket": "GuanWang",
                    "woolUser": "false",
                    "isp": "Android",
                    "useVipCdn": "false",
                    "movieId": movie_id,
                    "episodeId": target_ep.get("id"),
                    "isNewUser": "true",
                    "resolution": video.get("resolution"),
                    "mode": "1",
                    "clientType": "1",
                    "apkSignKey": APK_SIGN_KEY,
                    "androidVersion": "11",
                    "networkType": "NETWORK_WIFI",
                    "packageName": "com.external.castle",
                    "languageId": language_id,
                },
                separators=(",", ":"),
            )
            stream_data = self._hwnou(
                f"{API}/film-api/v2.0.7/movie/getVideo2?clientType=1&packageName=PKG&channel=CHANNEL&lang=en-US",
                method="POST",
                body=body,
            )
            video_url = dig(stream_data, ["data", "videoUrl"]) if stream_data else None
            if not isinstance(video_url, str) or not video_url:
                return fail("NetPlayz returned no video URL")

            quality = str(
                first_truthy(
                    video.get("resolutionDescription"),
                    f"{video['resolution']}p" if truthy(video.get("resolution")) else "Auto",
                )
            )
            built = stream(
                video_url,
                f"NetPlayz - {quality}",
                quality=quality,
                type="hls" if ".m3u8" in video_url else ("dash" if ".mpd" in video_url else "mp4"),
                headers=STREAM_HEADERS,
            )
            if not built:
                return fail("NetPlayz returned an invalid URL")
            return ok(tmdb_id, [built])
        except Exception as exc:
            self.log(f"NetPlayz error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(NetplayzResolver)
