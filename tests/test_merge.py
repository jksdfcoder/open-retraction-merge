from update import clean_doi, iso_date, merge
import pandas as pd


def test_clean_doi():
    assert clean_doi("https://doi.org/10.1000/XYZ") == "10.1000/xyz"
    assert clean_doi("") == ""
    assert clean_doi(None) == ""


def test_iso_date_rw_and_crossref():
    assert iso_date("3/14/2024 0:00", source="retraction_watch") == "2024-03-14"
    assert iso_date({"date-parts": [[2024, 3, 14]]}, source="crossref") == "2024-03-14"


def test_merge_rw_primary_crossref_fills_and_appends():
    rw = pd.DataFrame(
        [
            {
                "RetractionDOI": "10.1/aaa",
                "RetractionDOI_Clean": "10.1/aaa",
                "Title": "RW title",
                "RetractionDate": None,
                "OriginalPaperDate": "2020-01-01",
                "Source": "Retraction Watch",
            }
        ]
    )
    crossref = [
        {
            "DOI": "10.1/AAA",
            "title": ["CR title"],
            "publisher": "Elsevier",
            "issued": {"date-parts": [[2024, 2, 1]]},
            "update-to": [{"type": "retraction", "updated": {"date-parts": [[2024, 3, 1]]}}],
            "container-title": ["Journal of Example"],
            "type": "retraction",
            "is-referenced-by-count": 3,
            "URL": "https://doi.org/10.1/aaa",
        },
        {
            "DOI": "10.1/only-cr",
            "title": ["Crossref-only notice"],
            "publisher": "Wiley",
            "issued": {"date-parts": [[2025, 1, 1]]},
            "update-to": [],
            "container-title": ["Other Journal"],
            "type": "retraction",
            "is-referenced-by-count": 0,
            "URL": "https://doi.org/10.1/only-cr",
        },
    ]
    out, stats = merge(rw, crossref)
    assert stats["retraction_watch_rows"] == 1
    assert stats["both"] == 1
    assert stats["crossref_only"] == 1
    assert stats["total"] == 2
    both = out[out["Source"] == "Both"].iloc[0]
    assert both["Title"] == "RW title"
    assert both["RetractionDate"] == "2024-03-01"
    assert both["crossref_JournalName"] == "Journal of Example"
    only = out[out["Source"] == "Crossref only"].iloc[0]
    assert only["RetractionDOI"] == "10.1/only-cr"
