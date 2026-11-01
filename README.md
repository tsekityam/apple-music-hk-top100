# Apple Music Top 100: Hong Kong — daily snapshots

Daily archival of [Apple Music Top 100: Hong Kong](https://music.apple.com/hk/playlist/top-100-hong-kong/pl.7f35cffa10b54b91aab128ccc547f6ef) so year-end popularity can be computed from ranking history.

- **Playlist id:** `pl.7f35cffa10b54b91aab128ccc547f6ef`
- **Storefront:** `hk`
- **Timezone for snapshot dates:** `Asia/Hong_Kong` (UTC+8, no DST)

## Why

At year-end we want a clear answer to: *which song was most popular in Hong Kong according to this chart?* Popularity is inferred from how songs performed in the daily Top 100 over time (days at #1, time in Top 10, average rank, peak, longevity), not from a single end-of-year list.

## Data layout

```
data/
  latest.json          # most recent snapshot
  latest.md            # human-readable chart
  history/YYYY-MM-DD.json
  reports/YYYY-Www.scores.md  # weekly score reports (ISO week)
  reports/YYYY-MM.scores.md   # monthly score reports
  reports/YYYY.scores.md      # yearly score reports
  reports/YYYY.md             # ordinal year-end (when generated)
docs/
  SCORING.md
scripts/
  snapshot.py
  score_report.py
  year_end_report.py
.github/workflows/daily-snapshot.yml
```

Each track record includes: `rank`, `title`, `artists`, `album` (when available), `apple_music_id`, `url`, `snapshot_date` (`YYYY-MM-DD` in HKT), `snapshot_at` (ISO-8601 with `+08:00`).

## Fetch method

`scripts/snapshot.py` **prefers scraping the public playlist page** (no Apple developer token). It parses Apple’s embedded `serialized-server-data` for ranked tracks.

Optional: set env / GitHub Actions secret `APPLE_MUSIC_TOKEN` (Apple Music API developer JWT). With a token present, scrape is still tried first unless you pass `--prefer-api`. The API path is a reliability fallback.

```bash
python3 scripts/snapshot.py          # write data/latest.* and data/history/…
python3 scripts/snapshot.py --dry-run
APPLE_MUSIC_TOKEN=… python3 scripts/snapshot.py --prefer-api
```

## Scoring

Primary numeric popularity uses daily points **`p(r) = ln(101 / r)`** (natural log; `r` is the daily chart rank, 1–100), summed over every snapshot day in the period for songs. Each credited artist gets the full daily points of a track (no 1/n split). Details and examples: [`docs/SCORING.md`](docs/SCORING.md).

```bash
python3 scripts/score_report.py --week 2026-W43
python3 scripts/score_report.py --month 2026-10
python3 scripts/score_report.py --year 2026
python3 scripts/score_report.py --from 2026-09-20 --to 2026-10-31
```

Writes `data/reports/<period>.scores.md` and `.json` (top songs and top artists).

Naming: `YYYY-Www.scores.*` (ISO week Mon–Sun), `YYYY-MM.scores.*` (calendar month), `YYYY.scores.*` (calendar year). Week/month/year modes require the period’s **end-date** snapshot to exist (Sunday / last day of month / Dec 31) unless `--allow-incomplete` is passed.

## Year-end popularity ranking (ordinal alternate)

Lexicographic year-end sort (not the primary score). Kept for comparison with the additive system above.

```bash
python3 scripts/year_end_report.py --year 2026
```

### Formula (primary + tie-breakers)

Songs are ordered by:

1. **Days at #1** — descending (primary recommendation)
2. **Days in Top 10** — descending
3. **Average rank** while on the chart — ascending (lower is better)
4. **Best peak rank** — ascending
5. **Days on chart** (appearances in Top 100) — descending
6. **Title** — ascending (stable final tie-break)

Supporting fields in the JSON report: `weeks_on_chart`, `first_seen`, `last_seen`, `rank_sum`, etc. Identity prefers `apple_music_id`; otherwise title + artists.

## Schedule (GitHub Actions)

Workflow: `.github/workflows/daily-snapshot.yml`

| Trigger | When |
| --- | --- |
| `cron` | `0 0 * * *` — **00:00 UTC = 08:00 HKT** every day |
| `workflow_dispatch` | Manual; optional score week/month/year and ordinal year-end |

On each run the workflow:

1. Runs `scripts/snapshot.py` (snapshot date **D** in HKT)
2. **Score reports** (`p(r) = ln(101 / r)`, via `scripts/score_report.py`) only after that snapshot, when the period end is available:
   - **D is Sunday** → `--week` for that ISO week (`YYYY-Www.scores.*`)
   - **D is last calendar day of the month** → `--month YYYY-MM`
   - **D is 31 Dec** → `--year YYYY` (`.scores.*`, not the ordinal report)
   - Guard: `score_report.py` refuses to write unless `data/history/<end-date>.json` exists
3. Optionally runs ordinal `year_end_report.py` for the previous calendar year when it is **1 January** (HKT) or `run_year_end` is true
4. Commits and pushes under `data/` with `GITHUB_TOKEN` (`contents: write`)

Manual regen: set `workflow_dispatch` inputs `score_week` / `score_month` / `score_year` (e.g. `2026-W43`, `2026-10`, `2026`).

## Secrets

| Name | Required? | Purpose |
| --- | --- | --- |
| `APPLE_MUSIC_TOKEN` | No | Optional Apple Music Media API JWT if scrape breaks |
| `GITHUB_TOKEN` | Provided by Actions | Commit/push snapshot updates |

No Apple token is required for the default scrape path.

## License

Data is a personal archive of publicly listed chart rankings. Apple Music and related marks belong to Apple Inc. This repo is not affiliated with Apple.
