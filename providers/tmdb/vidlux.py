#!/usr/bin/env python3
"""
VidLux resolver (ported from VyseTV's film_sources/scrapers.dart, vidlux.js).
Answers are AES-256-GCM encrypted with a key derived from a fixed passphrase.

Requires: requests, pycryptodome
"""

import base64
import hashlib
import json
import os
import re
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import (UA, cli, fail, fetch_raw, fetch_text, first_truthy,
                    id_from_input, ok, stream, truthy)

try:
    from Crypto.Cipher import AES
except ImportError:
    raise ImportError("Please install pycryptodome: pip install pycryptodome")

BASE = "https://vidlux.xyz"
PASSPHRASE = "vidlux-stream-encryption-2026-secure-key"
PLAYBACK = {"User-Agent": UA, "Referer": f"{BASE}/", "Origin": BASE}
SERVERS = [
    ("robot", "Robot"), ("titan", "Titan"), ("spider", "Spider"),
    ("dragon", "Dragon"), ("quasar", "Quasar"), ("vidfast", "Flux"),
    ("rocket", "Aether"), ("star", "Star"), ("bolt", "Bolt"),
    ("quilox", "Quilox"), ("vidrock", "Nova"), ("dubai", "Dubai"),
    ("magic", "Magic"), ("vixsrc", "Aura"), ("astra", "Astra"),
]
# The site rate-limits a whole IP after a burst, so stop well before all 15.
MAX_SERVERS = 6


class VidluxResolver:
    def __init__(self, debug=False):
        self.debug = debug

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    @staticmethod
    def _decrypt(payload):
        try:
            key = hashlib.sha256(PASSPHRASE.encode("utf-8")).digest()
            raw = base64.b64decode(payload)
            iv, body = raw[:12], raw[12:]
            cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
            plain = cipher.decrypt_and_verify(body[:-16], body[-16:])
            return json.loads(plain.decode("utf-8"))
        except Exception:
            return None

    def resolve(self, url_or_id, media_type="movie", season=None, episode=None):
        tmdb_id = id_from_input(url_or_id)
        if not tmdb_id:
            return fail("Could not extract TMDB ID")
        is_tv = media_type == "tv" and season is not None and episode is not None
        try:
            if is_tv:
                embed_url = f"{BASE}/embed/tv/{tmdb_id}/{season}/{episode}"
            else:
                embed_url = f"{BASE}/embed/movie/{tmdb_id}"

            try:
                html = fetch_text(embed_url, headers={"User-Agent": UA, "Referer": f"{BASE}/"}, timeout=8)
            except Exception:
                return fail("VidLux embed page failed to load")

            token = None
            match = re.search(r"(\d{13}\.[a-f0-9]{8}\.[a-f0-9]{64})", html, re.I)
            if match:
                token = match.group(1)
            else:
                match = re.search(r"""requestToken["\\'\s:]+([a-zA-Z0-9._-]+)""", html, re.I)
                if match:
                    token = match.group(1)
            if not token:
                return fail("VidLux token not found")

            query = {
                "id": tmdb_id,
                "type": "tv" if is_tv else "movie",
                "_t": token,
            }
            if is_tv:
                query["season"] = str(season)
                query["episode"] = str(episode)
            qs = urllib.parse.urlencode(query)

            out = []
            seen = set()
            for server_id, label in SERVERS[:MAX_SERVERS]:
                try:
                    res = fetch_raw(
                        f"{BASE}/api/extract/{server_id}?{qs}",
                        headers={
                            "Accept": "*/*",
                            "Accept-Language": "en-US,en;q=0.9",
                            "User-Agent": UA,
                            "Referer": embed_url,
                            "Origin": BASE,
                        },
                        timeout=10,
                    )
                except Exception:
                    continue
                if res.status_code == 429:
                    # A burst locks the whole IP for ~10 minutes; asking again only extends it.
                    break
                if res.status_code >= 300:
                    continue
                try:
                    data = res.json()
                except Exception:
                    continue
                if truthy(data.get("encrypted")) and truthy(data.get("data")):
                    data = self._decrypt(str(data.get("data")))
                if not isinstance(data, dict):
                    continue

                items = data.get("streams") if isinstance(data.get("streams"), list) else (
                    data.get("sources") if isinstance(data.get("sources"), list) else []
                )
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    stream_url = first_truthy(item.get("file"), item.get("url"))
                    if not isinstance(stream_url, str):
                        continue
                    if stream_url.startswith("/"):
                        stream_url = f"{BASE}{stream_url}"
                    if not stream_url.startswith("http") or stream_url in seen:
                        continue
                    seen.add(stream_url)
                    quality = str(first_truthy(item.get("quality"), "Auto"))
                    if quality.strip().isdigit():
                        quality = f"{quality.strip()}p"
                    built = stream(
                        stream_url,
                        f"VidLux - {label}",
                        quality=quality,
                        type=item.get("type"),
                        headers=PLAYBACK,
                    )
                    if built:
                        out.append(built)
                if out:
                    break

            if not out:
                return fail("VidLux found no playable streams")
            return ok(tmdb_id, out)
        except Exception as exc:
            self.log(f"VidLux error: {exc}", "ERROR")
            return fail(exc)


if __name__ == "__main__":
    cli(VidluxResolver)
