# Reports

Score reports from `scripts/score_report.py` (`p(r) = ln(101 / r)`; see [`docs/SCORING.md`](../../docs/SCORING.md)):

| Pattern | Period |
| --- | --- |
| `YYYY-Www.scores.md` / `.json` | ISO week (Monday–Sunday) |
| `YYYY-MM.scores.md` / `.json` | Calendar month |
| `YYYY.scores.md` / `.json` | Calendar year |

Ordinal year-end (`YYYY.md` / `.json`): from `scripts/year_end_report.py` (lexicographic alternate).

Generated automatically by `.github/workflows/daily-snapshot.yml` after the period’s end-date snapshot lands (Sunday / month-end / 31 Dec), or via `workflow_dispatch`.
