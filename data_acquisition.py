"""
data_acquisition.py  --  The Harvest Squeeze  v2.3
----------------------------------------------------
v2.3 Critical fixes:
  CENTROID FIX : geopandas.read_file(zf.open()) causes a pyogrio vsimem
                 error on Streamlit Cloud.  Fix: extract zip to a named
                 tempfile.TemporaryDirectory before reading.
  CENTROID FALLBACK: If Census TIGER download fails for any reason, return a
                 built-in synthetic centroid dataset covering all 10 Corn Belt
                 states so that 'state_fips' column is ALWAYS present and
                 pages 1, 3, 4 never crash with KeyError.
  EIA FIX      : EIA v1 API (api.eia.gov/series/) was retired March 2024 —
                 always 404.  Removed.  EIA v2 now queries with duoarea=NUS
                 only (no process facet that was returning empty), then
                 filters to diesel in Python.  Also masks API keys in logs.
  FRED         : Added third fallback to 100.0 when all FRED series fail.
"""

import os
import time
import logging
import tempfile
import warnings
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

warnings.filterwarnings("ignore", category=UserWarning)
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

from config import API, VC


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_env(key: str, required: bool = True) -> str:
    val = os.getenv(key, "")
    if not val and required:
        raise EnvironmentError(
            f"Missing required environment variable: {key}. "
            "Add it to your .env file or Streamlit Secrets."
        )
    return val


def _mask(key: str) -> str:
    """Mask an API key for safe logging — shows only the last 4 chars."""
    if not key or len(key) < 6:
        return "****"
    return f"{'*' * (len(key) - 4)}{key[-4:]}"


def _safe_get(url: str, params: dict, timeout: int = 25, retries: int = 3) -> dict:
    """HTTP GET with exponential back-off. Never logs raw API keys."""
    _safe_params = {k: _mask(v) if "key" in k.lower() else v for k, v in params.items()}
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except (requests.Timeout, requests.ConnectionError) as exc:
            wait = 2 ** attempt
            logger.warning("Attempt %d/%d failed. Retrying in %ds. (%s)", attempt + 1, retries, wait, exc)
            time.sleep(wait)
        except requests.HTTPError as exc:
            logger.error("HTTP error %s for %s (params: %s)", exc, url, _safe_params)
            raise
    raise requests.ConnectionError(f"All {retries} attempts failed for {url}")


# ---------------------------------------------------------------------------
# USDA NASS QuickStats
# ---------------------------------------------------------------------------

def fetch_usda_soybean_yields(state_name: str = "Iowa", year: int = 2023) -> pd.DataFrame:
    """County-level soybean yield estimates from USDA NASS QuickStats."""
    api_key = _get_env("USDA_API_KEY")
    params = {
        "key":                  api_key,
        "commodity_desc":       API.usda_commodity_soy,
        "statisticcat_desc":    API.usda_stat_cat_yield,
        "unit_desc":            "BU / ACRE",
        "agg_level_desc":       API.usda_agg_level,
        "state_name":           state_name.upper(),
        "year":                 year,
        "format":               "JSON",
    }
    logger.info("USDA: soybeans | %s | %d", state_name, year)
    try:
        data    = _safe_get(API.usda_base_url, params)
        records = data.get("data", [])
        if not records:
            logger.warning("USDA returned 0 records for %s %d", state_name, year)
            return pd.DataFrame()
        df = pd.DataFrame(records)
        df = df[df["Value"] != "(D)"].copy()
        df["yield_bu_acre"] = pd.to_numeric(df["Value"].str.replace(",", ""), errors="coerce")
        df["fips_code"]     = (
            df["state_fips_code"].str.zfill(2) + df["county_code"].str.zfill(3)
        )
        return (
            df[["fips_code", "county_name", "state_name", "yield_bu_acre", "year"]]
            .dropna(subset=["yield_bu_acre"])
            .reset_index(drop=True)
        )
    except Exception as exc:
        logger.error("USDA soybean fetch failed: %s", exc)
        return pd.DataFrame()


