"""Retraction Watch first; Crossref fills missing fields and adds notices RW does not have."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

RWDB_URL = "https://gitlab.com/crossref/retraction-watch-data/-/raw/main/retraction_watch.csv"
CROSSREF_API = "https://api.crossref.org/works"
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

def mailto() -> str:
    return os.environ.get("CROSSREF_MAILTO") or "retraction-updater@users.noreply.github.com"


def clean_doi(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text or text == "nan":
        return ""
    text = re.sub(r"^https?://(dx\.)?doi\.org/", "", text)
    return text.strip()


def iso_date(value: object, *, source: str) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, dict) and "date-parts" in value:
        parts = (value.get("date-parts") or [[]])[0]
        if not parts:
            return None
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        return f"{year:04d}-{month:02d}-{day:02d}"
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    if " " in text:
        text = text.split(" ", 1)[0]
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text
    if re.match(r"^\d{4}/\d{1,2}$", text):
        year, month = text.split("/")
        return f"{int(year):04d}-{int(month):02d}-01"
    if re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", text):
        a, b, year = text.split("/")
        month, day = int(a), int(b)
        if source != "retraction_watch" and month > 12:
            month, day = day, month
        return f"{int(year):04d}-{month:02d}-{day:02d}"
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.strftime("%Y-%m-%d")


def load_retraction_watch(path: Path | None = None) -> pd.DataFrame:
    if path:
        df = pd.read_csv(path, encoding="latin1", low_memory=False)
    else:
        print("Downloading Retraction Watch database…")
        df = pd.read_csv(RWDB_URL, encoding="latin1", low_memory=False)
    df["RetractionDOI_Clean"] = df["RetractionDOI"].map(clean_doi) if "RetractionDOI" in df.columns else ""
    if "RetractionDate" in df.columns:
        df["RetractionDate"] = df["RetractionDate"].map(lambda x: iso_date(x, source="retraction_watch"))
    if "OriginalPaperDate" in df.columns:
        df["OriginalPaperDate"] = df["OriginalPaperDate"].map(lambda x: iso_date(x, source="retraction_watch"))
    df["Source"] = "Retraction Watch"
    print(f"  Retraction Watch rows: {len(df)}")
    return df


def fetch_crossref_year(year: int, session: requests.Session) -> list[dict[str, Any]]:
    headers = {"User-Agent": f"open-retraction-merge/1.0 (mailto:{mailto()})"}
    params = {
        "filter": f"update-type:retraction,from-pub-date:{year}-01-01,until-pub-date:{year}-12-31",
        "rows": "1000",
        "select": "DOI,title,publisher,created,issued,update-to,container-title,type,is-referenced-by-count,URL",
        "cursor": "*",
    }
    items: list[dict[str, Any]] = []
    cursor = "*"
    retries = 0
    while True:
        params["cursor"] = cursor
        try:
            response = session.get(CROSSREF_API, headers=headers, params=params, timeout=60)
        except requests.RequestException:
            retries += 1
            if retries > 5:
                break
            time.sleep(2)
            continue
        if response.status_code != 200:
            retries += 1
            if retries > 5:
                break
            time.sleep(2)
            continue
        retries = 0
        message = response.json().get("message", {})
        batch = message.get("items") or []
        items.extend(batch)
        next_cursor = message.get("next-cursor")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
    print(f"  Crossref {year}: {len(items)} notices")
    return items


def fetch_crossref(from_year: int, to_year: int) -> list[dict[str, Any]]:
    print(f"Fetching Crossref retraction notices {from_year}–{to_year}…")
    session = requests.Session()
    items: list[dict[str, Any]] = []
    for year in range(from_year, to_year + 1):
        items.extend(fetch_crossref_year(year, session))
        time.sleep(1)
    return items


def crossref_extras(item: dict[str, Any]) -> dict[str, Any]:
    title = (item.get("title") or [""])[0]
    journal = (item.get("container-title") or [""])[0]
    issued = iso_date(item.get("issued") or item.get("created"), source="crossref")
    retraction_date = None
    for update in item.get("update-to") or []:
        if update.get("type") == "retraction":
            retraction_date = iso_date(update.get("updated"), source="crossref")
            break
    return {
        "title": title,
        "publisher": item.get("publisher") or "",
        "issued": issued,
        "retraction_date": retraction_date or issued,
        "crossref_JournalName": journal,
        "crossref_CrossrefType": item.get("type") or "",
        "crossref_CitationCount": item.get("is-referenced-by-count") or 0,
        "crossref_PublisherURL": item.get("URL") or "",
        "crossref_Title": title,
        "crossref_Publisher": item.get("publisher") or "",
    }


def merge(rw: pd.DataFrame, crossref_items: list[dict[str, Any]]) -> tuple[pd.DataFrame, dict[str, int]]:
    records = rw.to_dict("records")
    index_by_doi: dict[str, int] = {}
    for i, row in enumerate(records):
        doi = clean_doi(row.get("RetractionDOI_Clean") or row.get("RetractionDOI"))
        if doi:
            index_by_doi[doi] = i
    both = 0
    crossref_only = 0
    rw_cols = list(rw.columns)
    for item in crossref_items:
        doi = clean_doi(item.get("DOI"))
        if not doi:
            continue
        extra = crossref_extras(item)
        if doi in index_by_doi:
            both += 1
            row = records[index_by_doi[doi]]
            row["Source"] = "Both"
            if not row.get("RetractionDate") and extra["retraction_date"]:
                row["RetractionDate"] = extra["retraction_date"]
            if not row.get("OriginalPaperDate") and extra["issued"]:
                row["OriginalPaperDate"] = extra["issued"]
            row.update({k: v for k, v in extra.items() if k.startswith("crossref_")})
            continue
        crossref_only += 1
        new_row = {col: None for col in rw_cols}
        new_row.update(
            {
                "RetractionDOI": item.get("DOI"),
                "Title": extra["title"],
                "Publisher": extra["publisher"],
                "RetractionDate": extra["retraction_date"],
                "OriginalPaperDate": extra["issued"],
                "ArticleType": "Retraction Notice",
                "Source": "Crossref only",
            }
        )
        new_row.update({k: v for k, v in extra.items() if k.startswith("crossref_")})
        records.append(new_row)
    out = pd.DataFrame.from_records(records)
    if "RetractionDOI_Clean" in out.columns:
        out = out.drop(columns=["RetractionDOI_Clean"])
    cols = list(out.columns)
    if "Source" in cols:
        cols.insert(0, cols.pop(cols.index("Source")))
        out = out[cols]
    stats = {
        "retraction_watch_rows": int(len(rw)),
        "crossref_notices": int(len(crossref_items)),
        "both": both,
        "crossref_only": crossref_only,
        "total": int(len(out)),
    }
    return out, stats


def write_outputs(df: pd.DataFrame, stats: dict[str, Any]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    gz_path = DATA / "retractions.csv.gz"
    df.to_csv(gz_path, index=False, encoding="utf-8", compression="gzip")
    stats = {
        **stats,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "row_count": int(len(df)),
        "files": ["data/retractions.csv.gz"],
    }
    (DATA / "status.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {gz_path} ({stats['total']} rows)")


def parse_args() -> argparse.Namespace:
    now = datetime.now(timezone.utc).year
    p = argparse.ArgumentParser(description="Refresh retraction notices (Retraction Watch + Crossref).")
    p.add_argument("--rw-path", type=Path, help="Local Retraction Watch CSV instead of GitLab")
    p.add_argument("--skip-crossref", action="store_true")
    p.add_argument("--crossref-from", type=int, default=now - 1)
    p.add_argument("--crossref-to", type=int, default=now)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    rw = load_retraction_watch(args.rw_path)
    if rw.empty:
        print("Retraction Watch download returned no rows.")
        return 1
    cr = [] if args.skip_crossref else fetch_crossref(args.crossref_from, args.crossref_to)
    merged, stats = merge(rw, cr)
    stats["crossref_years"] = None if args.skip_crossref else [args.crossref_from, args.crossref_to]
    write_outputs(merged, stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
