# Popularity scoring

Primary numeric popularity system for Apple Music Top 100: Hong Kong daily snapshots.
Period scores (month or year) are sums of **daily song points**. Artist scores reuse the same points with full credit on collaborations.

The older lexicographic year-end sort in `scripts/year_end_report.py` remains available as an **ordinal** alternate ranking (see [Relationship to ordinal year-end](#relationship-to-ordinal-year-end)).

## Daily song points

For a track at chart rank **R** on a given day:

```text
points = 101 − R
```

| Rank R | Points |
| ---: | ---: |
| 1 | 100 |
| 2 | 99 |
| 10 | 91 |
| 100 | 1 |

Only ranks **1–100** award points. A song not on the chart that day contributes **0**.

### Example (one day)

- Song A at **#1** → **100** points  
- Song B at **#2** → **99** points  
- Song C at **#50** → **51** points  

## Song period score

Over a selected date range (calendar month, year, or custom `--from` / `--to`):

```text
song_score = Σ daily points for that song on each day it appears in the Top 100
```

Song identity prefers `apple_music_id`; otherwise title + artists (same rule as `year_end_report.py`).

Supporting metrics kept for ranking and reports:

- `days_at_number_1`, `days_in_top_10`, `days_in_top_100`
- `average_rank`, `best_peak_rank`
- `first_seen`, `last_seen`

### Example (three days)

| Day | Rank | Points |
| --- | ---: | ---: |
| Mon | 1 | 100 |
| Tue | 3 | 98 |
| Wed | 5 | 96 |
| **Period score** | | **294** |

A long stay near the top can outscore a short #1 run that then falls off the chart.

## Artist period score

For each track appearance on each day:

1. Compute that track’s daily points (`101 − R`).
2. Give **every** artist name in the track’s `artists` list the **full** points for that track that day (**no 1/n split** on collabs).
3. If `artists` is missing or empty, fall back to splitting `artists_display` on `&` / `,` (same spirit as `snapshot.py`).

Aggregate by a **normalized** artist key (strip whitespace; case-insensitive). The **display** name shown in reports is the casing from the **most recent** chart appearance in the period.

```text
artist_score = Σ (full daily points of each credited track appearance)
```

Also reported: `distinct_songs` (unique song keys credited to the artist in the period).

### Example (one day, collaboration)

Track **NEON** by **A2O** & **A2O LITE** at **#1** → **100** points.

- **A2O** receives **100**  
- **A2O LITE** receives **100**  

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
| **Scoring (primary)** | `scripts/score_report.py` | Additive points from every chart day; comparable across months; song **and** artist tables |
| **Ordinal year-end (alternate)** | `scripts/year_end_report.py` | Lexicographic sort: days at #1 → days in Top 10 → average rank → peak → days on chart → title |

Scoring answers “who accumulated the most chart value?” Ordinal year-end answers “who dominated the #1 / Top 10 story, with rank quality as tie-breakers?” Keep both; prefer scoring when you need a single numeric leaderboard.

## How to run

```bash
python3 scripts/score_report.py --month 2026-10
python3 scripts/score_report.py --year 2026
python3 scripts/score_report.py --from 2026-09-20 --to 2026-10-31
```

Writes Markdown + JSON under `data/reports/` (e.g. `2026-10.scores.md` / `2026-10.scores.json`).