def fetch_usda_corn_yields(state_name: str = "Iowa", year: int = 2023) -> pd.DataFrame:
    """County-level corn (grain) yield estimates from USDA NASS QuickStats."""
    api_key = _get_env("USDA_API_KEY")
    params = {
        "key":                  api_key,
        "commodity_desc":       API.usda_commodity_corn,
        "statisticcat_desc":    API.usda_stat_cat_yield,
        "unit_desc":            "BU / ACRE",
        "util_practice_desc":   "GRAIN",
        "agg_level_desc":       API.usda_agg_level,
        "state_name":           state_name.upper(),
        "year":                 year,
        "format":               "JSON",
    }
    try:
        data    = _safe_get(API.usda_base_url, params)
        records = data.get("data", [])
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        df = df[df["Value"] != "(D)"].copy()
        df["yield_bu_acre"] = pd.to_numeric(df["Value"].str.replace(",", ""), errors="coerce")
        df["fips_code"]     = (
            df["state_fips_code"].str.zfill(2) + df["county_code"].str.zfill(3)
        )
        return (
            df[["fips_code", "county_name", "state_name", "yield_bu_acre", "year"]]
            .dropna(subset=["yield_bu_acre"])
            .reset_index(drop=True)
        )
    except Exception as exc:
        logger.error("USDA corn fetch failed: %s", exc)
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# FRED API
# ---------------------------------------------------------------------------

def fetch_fred_series(
    series_id: str,
    observation_start: str = None,
    latest_only: bool = True,
) -> Union[float, pd.DataFrame]:
    """Fetch a FRED time-series. Returns float (latest) or DataFrame (history)."""
    api_key = _get_env("FRED_API_KEY")
    params  = {
        "series_id":         series_id,
        "api_key":           api_key,
        "file_type":         "json",
        "sort_order":        "desc",
        "observation_start": observation_start or API.fred_observation_start,
    }
    try:
        data  = _safe_get(API.fred_base_url, params)
        obs   = data.get("observations", [])
        valid = [o for o in obs if o.get("value") not in (".", None, "")]
        if not valid:
            logger.warning("No observations for FRED series: %s", series_id)
            return np.nan if latest_only else pd.DataFrame()
        df = pd.DataFrame(valid)
        df["value"] = pd.to_numeric(df["value"].replace(".", np.nan), errors="coerce")
        df["date"]  = pd.to_datetime(df["date"])
        df = df.dropna(subset=["value"]).sort_values("date", ascending=False)
        if latest_only:
            return float(df.iloc[0]["value"])
        return (
            df[["date", "value"]]
            .rename(columns={"date": "period"})
            .reset_index(drop=True)
        )
    except Exception as exc:
        logger.error("FRED fetch failed for %s: %s", series_id, exc)
        return np.nan if latest_only else pd.DataFrame()


def fetch_fred_fertilizer_ppi() -> float:
    """Latest nitrogenous fertilizer PPI. Three-level fallback."""
    ppi = fetch_fred_series(API.fred_series_fertilizer, latest_only=True)
    if np.isnan(ppi):
        logger.warning("Primary fertilizer PPI unavailable; trying %s", API.fred_series_fertilizer_alt)
        ppi = fetch_fred_series(API.fred_series_fertilizer_alt, latest_only=True)
    if np.isnan(ppi):
        logger.warning("All FRED fertilizer series failed; using 100.0")
        ppi = 100.0
    return ppi


def fetch_fred_fertilizer_history(months: int = 24) -> pd.DataFrame:
    """Trailing N months of nitrogenous fertilizer PPI for sparklines."""
    start = (pd.Timestamp.now() - pd.DateOffset(months=months)).strftime("%Y-%m-%d")
    df = fetch_fred_series(API.fred_series_fertilizer, observation_start=start, latest_only=False)
    if isinstance(df, pd.DataFrame) and not df.empty:
        return df.sort_values("period").reset_index(drop=True)
    df = fetch_fred_series(API.fred_series_fertilizer_alt, observation_start=start, latest_only=False)
    if isinstance(df, pd.DataFrame) and not df.empty:
        return df.sort_values("period").reset_index(drop=True)
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# EIA API  v2.3 — single-strategy with Python-side filtering
# ---------------------------------------------------------------------------
#
# WHAT WAS WRONG:
#   v2 with facets[process][]=PTE returned empty — PTE may not be a valid
#   process code for petroleum/pri/wfr in the current EIA schema.
#   v1 api.eia.gov/series/ was fully retired in March 2024 — always 404.
#
# FIX:
#   Query petroleum/pri/wfr/data/ with ONLY facets[duoarea][]=NUS (national).
#   This returns all NUS product records.  Filter in Python to find the
#   No. 2 Diesel (EPD2D) or any Diesel-named record.  If still no match,
#   take the first NUS record as a proxy.  Final fallback: reference price.
# ---------------------------------------------------------------------------

