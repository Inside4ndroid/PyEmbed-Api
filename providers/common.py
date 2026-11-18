#!/usr/bin/env python3
"""
Shared helpers for PyEmbed-Api resolvers.

The HTTP/TMDB/HLS helpers mirror the ones VyseTV's film_sources use
(`film_sources/common.dart`, GPL-3.0), so the ported scrapers keep their
original request, header and extraction logic.

Requires: requests
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
import urllib.parse

import requests

try:  # urllib3 is a requests dependency; the retry adapter is optional.
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover
    Retry = None

# A browser User-Agent, as the VyseTV scrapers use by default.
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
)

# VyseTV's built-in key; override with PYEMBED_TMDB_KEY if it gets rate limited.
TMDB_API_KEY = (
    os.environ.get("PYEMBED_TMDB_KEY")
    or os.environ.get("TMDB_API_KEY")
    or "b3556f3b206e16f82df4d1f6fd4545e6"
)

DEFAULT_TIMEOUT = 15

_meta_cache = {}
_local = threading.local()


class HttpError(Exception):
    def __init__(self, status, url):
        super().__init__(f"HTTP {status} for {url}")
        self.status = status
        self.url = url


def session():
    """A requests session per thread: providers run in parallel and Session is not thread-safe."""
    s = getattr(_local, "session", None)
    if s is not None:
        return s
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": UA,
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    # The existing PyEmbed resolvers deliberately do not verify certificates:
    # several of these hosts serve incomplete chains on old Android devices.
    s.verify = False
    if Retry is not None:
        adapter = requests.adapters.HTTPAdapter(
            max_retries=Retry(total=1, connect=1, read=0, backoff_factor=0.2,
                              status_forcelist=(500, 502, 503, 504))
        )
        s.mount("https://", adapter)
        s.mount("http://", adapter)
    requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]
    _local.session = s
    return s


def fetch_raw(url, method="GET", headers=None, body=None, timeout=DEFAULT_TIMEOUT,
              follow_redirects=True, stream=False):
    """Any status, any method, like VyseTV's fetchRaw()."""
    kwargs = {
        "headers": headers or {},
        "timeout": timeout,
        "allow_redirects": follow_redirects,
        "stream": stream,
    }
    if body is not None:
        if isinstance(body, (dict, list)):
            kwargs["json"] = body
        else:
            kwargs["data"] = body
    return session().request(method, url, **kwargs)


def fetch_text(url, method="GET", headers=None, body=None, timeout=DEFAULT_TIMEOUT):
    r = fetch_raw(url, method=method, headers=headers, body=body, timeout=timeout)
    if r.status_code < 200 or r.status_code >= 300:
        raise HttpError(r.status_code, url)
    return r.text


def fetch_json(url, method="GET", headers=None, body=None, timeout=DEFAULT_TIMEOUT):
    return json.loads(fetch_text(url, method=method, headers=headers, body=body, timeout=timeout))


def dig(value, path, default=None):
    """Walk decoded JSON like JS's `a?.b?.c`; path items are str keys or int indexes."""
    for key in path:
        if isinstance(key, int) and isinstance(value, list):
            if key < 0 or key >= len(value):
                return default
            value = value[key]
        elif isinstance(key, str) and isinstance(value, dict):
            if key not in value:
                return default
            value = value[key]
        else:
            return default
    return value


def truthy(value):
    if value is None or value is False:
        return False
    if isinstance(value, (int, float)) and value == 0:
        return False
    if isinstance(value, str) and value == "":
        return False
    return True


def first_truthy(*values):
    for value in values:
        if truthy(value):
            return value
    return None


def audio_of(value):
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.lower() in ("", "null", "unknown", "default", "auto", "shared", "multi"):
        return None
    return text


# ── TMDB ──────────────────────────────────────────────────────────────────────

