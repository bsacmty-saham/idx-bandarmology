"""
Website data bundle builder.

Compresses the latest day's stock summary, broker summary, index summary,
and bandarmology scores into a single small JSON file the static dashboard
(`site/data/latest.json`) can fetch directly — instead of loading the full
multi-MB time-series files in the browser.

Usage:
    uv run python -m idx.pipelines.website 2026-08-14
"""

import os
import json
import datetime

from idx.core.utils import DATA_DIR, get_logger, ensure_data_dir

log = get_logger("idx.pipelines.website")

TIMESERIES_DIR = os.path.join(DATA_DIR, "timeseries")
BANDAR_DIR = os.path.join(DATA_DIR, "bandarmology")

# Website output lives in /site so it can be published as a GitHub Pages root
REPO_ROOT = os.path.abspath(os.path.join(DATA_DIR, ".."))
SITE_DATA_DIR = os.path.join(REPO_ROOT, "site", "data")


def _load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _latest_for_date(records, date_iso):
    return [r for r in records if r.get("Date", "").startswith(date_iso)]


def build_website_bundle(date_iso=None):
    if date_iso is None:
        date_iso = datetime.datetime.now().strftime("%Y-%m-%d")

    ensure_data_dir()
    os.makedirs(SITE_DATA_DIR, exist_ok=True)

    stock_all = _load_json(os.path.join(TIMESERIES_DIR, "stock_summary.json"), [])
    broker_all = _load_json(os.path.join(TIMESERIES_DIR, "broker_summary.json"), [])
    index_all = _load_json(os.path.join(TIMESERIES_DIR, "index_summary.json"), [])
    bandar = _load_json(os.path.join(BANDAR_DIR, f"{date_iso}.json"), [])
    corporate_actions = _load_json(os.path.join(DATA_DIR, "corporateActions.json"), {})
    news = _load_json(os.path.join(DATA_DIR, "news_latest.json"), {})

    stock_today = _latest_for_date(stock_all, date_iso)
    broker_today = _latest_for_date(broker_all, date_iso)
    index_today = _latest_for_date(index_all, date_iso)

    # If today has no data yet (e.g. weekend / before market close), fall
    # back to the most recent available trading day so the site never shows
    # a blank page.
    if not stock_today and stock_all:
        last_date = max(r.get("Date", "")[:10] for r in stock_all)
        date_iso = last_date
        stock_today = _latest_for_date(stock_all, date_iso)
        broker_today = _latest_for_date(broker_all, date_iso)
        index_today = _latest_for_date(index_all, date_iso)
        bandar = _load_json(os.path.join(BANDAR_DIR, f"{date_iso}.json"), [])

    # Slim down news to headline essentials + most recent 20
    news_items = (news or {}).get("data", []) if isinstance(news, dict) else []
    news_slim = news_items[:20]

    # Slim corporate actions to a flat "recent 30 across all categories" list
    ca_flat = []
    for ca_type, payload in (corporate_actions.get("categories") or {}).items():
        for rec in (payload or {}).get("data", []):
            rec_copy = dict(rec)
            rec_copy["_category"] = ca_type
            ca_flat.append(rec_copy)
    ca_flat = ca_flat[:30]

    bundle = {
        "date": date_iso,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        "stock_summary": stock_today,
        "broker_summary": broker_today,
        "index_summary": index_today,
        "bandarmology": bandar,
        "news": news_slim,
        "corporate_actions": ca_flat,
        "meta": {
            "stock_count": len(stock_today),
            "broker_count": len(broker_today),
            "index_count": len(index_today),
            "bandar_scored": len(bandar),
            "note": (
                "Broker summary is market-wide (per broker), not per-stock — "
                "IDX public API does not expose per-stock broker breakdowns "
                "or tick-level running trade data for free. Bandarmology "
                "scores here are a heuristic proxy from public stock summary "
                "data (volume/frequency anomalies, foreign flow, bid/offer "
                "imbalance), not investment advice."
            ),
        },
    }

    out_path = os.path.join(SITE_DATA_DIR, "latest.json")
    tmp_path = out_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2)
    os.replace(tmp_path, out_path)
    log.info("Website bundle written -> %s (date=%s)", out_path, date_iso)

    # Also keep a rolling archive so the site can show a small history chart
    archive_dir = os.path.join(SITE_DATA_DIR, "history")
    os.makedirs(archive_dir, exist_ok=True)
    archive_path = os.path.join(archive_dir, f"{date_iso}.json")
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, indent=2)

    return bundle


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else None
    build_website_bundle(d)