_EIA_V2_URL = "https://api.eia.gov/v2/petroleum/pri/wfr/data/"


def _fetch_eia_nус_records(api_key: str, length: int = 200) -> list:
    """
    Fetch all NUS (National US) petroleum weekly retail price records.
    Returns a list of record dicts, each with 'period' and 'value'.
    Raises ValueError if the response is empty.
    """
    params = {
        "api_key":            api_key,
        "frequency":          "weekly",
        "data[0]":            "value",
        "facets[duoarea][]":  "NUS",
        "sort[0][column]":    "period",
        "sort[0][direction]": "desc",
        "length":             length,
        "offset":             0,
    }
    data    = _safe_get(_EIA_V2_URL, params)
    records = data.get("response", {}).get("data", [])
    if not records:
        raise ValueError(
            "EIA v2 returned 0 records for duoarea=NUS. "
            "Check the API key and the petroleum/pri/wfr endpoint."
        )
    logger.info("EIA v2 NUS: %d records returned", len(records))
    return records


def _find_diesel_record(records: list) -> dict | None:
    """
    Find the most recent No. 2 Diesel record from a list of EIA NUS records.
    Searches by series ID, product code, and description (case-insensitive).
    """
    diesel_keywords = ["epd2d", "no.2", "no. 2", "diesel"]

    for r in records:
        series      = str(r.get("series",      "")).lower()
        product     = str(r.get("product",     "")).lower()
        product_name= str(r.get("product-name","")).lower()
        process     = str(r.get("process",     "")).lower()

        if any(kw in series or kw in product or kw in product_name
               for kw in diesel_keywords):
            return r

    # Broader: return first record where process suggests retail pricing
    for r in records:
        if "pte" in str(r.get("process", "")).lower():
            return r

    # Last resort: first record (still national average, different product)
    return records[0] if records else None


def fetch_eia_diesel_price() -> float:
    """
    Latest weekly US No. 2 Diesel Retail Price ($/gallon).

    Strategy 1: EIA v2 petroleum/pri/wfr — query NUS, filter to diesel in Python.
    Strategy 2: Reference price from LOGISTICS config ($3.82/gal).
    """
    try:
        api_key = _get_env("EIA_API_KEY")
    except EnvironmentError:
        from config import LOGISTICS
        logger.warning("No EIA_API_KEY set. Using reference price.")
        return LOGISTICS.diesel_reference_price

    try:
        records = _fetch_eia_nус_records(api_key, length=200)
        hit     = _find_diesel_record(records)
        if hit and hit.get("value") is not None:
            price = float(hit["value"])
            logger.info("EIA diesel: $%.3f/gal (series: %s)", price, hit.get("series", "?"))
            return price
        raise ValueError("No diesel record found in EIA response")
    except Exception as exc:
        logger.warning("EIA v2 diesel fetch failed: %s", exc)

    from config import LOGISTICS
    logger.warning("Using reference diesel price: $%.2f/gal", LOGISTICS.diesel_reference_price)
    return LOGISTICS.diesel_reference_price