def tmdb_meta(tmdb_id, is_tv, timeout=8):
    """Title/year/imdb/anime metadata, cached like getTmdbMetadata()."""
    key = (str(tmdb_id), bool(is_tv))
    if key in _meta_cache:
        return _meta_cache[key]

    result = {
        "title": "",
        "original_title": "",
        "titles": [],
        "year": None,
        "release_date": "",
        "imdb_id": None,
        "is_anime": False,
        "runtime": 0,
        "seasons": [],
    }
    endpoint = "tv" if is_tv else "movie"
    url = (
        f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}"
        f"?api_key={TMDB_API_KEY}&append_to_response=external_ids,alternative_titles"
    )
    try:
        r = fetch_raw(url, timeout=timeout)
        if r.status_code != 200:
            _meta_cache[key] = result
            return result
        data = r.json()
        title = first_truthy(data.get("name"), data.get("title")) or ""
        original = first_truthy(data.get("original_name"), data.get("original_title")) or ""
        release = first_truthy(data.get("first_air_date"), data.get("release_date")) or ""
        year = int(release[:4]) if len(release) >= 4 and release[:4].isdigit() else None
        imdb = first_truthy(data.get("imdb_id"), dig(data, ["external_ids", "imdb_id"]))
        runtime = 0
        if is_tv:
            runtime = dig(data, ["episode_run_time", 0]) or 24
        else:
            runtime = data.get("runtime") or 90
        titles = []
        if title:
            titles.append(title)
        if original and original not in titles:
            titles.append(original)
        alts = dig(data, ["alternative_titles", "titles"]) or dig(data, ["alternative_titles", "results"]) or []
        for alt in alts:
            alt_title = first_truthy(dig(alt, ["title"]), dig(alt, ["name"]))
            if isinstance(alt_title, str) and alt_title not in titles:
                titles.append(alt_title)
        genres = data.get("genres") or []
        is_anime = any(dig(g, ["id"]) == 16 for g in genres) and (
            "JP" in (data.get("origin_country") or []) or data.get("original_language") == "ja"
        )
        result.update(
            {
                "title": title,
                "original_title": original,
                "titles": titles,
                "year": year,
                "release_date": release,
                "imdb_id": imdb,
                "is_anime": bool(is_anime),
                "runtime": int(runtime or 0),
                "seasons": data.get("seasons") or [],
            }
        )
    except Exception:
        pass
    _meta_cache[key] = result
    return result


def resolve_imdb_id(tmdb_id, is_tv):
    """helpers.js resolveImdbId."""
    text = str(tmdb_id)
    if text.startswith("tt"):
        return text
    imdb = tmdb_meta(text, is_tv).get("imdb_id")
    return imdb or f"tt{text}"


def slugify(text):
    if not text:
        return ""
    normalized = (
        text.lower()
        .replace("à", "a").replace("á", "a").replace("â", "a").replace("ã", "a")
        .replace("ä", "a").replace("å", "a").replace("ç", "c").replace("è", "e")
        .replace("é", "e").replace("ê", "e").replace("ë", "e").replace("ì", "i")
        .replace("í", "i").replace("î", "i").replace("ï", "i").replace("ñ", "n")
        .replace("ò", "o").replace("ó", "o").replace("ô", "o").replace("õ", "o")
        .replace("ö", "o").replace("ù", "u").replace("ú", "u").replace("û", "u")
        .replace("ü", "u").replace("ý", "y").replace("ÿ", "y")
    )
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", normalized))


# ── HLS / quality ─────────────────────────────────────────────────────────────

def _first_uri(playlist):
    for line in playlist.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return None


def hls_audio_is_separate(master):
    return re.search(r"#EXT-X-MEDIA:[^\n]*TYPE=AUDIO[^\n]*URI=", master) is not None


def hls_variants(master_url, headers=None, timeout=6, bandwidth=False, skip=None):
    """
    Variants of an HLS master playlist, mirroring hlsVariantsOf().
    Returns a list of {"url", "quality"}, or None when it isn't a master.
    When audio lives in separate playlists, the master itself is returned whole.
    """
    try:
        text = fetch_text(master_url, headers=headers or {}, timeout=timeout)
    except Exception:
        return None
    if "#EXTM3U" not in text or "#EXT-X-STREAM-INF" not in text:
        return None

    lines = [line.strip() for line in text.splitlines()]
    out = []
    best = 0
    for index, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF:"):
            continue
        quality = "Auto"
        match = re.search(r"RESOLUTION=\d+x(\d+)", line, re.I)
        if match:
            height = int(match.group(1))
            quality = f"{height}p"
            best = max(best, height)
        elif bandwidth:
            match = re.search(r"BANDWIDTH=(\d+)", line, re.I)
            if match:
                bw = int(match.group(1))
                if bw > 3_000_000:
                    quality = "1080p"
                elif bw > 1_800_000:
                    quality = "960p"
                elif bw > 1_200_000:
                    quality = "720p"
                elif bw > 800_000:
                    quality = "640p"
                else:
                    quality = "480p"
        nxt = lines[index + 1] if index + 1 < len(lines) else ""
        if nxt and not nxt.startswith("#"):
            if skip and skip(nxt):
                continue
            out.append({"url": urllib.parse.urljoin(master_url, nxt), "quality": quality})

    if not out:
        return None
    if hls_audio_is_separate(text):
        return [{"url": master_url, "quality": f"{best}p" if best else "Auto"}]
    return out


