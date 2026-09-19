#!/usr/bin/env python3
"""Year-end popularity report from daily Top 100 HK snapshots.

Primary ranking metric (documented in README):
  1. Most days at #1 (desc)
  2. Tie-break: days in Top 10 (desc)
  3. Tie-break: average rank when on chart (asc — lower is better)
  4. Tie-break: best (peak) rank (asc)
  5. Tie-break: days on chart (desc)
  6. Tie-break: title (asc) for stability

Also emits supporting metrics: days in Top 100, weeks on chart (unique
ISO weeks with an appearance), sum of rank points, etc.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
HISTORY_DIR = REPO_ROOT / "data" / "history"
REPORTS_DIR = REPO_ROOT / "data" / "reports"


def parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def song_key(track: dict[str, Any]) -> str:
    """Stable identity: prefer Apple Music song id, else title+artists."""
    mid = (track.get("apple_music_id") or "").strip()
    if mid:
        return f"id:{mid}"
    title = (track.get("title") or "").strip().lower()
    artists = track.get("artists_display") or " & ".join(
        track.get("artists") or []
    )
    return f"title:{(title + '|' + artists.strip().lower())}"


def load_history(
    year: int | None = None,
    history_dir: Path = HISTORY_DIR,
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
        data = json.loads(path.read_text(encoding="utf-8"))
        snapshots.append(data)
    return snapshots


def aggregate(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Per song accumulators
    meta: dict[str, dict[str, Any]] = {}
    days_at_1: dict[str, int] = defaultdict(int)
    days_top10: dict[str, int] = defaultdict(int)
    days_top100: dict[str, int] = defaultdict(int)
    rank_sum: dict[str, int] = defaultdict(int)
    peak: dict[str, int] = {}
    weeks: dict[str, set[str]] = defaultdict(set)
    first_seen: dict[str, str] = {}
    last_seen: dict[str, str] = {}
    ranks_list: dict[str, list[int]] = defaultdict(list)

    for snap in snapshots:
        snap_date = snap.get("snapshot_date") or ""
        iso_week = ""
        if snap_date:
            d = parse_date(snap_date)
            iso_week = f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"
        for track in snap.get("tracks") or []:
            key = song_key(track)
            rank = int(track["rank"])
            if key not in meta:
                meta[key] = {
                    "apple_music_id": track.get("apple_music_id") or "",
                    "title": track.get("title") or "",
                    "artists": track.get("artists") or [],
                    "artists_display": track.get("artists_display")
                    or " & ".join(track.get("artists") or []),
                    "url": track.get("url"),
                    "album_examples": [],
                }
            else:
                # Keep most recent title/artists display
                meta[key]["title"] = track.get("title") or meta[key]["title"]
                meta[key]["artists"] = track.get("artists") or meta[key]["artists"]
                meta[key]["artists_display"] = track.get(
                    "artists_display"
                ) or meta[key]["artists_display"]
                if track.get("url"):
                    meta[key]["url"] = track["url"]
            album = track.get("album")
            if album and album not in meta[key]["album_examples"]:
                if len(meta[key]["album_examples"]) < 3:
                    meta[key]["album_examples"].append(album)

            days_top100[key] += 1
            if rank <= 10:
                days_top10[key] += 1
            if rank == 1:
                days_at_1[key] += 1
            rank_sum[key] += rank
            ranks_list[key].append(rank)
            if key not in peak or rank < peak[key]:
                peak[key] = rank
            if iso_week:
                weeks[key].add(iso_week)
            if key not in first_seen or snap_date < first_seen[key]:
                first_seen[key] = snap_date
            if key not in last_seen or snap_date > last_seen[key]:
                last_seen[key] = snap_date

    rows: list[dict[str, Any]] = []
    for key, info in meta.items():
        days = days_top100[key]
        avg = rank_sum[key] / days if days else 0.0
        row = {
            **info,
            "days_at_number_1": days_at_1[key],
            "days_in_top_10": days_top10[key],
            "days_in_top_100": days,
            "days_on_chart": days,
            "weeks_on_chart": len(weeks[key]),
            "average_rank": round(avg, 4),
            "best_peak_rank": peak[key],
            "first_seen": first_seen.get(key),
            "last_seen": last_seen.get(key),
            "rank_sum": rank_sum[key],
        }
        rows.append(row)

    def sort_key(r: dict[str, Any]) -> tuple:
        return (
            -int(r["days_at_number_1"]),
            -int(r["days_in_top_10"]),
            float(r["average_rank"]),
            int(r["best_peak_rank"]),
            -int(r["days_on_chart"]),
            (r.get("title") or "").lower(),
        )

    rows.sort(key=sort_key)
    for i, r in enumerate(rows, start=1):
        r["year_rank"] = i
    return rows


def render_markdown(
    year: int,
    rows: list[dict[str, Any]],
    snapshot_count: int,
    date_range: tuple[str | None, str | None],
) -> str:
    start, end = date_range
    lines = [
        f"# Apple Music Top 100 Hong Kong — {year} year-end report",
        "",
        "## Ranking formula",
        "",
        "Songs are ranked by this composite (primary → tie-breakers):",
        "",
        "1. **Days at #1** (more is better)",
        "2. **Days in Top 10** (more is better)",
        "3. **Average rank** while on the chart (lower is better)",
        "4. **Best peak rank** (lower is better)",
        "5. **Days on chart** (more is better)",
        "6. Title (A→Z) for stability",
        "",
        f"- Snapshots used: **{snapshot_count}**",
        f"- Date range: `{start}` → `{end}`",
        f"- Songs appearing: **{len(rows)}**",
        "",
        "## Top songs",
        "",
        "| Year rank | Title | Artists | Days #1 | Days Top10 | Days chart | Avg rank | Peak | Weeks |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    def esc(s: str) -> str:
        return (s or "").replace("|", "\\|")

    for r in rows[:100]:
        lines.append(
            "| {yr} | {title} | {artists} | {d1} | {t10} | {dc} | {avg} | {peak} | {w} |".format(
                yr=r["year_rank"],
                title=esc(r.get("title") or ""),
                artists=esc(r.get("artists_display") or ""),
                d1=r["days_at_number_1"],
                t10=r["days_in_top_10"],
                dc=r["days_on_chart"],
                avg=f"{r['average_rank']:.2f}",
                peak=r["best_peak_rank"],
                w=r["weeks_on_chart"],
            )
        )
    if len(rows) > 100:
        lines.append("")
        lines.append(f"_… {len(rows) - 100} more songs in the JSON report._")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Calendar year to summarize (default: year of latest snapshot, or prior year on Jan 1)",
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

    all_snaps = load_history(year=None, history_dir=args.history_dir)
    if not all_snaps:
        print("ERROR: no history snapshots found", file=sys.stderr)
        return 1

    dates = sorted(s["snapshot_date"] for s in all_snaps if s.get("snapshot_date"))
    year = args.year
    if year is None:
        latest = parse_date(dates[-1])
        # On Jan 1, default to previous year (year just completed)
        if latest.month == 1 and latest.day == 1:
            year = latest.year - 1
        else:
            year = latest.year

    snaps = [s for s in all_snaps if (s.get("snapshot_date") or "").startswith(f"{year}-")]
    if not snaps:
        print(f"ERROR: no snapshots for year {year}", file=sys.stderr)
        return 1

    rows = aggregate(snaps)
    snap_dates = sorted(s["snapshot_date"] for s in snaps)
    date_range = (snap_dates[0], snap_dates[-1])
    md = render_markdown(year, rows, len(snaps), date_range)

    report = {
        "year": year,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "snapshot_count": len(snaps),
        "date_range": {"start": date_range[0], "end": date_range[1]},
        "ranking_formula": [
            "days_at_number_1 DESC",
            "days_in_top_10 DESC",
            "average_rank ASC",
            "best_peak_rank ASC",
            "days_on_chart DESC",
            "title ASC",
        ],
        "songs": rows,
    }

    if args.stdout_only:
        print(md)
        return 0

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / f"{year}.json"
    md_path = args.out_dir / f"{year}.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md_path.write_text(md, encoding="utf-8")
    print(md)
    print(f"\nWrote {json_path.relative_to(REPO_ROOT)} and {md_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
