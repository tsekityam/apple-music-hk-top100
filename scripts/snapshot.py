#!/usr/bin/env python3
"""Daily snapshot of Apple Music Top 100: Hong Kong.

Prefers scraping the public playlist page (no developer token).
Optionally uses Apple Music API Catalog when APPLE_MUSIC_TOKEN is set
(or --prefer-api), falling back to the scrape path on failure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

PLAYLIST_ID = "pl.7f35cffa10b54b91aab128ccc547f6ef"
STOREFRONT = "hk"
PLAYLIST_URL = (
    f"https://music.apple.com/{STOREFRONT}/playlist/"
    f"top-100-hong-kong/{PLAYLIST_ID}"
)
HKT = ZoneInfo("Asia/Hong_Kong")
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
HISTORY_DIR = DATA_DIR / "history"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def now_hkt() -> datetime:
    return datetime.now(HKT)


def http_get(url: str, headers: dict[str, str] | None = None) -> bytes:
    req_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/json,*/*",
        "Accept-Language": "en-HK,en;q=0.9,zh-HK;q=0.8",
    }
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def normalize_artists(artist_name: str) -> list[str]:
    if not artist_name:
        return []
    # Apple often joins with " & " or ", "
    parts = re.split(r"\s*&\s*|,\s*", artist_name)
    return [p.strip() for p in parts if p.strip()]


def track_record(
    *,
    rank: int,
    title: str,
    artists: list[str] | str,
    album: str | None,
    apple_music_id: str,
    url: str | None,
    snapshot_date: str,
    snapshot_at: str,
) -> dict[str, Any]:
    if isinstance(artists, str):
        artists_list = normalize_artists(artists)
        artists_display = artists
    else:
        artists_list = artists
        artists_display = " & ".join(artists)
    if not url and apple_music_id:
        url = f"https://music.apple.com/{STOREFRONT}/song/{apple_music_id}"
    return {
        "rank": rank,
        "title": title,
        "artists": artists_list,
        "artists_display": artists_display,
        "album": album,
        "apple_music_id": str(apple_music_id),
        "url": url,
        "snapshot_date": snapshot_date,
        "snapshot_at": snapshot_at,
    }


def extract_songs_from_ssd(ssd: Any) -> list[dict[str, Any]]:
    songs: list[dict[str, Any]] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            ranking = obj.get("rankingText")
            artist = obj.get("artistName")
            title = obj.get("title")
            cd = obj.get("contentDescriptor") or {}
            if (
                ranking is not None
                and artist
                and title
                and isinstance(cd, dict)
                and cd.get("kind") == "song"
            ):
                ids = cd.get("identifiers") or {}
                song_id = str(ids.get("storeAdamID") or "")
                album = None
                tertiary = obj.get("tertiaryLinks") or []
                if tertiary and isinstance(tertiary[0], dict):
                    album = tertiary[0].get("title")
                try:
                    rank = int(str(ranking).strip())
                except ValueError:
                    rank = len(songs) + 1
                songs.append(
                    {
                        "rank": rank,
                        "title": title,
                        "artists": artist,
                        "album": album,
                        "apple_music_id": song_id,
                        "url": cd.get("url"),
                    }
                )
                return
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(ssd)
    songs.sort(key=lambda t: t["rank"])
    return songs


def fetch_via_scrape() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    html = http_get(PLAYLIST_URL).decode("utf-8", errors="replace")
    m = re.search(
        r'<script[^>]*id=["\']serialized-server-data["\'][^>]*>(.*?)</script>',
        html,
        re.S,
    )
    if not m:
        raise RuntimeError(
            "Could not find serialized-server-data on playlist page"
        )
    ssd = json.loads(m.group(1))
    raw_songs = extract_songs_from_ssd(ssd)
    if len(raw_songs) < 50:
        # Fallback: schema.org ld+json (title/url/id only; no artists)
        ld_m = re.search(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html,
            re.S,
        )
        if not ld_m:
            raise RuntimeError(
                f"Scrape found only {len(raw_songs)} songs and no ld+json"
            )
        ld = json.loads(ld_m.group(1))
        tracks = ld.get("track") or []
        raw_songs = []
        for i, t in enumerate(tracks, start=1):
            url = t.get("url") or ""
            mid = ""
            id_m = re.search(r"/(\d+)(?:\?|$)", url)
            if id_m:
                mid = id_m.group(1)
            raw_songs.append(
                {
                    "rank": i,
                    "title": t.get("name") or "",
                    "artists": "",
                    "album": None,
                    "apple_music_id": mid,
                    "url": url,
                }
            )
    meta = {
        "source": "public_page_scrape",
        "playlist_url": PLAYLIST_URL,
        "playlist_id": PLAYLIST_ID,
        "storefront": STOREFRONT,
        "track_count": len(raw_songs),
    }
    return raw_songs, meta


def fetch_via_api(token: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # Paginate relationships/tracks
    base = (
        f"https://api.music.apple.com/v1/catalog/{STOREFRONT}/playlists/"
        f"{PLAYLIST_ID}"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Origin": "https://music.apple.com",
        "Referer": "https://music.apple.com/",
        "User-Agent": USER_AGENT,
    }
    raw_songs: list[dict[str, Any]] = []
    offset = 0
    limit = 100
    while True:
        url = (
            f"{base}/tracks?limit={limit}&offset={offset}"
            if offset
            else f"{base}?include=tracks"
        )
        data = json.loads(http_get(url, headers=headers).decode("utf-8"))
        if offset == 0 and "data" in data and data["data"]:
            # First call returned playlist with included tracks
            included = data.get("included") or []
            track_data = [
                x for x in included if x.get("type") == "songs"
            ]
            # Prefer ordered relationship
            rel = (
                data["data"][0]
                .get("relationships", {})
                .get("tracks", {})
                .get("data", [])
            )
            if rel:
                by_id = {x["id"]: x for x in track_data}
                ordered = []
                for ref in rel:
                    song = by_id.get(ref["id"])
                    if song:
                        ordered.append(song)
                # If included incomplete, fetch tracks endpoint
                if len(ordered) >= len(rel):
                    track_data = ordered
                else:
                    tracks_url = f"{base}/tracks?limit={limit}"
                    track_data = []
                    next_url: str | None = tracks_url
                    while next_url:
                        page = json.loads(
                            http_get(next_url, headers=headers).decode("utf-8")
                        )
                        track_data.extend(page.get("data") or [])
                        next_url = (page.get("next") or None)
                        if next_url and next_url.startswith("/"):
                            next_url = "https://api.music.apple.com" + next_url
                    break
            for i, song in enumerate(track_data, start=1):
                attrs = song.get("attributes") or {}
                raw_songs.append(
                    {
                        "rank": i,
                        "title": attrs.get("name") or "",
                        "artists": attrs.get("artistName") or "",
                        "album": attrs.get("albumName"),
                        "apple_music_id": str(song.get("id") or ""),
                        "url": attrs.get("url"),
                    }
                )
            break
        else:
            page_tracks = data.get("data") or []
            for song in page_tracks:
                attrs = song.get("attributes") or {}
                raw_songs.append(
                    {
                        "rank": len(raw_songs) + 1,
                        "title": attrs.get("name") or "",
                        "artists": attrs.get("artistName") or "",
                        "album": attrs.get("albumName"),
                        "apple_music_id": str(song.get("id") or ""),
                        "url": attrs.get("url"),
                    }
                )
            next_url = data.get("next")
            if not next_url:
                break
            if next_url.startswith("/"):
                next_url = "https://api.music.apple.com" + next_url
            # continue via absolute next
            data = json.loads(http_get(next_url, headers=headers).decode("utf-8"))
            page_tracks = data.get("data") or []
            for song in page_tracks:
                attrs = song.get("attributes") or {}
                raw_songs.append(
                    {
                        "rank": len(raw_songs) + 1,
                        "title": attrs.get("name") or "",
                        "artists": attrs.get("artistName") or "",
                        "album": attrs.get("albumName"),
                        "apple_music_id": str(song.get("id") or ""),
                        "url": attrs.get("url"),
                    }
                )
            while data.get("next"):
                next_url = data["next"]
                if next_url.startswith("/"):
                    next_url = "https://api.music.apple.com" + next_url
                data = json.loads(
                    http_get(next_url, headers=headers).decode("utf-8")
                )
                for song in data.get("data") or []:
                    attrs = song.get("attributes") or {}
                    raw_songs.append(
                        {
                            "rank": len(raw_songs) + 1,
                            "title": attrs.get("name") or "",
                            "artists": attrs.get("artistName") or "",
                            "album": attrs.get("albumName"),
                            "apple_music_id": str(song.get("id") or ""),
                            "url": attrs.get("url"),
                        }
                    )
            break

    if not raw_songs:
        raise RuntimeError("Apple Music API returned no tracks")
    meta = {
        "source": "apple_music_api",
        "playlist_url": PLAYLIST_URL,
        "playlist_id": PLAYLIST_ID,
        "storefront": STOREFRONT,
        "track_count": len(raw_songs),
    }
    return raw_songs, meta


def build_snapshot(
    raw_songs: list[dict[str, Any]],
    meta: dict[str, Any],
    when: datetime | None = None,
) -> dict[str, Any]:
    when = when or now_hkt()
    snapshot_date = when.strftime("%Y-%m-%d")
    snapshot_at = when.isoformat(timespec="seconds")
    tracks = [
        track_record(
            rank=int(s["rank"]),
            title=s["title"],
            artists=s.get("artists") or "",
            album=s.get("album"),
            apple_music_id=s.get("apple_music_id") or "",
            url=s.get("url"),
            snapshot_date=snapshot_date,
            snapshot_at=snapshot_at,
        )
        for s in raw_songs
    ]
    return {
        "playlist_id": PLAYLIST_ID,
        "playlist_name": "Top 100: Hong Kong",
        "playlist_url": PLAYLIST_URL,
        "storefront": STOREFRONT,
        "snapshot_date": snapshot_date,
        "snapshot_at": snapshot_at,
        "timezone": "Asia/Hong_Kong",
        "source": meta.get("source"),
        "track_count": len(tracks),
        "tracks": tracks,
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    lines = [
        f"# Apple Music Top 100: Hong Kong — {snapshot['snapshot_date']}",
        "",
        f"- Snapshot at: `{snapshot['snapshot_at']}` ({snapshot['timezone']})",
        f"- Source: `{snapshot['source']}`",
        f"- Tracks: {snapshot['track_count']}",
        f"- Playlist: {snapshot['playlist_url']}",
        "",
        "| Rank | Title | Artists | Album |",
        "| ---: | --- | --- | --- |",
    ]
    for t in snapshot["tracks"]:
        artists = t.get("artists_display") or " & ".join(t.get("artists") or [])
        album = t.get("album") or ""
        title = t.get("title") or ""
        # escape pipes
        def esc(s: str) -> str:
            return s.replace("|", "\\|")

        lines.append(
            f"| {t['rank']} | {esc(title)} | {esc(artists)} | {esc(album)} |"
        )
    lines.append("")
    return "\n".join(lines)



def update_changelog(snapshot: dict[str, Any]) -> Path:
    changelog = DATA_DIR / "changelog.md"
    date = snapshot["snapshot_date"]
    top = snapshot["tracks"][0] if snapshot["tracks"] else None
    if top:
        entry = (
            f"- **{date}** — #1: {top['title']} — {top.get('artists_display') or ''} "
            f"({snapshot['track_count']} tracks, source={snapshot['source']})"
        )
    else:
        entry = f"- **{date}** — empty snapshot (source={snapshot['source']})"

    if changelog.exists():
        existing = changelog.read_text(encoding="utf-8")
        pattern = re.compile(rf"^- \*\*{re.escape(date)}\*\*.*$", re.M)
        if pattern.search(existing):
            text = pattern.sub(entry, existing, count=1)
        else:
            lines = existing.splitlines()
            insert_at = 0
            if lines and lines[0].startswith("#"):
                insert_at = 1
                while insert_at < len(lines) and not lines[insert_at].startswith("- "):
                    insert_at += 1
            lines.insert(insert_at, entry)
            text = "\n".join(lines) + "\n"
    else:
        text = (
            "# Changelog\n\n"
            "Daily #1 song from Apple Music Top 100: Hong Kong.\n\n"
            f"{entry}\n"
        )
    if not text.endswith("\n"):
        text += "\n"
    changelog.write_text(text, encoding="utf-8")
    return changelog


def write_snapshot(snapshot: dict[str, Any]) -> tuple[Path, Path, Path, Path]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    date = snapshot["snapshot_date"]
    history_path = HISTORY_DIR / f"{date}.json"
    latest_json = DATA_DIR / "latest.json"
    latest_md = DATA_DIR / "latest.md"
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    history_path.write_text(payload, encoding="utf-8")
    latest_json.write_text(payload, encoding="utf-8")
    latest_md.write_text(render_markdown(snapshot), encoding="utf-8")
    changelog_path = update_changelog(snapshot)
    return history_path, latest_json, latest_md, changelog_path


def fetch_raw(prefer_api: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    token = os.environ.get("APPLE_MUSIC_TOKEN", "").strip()
    errors: list[str] = []

    order: list[str]
    if prefer_api and token:
        order = ["api", "scrape"]
    elif token:
        order = ["scrape", "api"]
    else:
        order = ["scrape"]

    for method in order:
        try:
            if method == "scrape":
                return fetch_via_scrape()
            return fetch_via_api(token)
        except Exception as exc:  # noqa: BLE001 — report & try next
            errors.append(f"{method}: {exc}")
    raise RuntimeError("All fetch methods failed: " + "; ".join(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefer-api",
        action="store_true",
        help="Prefer APPLE_MUSIC_TOKEN API over public scrape",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and print summary without writing files",
    )
    args = parser.parse_args(argv)

    raw, meta = fetch_raw(prefer_api=args.prefer_api)
    snapshot = build_snapshot(raw, meta)

    print(
        f"Fetched {snapshot['track_count']} tracks via {snapshot['source']} "
        f"for {snapshot['snapshot_date']}"
    )
    for t in snapshot["tracks"][:3]:
        print(
            f"  #{t['rank']}: {t['title']} — {t['artists_display']} "
            f"[{t['apple_music_id']}]"
        )

    if args.dry_run:
        return 0

    paths = write_snapshot(snapshot)
    print("Wrote:")
    for p in paths:
        print(f"  {p.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
