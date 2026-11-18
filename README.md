# EmbedScraper

A collection of standalone Python resolvers that scrape streaming URLs from various embedded video providers. Designed for use with Android applications via a Python bridge, replacing the need for a Kodi UI dependency.

---

## Features

- **TMDB + Anime resolvers** — video stream extraction from 16 sources
- **Live TV playlists** — M3U parsing from 9 providers (Xumo, Tubi, PlutoTV, etc.)
- **Torrent providers** — magnet/direct streams from TorrentDL, Torrentio, Comet, EasyNews, Supreme
- **Consistent output** — every resolver returns a unified JSON structure
- **Aggregate modes** — run groups at once (`get_all_tmdb.py`, `get_all_livetv.py`, `get_all_torrents.py`)
- **No Kodi dependency** — fully standalone Python 3 scripts

---

## Requirements

- Python 3.8+
- [pip](https://pip.pypa.io/)

### Dependencies

Install with:

```bash
pip install -r requirements.txt
```

| Package | Used by |
|---|---|
| `requests` | HTTP requests |
| `beautifulsoup4` | HTML parsing |
| `websocket-client` | WebSocket streams (StreamFlix) |
| `pycryptodome` | AES/DES3 decryption |

---

## Usage

### Individual resolver

Each resolver accepts a **TMDB ID** or **TMDB URL**, plus optional media type, season, and episode.

```bash
# TMDB resolver (movie)
python providers/tmdb/castle.py 550

# TMDB resolver (TV show)
python providers/tmdb/vidlink.py 1396 --type tv --season 1 --episode 1

# Anime resolver
python providers/anime/anizone.py 550

# Pretty-print
python providers/tmdb/fsharetv.py 550 --pretty
```

### Aggregate TMDB resolvers

Run all TMDB + anime resolvers at once:

```bash
python get_all_tmdb.py 550
python get_all_tmdb.py 1399 --type tv --season 1 --episode 1 --pretty
```

### Aggregate live TV

Fetch all live TV playlists in one command:

```bash
python get_all_livetv.py
```

### Aggregate torrent providers

Run all torrent/Usenet providers:

```bash
python get_all_torrents.py 550
python get_all_torrents.py 1399 --type tv --season 1 --episode 1
python get_all_torrents.py 550 --realdebrid RD_KEY --alldebrid AD_KEY --premiumize PM_KEY --torbox TB_KEY
python get_all_torrents.py 550 --username EN_USER --password EN_PASS
```

### Individual scripts

```bash
# TMDB resolver
python providers/tmdb/castle.py 550

# Anime resolver
python providers/anime/hianime.py 276880 --type tv --season 1 --episode 1

# Live TV playlist
python providers/livetv/xumo.py

# Torrent provider
python providers/torrent/torrentio.py 550
python providers/torrent/comet.py 550 --realdebrid RD_KEY --alldebrid AD_KEY --premiumize PM_KEY --torbox TB_KEY
python providers/torrent/easynews.py 550 --username USER --password PASS
python providers/torrent/supreme.py 550 --alldebrid AD_KEY --premiumize PM_KEY --torbox TB_KEY
```

> **Note:** The **ShowBox** resolver requires a `--ui-cookie`:
> ```bash
> python get_all_tmdb.py 550 --ui-cookie "your_token"
> ```
>
> To get the cookie:
> 1. Go to [febbox.com](https://febbox.com) and log in with Google (use a fresh account)
> 2. Open DevTools (`F12`) → **Application** tab → **Cookies**
> 3. Copy the **`ui`** cookie's value
> 4. Close the tab — do **not** log out

---

## Available Resolvers

### Live TV (`livetv/`)

| Module | Source | Type |
|---|---|---|
| `xumo` | Xumo Playlist | M3U → JSON |
| `tubi` | Tubi Playlist | M3U → JSON |
| `yupptv` | YuppTV Playlist | M3U → JSON |
| `us_local` | US Local Channels | M3U → JSON |
| `samsung` | Samsung TV Plus | M3U → JSON |
| `roku` | Roku Channel | M3U → JSON |
| `lgtv` | LG TV Channels | M3U → JSON |
| `iptv_org` | IPTV-org Global | M3U → JSON |
| `plutotv` | PlutoTV API | API → JSON |

### Torrent (`torrent/`)

| Module | Source | Requires |
|---|---|---|
| `torrentio` | Torrentio Stremio | — |
| `comet` | Comet (elfhosted) | Debrid API key(s) |
| `easynews` | EasyNews Usenet | Username + password |
| `supreme` | Supreme (sup-nyp1.onrender.com) | Debrid API key(s) |

### Anime (`anime/`)

| Module | Class | Site | Movies | TV |
|---|---|---|---|---|

| Module | Class | Site | Movies | TV |
|---|---|---|---|---|
| `anizone` | `AniZoneResolver` | AniZone (anizone.to) | ✓ | ✓ |
| `hianime` | `HiAnimeResolver` | HiAnime (MegaPlay/Vidwish/MegaCloud) | ✓ | ✓ |

### TMDB (`tmdb/`)

| Module | Class | Site | Movies | TV |
|---|---|---|---|---|
| `castle` | `CastleResolver` | Castle (hlowb.com) | ✓ | ✓ |
| `fsharetv` | `FshareTvResolver` | FshareTV (fsharetv.cc) | ✓ | ✗ |
| `hdhub` | `HdHubResolver` | HdHub | ✓ | ✓ |
| `movieblast` | `MovieBlastResolver` | MovieBlast | ✓ | ✓ |
| `moviesdrive` | `MoviesDriveResolver` | MoviesDrive | ✓ | ✓ |
| `netmirror` | `NetMirrorResolver` | NetMirror (NewTV) | ✓ | ✓ |
| `showbox` | `ShowBoxResolver` | ShowBox / FebBox | ✓ | ✓ |
| `streamflix` | `StreamFlixResolver` | StreamFlix | ✓ | ✓ |
| `vidapi` | `VidApiResolver` | VidApi (vaplayer.ru) | ✓ | ✓ |
| `vidlink` | `VidlinkResolver` | Vidlink (vidlink.pro) | ✓ | ✓ |
| `vidnest` | `VidNestResolver` | VidNest (vidnest.fun) | ✓ | ✓ |
| `vidrock` | `VidrockResolver` | Vidrock (vidrock.net) | ✓ | ✓ |
| `vidzee` | `VidzeeResolver` | Vidzee (player.vidzee.wtf) | ✓ | ✓ |
| `vixsrc` | `VixSrcResolver` | VixSrc (vixsrc.to) | ✓ | ✓ |
| `111477` | `S111477Resolver` | 111477 (st.111477.xyz) | ✓ | ✓ |
| `vidbolt` | `VidboltResolver` | VidBolt (vidbolt.xyz) | ✓ | ✓ |
| `yastream` | `YastreamResolver` | YaStream (Stremio addon) | ✓ | ✓ |
| `watchout` | `WatchoutResolver` | WatchOut (GitHub feed) | ✓ | ✓ |
| `vidspark` | `VidsparkResolver` | VidSpark (vidspark.to) | ✓ | ✓ |
| `braflix` | `BraflixResolver` | BraFlix (braflix.dev, DASH) | ✓ | ✓ |
| `moviebox` | `MovieboxResolver` | MovieBox (net79.cc) | ✓ | ✓ |
| `vidlux` | `VidluxResolver` | VidLux (vidlux.xyz) | ✓ | ✓ |

The last eight are ported from [VyseTV](https://gitlab.com/ayman707-ux/vysetv)'s
`film_sources/scrapers.dart` (GPL-3.0). They share `providers/common.py` for
HTTP, TMDB metadata, HLS variant parsing and quality normalisation.

---

## Output Format

### Success

```json
{
  "status": "success",
  "tmdb_id": "550",
  "playable_urls": [
    {
      "url": "https://cdn.example.com/stream.m3u8",
      "quality": "1080p",
      "type": "hls",
      "headers": {
        "Referer": "https://example.com",
        "User-Agent": "Mozilla/5.0 ..."
      },
      "server": "SourceName"
    }
  ]
}
```

### Error

```json
{
  "status": "error",
  "message": "No playable streams found"
}
```

### Aggregate output (`get_all_tmdb.py`)

```json
{
  "status": "success",
  "input": {
    "url_or_id": "550",
    "media_type": "movie",
    "season": null,
    "episode": null
  },
  "resolvers": {
    "castle": { "status": "success", "playable_urls": [...] },
    "fsharetv": { "status": "error", "message": "..." },
    "hdhub": { "status": "skipped", "message": "..." }
  },
  "total_playable_urls": 5
}
```

---

## Common Arguments

| Argument | Description |
|---|---|
| `url_or_id` | TMDB ID (e.g. `550`) or TMDB URL (e.g. `https://www.themoviedb.org/movie/550`) |
| `--type` | `movie` or `tv` (default: `movie`) |
| `--season` | Season number (TV only) |
| `--episode` | Episode number (TV only) |
| `--debug` | Enable verbose debug output |
| `--pretty` | Pretty-print the JSON result |
| `--ui-cookie` | FebBox UI token (ShowBox only) |
| `--realdebrid` | RealDebrid API key (Comet) |
| `--alldebrid` | AllDebrid API key (Comet, Supreme) |
| `--premiumize` | Premiumize API key (Comet, Supreme) |
| `--torbox` | TorBox API key (Comet, Supreme) |
| `--username` | EasyNews username |
| `--password` | EasyNews password |
