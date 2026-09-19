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
  reports/YYYY.md      # year-end Markdown (when generated)
  reports/YYYY.json
scripts/
  snapshot.py
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

## Year-end popularity ranking

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
| `workflow_dispatch` | Manual; optional inputs to run year-end report |

On each run the workflow:

1. Runs `scripts/snapshot.py`
2. Commits and pushes changes under `data/` with `GITHUB_TOKEN` (`contents: write`)
3. Optionally runs `year_end_report.py` for the previous calendar year when:
   - it is **1 January** (HKT), or
   - `workflow_dispatch` input `run_year_end` is true

## Secrets

| Name | Required? | Purpose |
| --- | --- | --- |
| `APPLE_MUSIC_TOKEN` | No | Optional Apple Music Media API JWT if scrape breaks |
| `GITHUB_TOKEN` | Provided by Actions | Commit/push snapshot updates |

No Apple token is required for the default scrape path.

## License

Data is a personal archive of publicly listed chart rankings. Apple Music and related marks belong to Apple Inc. This repo is not affiliated with Apple.
