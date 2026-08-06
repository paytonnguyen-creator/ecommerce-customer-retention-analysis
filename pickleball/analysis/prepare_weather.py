"""
Build the real-weather backbone for the court-demand study.

WHY THIS FILE EXISTS SEPARATELY
-------------------------------
The court sessions in this project are simulated (no municipal parks
department publishes paddle-stack telemetry). The weather is not. Keeping the
two in different files makes the seam impossible to miss: everything produced
here is measured, everything produced by `simulate_courts.py` is assumed.

That seam matters for reading the results. A demand model fitted to simulated
arrivals can only recover the assumptions that generated them. What it cannot
fake is the *joint distribution of the weather itself* -- the fact that warm
evenings cluster in July, that a 70F day in Seattle is often a 70F day
followed by another one, that rain and cold arrive together, and that in
December an outdoor unlit court is unusable after 16:20 no matter how mild it
is. Those correlations are what make a forecasting problem hard, and they are
real here.

SOURCES (both ship inside the `vega_datasets` package -- no download)
  seattle-weather   NOAA daily observations, 2012-01-01 .. 2015-12-31 (1,461 days)
                    precipitation (mm), temp_max/min (C), wind (m/s), condition
  seattle-temps     NOAA hourly temperature, Seattle, 2010 (8,759 hours)

The daily file has no hourly resolution and the hourly file covers a different
year, so they are joined the only honest way: the 2010 hourly file supplies
the *shape* of a Seattle day by month -- where in the min-to-max range each
hour typically sits -- and the daily file supplies the actual min and max being
interpolated. Same weather station, same city. The shape is measured, not
invented; what it is not is the specific hourly path of a specific 2013 day.

Daylight is computed from solar geometry (NOAA's algorithm) rather than
assumed, because outdoor courts are unlit: playable hours in Seattle run
~15.9h in June and ~8.3h in December, and that seasonal capacity swing is a
real constraint no assumption should be allowed to soften.

Run:    python pickleball/analysis/prepare_weather.py
Writes: pickleball/data/hourly_weather.csv
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from vega_datasets import local_data

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Seattle-Tacoma, the station behind both vega datasets.
LAT, LON, TZ = 47.61, -122.33, ZoneInfo("America/Los_Angeles")

# Courts are municipal: gates open at 07:00, lights-out curfew at 21:00. The
# binding constraint is usually daylight, not the curfew -- see `playable`.
OPEN_HOUR, CLOSE_HOUR = 7, 21


def c_to_f(c: pd.Series | float) -> pd.Series | float:
    return c * 9 / 5 + 32


# ── 1. Diurnal shape, measured from the 2010 hourly file ─────────────────────
def diurnal_shape() -> pd.DataFrame:
    """Mean position of each hour within its own day's min-max range, by month.

    A value of 0 means "that hour is typically the coldest of the day", 1 means
    "typically the warmest". Averaging within month keeps the seasonal shift of
    the daily peak (mid-afternoon in July, later-and-flatter in December).
    """
    h = local_data("seattle-temps").copy()
    h["day"] = h["date"].dt.normalize()
    h["hour"] = h["date"].dt.hour
    h["month"] = h["date"].dt.month

    span = h.groupby("day")["temp"].agg(["min", "max"])
    h = h.join(span, on="day")
    # Flat days carry no shape information; drop rather than divide by ~0.
    h = h[(h["max"] - h["min"]) > 1.0].copy()
    h["frac"] = (h["temp"] - h["min"]) / (h["max"] - h["min"])

    shape = h.groupby(["month", "hour"])["frac"].mean().rename("frac").reset_index()
    # Re-normalise so each month's shape still spans exactly 0..1 after
    # averaging (averaging pulls the extremes in slightly).
    lo = shape.groupby("month")["frac"].transform("min")
    hi = shape.groupby("month")["frac"].transform("max")
    shape["frac"] = (shape["frac"] - lo) / (hi - lo)
    return shape


# ── 2. Daylight, computed from solar geometry ───────────────────────────────
def sun_times(day: pd.Timestamp) -> tuple[float, float]:
    """Local-clock sunrise and sunset in decimal hours (NOAA solar algorithm)."""
    doy = day.dayofyear
    gamma = 2 * np.pi / 365 * (doy - 1 + 0.5)  # evaluated at solar noon

    eqtime = 229.18 * (
        0.000075
        + 0.001868 * np.cos(gamma)
        - 0.032077 * np.sin(gamma)
        - 0.014615 * np.cos(2 * gamma)
        - 0.040849 * np.sin(2 * gamma)
    )
    decl = (
        0.006918
        - 0.399912 * np.cos(gamma)
        + 0.070257 * np.sin(gamma)
        - 0.006758 * np.cos(2 * gamma)
        + 0.000907 * np.sin(2 * gamma)
        - 0.002697 * np.cos(3 * gamma)
        + 0.001480 * np.sin(3 * gamma)
    )

    lat = np.radians(LAT)
    # 90.833 deg accounts for refraction and the solar disc's radius.
    cos_ha = np.cos(np.radians(90.833)) / (np.cos(lat) * np.cos(decl)) - np.tan(lat) * np.tan(decl)
    cos_ha = float(np.clip(cos_ha, -1.0, 1.0))  # polar cases; never hit at 47N
    ha = np.degrees(np.arccos(cos_ha))

    out = []
    for signed_ha in (ha, -ha):
        utc_minutes = 720 - 4 * (LON + signed_ha) - eqtime
        stamp = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(
            minutes=float(utc_minutes)
        )
        local = stamp.astimezone(TZ)
        out.append(local.hour + local.minute / 60 + local.second / 3600)
    return out[0], out[1]


# ── 3. Assemble ─────────────────────────────────────────────────────────────
def build() -> tuple[pd.DataFrame, dict]:
    daily = local_data("seattle-weather").copy()
    daily["date"] = pd.to_datetime(daily["date"])
    daily["temp_max_f"] = c_to_f(daily["temp_max"])
    daily["temp_min_f"] = c_to_f(daily["temp_min"])
    daily["month"] = daily["date"].dt.month

    shape = diurnal_shape()

    sun = pd.DataFrame(
        [{"date": d, "sunrise": sr, "sunset": ss} for d in daily["date"] for sr, ss in [sun_times(d)]]
    )

    hours = pd.DataFrame({"hour": range(24)})
    df = daily.merge(hours, how="cross").merge(shape, on=["month", "hour"], how="left")
    df = df.merge(sun, on="date", how="left")

    df["temp_f"] = df["temp_min_f"] + df["frac"] * (df["temp_max_f"] - df["temp_min_f"])
    df["temp_f"] = df["temp_f"].round(2)

    # An hour counts as daylight if the whole hour sits inside sunrise..sunset;
    # half-lit hours are excluded because you cannot start an 11-point game in
    # them. The curfew and the gate hours bound it further.
    df["daylight"] = (df["hour"] >= np.ceil(df["sunrise"])) & (df["hour"] + 1 <= df["sunset"])
    df["playable"] = df["daylight"] & df["hour"].between(OPEN_HOUR, CLOSE_HOUR - 1)

    df["is_wet"] = df["precipitation"] > 0.5  # mm; below this the surface stays playable
    df["dow"] = df["date"].dt.dayofweek  # 0 = Monday
    df["is_weekend"] = df["dow"] >= 5

    cols = [
        "date", "hour", "temp_f", "precipitation", "wind", "weather",
        "is_wet", "daylight", "playable", "dow", "is_weekend", "sunrise", "sunset",
    ]
    df = df[cols].sort_values(["date", "hour"]).reset_index(drop=True)

    playable_by_month = (
        df.groupby(df["date"].dt.month)["playable"].sum()
        / df.groupby(df["date"].dt.month)["date"].nunique()
    )

    log = {
        "source": "NOAA via vega_datasets: seattle-weather (daily 2012-2015), seattle-temps (hourly 2010)",
        "days": int(df["date"].nunique()),
        "hours": int(len(df)),
        "date_min": str(df["date"].min().date()),
        "date_max": str(df["date"].max().date()),
        "wet_day_share": round(float(daily["precipitation"].gt(0.5).mean()), 4),
        "temp_f_min": float(df["temp_f"].min()),
        "temp_f_max": float(df["temp_f"].max()),
        "playable_hours_per_day": round(float(df.groupby("date")["playable"].sum().mean()), 2),
        "playable_hours_june": round(float(playable_by_month.loc[6]), 2),
        "playable_hours_december": round(float(playable_by_month.loc[12]), 2),
    }
    return df, log


if __name__ == "__main__":
    DATA.mkdir(parents=True, exist_ok=True)
    df, log = build()
    df.to_csv(DATA / "hourly_weather.csv", index=False)
    (DATA / "weather_provenance.json").write_text(json.dumps(log, indent=2) + "\n")
    print(json.dumps(log, indent=2))
    print(f"\nwrote {DATA / 'hourly_weather.csv'}  ({len(df):,} hourly rows)")