def quality_label(raw, url=""):
    """Normalise a source's word for a quality to '4K'/'1080p'/.../'Auto'."""
    text = str(raw or "").strip().lower()
    if "4k" in text or "2160" in text or text == "uhd":
        return "4K"
    if text in ("fhd", "fullhd", "full hd"):
        return "1080p"
    if text == "hd":
        return "720p"
    if text == "sd":
        return "480p"
    for height in (1440, 1080, 720, 480, 360, 240):
        if str(height) in text:
            return f"{height}p"
    if text in ("auto", "hd", "sd", "unknown", ""):
        low_url = str(url or "").lower()
        if "2160" in low_url or "4k" in low_url:
            return "4K"
        for height in (1440, 1080, 720, 480, 360, 240):
            if f"{height}p" in low_url:
                return f"{height}p"
        return "Auto"
    if text.isdigit():
        return f"{text}p"
    return text


def quality_rank(value):
    text = str(value or "").lower()
    if "4k" in text or "2160" in text:
        return 2160
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else 0


def stream_type(url, given=None):
    text = str(given or "").lower()
    if text in ("hls", "m3u8"):
        return "hls"
    if text in ("dash", "mpd"):
        return "dash"
    low = str(url or "").lower()
    if ".m3u8" in low:
        return "hls"
    if ".mpd" in low:
        return "dash"
    return "mp4"


def stream(url, server, quality="Auto", type=None, headers=None, audio=None):
    """Build one PyEmbed playable_urls entry; None when the URL is unusable."""
    if not isinstance(url, str):
        return None
    url = url.strip()
    if not url.startswith("http"):
        return None
    label = quality_label(quality, url)
    if audio:
        server = f"{server} [{audio}]"
    return {
        "url": url,
        "quality": label,
        "type": stream_type(url, type),
        "headers": headers or {},
        "server": server or "Server",
    }


def dedupe(streams):
    seen = set()
    out = []
    for item in streams:
        if not item:
            continue
        url = item.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(item)
    return out


def ok(tmdb_id, streams):
    """Unified success response."""
    return json.dumps(
        {
            "status": "success",
            "tmdb_id": str(tmdb_id),
            "playable_urls": dedupe(streams),
        }
    )


def fail(message):
    return json.dumps({"status": "error", "message": str(message)})


# ── misc ──────────────────────────────────────────────────────────────────────

def b64url(text):
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def sha256_hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def format_size(value):
    try:
        size = float(value)
    except (TypeError, ValueError):
        return ""
    if size <= 0:
        return ""
    gb = size / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.2f} GB"
    return f"{round(size / (1024 ** 2))} MB"


def cli(resolver_cls):
    """Small CLI shared by the ports: python providers/tmdb/<name>.py 550 --type tv ..."""
    import argparse

    parser = argparse.ArgumentParser(description=resolver_cls.__name__)
    parser.add_argument("url_or_id", help="TMDB ID or URL")
    parser.add_argument("--type", choices=["movie", "tv"], default="movie")
    parser.add_argument("--season", type=int)
    parser.add_argument("--episode", type=int)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    resolver = resolver_cls(debug=args.debug)
    result = resolver.resolve(args.url_or_id, args.type, args.season, args.episode)
    if args.pretty:
        try:
            result = json.dumps(json.loads(result), indent=2)
        except Exception:
            pass
    print(result)


def id_from_input(url_or_id):
    """Extract a TMDB id from a URL, like the receivers' entry points."""
    text = str(url_or_id)
    if text.startswith("http"):
        match = re.search(r"/(?:movie|tv)/(\d+)", text)
        return match.group(1) if match else None
    return text
