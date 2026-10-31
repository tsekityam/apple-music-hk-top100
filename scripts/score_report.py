#!/usr/bin/env python3
"""Popularity score reports from daily Top 100 HK snapshots.

Daily points use 10 rank groups with decreasing adjacent gaps
(group 1–10 gap 10 … group 91–100 gap 1), anchored at #100 = 1
(#1 = 541). Song period score: sum of daily points. Artist period
score: every credited artist gets the full daily points (no 1/n).
See docs/SCORING.md.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORY_DIR = REPO_ROOT / "data" / "history"
REPORTS_DIR = REPO_ROOT / "data" / "reports"

from year_end_report import parse_date, song_key  # noqa: E402  (same scripts/ dir on path)

WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$", re.IGNORECASE)


def group_step(rank: int) -> int:
    """Adjacent-gap size for the group containing `rank` (1–100)."""
    return 11 - math.ceil(rank / 10)


def daily_points(rank: int) -> int:
    """Points for chart rank R: #100 = 1 implies #1 = 541.

    Moving from r to r+1 subtracts step(r+1) = 11 - ceil((r+1)/10).
    """
    if rank < 1 or rank > 100:
        return 0
    total = 1  # anchor #100
    for k in range(rank + 1, 101):
        total += group_step(k)
    return total


def artist_names(track: dict[str, Any]) -> list[str]:
    artists = track.get("artists")
    if isinstance(artists, list) and artists:
        return [str(a).strip() for a in artists if str(a).strip()]
    display = (track.get("artists_display") or "").strip()
    if not display:
        return []
    parts = re.split(r"\s*&\s*|,\s*", display)
    return [p.strip() for p in parts if p.strip()]


def normalize_artist_key(name: str) -> str:
    return name.strip().casefold()


def parse_week(s: str) -> str:
    m = WEEK_RE.fullmatch(s.strip())
    if not m:
        raise argparse.ArgumentTypeError("week must be YYYY-Www (ISO week), e.g. 2026-W43")
    year, week = int(m.group(1)), int(m.group(2))
    try:
        date.fromisocalendar(year, week, 1)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"invalid ISO week: {s}") from e
    return f"{year}-W{week:02d}"


def week_bounds(week: str) -> tuple[date, date]:
    """Inclusive Monday–Sunday for an ISO week label YYYY-Www."""
    m = WEEK_RE.fullmatch(week)
    assert m
    year, w = int(m.group(1)), int(m.group(2))
    start = date.fromisocalendar(year, w, 1)
    end = date.fromisocalendar(year, w, 7)
    return start, end


def month_bounds(month: str) -> tuple[date, date]:
    y_str, m_str = month.split("-", 1)
    year, mon = int(y_str), int(m_str)
    start = date(year, mon, 1)
    if mon == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, mon + 1, 1) - timedelta(days=1)
    return start, end


def year_bounds(year: int) -> tuple[date, date]:
    return date(year, 1, 1), date(year, 12, 31)


def history_has_date(history_dir: Path, d: date) -> bool:
    return (history_dir / f"{d.isoformat()}.json").is_file()


def load_snapshots(
    *,
    history_dir: Path,
    year: int | None = None,
    month: str | None = None,
    week: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    files = sorted(history_dir.glob("????-??-??.json"))
    snapshots: list[dict[str, Any]] = []
    for path in files:
        try:
            snap_date = parse_date(path.stem)
        except ValueError:
            continue
        if year is not None and snap_date.year != year:
            continue
        if month is not None:
            y_str, m_str = month.split("-", 1)
            if snap_date.year != int(y_str) or snap_date.month != int(m_str):
                continue
        if week is not None:
            iso = snap_date.isocalendar()
            m = WEEK_RE.fullmatch(week)
            assert m
            if iso.year != int(m.group(1)) or iso.week != int(m.group(2)):
                continue
        if date_from is not None and snap_date < date_from:
            continue
        if date_to is not None and snap_date > date_to:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        snapshots.append(data)
    return snapshots


def aggregate_songs(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}
    score: dict[str, int] = defaultdict(int)
    days_at_1: dict[str, int] = defaultdict(int)
    days_top10: dict[str, int] = defaultdict(int)
    days_top100: dict[str, int] = defaultdict(int)
    rank_sum: dict[str, int] = defaultdict(int)
    peak: dict[str, int] = {}
    first_seen: dict[str, str] = {}
    last_seen: dict[str, str] = {}

    for snap in snapshots:
        snap_date = snap.get("snapshot_date") or ""
        for track in snap.get("tracks") or []:
            rank = int(track["rank"])
            if rank < 1 or rank > 100:
                continue
            key = song_key(track)
            pts = daily_points(rank)
            if key not in meta:
                meta[key] = {
                    "apple_music_id": track.get("apple_music_id") or "",
                    "title": track.get("title") or "",
                    "artists": track.get("artists") or [],
                    "artists_display": track.get("artists_display")
                    or " & ".join(track.get("artists") or []),
                    "url": track.get("url"),
                }
            else:
                meta[key]["title"] = track.get("title") or meta[key]["title"]
                meta[key]["artists"] = track.get("artists") or meta[key]["artists"]
                meta[key]["artists_display"] = (
                    track.get("artists_display") or meta[key]["artists_display"]
                )
                if track.get("url"):
                    meta[key]["url"] = track["url"]
                if track.get("apple_music_id"):
                    meta[key]["apple_music_id"] = track["apple_music_id"]

            score[key] += pts
            days_top100[key] += 1
            if rank <= 10:
                days_top10[key] += 1
            if rank == 1:
                days_at_1[key] += 1
            rank_sum[key] += rank
            if key not in peak or rank < peak[key]:
                peak[key] = rank
            if snap_date:
                if key not in first_seen or snap_date < first_seen[key]:
                    first_seen[key] = snap_date
                if key not in last_seen or snap_date > last_seen[key]:
                    last_seen[key] = snap_date

    rows: list[dict[str, Any]] = []
    for key, info in meta.items():
        days = days_top100[key]
        avg = rank_sum[key] / days if days else 0.0
        rows.append(
            {
                **info,
                "score": score[key],
                "days_at_number_1": days_at_1[key],
                "days_in_top_10": days_top10[key],
                "days_in_top_100": days,
                "average_rank": round(avg, 4),
                "best_peak_rank": peak[key],
                "first_seen": first_seen.get(key),
                "last_seen": last_seen.get(key),
            }
        )

    def sort_key(r: dict[str, Any]) -> tuple:
        return (
            -int(r["score"]),
            -int(r["days_at_number_1"]),
            -int(r["days_in_top_10"]),
            float(r["average_rank"]),
            int(r["best_peak_rank"]),
            (r.get("title") or "").lower(),
        )

    rows.sort(key=sort_key)
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows


def aggregate_artists(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    score: dict[str, int] = defaultdict(int)
    songs: dict[str, set[str]] = defaultdict(set)
    display: dict[str, str] = {}
    last_seen: dict[str, str] = {}

    for snap in snapshots:
        snap_date = snap.get("snapshot_date") or ""
        for track in snap.get("tracks") or []:
            rank = int(track["rank"])
            if rank < 1 or rank > 100:
                continue
            pts = daily_points(rank)
            sk = song_key(track)
            for name in artist_names(track):
                key = normalize_artist_key(name)
                if not key:
                    continue
                score[key] += pts
                songs[key].add(sk)
                # Most recent appearance wins display casing.
                if key not in last_seen or snap_date >= last_seen[key]:
                    last_seen[key] = snap_date
                    display[key] = name.strip()

    rows: list[dict[str, Any]] = []
    for key, pts in score.items():
        rows.append(
            {
                "name": display.get(key) or key,
                "score": pts,
                "distinct_songs": len(songs[key]),
            }
        )

    def sort_key(r: dict[str, Any]) -> tuple:
        return (
            -int(r["score"]),
            -int(r["distinct_songs"]),
            (r.get("name") or "").casefold(),
        )

    rows.sort(key=sort_key)
    for i, r in enumerate(rows, start=1):
        r["rank"] = i
    return rows


def period_label(
    *,
    year: int | None,
    month: str | None,
    week: str | None,
    date_from: date | None,
    date_to: date | None,
    snap_dates: list[str],
) -> str:
    if week:
        return week
    if month:
        return month
    if year is not None and date_from is None and date_to is None:
        return str(year)
    start = date_from.isoformat() if date_from else (snap_dates[0] if snap_dates else "")
    end = date_to.isoformat() if date_to else (snap_dates[-1] if snap_dates else "")
    if start and end and start == end:
        return start
    return f"{start}_to_{end}"


def report_stem(label: str) -> str:
    # 2026-W43.scores / 2026-10.scores / 2026.scores / range_to_range.scores
    return f"{label}.scores"


def render_markdown(
    *,
    label: str,
    songs: list[dict[str, Any]],
    artists: list[dict[str, Any]],
    snapshot_count: int,
    date_range: tuple[str | None, str | None],
) -> str:
    start, end = date_range

    def esc(s: str) -> str:
        return (s or "").replace("|", "\\|")

    lines = [
        f"# Apple Music Top 100 Hong Kong — score report ({label})",
        "",
        "## Scoring formula",
        "",
        "Daily points: 10 rank groups (gaps 10…1), anchor `#100 = 1` → `#1 = 541`.",
        "Song score: sum of daily points over the period.",
        "Artist score: each credited artist receives the full daily points of each track (no 1/n split).",
        "Full documentation: [`docs/SCORING.md`](../../docs/SCORING.md).",
        "",
        f"- Snapshots used: **{snapshot_count}**",
        f"- Date range: `{start}` → `{end}`",
        f"- Songs appearing: **{len(songs)}**",
        f"- Artists appearing: **{len(artists)}**",
        "",
        "## Top songs",
        "",
        "| Rank | Score | Title | Artists | Days #1 | Days Top10 | Days chart | Avg rank | Peak |",
        "| ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in songs[:100]:
        lines.append(
            "| {rank} | {score} | {title} | {artists} | {d1} | {t10} | {dc} | {avg} | {peak} |".format(
                rank=r["rank"],
                score=r["score"],
                title=esc(r.get("title") or ""),
                artists=esc(r.get("artists_display") or ""),
                d1=r["days_at_number_1"],
                t10=r["days_in_top_10"],
                dc=r["days_in_top_100"],
                avg=f"{r['average_rank']:.2f}",
                peak=r["best_peak_rank"],
            )
        )
    if len(songs) > 100:
        lines.append("")
        lines.append(f"_… {len(songs) - 100} more songs in the JSON report._")

    lines.extend(
        [
            "",
            "## Top artists",
            "",
            "| Rank | Score | Artist | Distinct songs |",
            "| ---: | ---: | --- | ---: |",
        ]
    )
    for r in artists[:100]:
        lines.append(
            "| {rank} | {score} | {name} | {songs} |".format(
                rank=r["rank"],
                score=r["score"],
                name=esc(r.get("name") or ""),
                songs=r["distinct_songs"],
            )
        )
    if len(artists) > 100:
        lines.append("")
        lines.append(f"_… {len(artists) - 100} more artists in the JSON report._")
    lines.append("")
    return "\n".join(lines)


def parse_month(s: str) -> str:
    datetime.strptime(s, "%Y-%m")
    return s


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=None, help="Calendar year")
    parser.add_argument(
        "--month",
        type=parse_month,
        default=None,
        help="Calendar month as YYYY-MM",
    )
    parser.add_argument(
        "--week",
        type=parse_week,
        default=None,
        help="ISO week as YYYY-Www (Mon–Sun)",
    )
    parser.add_argument(
        "--from",
        dest="date_from",
        type=parse_date,
        default=None,
        help="Inclusive start date YYYY-MM-DD",
    )
    parser.add_argument(
        "--to",
        dest="date_to",
        type=parse_date,
        default=None,
        help="Inclusive end date YYYY-MM-DD",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Allow week/month/year reports even if the period end-date snapshot is missing",
    )
    parser.add_argument(
        "--history-dir",
        type=Path,
        default=HISTORY_DIR,
        help="Directory of YYYY-MM-DD.json snapshots",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPORTS_DIR,
        help="Output directory for report files",
    )
    parser.add_argument(
        "--stdout-only",
        action="store_true",
        help="Print Markdown to stdout and skip writing files",
    )
    args = parser.parse_args(argv)

    if args.date_from and args.date_to and args.date_from > args.date_to:
        print("ERROR: --from must be on or before --to", file=sys.stderr)
        return 1
    if not any(
        [args.year, args.month, args.week, args.date_from, args.date_to]
    ):
        print(
            "ERROR: provide --year and/or --month and/or --week and/or --from/--to",
            file=sys.stderr,
        )
        return 1

    if args.week and (args.month or args.year):
        print("ERROR: --week cannot be combined with --month/--year", file=sys.stderr)
        return 1
    if args.year and args.month:
        y_str, _ = args.month.split("-", 1)
        if int(y_str) != args.year:
            print("ERROR: --year does not match --month", file=sys.stderr)
            return 1

    # Guard: week/month/year require the period's end-date snapshot unless overridden.
    end_required: date | None = None
    if args.week:
        _, end_required = week_bounds(args.week)
    elif args.month:
        _, end_required = month_bounds(args.month)
    elif args.year is not None and not args.month and not args.date_from and not args.date_to:
        _, end_required = year_bounds(args.year)

    if end_required is not None and not args.allow_incomplete:
        if not history_has_date(args.history_dir, end_required):
            print(
                f"ERROR: missing period end snapshot {end_required.isoformat()}.json "
                f"(pass --allow-incomplete to override)",
                file=sys.stderr,
            )
            return 1

    snaps = load_snapshots(
        history_dir=args.history_dir,
        year=None if (args.month or args.week) else args.year,
        month=args.month,
        week=args.week,
        date_from=args.date_from,
        date_to=args.date_to,
    )

    if not snaps:
        print("ERROR: no snapshots matched the selected period", file=sys.stderr)
        return 1

    songs = aggregate_songs(snaps)
    artists = aggregate_artists(snaps)
    snap_dates = sorted(s["snapshot_date"] for s in snaps if s.get("snapshot_date"))
    date_range = (snap_dates[0], snap_dates[-1])
    if args.week:
        label = args.week
    elif args.month:
        label = args.month
    elif args.year is not None and not args.date_from and not args.date_to:
        label = str(args.year)
    else:
        label = period_label(
            year=args.year,
            month=args.month,
            week=args.week,
            date_from=args.date_from,
            date_to=args.date_to,
            snap_dates=snap_dates,
        )

    md = render_markdown(
        label=label,
        songs=songs,
        artists=artists,
        snapshot_count=len(snaps),
        date_range=date_range,
    )

    report = {
        "period": label,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "snapshot_count": len(snaps),
        "date_range": {"start": date_range[0], "end": date_range[1]},
        "scoring": {
            "daily_points": (
                "10 groups of 10 ranks; within-group gap = 11 - group_index; "
                "points(r)-points(r+1)=step(r+1); #100=1 → #1=541"
            ),
            "key_values": {
                "1": 541,
                "2": 531,
                "10": 451,
                "11": 442,
                "20": 361,
                "100": 1,
            },
            "song_score": "sum of daily points",
            "artist_score": "full daily points to each credited artist (no 1/n)",
            "docs": "docs/SCORING.md",
        },
        "song_ranking": [
            "score DESC",
            "days_at_number_1 DESC",
            "days_in_top_10 DESC",
            "average_rank ASC",
            "best_peak_rank ASC",
            "title ASC",
        ],
        "artist_ranking": [
            "score DESC",
            "distinct_songs DESC",
            "name ASC",
        ],
        "songs": songs,
        "artists": artists,
    }

    if args.stdout_only:
        print(md)
        return 0

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = report_stem(label)
    json_path = args.out_dir / f"{stem}.json"
    md_path = args.out_dir / f"{stem}.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md_path.write_text(md, encoding="utf-8")
    print(md)
    print(
        f"\nWrote {json_path.relative_to(REPO_ROOT)} and {md_path.relative_to(REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
