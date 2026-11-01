# Popularity scoring

Primary numeric popularity system for Apple Music Top 100: Hong Kong daily snapshots.
Period scores (week, month, or year) are sums of **daily song points**. Artist scores reuse the same points with full credit on collaborations.

The only implementation is `daily_points()` in `scripts/score_report.py`. Weekly, monthly, and yearly GitHub Actions call that script; they do not reimplement the formula.

The older lexicographic year-end sort in `scripts/year_end_report.py` remains available as an **ordinal** alternate ranking (see [Relationship to ordinal year-end](#relationship-to-ordinal-year-end)). It does not use these points.

## Daily song points

For a daily chart rank **r** (1 through 100):

```text
p(r) = ln(101 / r)
```

`ln` is the natural logarithm. Only ranks **1–100** award points. A song not on the chart that day contributes **0**.

The curve is steep at the top (`#1` is worth much more than `#2`) and flattens toward the bottom of the chart, so a short run at #1 outranks a long stay in the middle.

### Key values

Reported to 6 decimal places (same rounding as published period scores):

| Rank r | Points p(r) |
| ---: | ---: |
| 1 | **4.615121** |
| 2 | **3.921973** |
| 10 | **2.312535** |
| 11 | **2.217225** |
| 20 | **1.619388** |
| 100 | **0.009950** |

### Example (one day)

- Song A at **#1** → **4.615121** points
- Song B at **#2** → **3.921973** points
- Song C at **#10** → **2.312535** points
- Song D at **#11** → **2.217225** points

## Song period score

Over a selected date range (ISO week, calendar month, calendar year, or custom `--from` / `--to`):

```text
song_score = Σ p(r) for that song on each snapshot day it appears in the Top 100
```

Published scores round that sum to **6 decimal places**. Song identity prefers `apple_music_id`; otherwise title + artists (same rule as `year_end_report.py`).

Supporting metrics kept for ranking and reports:

- `days_at_number_1`, `days_in_top_10`, `days_in_top_100`
- `average_rank`, `best_peak_rank`
- `first_seen`, `last_seen`

### Example (three days)

| Day | Rank | Points |
| --- | ---: | ---: |
| Mon | 1 | 4.615121 |
| Tue | 3 | 3.516508 |
| Wed | 5 | 3.005683 |
| **Period score** | | **11.137311** |

Each daily figure above is `p(r)` rounded for display. The period score is the exact sum, then rounded to 6 decimal places (adding the displayed daily rows can differ by 0.000001).

## Artist period score

For each track appearance on each day:

1. Compute that track’s daily points with `p(r) = ln(101 / r)`.
2. Give **every** artist name in the track’s `artists` list the **full** points for that track that day (**no 1/n split** on collabs).
3. If `artists` is missing or empty, fall back to splitting `artists_display` on `&` / `,` (same spirit as `snapshot.py`).

Aggregate by a **normalized** artist key (strip whitespace; case-insensitive). The **display** name shown in reports is the casing from the **most recent** chart appearance in the period.

```text
artist_score = Σ (full daily points of each credited track appearance)
```

That is the sum of the period scores of every song that credits the artist (full credit on each collab track). Also reported: `distinct_songs` (unique song keys credited to the artist in the period).

### Example (one day, collaboration)

Track **NEON** by **A2O** & **A2O LITE** at **#1** → **4.615121** points.

- **A2O** receives **4.615121**
- **A2O LITE** receives **4.615121**

If the same artist is credited on two different Top 100 songs that day, they receive the sum of both songs’ daily points.

## Ranking output

### Songs

Ordered by:

1. `score` DESC
2. `days_at_number_1` DESC
3. `days_in_top_10` DESC
4. `average_rank` ASC
5. `best_peak_rank` ASC
6. `title` ASC

### Artists

Ordered by:

1. `score` DESC
2. `distinct_songs` DESC
3. `name` ASC

## Relationship to ordinal year-end

| System | Script | What it optimizes |
| --- | --- | --- |
| **Scoring (primary)** | `scripts/score_report.py` | Additive `ln(101 / r)` points from every chart day; comparable across weeks, months, and years; song **and** artist tables |
| **Ordinal year-end (alternate)** | `scripts/year_end_report.py` | Lexicographic sort: days at #1 → days in Top 10 → average rank → peak → days on chart → title |

Scoring answers “who accumulated the most chart value?” Ordinal year-end answers “who dominated the #1 / Top 10 story, with rank quality as tie-breakers?” Keep both; prefer scoring when you need a single numeric leaderboard.

## How to run

```bash
python3 scripts/score_report.py --week 2026-W43
python3 scripts/score_report.py --month 2026-10
python3 scripts/score_report.py --year 2026
python3 scripts/score_report.py --from 2026-09-20 --to 2026-10-31
```

Writes Markdown + JSON under `data/reports/`:

| Period | Files |
| --- | --- |
| ISO week (Mon–Sun) | `YYYY-Www.scores.md` / `.json` |
| Calendar month | `YYYY-MM.scores.md` / `.json` |
| Calendar year | `YYYY.scores.md` / `.json` |

Week/month/year modes require the period **end-date** snapshot (`Sunday` / last day of month / `Dec 31`) unless `--allow-incomplete` is passed.

### Automation

Daily workflow (`.github/workflows/daily-snapshot.yml`) runs these **after** a successful snapshot for date **D**, not on a separate blind cron: Sunday → week; month-end → month; 31 Dec → year. See README for `workflow_dispatch` manual regen.