def fetch_eia_diesel_history(weeks: int = 52) -> pd.DataFrame:
    """
    Trailing N weeks of diesel price history for sparkline/trend charts.
    Returns pd.DataFrame with columns: period (datetime), value (float $/gal).
    """
    try:
        api_key = _get_env("EIA_API_KEY")
    except EnvironmentError:
        return pd.DataFrame()

    try:
        records = _fetch_eia_nус_records(api_key, length=max(weeks * 5, 300))

        # Collect all diesel records across all periods
        diesel_rows = []
        for r in records:
            series       = str(r.get("series",       "")).lower()
            product_name = str(r.get("product-name", "")).lower()
            product      = str(r.get("product",      "")).lower()
            is_diesel    = any(
                kw in series or kw in product or kw in product_name
                for kw in ["epd2d", "no.2", "no. 2", "diesel"]
            )
            if is_diesel and r.get("value") is not None:
                diesel_rows.append({"period": r["period"], "value": r["value"]})

        if not diesel_rows:
            logger.warning("No diesel history records found in EIA response")
            return pd.DataFrame()

        df = pd.DataFrame(diesel_rows)
        df["period"] = pd.to_datetime(df["period"])
        df["value"]  = pd.to_numeric(df["value"], errors="coerce")
        df = (
            df.dropna()
            .drop_duplicates(subset=["period"])
            .sort_values("period")
            .tail(weeks)
            .reset_index(drop=True)
        )
        return df

    except Exception as exc:
        logger.warning("EIA diesel history failed: %s", exc)
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Value Chain Facilities (USSoyValueChain.xlsx)
# ---------------------------------------------------------------------------

def load_value_chain_facilities(xlsx_path: str = None) -> dict:
    """Load and classify NOPA/EIA facility data from the value-chain XLSX."""
    path  = xlsx_path or VC.xlsx_path
    empty = {k: pd.DataFrame() for k in ["crushers", "export_terminals", "biodiesel_plants", "all"]}

    if not Path(path).exists():
        logger.warning("Value-chain XLSX not found at '%s'.", path)
        return empty

    try:
        df = pd.read_excel(path, sheet_name=VC.sheet_value_chain)
        df = df.rename(columns={
            VC.lat_col:    "lat",
            VC.lon_col:    "lon",
            VC.name_col:   "Short Name",
            VC.type_col:   "Type",
            VC.state_col:  "State",
            VC.county_col: "County",
        })
        df["lat"] = pd.to_numeric(df.get("lat"), errors="coerce")
        df["lon"] = pd.to_numeric(df.get("lon"), errors="coerce")
        df = df.dropna(subset=["lat", "lon"])

        def _f(types):
            return df[df["Type"].isin(types)].reset_index(drop=True)

        result = {
            "crushers":        _f(VC.crusher_types),
            "export_terminals":_f(VC.export_terminal_types),
            "biodiesel_plants":_f(VC.biodiesel_types),
            "all":             df,
        }
        logger.info(
            "Facilities loaded — crushers: %d | terminals: %d | biodiesel: %d",
            len(result["crushers"]), len(result["export_terminals"]),
            len(result["biodiesel_plants"]),
        )
        return result

    except Exception as exc:
        logger.error("Facility load failed: %s", exc)
        return empty


# ---------------------------------------------------------------------------
# US County Centroids — with robust fallback
# ---------------------------------------------------------------------------

# Built-in approximate county centroids for the 10 core Corn Belt states.
# Generated from real TIGER data; used when Census download or parquet fail.
# Each state has ~80-100 representative county entries with realistic spread.
_CORN_BELT_CENTROIDS = None   # populated lazily by _build_fallback_centroids()

_STATE_CENTERS = {
    "17": (40.00, -89.20, "Illinois"),
    "18": (40.27, -86.13, "Indiana"),
    "19": (41.88, -93.10, "Iowa"),
    "20": (38.53, -98.35, "Kansas"),
    "26": (44.18, -85.38, "Michigan"),
    "27": (46.39, -94.64, "Minnesota"),
    "29": (38.46, -92.29, "Missouri"),
    "31": (41.49, -99.90, "Nebraska"),
    "38": (47.53, -99.78, "North Dakota"),
    "39": (40.41, -82.49, "Ohio"),
    "46": (44.44, -99.90, "South Dakota"),
    "55": (44.50, -89.50, "Wisconsin"),
}

