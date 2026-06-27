#!/usr/bin/env python3
"""
Vidlink Resolver - Standalone Version
Supports both movies and TV shows.
Returns JSON with stream URL and headers (subtitles omitted).
Based on vidlink.js
Requires: requests
"""

import re
import json
import time
import urllib.parse
import requests
from typing import Dict, List, Optional, Any

__version__ = "1.0.1"

# Constants
TMDB_API_KEY = "68e094699525b18a70bab2f86b1fa706"
ENC_DEC_API = "https://enc-dec.app/api"
VIDLINK_API = "https://vidlink.pro/api/b"

VIDLINK_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Connection": "keep-alive",
    "Referer": "https://vidlink.pro/",
    "Origin": "https://vidlink.pro",
    "Accept": "application/json,*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
}

QUALITY_ORDER = {
    "4K": 5,
    "1440p": 4,
    "1080p": 3,
    "720p": 2,
    "480p": 1,
    "360p": 0,
    "240p": -1,
    "Auto": -2,
    "Unknown": -3,
}


class VidlinkResolver:
    def __init__(self, debug=False):
        self.debug = debug
        self.session = requests.Session()
        self.session.headers.update(VIDLINK_HEADERS)

    def log(self, message, level="INFO"):
        if self.debug or level == "ERROR":
            print(f"[{level}] {message}")

    def _make_request(self, url, method="GET", headers=None, json_data=None, timeout=20):
        if headers is None:
            headers = VIDLINK_HEADERS.copy()
        try:
            if method.upper() == "GET":
                resp = self.session.get(url, headers=headers, timeout=timeout)
            else:
                resp = self.session.post(url, headers=headers, json=json_data, timeout=timeout)
            if resp.status_code >= 400:
                raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")
            return resp
        except Exception as e:
            self.log(f"Request failed for {url}: {e}", "ERROR")
            raise

    def _get_tmdb_info(self, tmdb_id: str, media_type: str) -> Dict:
        endpoint = "tv" if media_type == "tv" else "movie"
        url = f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}?api_key={TMDB_API_KEY}"
        try:
            resp = self._make_request(url, headers={"Accept": "application/json"})
            data = resp.json()
            title = data.get('name') if media_type == 'tv' else data.get('title')
            release_date = data.get('first_air_date') if media_type == 'tv' else data.get('release_date')
            year = release_date[:4] if release_date else None
            if not title:
                raise Exception("Could not extract title from TMDB response")
            self.log(f"TMDB Info: '{title}' ({year})")
            return {"title": title, "year": year}
        except Exception as e:
            self.log(f"TMDB fetch error: {e}", "ERROR")
            raise

    def _encrypt_tmdb_id(self, tmdb_id: str) -> str:
        self.log(f"Encrypting TMDB ID: {tmdb_id}")
        url = f"{ENC_DEC_API}/enc-vidlink?text={tmdb_id}"
        try:
            resp = self._make_request(url)
            data = resp.json()
            if data and data.get("result"):
                self.log("Successfully encrypted TMDB ID")
                return data["result"]
            else:
                raise Exception("Invalid encryption response format")
        except Exception as e:
            self.log(f"Encryption failed: {e}", "ERROR")
            raise

    def _resolve_url(self, url: str, base_url: str) -> str:
        if url.startswith("http"):
            return url
        try:
            return urllib.parse.urljoin(base_url, url)
        except:
            return url

    def _get_quality_from_resolution(self, resolution: str) -> str:
        if not resolution:
            return "Auto"
        if "x" in resolution:
            parts = resolution.split("x")
            try:
                height = int(parts[1])
                if height >= 2160:
                    return "4K"
                if height >= 1440:
                    return "1440p"
                if height >= 1080:
                    return "1080p"
                if height >= 720:
                    return "720p"
                if height >= 480:
                    return "480p"
                if height >= 360:
                    return "360p"
                return "240p"
            except:
                pass
        return "Auto"

    def _parse_m3u8(self, content: str, base_url: str) -> List[Dict]:
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        streams = []
        current_stream = None
        for line in lines:
            if line.startswith("#EXT-X-STREAM-INF:"):
                current_stream = {"bandwidth": None, "resolution": None, "url": None}
                bw_match = re.search(r"BANDWIDTH=(\d+)", line)
                if bw_match:
                    current_stream["bandwidth"] = int(bw_match.group(1))
                res_match = re.search(r"RESOLUTION=(\d+x\d+)", line)
                if res_match:
                    current_stream["resolution"] = res_match.group(1)
            elif current_stream and not line.startswith("#"):
                current_stream["url"] = self._resolve_url(line, base_url)
                streams.append(current_stream)
                current_stream = None
        return streams

    def _fetch_and_parse_m3u8(self, playlist_url: str, media_info: Dict) -> List[Dict]:
        self.log(f"Fetching M3U8 playlist: {playlist_url[:80]}...")
        try:
            resp = self._make_request(playlist_url, headers=VIDLINK_HEADERS)
            m3u8_content = resp.text
            self.log("Parsing M3U8 content", "DEBUG")
            parsed_streams = self._parse_m3u8(m3u8_content, playlist_url)

            if not parsed_streams:
                self.log("No quality variants found, returning master playlist")
                return [{
                    "name": "Vidlink - Auto",
                    "title": media_info.get("title", "Unknown"),
                    "url": playlist_url,
                    "quality": "Auto",
                    "size": "Unknown",
                    "headers": VIDLINK_HEADERS,
                    "provider": "vidlink",
                }]

            self.log(f"Found {len(parsed_streams)} quality variants")
            streams = []
            for s in parsed_streams:
                quality = self._get_quality_from_resolution(s.get("resolution"))
                streams.append({
                    "name": f"Vidlink - {quality}",
                    "title": media_info.get("title", "Unknown"),
                    "url": s["url"],
                    "quality": quality,
                    "size": "Unknown",
                    "headers": VIDLINK_HEADERS,
                    "provider": "vidlink",
                })
            return streams
        except Exception as e:
            self.log(f"Error fetching/parsing M3U8: {e}", "ERROR")
            return [{
                "name": "Vidlink - Auto",
                "title": media_info.get("title", "Unknown"),
                "url": playlist_url,
                "quality": "Auto",
                "size": "Unknown",
                "headers": VIDLINK_HEADERS,
                "provider": "vidlink",
            }]

    def _extract_quality(self, stream_data: Any) -> str:
        if not stream_data:
            return "Unknown"
        if isinstance(stream_data, dict):
            for field in ["quality", "resolution", "label", "name"]:
                if field in stream_data and stream_data[field]:
                    val = str(stream_data[field]).lower()
                    if "2160" in val or "4k" in val:
                        return "4K"
                    if "1440" in val or "2k" in val:
                        return "1440p"
                    if "1080" in val or "fhd" in val:
                        return "1080p"
                    if "720" in val or "hd" in val:
                        return "720p"
                    if "480" in val or "sd" in val:
                        return "480p"
                    if "360" in val:
                        return "360p"
                    if "240" in val:
                        return "240p"
                    match = re.search(r"(\d{3,4})[pP]?", val)
                    if match:
                        res = int(match.group(1))
                        if res >= 2160:
                            return "4K"
                        if res >= 1440:
                            return "1440p"
                        if res >= 1080:
                            return "1080p"
                        if res >= 720:
                            return "720p"
                        if res >= 480:
                            return "480p"
                        if res >= 360:
                            return "360p"
                        return "240p"
        return "Unknown"

    def _create_stream_title(self, media_info: Dict) -> str:
        if media_info.get("media_type") == "tv" and media_info.get("season") is not None and media_info.get("episode") is not None:
            return f"{media_info['title']} S{media_info['season']:02d}E{media_info['episode']:02d}"
        if media_info.get("year"):
            return f"{media_info['title']} ({media_info['year']})"
        return media_info["title"]

    def _process_vidlink_response(self, data: Dict, media_info: Dict) -> List[Dict]:
        streams = []
        try:
            self.log("Processing response data", "DEBUG")
            stream_title = self._create_stream_title(media_info)

            # Handle stream.qualities
            if data.get("stream") and data["stream"].get("qualities"):
                self.log("Processing qualities from stream object", "DEBUG")
                for q_key, q_data in data["stream"]["qualities"].items():
                    if q_data.get("url"):
                        quality = self._extract_quality({"quality": q_key})
                        streams.append({
                            "name": f"Vidlink - {quality}",
                            "title": stream_title,
                            "url": q_data["url"],
                            "quality": quality,
                            "size": "Unknown",
                            "headers": VIDLINK_HEADERS,
                            "provider": "vidlink",
                        })
                if data["stream"].get("playlist"):
                    streams.append({
                        "_is_playlist": True,
                        "url": data["stream"]["playlist"],
                        "media_info": {**media_info, "title": stream_title},
                    })

            # Handle only playlist
            elif data.get("stream") and data["stream"].get("playlist") and not data["stream"].get("qualities"):
                self.log("Processing playlist-only response", "DEBUG")
                streams.append({
                    "_is_playlist": True,
                    "url": data["stream"]["playlist"],
                    "media_info": {**media_info, "title": stream_title},
                })

            # Handle direct url
            elif data.get("url"):
                quality = self._extract_quality(data)
                streams.append({
                    "name": f"Vidlink - {quality}",
                    "title": stream_title,
                    "url": data["url"],
                    "quality": quality,
                    "size": "Unknown",
                    "headers": VIDLINK_HEADERS,
                    "provider": "vidlink",
                })

            # Handle streams array
            elif data.get("streams") and isinstance(data["streams"], list):
                for idx, stream in enumerate(data["streams"]):
                    if stream.get("url"):
                        quality = self._extract_quality(stream)
                        streams.append({
                            "name": f"Vidlink Stream {idx+1} - {quality}",
                            "title": stream_title,
                            "url": stream["url"],
                            "quality": quality,
                            "size": stream.get("size", "Unknown"),
                            "headers": VIDLINK_HEADERS,
                            "provider": "vidlink",
                        })

            # Handle links array
            elif data.get("links") and isinstance(data["links"], list):
                for idx, link in enumerate(data["links"]):
                    if link.get("url"):
                        quality = self._extract_quality(link)
                        streams.append({
                            "name": f"Vidlink Link {idx+1} - {quality}",
                            "title": stream_title,
                            "url": link["url"],
                            "quality": quality,
                            "size": link.get("size", "Unknown"),
                            "headers": VIDLINK_HEADERS,
                            "provider": "vidlink",
                        })

            # Fallback: recursive search in object
            else:
                self.log("No structured streams found, attempting recursive search", "DEBUG")
                def find_urls(obj, path=""):
                    if isinstance(obj, dict):
                        for key, value in obj.items():
                            new_path = f"{path}.{key}" if path else key
                            if isinstance(value, str) and (value.startswith("http") or ".m3u8" in value):
                                # Skip subtitle/caption URLs
                                if any(x in value.lower() for x in [".srt", ".vtt", "subtitle", "caption"]) or any(x in key.lower() for x in ["subtitle", "caption"]):
                                    continue
                                quality = self._extract_quality({key: value})
                                streams.append({
                                    "name": f"Vidlink {key} - {quality}",
                                    "title": stream_title,
                                    "url": value,
                                    "quality": quality,
                                    "size": "Unknown",
                                    "headers": VIDLINK_HEADERS,
                                    "provider": "vidlink",
                                })
                            elif isinstance(value, (dict, list)) and not any(x in key.lower() for x in ["subtitle", "caption"]):
                                find_urls(value, new_path)
                    elif isinstance(obj, list):
                        for i, item in enumerate(obj):
                            find_urls(item, f"{path}[{i}]")
                find_urls(data)

            self.log(f"Extracted {len(streams)} streams from response", "DEBUG")
        except Exception as e:
            self.log(f"Error processing response: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "DEBUG")
        return streams

    def resolve(self, url_or_id: str, media_type: str = "movie", season: int = None, episode: int = None) -> str:
        self.log("=" * 80)
        self.log(f"Vidlink Resolver Started - {media_type} ID: {url_or_id}")

        if url_or_id.startswith("http"):
            match = re.search(r"/(?:movie|tv)/(\d+)", url_or_id)
            if match:
                tmdb_id = match.group(1)
                if "/tv/" in url_or_id:
                    media_type = "tv"
                    se_match = re.search(r"/tv/\d+/(\d+)/(\d+)", url_or_id)
                    if se_match:
                        season = int(se_match.group(1))
                        episode = int(se_match.group(2))
            else:
                return json.dumps({
                    "status": "error",
                    "message": "Could not extract TMDB ID from URL"
                })
        else:
            tmdb_id = url_or_id

        self.log(f"TMDB ID: {tmdb_id}")
        self.log(f"Content Type: {'TV Show' if media_type == 'tv' else 'Movie'}")
        if media_type == "tv":
            self.log(f"Season: {season}, Episode: {episode}")

        try:
            tmdb_info = self._get_tmdb_info(tmdb_id, media_type)
            title = tmdb_info["title"]
            year = tmdb_info["year"]

            encrypted_id = self._encrypt_tmdb_id(tmdb_id)

            if media_type == "tv" and season is not None and episode is not None:
                vidlink_url = f"{VIDLINK_API}/tv/{encrypted_id}/{season}/{episode}"
            else:
                vidlink_url = f"{VIDLINK_API}/movie/{encrypted_id}"

            self.log(f"Requesting: {vidlink_url}")
            resp = self._make_request(vidlink_url, headers=VIDLINK_HEADERS)
            data = resp.json()
            self.log("Received response from Vidlink API", "DEBUG")

            media_info = {
                "title": title,
                "year": year,
                "media_type": media_type,
                "season": season,
                "episode": episode
            }

            streams = self._process_vidlink_response(data, media_info)

            if not streams:
                raise Exception("No streams found in response")

            playlist_streams = [s for s in streams if s.get("_is_playlist")]
            direct_streams = [s for s in streams if not s.get("_is_playlist")]

            if playlist_streams:
                self.log(f"Processing {len(playlist_streams)} M3U8 playlists")
                all_streams = direct_streams.copy()
                for ps in playlist_streams:
                    parsed = self._fetch_and_parse_m3u8(ps["url"], ps["media_info"])
                    all_streams.extend(parsed)
                all_streams.sort(key=lambda x: QUALITY_ORDER.get(x.get("quality", "Unknown"), -3), reverse=True)
                final_streams = all_streams
            else:
                direct_streams.sort(key=lambda x: QUALITY_ORDER.get(x.get("quality", "Unknown"), -3), reverse=True)
                final_streams = direct_streams

            if not final_streams:
                raise Exception("No playable streams after processing")

            playable_urls = []
            for s in final_streams:
                url = s["url"]
                if ".m3u8" in url.lower():
                    stream_type = "hls"
                elif ".mpd" in url.lower():
                    stream_type = "dash"
                elif ".mp4" in url.lower() or ".mkv" in url.lower():
                    stream_type = "mp4"
                else:
                    stream_type = "direct"

                headers = s.get("headers", VIDLINK_HEADERS.copy())
                playable_urls.append({
                    "url": url,
                    "quality": s.get("quality", "Unknown"),
                    "type": stream_type,
                    "headers": headers,
                    "server": "Vidlink",
                    "size": s.get("size", "Unknown"),
                    # Subtitles omitted
                })

            response = {
                "status": "success",
                "tmdb_id": tmdb_id,
                "playable_urls": playable_urls
            }

            self.log("=" * 80)
            self.log("RESOLUTION COMPLETE")
            self.log(f"Found {len(playable_urls)} playable sources")
            return json.dumps(response, indent=2)

        except Exception as e:
            self.log(f"Error: {e}", "ERROR")
            import traceback
            self.log(traceback.format_exc(), "ERROR")
            return json.dumps({
                "status": "error",
                "message": str(e)
            })


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Vidlink Resolver (subtitles omitted)")
    parser.add_argument("url_or_id", help="TMDB ID or URL")
    parser.add_argument("--type", choices=["movie", "tv"], default="movie", help="Media type (default: movie)")
    parser.add_argument("--season", type=int, help="Season number (for TV)")
    parser.add_argument("--episode", type=int, help="Episode number (for TV)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--pretty", action="store_true", help="Pretty print JSON output")

    args = parser.parse_args()

    resolver = VidlinkResolver(debug=args.debug)
    result_json = resolver.resolve(
        args.url_or_id,
        media_type=args.type,
        season=args.season,
        episode=args.episode
    )

    if args.pretty:
        try:
            data = json.loads(result_json)
            print(json.dumps(data, indent=2))
        except:
            print(result_json)
    else:
        print(result_json)


if __name__ == "__main__":
    main()