# Open Retraction Merge

A small pipeline for building a combined retraction table.

**Retraction Watch is the source of truth.** Crossref is used only to fill missing dates, journal names, and citation counts, and to add notices that are not yet in Watch.

The job is written so it can run on a **6-hour** cycle: Watch is a full download; Crossref is limited to the current and previous calendar year so a scheduled run stays inside that window. This repository ships the method (`update.py`). It does not host the resulting dump.

## How it works

```text
Retraction Watch CSV (GitLab)
        │
        ▼
  keep every Watch row
        │
        ├── Crossref retraction notices (REST, last two years)
        │         │
        │         ├── same DOI → fill blanks, tag Source=Both
        │         └── new DOI  → append, tag Source=Crossref only
        ▼
  local retractions.csv.gz
```

1. Download the public [Retraction Watch database](https://gitlab.com/crossref/retraction-watch-data).
2. Query the [Crossref works API](https://api.crossref.org/works) with `update-type:retraction` for a short year window.
3. Match on DOI. Watch fields win when present; Crossref writes `crossref_*` columns and fills empty dates.
4. Write a gzip snapshot on the machine that ran the script.

`Source` on each row is `Retraction Watch`, `Both`, or `Crossref only`.

## Run it yourself

```bash
git clone https://github.com/jksdfcoder/open-retraction-merge.git
cd open-retraction-merge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export CROSSREF_MAILTO=you@example.com
python update.py
```

Output is local only (`data/retractions.csv.gz`). Nothing is pushed back to GitHub.

| Command | Purpose |
| --- | --- |
| `python update.py` | Watch (full) + Crossref (last two years) |
| `python update.py --skip-crossref` | Watch only |
| `python update.py --crossref-from 2000` | Optional full Crossref backfill (slow) |
| `python -m pytest tests/` | Merge checks |

To refresh every six hours on your own host:

```cron
0 */6 * * * cd /path/to/open-retraction-merge && .venv/bin/python update.py
```

## License

MIT for the code. Retraction Watch and Crossref remain under their own terms.