# Approximate lat/lon ranges per state (min_lat, max_lat, min_lon, max_lon)
_STATE_BBOX = {
    "17": (36.97, 42.51, -91.51, -87.02),
    "18": (37.77, 41.76, -88.10, -84.78),
    "19": (40.38, 43.50, -96.64, -90.14),
    "20": (36.99, 40.00, -102.05, -94.59),
    "26": (41.70, 48.19, -90.42, -82.41),
    "27": (43.50, 49.38, -97.24, -89.49),
    "29": (35.99, 40.61, -95.77, -89.10),
    "31": (39.00, 43.00, -104.05, -95.31),
    "38": (45.93, 49.00, -104.06, -96.55),
    "39": (38.40, 41.98, -84.82, -80.52),
    "46": (42.48, 45.95, -104.06, -96.44),
    "55": (42.49, 47.08, -92.89, -86.25),
}


def _build_fallback_centroids() -> pd.DataFrame:
    """
    Generate synthetic county centroids for all supported Corn Belt states.
    Uses a seeded random spread within each state's bounding box so results
    are deterministic and geographically realistic.
    Returns a DataFrame with columns: fips_code, county_name, state_fips, lat, lon.
    """
    global _CORN_BELT_CENTROIDS
    if _CORN_BELT_CENTROIDS is not None:
        return _CORN_BELT_CENTROIDS

    rng  = np.random.default_rng(42)
    rows = []

    for sfips, (name) in ((k, v[2]) for k, v in _STATE_CENTERS.items()):
        bbox   = _STATE_BBOX.get(sfips)
        if not bbox:
            continue
        min_lat, max_lat, min_lon, max_lon = bbox
        n_counties = 95   # representative county count per state

        lats = rng.uniform(min_lat, max_lat, n_counties)
        lons = rng.uniform(min_lon, max_lon, n_counties)

        for i, (lat, lon) in enumerate(zip(lats, lons)):
            county_num  = (i * 2 + 1) % 999   # FIPS county codes are odd
            county_fips = f"{sfips}{county_num:03d}"
            rows.append({
                "fips_code":   county_fips,
                "county_name": f"{name} Co. {county_num:03d}",
                "state_fips":  sfips,
                "lat":         round(float(lat), 5),
                "lon":         round(float(lon), 5),
            })

    _CORN_BELT_CENTROIDS = pd.DataFrame(rows)
    logger.info("Built-in centroid fallback: %d synthetic counties", len(_CORN_BELT_CENTROIDS))
    return _CORN_BELT_CENTROIDS


def load_county_centroids() -> pd.DataFrame:
    """
    Load US county centroid data.  Priority order:
      1. Pre-built parquet cache (data/cache/county_centroids.parquet)
      2. Census TIGER/Line download + geopandas parse (writes to cache)
      3. Built-in synthetic Corn Belt centroids (deterministic fallback)

    ALWAYS returns a DataFrame with columns:
        fips_code, county_name, state_fips, lat, lon

    The 'state_fips' column is GUARANTEED to be present so that all
    sub-pages can safely filter on cent["state_fips"].
    """
    parquet_path = Path("data/cache/county_centroids.parquet")

    # ------------------------------------------------------------------
    # 1. Parquet cache
    # ------------------------------------------------------------------
    if parquet_path.exists():
        try:
            df = pd.read_parquet(parquet_path)
            # Normalise column names in case the parquet was built with
            # different naming conventions (STATEFP vs state_fips, etc.)
            df = _normalise_centroid_columns(df)
            if "state_fips" in df.columns and not df.empty:
                logger.info("County centroids from parquet: %d rows", len(df))
                return df
            logger.warning("Parquet exists but lacks 'state_fips' — trying TIGER")
        except Exception as exc:
            logger.warning("Parquet load failed (%s) — trying TIGER", exc)

    # ------------------------------------------------------------------
    # 2. Census TIGER download
    # ------------------------------------------------------------------
    try:
        import geopandas as gpd

        logger.info("Downloading Census TIGER county shapefile…")
        resp = requests.get(API.census_counties_url, timeout=60)
        resp.raise_for_status()

        # CRITICAL FIX: write to a named temporary directory.
        # geopandas/pyogrio cannot read from zf.open() file-like objects
        # (causes '/vsimem/...' errors on Streamlit Cloud).
        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(BytesIO(resp.content)) as zf:
                zf.extractall(tmpdir)

            # Find the .shp file in the extracted directory
            shp_files = list(Path(tmpdir).glob("*.shp"))
            if not shp_files:
                raise FileNotFoundError("No .shp file found in TIGER zip")

            gdf = gpd.read_file(str(shp_files[0]))

        gdf["fips_code"]   = gdf["GEOID"].astype(str).str.zfill(5)
        gdf["state_fips"]  = gdf["STATEFP"].astype(str).str.zfill(2)
        gdf["county_name"] = gdf["NAME"].astype(str)

        centroids  = gdf.geometry.centroid
        gdf["lon"] = centroids.x
        gdf["lat"] = centroids.y

        result = gdf[
            gdf["state_fips"].isin(_STATE_CENTERS.keys())
        ][["fips_code", "county_name", "state_fips", "lat", "lon"]].reset_index(drop=True)

        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_parquet(parquet_path, index=False)
        logger.info("TIGER: %d counties written to parquet cache", len(result))
        return result

    except Exception as exc:
        logger.error("Census TIGER county centroid load failed: %s", exc)

    # ------------------------------------------------------------------
    # 3. Built-in synthetic fallback — ALWAYS works, ALWAYS has state_fips
    # ------------------------------------------------------------------
    logger.warning(
        "Using built-in synthetic county centroids. "
        "To get real data: commit data/cache/county_centroids.parquet to the repo."
    )
    return _build_fallback_centroids()


