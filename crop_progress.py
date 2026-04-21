"""
crop_progress.py
----------------
USDA NASS Crop Progress and Condition data module.

Weekly data released every Monday during the growing season (Apr-Nov).
Covers planting pace, emergence, reproductive stage milestones, and
five-category condition ratings (EXCELLENT / GOOD / FAIR / POOR / VERY POOR).

The Crop Condition Index (CCI) collapses the five ratings into a single
0-100 score that feeds the yield modifier in the profitability model.

All live data requires USDA_API_KEY in the environment.
Demo data is available without any API key via get_demo_crop_progress().
"""

import logging
import os
from typing import Optional

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

USDA_BASE_URL = "https://quickstats.nass.usda.gov/api/api_GET/"

# Progress milestones tracked by commodity
PROGRESS_UNITS = {
    "soybean": [
        "PCT PLANTED",
        "PCT EMERGED",
        "PCT BLOOMING",
        "PCT SETTING PODS",
        "PCT DROPPING LEAVES",
        "PCT HARVESTED",
    ],
    "corn": [
        "PCT PLANTED",
        "PCT EMERGED",
        "PCT SILKING",
        "PCT DOUGH",
        "PCT DENTED",
        "PCT MATURE",
        "PCT HARVESTED",
    ],
}

# CCI weights: EXCELLENT=100, GOOD=75, FAIR=50, POOR=25, VERY POOR=0
CONDITION_WEIGHTS = {
    "EXCELLENT": 100,
    "GOOD":      75,
    "FAIR":      50,
    "POOR":      25,
    "VERY POOR": 0,
}

CORN_BELT_STATES = [
    "ILLINOIS", "INDIANA", "IOWA", "KANSAS", "MICHIGAN",
    "MINNESOTA", "MISSOURI", "NEBRASKA", "OHIO",
    "SOUTH DAKOTA", "WISCONSIN",
]

