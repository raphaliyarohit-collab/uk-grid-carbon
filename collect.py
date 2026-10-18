"""
UK Grid Carbon Tracker - data collector
=======================================

Pulls half-hourly data from the NESO Carbon Intensity API (free, no API key)
and keeps four CSV files in ./data up to date:

  national_intensity.csv   GB carbon intensity, forecast vs actual (gCO2/kWh)
  national_generation.csv  GB generation mix (% by fuel)
  regional_intensity.csv   every GB region (incl. North & South Scotland) + country totals
  regional_forecast_48h.csv  next 48 hours by region (overwritten every run)

Run it every 30 minutes (GitHub Actions does this for you, see
.github/workflows/collect.yml). Each run upserts the last 24 hours, so
late-arriving "actual" values and revised forecasts replace older rows.

Usage:
  python collect.py                  # normal run (last 24h + next 48h)
  python collect.py --backfill 30    # one-off: load the last 30 days of history
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://api.carbonintensity.org.uk"
DATA_DIR = Path(__file__).parent / "data"
FUELS = ["biomass", "coal", "imports", "gas", "nuclear", "other", "hydro", "solar", "wind"]
CHUNK_DAYS = 7  # API caps date ranges (14 days for /intensity); 7 is safe for all endpoints

session = requests.Session()
session.headers.update({"Accept": "application/json", "User-Agent": "uk-grid-carbon-portfolio"})


# --------------------------------------------------------------------------- helpers

def iso(dt: datetime) -> str:
    """Format a datetime the way the API wants it: YYYY-MM-DDThh:mmZ (UTC)."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def get(path: str, retries: int = 3) -> list:
    """GET an endpoint and return its 'data' list, retrying on transient errors."""
    url = f"{BASE_URL}{path}"
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json().get("data", [])
        except (requests.RequestException, ValueError) as exc:
            if attempt == retries:
                raise RuntimeError(f"Failed after {retries} attempts: {url}") from exc
            time.sleep(5 * attempt)
    return []


def mix_to_columns(mix: list[dict]) -> dict:
    """[{'fuel':'gas','perc':43.6}, ...] -> {'gas_pct': 43.6, ...}"""
    cols = {f"{f}_pct": None for f in FUELS}
    for item in mix or []:
        cols[f"{item['fuel']}_pct"] = item.get("perc")
    return cols


# --------------------------------------------------------------------------- parsers

def parse_national_intensity(rows: list) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "from_utc": r["from"],
            "to_utc": r["to"],
            "forecast_gco2": r["intensity"].get("forecast"),
            "actual_gco2": r["intensity"].get("actual"),
            "intensity_index": r["intensity"].get("index"),
        }
        for r in rows
    )


def parse_national_generation(rows: list) -> pd.DataFrame:
    return pd.DataFrame(
        {"from_utc": r["from"], "to_utc": r["to"], **mix_to_columns(r.get("generationmix"))}
        for r in rows
    )


def parse_regional(rows: list) -> pd.DataFrame:
    """Regional endpoints return one row per half hour, each with a list of regions."""
    records = []
    for period in rows:
        for reg in period.get("regions", []):
            records.append(
                {
                    "from_utc": period["from"],
                    "to_utc": period["to"],
                    "region_id": reg["regionid"],
                    "region": reg["shortname"],
                    "dno_region": reg.get("dnoregion"),
                    "forecast_gco2": reg["intensity"].get("forecast"),
                    "intensity_index": reg["intensity"].get("index"),
                    **mix_to_columns(reg.get("generationmix")),
                }
            )
    return pd.DataFrame(records)


# --------------------------------------------------------------------------- storage

def upsert(new: pd.DataFrame, filename: str, keys: list[str]) -> int:
    """Merge new rows into a CSV, newest version of each key wins. Returns row count."""
    path = DATA_DIR / filename
    if new.empty:
        return 0
    if path.exists():
        old = pd.read_csv(path)
        combined = pd.concat([old, new], ignore_index=True)
    else:
        combined = new
    combined = combined.drop_duplicates(subset=keys, keep="last").sort_values(keys)
    combined.to_csv(path, index=False)
    return len(combined)


def stamp(df: pd.DataFrame, run_time: datetime) -> pd.DataFrame:
    """Add UK local time (handles GMT/BST switch) and a load timestamp."""
    if not df.empty:
        uk = pd.to_datetime(df["from_utc"], utc=True).dt.tz_convert("Europe/London")
        df.insert(2, "from_uk", uk.dt.strftime("%Y-%m-%d %H:%M"))
        df["loaded_at_utc"] = iso(run_time)
    return df


# --------------------------------------------------------------------------- jobs

def collect_window(start: datetime, end: datetime, run_time: datetime) -> None:
    """Fetch history between start and end in safe-sized chunks and upsert it."""
    cursor = start
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=CHUNK_DAYS), end)
        f, t = iso(cursor), iso(chunk_end)

        n1 = upsert(stamp(parse_national_intensity(get(f"/intensity/{f}/{t}")), run_time),
                    "national_intensity.csv", ["from_utc"])
        n2 = upsert(stamp(parse_national_generation(get(f"/generation/{f}/{t}")), run_time),
                    "national_generation.csv", ["from_utc"])
        n3 = upsert(stamp(parse_regional(get(f"/regional/intensity/{f}/{t}")), run_time),
                    "regional_intensity.csv", ["from_utc", "region_id"])
        print(f"  {f} -> {t}: national={n1} generation={n2} regional={n3} rows in files")
        cursor = chunk_end


def collect_forecast(run_time: datetime) -> None:
    """Next 48h for every region. Overwritten each run: it's a snapshot, not history."""
    df = stamp(parse_regional(get(f"/regional/intensity/{iso(run_time)}/fw48h")), run_time)
    if not df.empty:
        df.to_csv(DATA_DIR / "regional_forecast_48h.csv", index=False)
    print(f"  forecast: {len(df)} rows")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backfill", type=int, metavar="DAYS", help="load this many days of history")
    args = parser.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    days = args.backfill or 1

    print(f"Run at {iso(now)} - collecting last {days} day(s)")
    collect_window(now - timedelta(days=days), now, now)
    collect_forecast(now)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