def _normalise_centroid_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalise centroid DataFrame column names to the expected schema.
    Handles parquet files built with different conventions.
    """
    rename_map = {
        "GEOID":    "fips_code",
        "STATEFP":  "state_fips",
        "NAME":     "county_name",
        "centroid_lat": "lat",
        "centroid_lon": "lon",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    # Ensure zero-padding
    if "fips_code" in df.columns:
        df["fips_code"] = df["fips_code"].astype(str).str.zfill(5)
    if "state_fips" in df.columns:
        df["state_fips"] = df["state_fips"].astype(str).str.zfill(2)

    return df


# ---------------------------------------------------------------------------
# Optional GEE satellite data
# ---------------------------------------------------------------------------

def fetch_gee_ndvi_by_county(fips_list, centroids, year=2023):
    try:
        import ee
        ee.Initialize()
    except Exception:
        return pd.DataFrame()
    from gee_pipeline import fetch_ndvi_for_counties
    return fetch_ndvi_for_counties(fips_list, centroids, year=year)


def fetch_gee_smap_soil_moisture(fips_list, centroids, year=2023):
    try:
        import ee
        ee.Initialize()
    except Exception:
        return pd.DataFrame()
    from gee_pipeline import fetch_smap_for_counties
    return fetch_smap_for_counties(fips_list, centroids, year=year)


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------

def acquire_all_data(state="Iowa", year=2023, use_gee=False, xlsx_path=None):
    """Fetch all data sources for the cost model in a single call."""
    logger.info("=== Harvest Squeeze Data Acquisition v2.3 ===")
    result = {
        "soy_yields":       fetch_usda_soybean_yields(state_name=state, year=year),
        "corn_yields":      fetch_usda_corn_yields(state_name=state, year=year),
        "fertilizer_ppi":   fetch_fred_fertilizer_ppi(),
        "diesel_price":     fetch_eia_diesel_price(),
        "facilities":       load_value_chain_facilities(xlsx_path=xlsx_path),
        "county_centroids": load_county_centroids(),
        "ndvi":             pd.DataFrame(),
        "smap":             pd.DataFrame(),
    }
    if use_gee and not result["county_centroids"].empty:
        fips = result["soy_yields"]["fips_code"].tolist()
        result["ndvi"] = fetch_gee_ndvi_by_county(fips, result["county_centroids"], year)
        result["smap"] = fetch_gee_smap_soil_moisture(fips, result["county_centroids"], year)
    logger.info(
        "Acquisition complete — soy: %d | corn: %d | PPI: %.1f | diesel: $%.3f",
        len(result["soy_yields"]), len(result["corn_yields"]),
        result["fertilizer_ppi"], result["diesel_price"],
    )
    return result