# 5-year average planting pace at USDA report week 20 (mid-May benchmark)
PLANTING_PACE_BENCHMARKS = {
    "soybean": {
        "IOWA": 45, "ILLINOIS": 48, "INDIANA": 42, "MINNESOTA": 30,
        "NEBRASKA": 52, "OHIO": 38, "MICHIGAN": 28, "WISCONSIN": 25,
        "MISSOURI": 55, "KANSAS": 60, "SOUTH DAKOTA": 35,
    },
    "corn": {
        "IOWA": 72, "ILLINOIS": 68, "INDIANA": 65, "MINNESOTA": 55,
        "NEBRASKA": 70, "OHIO": 60, "MICHIGAN": 52, "WISCONSIN": 48,
        "MISSOURI": 70, "KANSAS": 72, "SOUTH DAKOTA": 60,
    },
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _usda_get(params: dict, timeout: int = 20) -> dict:
    api_key = os.getenv("USDA_API_KEY", "")
    if not api_key:
        raise EnvironmentError("USDA_API_KEY not set. Add to .env file.")
    params = {**params, "key": api_key, "format": "JSON"}
    resp = requests.get(USDA_BASE_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Fetch functions
# ---------------------------------------------------------------------------

def fetch_crop_progress(
    commodity: str = "SOYBEANS",
    state_name: str = "IOWA",
    year: int = 2025,
    unit_desc: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch weekly crop progress from USDA NASS QuickStats.

    Parameters
    ----------
    commodity : str
        'SOYBEANS' or 'CORN' (UPPERCASE, as NASS expects).
    state_name : str
        Full state name in UPPERCASE (e.g. 'IOWA').
    year : int
        Crop year.
    unit_desc : str, optional
        Specific metric such as 'PCT PLANTED'. If None, fetches all.

    Returns
    -------
    pd.DataFrame
        Columns: week_ending, state_name, commodity, unit_desc, pct_value.
    """
    params = {
        "commodity_desc":    commodity,
        "statisticcat_desc": "PROGRESS",
        "state_name":        state_name,
        "year":              year,
        "freq_desc":         "WEEKLY",
        "agg_level_desc":    "STATE",
        "source_desc":       "SURVEY",
    }
    if unit_desc:
        params["unit_desc"] = unit_desc

    logger.info("Fetching crop progress: %s %s %d", commodity, state_name, year)

    try:
        data = _usda_get(params)
    except EnvironmentError:
        raise
    except Exception as exc:
        logger.error("Crop progress fetch failed: %s", exc)
        return pd.DataFrame()

    if "data" not in data or not data["data"]:
        return pd.DataFrame()

    df = pd.DataFrame(data["data"])
    df["pct_value"]  = pd.to_numeric(df["Value"].str.replace(",", ""), errors="coerce")
    df["week_ending"] = pd.to_datetime(df["week_ending"], errors="coerce")
    df = df.dropna(subset=["pct_value", "week_ending"])

    return (
        df[["week_ending", "state_name", "commodity_desc", "unit_desc", "pct_value"]]
        .rename(columns={"commodity_desc": "commodity"})
        .sort_values("week_ending")
        .reset_index(drop=True)
    )


def fetch_crop_condition(
    commodity: str = "SOYBEANS",
    state_name: str = "IOWA",
    year: int = 2025,
) -> pd.DataFrame:
    """
    Fetch weekly crop condition ratings from USDA NASS QuickStats.

    Returns
    -------
    pd.DataFrame
        Columns: week_ending, state_name, commodity, condition_label,
                 pct_value, cci_weight, cci_contribution.
    """
    params = {
        "commodity_desc":    commodity,
        "statisticcat_desc": "CONDITION",
        "state_name":        state_name,
        "year":              year,
        "freq_desc":         "WEEKLY",
        "agg_level_desc":    "STATE",
        "source_desc":       "SURVEY",
    }

    logger.info("Fetching crop condition: %s %s %d", commodity, state_name, year)

    try:
        data = _usda_get(params)
    except EnvironmentError:
        raise
    except Exception as exc:
        logger.error("Crop condition fetch failed: %s", exc)
        return pd.DataFrame()

    if "data" not in data or not data["data"]:
        return pd.DataFrame()

    df = pd.DataFrame(data["data"])
    df["pct_value"]       = pd.to_numeric(df["Value"].str.replace(",", ""), errors="coerce")
    df["week_ending"]     = pd.to_datetime(df["week_ending"], errors="coerce")
    df["condition_label"] = df["unit_desc"].str.replace("PCT ", "").str.strip()
    df["cci_weight"]      = df["condition_label"].map(CONDITION_WEIGHTS).fillna(50)
    df["cci_contribution"]= df["pct_value"] * df["cci_weight"] / 100

    df = df.dropna(subset=["pct_value", "week_ending"])

    return (
        df[["week_ending", "state_name", "commodity_desc", "condition_label",
            "pct_value", "cci_weight", "cci_contribution"]]
        .rename(columns={"commodity_desc": "commodity"})
        .sort_values(["week_ending", "condition_label"])
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Derived metrics
# ---------------------------------------------------------------------------

def calculate_crop_condition_index(condition_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute the weekly Crop Condition Index from condition ratings.

    CCI = sum(pct_category * weight) / 100
    Range: 0 (all VERY POOR) to 100 (all EXCELLENT).
    Historical Iowa soybean average: approximately 62.

    Returns
    -------
    pd.DataFrame
        Columns: week_ending, state_name, commodity, cci,
                 pct_good_excellent, pct_poor_very_poor, cci_signal.
    """
    if condition_df.empty:
        return pd.DataFrame()

    def _ge(x):
        labels = condition_df.loc[x.index, "condition_label"]
        return x[labels.isin(["GOOD", "EXCELLENT"])].sum()

    def _pw(x):
        labels = condition_df.loc[x.index, "condition_label"]
        return x[labels.isin(["POOR", "VERY POOR"])].sum()

    cci = (
        condition_df
        .groupby(["week_ending", "state_name", "commodity"])
        .agg(
            cci                = ("cci_contribution",  "sum"),
            pct_good_excellent = ("pct_value",         _ge),
            pct_poor_very_poor = ("pct_value",         _pw),
        )
        .reset_index()
    )

    cci["cci_signal"] = np.select(
        [cci["cci"] >= 65, cci["cci"] <= 45],
        ["BULLISH", "BEARISH"],
        default="NEUTRAL",
    )

    return cci.sort_values("week_ending").reset_index(drop=True)


def calculate_planting_pace_score(
    progress_df: pd.DataFrame,
    commodity_key: str = "soybean",
    reference_week: int = 20,
) -> pd.DataFrame:
    """
    Compare current planting pace to the 5-year average benchmark.

    Returns
    -------
    pd.DataFrame
        Columns: state_name, week_ending, pct_planted, benchmark_pct,
                 pace_delta, pace_flag.
    """
    if progress_df.empty:
        return pd.DataFrame()

    df = progress_df.copy()
    df["iso_week"] = df["week_ending"].dt.isocalendar().week.astype(int)
    bench = PLANTING_PACE_BENCHMARKS.get(commodity_key, {})

    window = df[df["iso_week"].between(reference_week - 1, reference_week + 1)]
    if window.empty:
        window = df

    rows = []
    for state, grp in window.groupby("state_name"):
        latest    = grp.sort_values("week_ending").iloc[-1]
        benchmark = bench.get(state, 50)
        delta     = latest["pct_value"] - benchmark
        flag = np.select(
            [delta >= 10, delta >= -5, delta >= -15],
            ["AHEAD", "ON TRACK", "BEHIND"],
            default="SEVERELY BEHIND",
        )
        rows.append({
            "state_name":   state,
            "week_ending":  latest["week_ending"],
            "pct_planted":  latest["pct_value"],
            "benchmark_pct": benchmark,
            "pace_delta":   round(float(delta), 1),
            "pace_flag":    str(flag),
        })

    return pd.DataFrame(rows).sort_values("pace_delta").reset_index(drop=True)


def get_latest_condition_snapshot(condition_df: pd.DataFrame) -> dict:
    """Return the most recent week's condition as a summary dict."""
    if condition_df.empty:
        return {"cci": None, "cci_signal": "N/A", "week_ending": None,
                "pct_good_excellent": 0, "pct_poor_very_poor": 0, "top_condition": "N/A"}

    latest_wk = condition_df["week_ending"].max()
    latest    = condition_df[condition_df["week_ending"] == latest_wk]

    cci_val   = (latest["pct_value"] * latest["cci_weight"] / 100).sum()
    pct_ge    = latest[latest["condition_label"].isin(["GOOD","EXCELLENT"])]["pct_value"].sum()
    pct_pw    = latest[latest["condition_label"].isin(["POOR","VERY POOR"])]["pct_value"].sum()
    top_cond  = latest.sort_values("pct_value", ascending=False).iloc[0]["condition_label"]
    signal    = "BULLISH" if cci_val >= 65 else ("BEARISH" if cci_val <= 45 else "NEUTRAL")

    return {
        "week_ending":        latest_wk,
        "cci":                round(float(cci_val), 1),
        "pct_good_excellent": round(float(pct_ge), 1),
        "pct_poor_very_poor": round(float(pct_pw), 1),
        "cci_signal":         signal,
        "top_condition":      top_cond,
    }


# ---------------------------------------------------------------------------
# Demo data generator (no API key required)
# ---------------------------------------------------------------------------

def get_demo_crop_progress(
    commodity_key: str = "soybean",
    state: str = "IOWA",
    year: int = 2025,
) -> dict:
    """
    Generate realistic simulated crop progress data for dashboard demo mode.

    Returns
    -------
    dict
        Keys: 'progress' (pd.DataFrame), 'condition' (pd.DataFrame), 'cci' (pd.DataFrame).
    """
    weeks = pd.date_range(f"{year}-04-14", periods=20, freq="7D")
    x     = np.arange(20)

    planted_pcts  = np.clip(100 / (1 + np.exp(-0.6 * (x - 6))),  0, 100).round(1)
    emerged_pcts  = np.clip(planted_pcts - 12, 0, 100).round(1)
    blooming_pcts = np.clip(100 / (1 + np.exp(-0.7 * (x - 12))), 0, 100).round(1)

    progress_rows = []
    for i, w in enumerate(weeks):
        for unit, vals in [
            ("PCT PLANTED",  planted_pcts),
            ("PCT EMERGED",  emerged_pcts),
            ("PCT BLOOMING", blooming_pcts),
        ]:
            progress_rows.append({
                "week_ending": w,
                "state_name":  state,
                "commodity":   commodity_key.upper() + "S",
                "unit_desc":   unit,
                "pct_value":   float(vals[i]),
            })

    progress_df = pd.DataFrame(progress_rows)

    rng        = np.random.default_rng(42)
    base_cci   = 62 + 8 * np.sin(np.linspace(0, np.pi, 20))
    cond_rows  = []

    for i, w in enumerate(weeks):
        exc  = int(np.clip(base_cci[i] * 0.25 + rng.normal(0, 2), 5, 30))
        good = int(np.clip(base_cci[i] * 0.55 + rng.normal(0, 3), 30, 55))
        fair = int(np.clip(100 - exc - good - 10, 8, 35))
        poor = int(np.clip(100 - exc - good - fair - 3, 2, 15))
        vp   = max(0, 100 - exc - good - fair - poor)

        for label, pct, wt in [
            ("EXCELLENT", exc,  100),
            ("GOOD",      good, 75),
            ("FAIR",      fair, 50),
            ("POOR",      poor, 25),
            ("VERY POOR", vp,   0),
        ]:
            cond_rows.append({
                "week_ending":     w,
                "state_name":      state,
                "commodity":       commodity_key.upper() + "S",
                "condition_label": label,
                "pct_value":       float(pct),
                "cci_weight":      wt,
                "cci_contribution": pct * wt / 100,
            })

    condition_df = pd.DataFrame(cond_rows)
    cci_df       = calculate_crop_condition_index(condition_df)

    return {"progress": progress_df, "condition": condition_df, "cci": cci_df}


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "=" * 56)
    print("  Crop Progress Module Test")
    print("=" * 56)

    demo = get_demo_crop_progress("soybean", "IOWA", 2025)
    snap = get_latest_condition_snapshot(demo["condition"])

    print("\nDemo progress (last 4 weeks — PCT PLANTED):")
    planted = demo["progress"][demo["progress"]["unit_desc"] == "PCT PLANTED"]
    print(planted[["week_ending","pct_value"]].tail(4).to_string(index=False))

    print("\nDemo CCI (last 4 weeks):")
    print(demo["cci"][["week_ending","cci","cci_signal"]].tail(4).to_string(index=False))

    print("\nLatest snapshot:")
    for k, v in snap.items():
        print(f"  {k}: {v}")

    if os.getenv("USDA_API_KEY"):
        print("\nLive data test (Iowa soybeans 2024):")
        df = fetch_crop_progress("SOYBEANS", "IOWA", 2024, "PCT PLANTED")
        print(f"  Retrieved {len(df)} weekly records")
        print(df.tail(4).to_string(index=False))
    else:
        print("\nAdd USDA_API_KEY to .env to test live data fetch.")

    print("\n" + "=" * 56 + "\n")
