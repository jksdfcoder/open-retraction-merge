# Open Retraction Merge

Keeps a rolling snapshot of retraction notices. **Retraction Watch is the source of truth.** Crossref supplies missing dates, journal names, and citation counts, and adds notices that are not yet in Retraction Watch.

Scheduled refresh: **every 6 hours** (GitHub Actions). Crossref is queried for the current and previous calendar year so the job stays inside a 6-hour window; Retraction Watch is always a full download.

**Latest snapshot:** [retractions.csv.gz](https://github.com/jksdfcoder/open-retraction-merge/releases/latest/download/retractions.csv.gz)

## Quick start

```bash
git clone https://github.com/jksdfcoder/open-retraction-merge.git
cd open-retraction-merge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export CROSSREF_MAILTO=you@example.com   # Crossref polite pool
python update.py
```

`data/retractions.csv.gz` and `data/status.json` are written locally. On GitHub, the gzip snapshot is published as a release asset; `data/status.json` is committed so the last run is visible in the repo.

| Command | Purpose |
| --- | --- |
| `python update.py` | Full Retraction Watch + Crossref for last two years |
| `python update.py --skip-crossref` | Retraction Watch only |
| `python update.py --crossref-from 2000` | Optional full Crossref backfill (slow; not used on the 6-hour schedule) |
| `python -m pytest tests/` | Merge checks |

## Output

Each row has `Source`: `Retraction Watch`, `Both`, or `Crossref only`. Retraction Watch fields are kept when present; Crossref is used only to fill blanks and to attach `crossref_*` columns.

## Data sources

- [Retraction Watch database](https://gitlab.com/crossref/retraction-watch-data) (Crossref GitLab)
- [Crossref REST API](https://api.crossref.org/works) (`update-type:retraction`)

## License

MIT for the code. Retraction Watch and Crossref remain under their own terms; attribution stays with those projects.
