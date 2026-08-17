"""
Bandarmology (accumulation/distribution) scoring pipeline.

IMPORTANT — DATA SCOPE:
IDX's public `TradingSummary/GetBrokerSummary` endpoint is MARKET-WIDE
(aggregated per broker across the entire exchange), NOT broken down per
stock. Per-stock, per-broker "who bought/sold this ticker" data (the classic
bandarmology broker table) and tick-level running trade / done detail are
only available through IDX's paid Data Services or licensed broker
terminals — this pipeline does not and cannot fabricate that.

What this pipeline DOES compute, from data that IS legitimately public via
this repo's scrapers (`fetch_stock_summary` time-series):

  - Foreign Net Flow          : ForeignBuy - ForeignSell (value-weighted)
  - Volume Z-Score            : today's volume vs trailing N-day mean/stdev
  - Frequency Z-Score         : today's transaction frequency vs trailing N-day
  - Bid/Offer Imbalance       : (BidVolume - OfferVolume) / (BidVolume + OfferVolume)
  - Price-Volume Divergence   : price change vs volume change (accumulation
                                 signature = price flat/down but volume/freq spike)
  - Composite Accumulation Score (0-100), a weighted blend of the above,
    used purely as a heuristic screener — NOT investment advice.

Usage:
    uv run python -m idx.pipelines.bandarmology --date 20260814
"""

import os
import json
import argparse
import datetime
import statistics
from collections import defaultdict

from idx.core.utils import DATA_DIR, get_logger, ensure_data_dir

log = get_logger("idx.pipelines.bandarmology")

TIMESERIES_DIR = os.path.join(DATA_DIR, "timeseries")
STOCK_TS_FILE = os.path.join(TIMESERIES_DIR, "stock_summary.json")
OUTPUT_DIR = os.path.join(DATA_DIR, "bandarmology")

LOOKBACK_DAYS = 20  # trailing window for z-score baselines


def _load_stock_timeseries():
    if not os.path.exists(STOCK_TS_FILE):
        log.error("Stock summary time-series not found at %s. Run `cli.py backfill` or `cli.py daily` first.", STOCK_TS_FILE)
        return []
    with open(STOCK_TS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _group_by_stock(records):
    by_stock = defaultdict(list)
    for rec in records:
        code = rec.get("StockCode")
        if code:
            by_stock[code].append(rec)
    for code in by_stock:
        by_stock[code].sort(key=lambda r: r.get("Date", ""))
    return by_stock


def _zscore(value, series):
    """Z-score of `value` against trailing `series` (excludes value itself)."""
    if len(series) < 3:
        return 0.0
    mean = statistics.mean(series)
    stdev = statistics.pstdev(series)
    if stdev == 0:
        return 0.0
    return (value - mean) / stdev


def _clip(x, lo=-3.0, hi=3.0):
    return max(lo, min(hi, x))


def compute_scores(target_date, records=None):
    """Computes accumulation/distribution scores for every stock on target_date (YYYY-MM-DD)."""
    if records is None:
        records = _load_stock_timeseries()
    if not records:
        return []

    by_stock = _group_by_stock(records)
    results = []

    for code, history in by_stock.items():
        history_before = [r for r in history if r.get("Date", "") < target_date]
        today_rows = [r for r in history if r.get("Date", "").startswith(target_date)]
        if not today_rows:
            continue
        today = today_rows[-1]

        window = history_before[-LOOKBACK_DAYS:]
        if len(window) < 5:
            continue  # not enough baseline history yet

        vol_series = [w.get("Volume", 0) or 0 for w in window]
        freq_series = [w.get("Frequency", 0) or 0 for w in window]

        volume = today.get("Volume", 0) or 0
        frequency = today.get("Frequency", 0) or 0
        close = today.get("Close", 0) or 0
        prev = today.get("Previous", 0) or 0
        f_buy = today.get("ForeignBuy", 0) or 0
        f_sell = today.get("ForeignSell", 0) or 0
        bid_vol = today.get("BidVolume", 0) or 0
        offer_vol = today.get("OfferVolume", 0) or 0
        value = today.get("Value", 0) or 0

        vol_z = _clip(_zscore(volume, vol_series))
        freq_z = _clip(_zscore(frequency, freq_series))

        foreign_net = f_buy - f_sell
        foreign_net_ratio = (foreign_net / volume) if volume else 0.0

        bo_total = bid_vol + offer_vol
        bid_offer_imbalance = ((bid_vol - offer_vol) / bo_total) if bo_total else 0.0

        price_chg_pct = ((close - prev) / prev * 100) if prev else 0.0

        # Accumulation signature: volume/freq spiking while price is flat/down
        # (quiet absorption) scores higher than a spike with a big price pop
        # (which is more likely public momentum, not stealth accumulation).
        quiet_absorption = max(0.0, 1.0 - min(abs(price_chg_pct) / 3.0, 1.0))

        composite = (
            0.30 * ((vol_z + 3) / 6) +          # normalize z(-3..3) -> 0..1
            0.20 * ((freq_z + 3) / 6) +
            0.25 * ((foreign_net_ratio + 1) / 2 if -1 <= foreign_net_ratio <= 1 else (1 if foreign_net_ratio > 1 else 0)) +
            0.15 * ((bid_offer_imbalance + 1) / 2) +
            0.10 * quiet_absorption
        ) * 100

        results.append({
            "StockCode": code,
            "Date": target_date,
            "Close": close,
            "PriceChangePct": round(price_chg_pct, 2),
            "Volume": volume,
            "Frequency": frequency,
            "Value": value,
            "VolumeZScore": round(vol_z, 2),
            "FrequencyZScore": round(freq_z, 2),
            "ForeignNet": foreign_net,
            "ForeignNetRatio": round(foreign_net_ratio, 4),
            "BidOfferImbalance": round(bid_offer_imbalance, 4),
            "AccumulationScore": round(composite, 2),
        })

    results.sort(key=lambda r: r["AccumulationScore"], reverse=True)
    return results


def run(target_date=None):
    if target_date is None:
        target_date = datetime.datetime.now().strftime("%Y-%m-%d")

    ensure_data_dir()
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    records = _load_stock_timeseries()
    scores = compute_scores(target_date, records)

    out_path = os.path.join(OUTPUT_DIR, f"{target_date}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=2)
    log.info("Wrote %d scored stocks -> %s", len(scores), out_path)

    # Also refresh a "latest.json" pointer for the website to always fetch
    latest_path = os.path.join(OUTPUT_DIR, "latest.json")
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump({"date": target_date, "data": scores}, f, indent=2)
    log.info("Updated latest.json (date=%s)", target_date)

    return scores


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute bandarmology accumulation/distribution scores")
    parser.add_argument("--date", help="Target date YYYY-MM-DD (default: today)", default=None)
    args = parser.parse_args()
    run(target_date=args.date)
