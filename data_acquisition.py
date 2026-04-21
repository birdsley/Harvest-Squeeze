"""
data_acquisition.py
--------------------
Data Acquisition Engine for The Harvest Squeeze dashboard.

Handles all external data fetching:
  - USDA NASS QuickStats  → County-level soybean/corn yield estimates
  - FRED (St. Louis Fed)  → Nitrogenous Fertilizer PPI index
  - EIA                   → Weekly No. 2 Diesel Retail Prices
  - US Census TIGER       → County boundary shapefiles (for centroids)
  - GEE (Google Earth Engine) → MODIS NDVI + NASA SMAP soil moisture

All functions return clean pandas DataFrames or scalar floats.
API keys are loaded from environment variables via python-dotenv.
"""

import os
import time
import logging
import warnings
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np
import requests
from dotenv import load_dotenv

# Suppress geopandas/fiona warnings in non-interactive mode
warnings.filterwarnings("ignore", category=UserWarning)

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

from config import API, VC


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_env(key: str, required: bool = True) -> str:
    """Retrieve an environment variable with a descriptive error on failure."""
    val = os.getenv(key, "")
    if not val and required:
        raise EnvironmentError(
            f"Missing required env var: {key}. "
            f"Add it to your .env file (see .env.example)."
        )
    return val


def _safe_get(url: str, params: dict, timeout: int = 20, retries: int = 3) -> dict:
    """
    Robust HTTP GET with retry/back-off logic.

    Parameters
    ----------
    url : str
        Request URL.
    params : dict
        Query parameters.
    timeout : int
        Seconds before timeout per attempt.
    retries : int
        Max retry attempts.

    Returns
    -------
    dict
        Parsed JSON response.

    Raises
    ------
    requests.HTTPError
        If all retries fail.
    """
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            logger.warning("Timeout on attempt %d/%d: %s", attempt, retries, url)
            if attempt < retries:
                time.sleep(2 ** attempt)
        except requests.exceptions.HTTPError as exc:
            logger.error("HTTP error %s: %s", exc.response.status_code, url)
            raise
    raise requests.exceptions.Timeout(f"All {retries} retries failed for {url}")


# ---------------------------------------------------------------------------
# USDA NASS QuickStats
# ---------------------------------------------------------------------------

def fetch_usda_soybean_yields(
    state_name: str = "IOWA",
    year: int = 2023,
    county_fips: Optional[str] = None,
) -> pd.DataFrame:
    """
    Fetch county-level soybean yield estimates from USDA NASS QuickStats.

    Parameters
    ----------
    state_name : str
        Full state name in UPPERCASE (e.g., 'IOWA', 'ILLINOIS').
    year : int
        Survey/estimate year. Use most recent finalized year (2023).
    county_fips : str, optional
        If provided, filter to a single county FIPS code.

    Returns
    -------
    pd.DataFrame
        Columns: fips_code, state_name, county_name, yield_bu_acre, year
    """
    api_key = _get_env("USDA_API_KEY")
    params = {
        "key": api_key,
        "commodity_desc": API.usda_commodity_soy,
        "statisticcat_desc": API.usda_stat_cat_yield,
        "unit_desc": "BU / ACRE",
        "agg_level_desc": API.usda_agg_level,
        "state_name": state_name,
        "year": year,
        "format": "JSON",
    }
    if county_fips:
        params["county_code"] = county_fips[-3:]  # QuickStats uses 3-digit county code

    logger.info("Fetching USDA soybean yields: state=%s, year=%d", state_name, year)
    data = _safe_get(API.usda_base_url, params)

    if "data" not in data or not data["data"]:
        logger.warning("No yield data returned for state=%s, year=%d", state_name, year)
        return pd.DataFrame()

    df = pd.DataFrame(data["data"])

    # Keep only SURVEY records (not forecasts) and clean up
    df = df[df["source_desc"] == "SURVEY"].copy()
    df["yield_bu_acre"] = pd.to_numeric(df["Value"].str.replace(",", ""), errors="coerce")
    df["fips_code"] = df["state_fips_code"].str.zfill(2) + df["county_code"].str.zfill(3)
    df["year"] = df["year"].astype(int)

    output = df[["fips_code", "state_name", "county_name", "yield_bu_acre", "year"]].copy()
    output = output.dropna(subset=["yield_bu_acre", "fips_code"])
    output = output[output["fips_code"].str.match(r"^\d{5}$")]  # Drop 'OTHER' rows

    logger.info("Retrieved %d county yield records for %s", len(output), state_name)
    return output.reset_index(drop=True)


def fetch_usda_corn_yields(
    state_name: str = "IOWA",
    year: int = 2023,
) -> pd.DataFrame:
    """
    Fetch county-level corn yield estimates from USDA NASS QuickStats.

    Parameters
    ----------
    state_name : str
        Full state name in UPPERCASE.
    year : int
        Survey/estimate year.

    Returns
    -------
    pd.DataFrame
        Columns: fips_code, state_name, county_name, yield_bu_acre, year
    """
    api_key = _get_env("USDA_API_KEY")
    params = {
        "key": api_key,
        "commodity_desc": API.usda_commodity_corn,
        "statisticcat_desc": API.usda_stat_cat_yield,
        "unit_desc": "BU / ACRE",
        "agg_level_desc": API.usda_agg_level,
        "state_name": state_name,
        "year": year,
        "format": "JSON",
    }

    logger.info("Fetching USDA corn yields: state=%s, year=%d", state_name, year)
    data = _safe_get(API.usda_base_url, params)

    if "data" not in data or not data["data"]:
        return pd.DataFrame()

    df = pd.DataFrame(data["data"])
    df = df[df["source_desc"] == "SURVEY"].copy()
    df["yield_bu_acre"] = pd.to_numeric(df["Value"].str.replace(",", ""), errors="coerce")
    df["fips_code"] = df["state_fips_code"].str.zfill(2) + df["county_code"].str.zfill(3)
    df["year"] = df["year"].astype(int)

    output = df[["fips_code", "state_name", "county_name", "yield_bu_acre", "year"]].copy()
    output = output.dropna(subset=["yield_bu_acre", "fips_code"])
    output = output[output["fips_code"].str.match(r"^\d{5}$")]

    logger.info("Retrieved %d county corn yield records for %s", len(output), state_name)
    return output.reset_index(drop=True)


def fetch_usda_planted_acres(
    state_name: str = "IOWA",
    commodity: str = "SOYBEANS",
    year: int = 2023,
) -> pd.DataFrame:
    """
    Fetch county-level planted acres from USDA NASS QuickStats.

    Returns
    -------
    pd.DataFrame
        Columns: fips_code, planted_acres
    """
    api_key = _get_env("USDA_API_KEY")
    params = {
        "key": api_key,
        "commodity_desc": commodity,
        "statisticcat_desc": "AREA PLANTED",
        "unit_desc": "ACRES",
        "agg_level_desc": API.usda_agg_level,
        "state_name": state_name,
        "year": year,
        "format": "JSON",
    }

    logger.info("Fetching planted acres: %s, %s, %d", commodity, state_name, year)
    data = _safe_get(API.usda_base_url, params)

    if "data" not in data or not data["data"]:
        return pd.DataFrame()

    df = pd.DataFrame(data["data"])
    df = df[df["source_desc"].isin(["SURVEY", "CENSUS"])].copy()
    df["planted_acres"] = pd.to_numeric(df["Value"].str.replace(",", ""), errors="coerce")
    df["fips_code"] = df["state_fips_code"].str.zfill(2) + df["county_code"].str.zfill(3)

    output = df[["fips_code", "planted_acres"]].dropna().copy()
    output = output[output["fips_code"].str.match(r"^\d{5}$")]
    return output.reset_index(drop=True)


# ---------------------------------------------------------------------------
# FRED API (Federal Reserve Economic Data)
# ---------------------------------------------------------------------------

def fetch_fred_series(
    series_id: str,
    observation_start: str = "2023-01-01",
    latest_only: bool = True,
) -> pd.DataFrame | float:
    """
    Fetch a FRED data series.

    Parameters
    ----------
    series_id : str
        FRED series identifier (e.g., 'PCU3253113253111').
    observation_start : str
        ISO date string for start of observations.
    latest_only : bool
        If True, return only the latest non-null scalar value.

    Returns
    -------
    float | pd.DataFrame
        Latest value (if latest_only=True) or full time-series DataFrame.
    """
    api_key = _get_env("FRED_API_KEY")
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "observation_start": observation_start,
        "file_type": "json",
        "sort_order": "desc",
    }

    logger.info("Fetching FRED series: %s", series_id)
    data = _safe_get(API.fred_base_url, params)

    observations = data.get("observations", [])
    if not observations:
        logger.warning("No observations returned for FRED series: %s", series_id)
        return np.nan if latest_only else pd.DataFrame()

    df = pd.DataFrame(observations)
    df["value"] = pd.to_numeric(df["value"].replace(".", np.nan), errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["value"]).sort_values("date", ascending=False)

    if latest_only:
        latest = df.iloc[0]
        logger.info(
            "FRED %s: latest value = %.2f on %s",
            series_id, latest["value"], latest["date"].date(),
        )
        return float(latest["value"])

    return df[["date", "value"]].reset_index(drop=True)


def fetch_fred_fertilizer_ppi() -> float:
    """
    Fetch the latest Nitrogenous Fertilizer Producer Price Index from FRED.

    Series: PCU3253113253111 (PPI by NAICS: Nitrogenous fertilizer manufacturing)
    Base: Dec 1984 = 100

    Returns
    -------
    float
        Latest PPI index value.
    """
    ppi = fetch_fred_series(API.fred_series_fertilizer, latest_only=True)
    if np.isnan(ppi):
        # Fallback to broader fertilizer PPI series
        logger.warning("Primary fertilizer PPI unavailable, using fallback series %s", API.fred_series_fertilizer_alt)
        ppi = fetch_fred_series(API.fred_series_fertilizer_alt, latest_only=True)
    return ppi


def fetch_fred_fertilizer_history(months: int = 24) -> pd.DataFrame:
    """
    Fetch the trailing N months of fertilizer PPI for trend charting.

    Returns
    -------
    pd.DataFrame
        Columns: date, value (PPI index)
    """
    start = pd.Timestamp.now() - pd.DateOffset(months=months)
    return fetch_fred_series(
        API.fred_series_fertilizer,
        observation_start=start.strftime("%Y-%m-%d"),
        latest_only=False,
    )


# ---------------------------------------------------------------------------
# EIA API (Energy Information Administration)
# ---------------------------------------------------------------------------

def fetch_eia_diesel_price() -> float:
    """
    Fetch the latest weekly U.S. No. 2 Diesel Retail Price ($/gallon) from EIA.

    Uses EIA API v2 endpoint. Series: EMD_EPD2D_PTE_NUS_DPG.

    Returns
    -------
    float
        Most recent weekly diesel retail price in $/gallon.
    """
    api_key = _get_env("EIA_API_KEY")

    url = API.eia_base_url
    params = {
        "api_key": api_key,
        "frequency": "weekly",
        "data[0]": "value",
        "facets[series][]": API.eia_series_diesel,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 5,
        "offset": 0,
    }

    logger.info("Fetching EIA diesel price: series=%s", API.eia_series_diesel)
    try:
        data = _safe_get(url, params)
        records = data.get("response", {}).get("data", [])
        if not records:
            raise ValueError("Empty EIA response")
        latest = records[0]
        price = float(latest["value"])
        logger.info("EIA Diesel: $%.3f/gal (period: %s)", price, latest.get("period"))
        return price
    except Exception as exc:
        logger.error("EIA fetch failed: %s. Using reference price.", exc)
        from config import LOGISTICS
        return LOGISTICS.diesel_reference_price


def fetch_eia_diesel_history(weeks: int = 52) -> pd.DataFrame:
    """
    Fetch trailing N weeks of diesel price history for trend charting.

    Returns
    -------
    pd.DataFrame
        Columns: period (date), value ($/gallon)
    """
    api_key = _get_env("EIA_API_KEY")
    params = {
        "api_key": api_key,
        "frequency": "weekly",
        "data[0]": "value",
        "facets[series][]": API.eia_series_diesel,
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": weeks,
        "offset": 0,
    }

    data = _safe_get(API.eia_base_url, params)
    records = data.get("response", {}).get("data", [])
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["period"] = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df[["period", "value"]].dropna().sort_values("period").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Value Chain Facility Data (from USSoyValueChain.xlsx)
# ---------------------------------------------------------------------------

def load_value_chain_facilities(xlsx_path: str = None) -> dict[str, pd.DataFrame]:
    """
    Load and classify facility data from the EIA/NOPA Value Chain XLSX.

    Reads the 'Value Chain' sheet and segments facilities into:
      - crushers: NOPA soybean processors
      - export_terminals: River/ocean export facilities
      - biodiesel_plants: Biodiesel + renewable diesel facilities

    Parameters
    ----------
    xlsx_path : str, optional
        Path to the XLSX file. Defaults to VC.xlsx_path from config.

    Returns
    -------
    dict[str, pd.DataFrame]
        Keys: 'crushers', 'export_terminals', 'biodiesel_plants', 'all'
    """
    path = xlsx_path or VC.xlsx_path
    logger.info("Loading value chain data from: %s", path)

    df = pd.read_excel(path, sheet_name=VC.sheet_value_chain)

    # Standardize lat/lon columns
    df = df.rename(columns={VC.lat_col: "lat", VC.lon_col: "lon"})
    df = df.dropna(subset=["lat", "lon"])
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])

    crushers = df[df[VC.type_col].isin(VC.crusher_types)].copy()
    export_terminals = df[df[VC.type_col].isin(VC.export_terminal_types)].copy()
    biodiesel = df[df[VC.type_col].isin(VC.biodiesel_types)].copy()

    logger.info(
        "Loaded: %d crushers | %d export terminals | %d biodiesel plants",
        len(crushers), len(export_terminals), len(biodiesel),
    )

    return {
        "crushers": crushers.reset_index(drop=True),
        "export_terminals": export_terminals.reset_index(drop=True),
        "biodiesel_plants": biodiesel.reset_index(drop=True),
        "all": df.reset_index(drop=True),
    }


def load_meal_consumption_demand() -> pd.DataFrame:
    """
    Load soybean meal consumption demand-side data (livestock operations).

    Returns
    -------
    pd.DataFrame
        Columns: Type, Name, lat, lon, State, County, Type2 (meal consumption type)
    """
    xlsx_path = VC.xlsx_path
    logger.info("Loading meal consumption data from: %s", xlsx_path)

    df = pd.read_excel(xlsx_path, sheet_name=VC.sheet_meal_consumption)
    df = df.rename(columns={VC.lat_col: "lat", VC.lon_col: "lon"})
    df = df.dropna(subset=["lat", "lon"])
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])

    logger.info("Loaded %d meal consumption facility records", len(df))
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Google Earth Engine (GEE) — NDVI + SMAP Soil Moisture
# ---------------------------------------------------------------------------

def fetch_gee_ndvi_by_county(
    county_fips_list: list[str],
    county_centroids: pd.DataFrame,
    year: int = 2025,
    month_start: int = 6,
    month_end: int = 8,
    scale_m: int = 1000,
) -> pd.DataFrame:
    """
    Fetch MODIS NDVI (Terra MOD13A2) growing-season mean for each county.

    Uses a 1km buffer around county centroids to sample NDVI values.
    GEE authentication must be completed prior to calling this function
    via `ee.Authenticate()` and `ee.Initialize()`.

    Parameters
    ----------
    county_fips_list : list[str]
        List of 5-digit FIPS codes to retrieve NDVI for.
    county_centroids : pd.DataFrame
        Must contain columns: fips_code, lat, lon.
    year : int
        Growing season year (June–August window).
    month_start : int
        Start month of NDVI averaging window (1-indexed).
    month_end : int
        End month of NDVI averaging window (inclusive).
    scale_m : int
        Pixel scale for GEE reduceRegion (meters).

    Returns
    -------
    pd.DataFrame
        Columns: fips_code, ndvi_mean, ndvi_z_score
    """
    try:
        import ee
    except ImportError:
        logger.error("earthengine-api not installed. Run: pip install earthengine-api")
        return pd.DataFrame(columns=["fips_code", "ndvi_mean", "ndvi_z_score"])

    try:
        ee.Initialize(opt_url="https://earthengine.googleapis.com")
    except Exception as exc:
        logger.error("GEE initialization failed: %s", exc)
        return pd.DataFrame(columns=["fips_code", "ndvi_mean", "ndvi_z_score"])

    logger.info(
        "Fetching GEE NDVI for %d counties, year=%d, months %d-%d",
        len(county_fips_list), year, month_start, month_end,
    )

    collection = (
        ee.ImageCollection(API.gee_ndvi_collection)
        .filterDate(
            f"{year}-{month_start:02d}-01",
            f"{year}-{month_end:02d}-30",
        )
        .select("NDVI")
    )

    results = []
    centroid_lookup = county_centroids.set_index("fips_code")

    for fips in county_fips_list:
        if fips not in centroid_lookup.index:
            continue
        row = centroid_lookup.loc[fips]
        point = ee.Geometry.Point([row["lon"], row["lat"]])
        buffer = point.buffer(15000)  # 15km buffer to capture county area

        try:
            ndvi_img = collection.mean()
            stats = ndvi_img.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=buffer,
                scale=scale_m,
                maxPixels=1e9,
            ).getInfo()
            ndvi_raw = stats.get("NDVI", None)
            if ndvi_raw is not None:
                ndvi_scaled = ndvi_raw * 0.0001  # MODIS scale factor
                results.append({"fips_code": fips, "ndvi_mean": ndvi_scaled})
        except Exception as exc:
            logger.warning("GEE NDVI failed for FIPS %s: %s", fips, exc)

    if not results:
        return pd.DataFrame(columns=["fips_code", "ndvi_mean", "ndvi_z_score"])

    df = pd.DataFrame(results)
    # Compute Z-score relative to the sampled set
    df["ndvi_z_score"] = (df["ndvi_mean"] - df["ndvi_mean"].mean()) / df["ndvi_mean"].std()

    logger.info("GEE NDVI retrieved for %d / %d counties", len(df), len(county_fips_list))
    return df


def fetch_gee_smap_soil_moisture(
    county_fips_list: list[str],
    county_centroids: pd.DataFrame,
    year: int = 2025,
    month: int = 7,
) -> pd.DataFrame:
    """
    Fetch NASA SMAP 10km root-zone soil moisture (ssm) for county centroids.

    Parameters
    ----------
    county_fips_list : list[str]
        5-digit FIPS codes.
    county_centroids : pd.DataFrame
        Must contain columns: fips_code, lat, lon.
    year : int
        Year for soil moisture query.
    month : int
        Month for soil moisture (peak season = July recommended).

    Returns
    -------
    pd.DataFrame
        Columns: fips_code, smap_ssm_mean (volumetric soil moisture m³/m³)
    """
    try:
        import ee
    except ImportError:
        logger.error("earthengine-api not installed.")
        return pd.DataFrame(columns=["fips_code", "smap_ssm_mean"])

    try:
        ee.Initialize(opt_url="https://earthengine.googleapis.com")
    except Exception as exc:
        logger.error("GEE initialization failed: %s", exc)
        return pd.DataFrame(columns=["fips_code", "smap_ssm_mean"])

    logger.info("Fetching GEE SMAP soil moisture: year=%d, month=%d", year, month)

    smap = (
        ee.ImageCollection(API.gee_smap_collection)
        .filterDate(
            f"{year}-{month:02d}-01",
            f"{year}-{month:02d}-28",
        )
        .select("ssm")
        .mean()
    )

    centroid_lookup = county_centroids.set_index("fips_code")
    results = []

    for fips in county_fips_list:
        if fips not in centroid_lookup.index:
            continue
        row = centroid_lookup.loc[fips]
        point = ee.Geometry.Point([row["lon"], row["lat"]])
        buffer = point.buffer(10000)

        try:
            stats = smap.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=buffer,
                scale=10000,
                maxPixels=1e9,
            ).getInfo()
            ssm = stats.get("ssm", None)
            if ssm is not None:
                results.append({"fips_code": fips, "smap_ssm_mean": float(ssm)})
        except Exception as exc:
            logger.warning("GEE SMAP failed for FIPS %s: %s", fips, exc)

    if not results:
        return pd.DataFrame(columns=["fips_code", "smap_ssm_mean"])

    df = pd.DataFrame(results)
    logger.info("GEE SMAP retrieved for %d / %d counties", len(df), len(county_fips_list))
    return df


# ---------------------------------------------------------------------------
# County Geometry (Census TIGER)
# ---------------------------------------------------------------------------

def load_county_centroids(
    cache_path: str = "data/cache/county_centroids.parquet",
    conus_only: bool = True,
) -> pd.DataFrame:
    """
    Load US county centroids from Census TIGER shapefiles.

    Caches the result as a parquet file for fast subsequent loads.

    Parameters
    ----------
    cache_path : str
        Local path for the cached parquet file.
    conus_only : bool
        If True, exclude Alaska, Hawaii, and territories.

    Returns
    -------
    pd.DataFrame
        Columns: fips_code, county_name, state_fips, lat, lon
    """
    cache = Path(cache_path)
    if cache.exists():
        logger.info("Loading county centroids from cache: %s", cache_path)
        return pd.read_parquet(cache_path)

    logger.info("Downloading Census TIGER county data (first-run only)...")
    try:
        import geopandas as gpd
    except ImportError:
        raise ImportError("geopandas required. Run: pip install geopandas")

    cache.parent.mkdir(parents=True, exist_ok=True)

    gdf = gpd.read_file(API.census_counties_url)
    gdf = gdf.to_crs(epsg=4326)
    gdf["centroid"] = gdf.geometry.centroid
    gdf["lat"] = gdf["centroid"].y
    gdf["lon"] = gdf["centroid"].x
    gdf["fips_code"] = gdf["STATEFP"].str.zfill(2) + gdf["COUNTYFP"].str.zfill(3)
    gdf["state_fips"] = gdf["STATEFP"]
    gdf["county_name"] = gdf["NAME"]

    df = gdf[["fips_code", "county_name", "state_fips", "lat", "lon"]].copy()

    if conus_only:
        # Exclude non-CONUS state FIPS codes
        exclude = {"02", "15", "60", "66", "69", "72", "78"}
        df = df[~df["state_fips"].isin(exclude)]

    df = df.dropna().reset_index(drop=True)
    df.to_parquet(cache_path, index=False)
    logger.info("Saved %d county centroids to cache: %s", len(df), cache_path)
    return df


# ---------------------------------------------------------------------------
# Master Acquisition Function
# ---------------------------------------------------------------------------

def acquire_all_data(
    state: str = "IOWA",
    year: int = 2023,
    use_gee: bool = False,
    xlsx_path: str = None,
) -> dict:
    """
    Master orchestration function — fetch all data sources in one call.

    Parameters
    ----------
    state : str
        State name for USDA yield queries.
    year : int
        Base yield year (most recent finalized USDA survey year).
    use_gee : bool
        Whether to attempt Google Earth Engine NDVI/SMAP retrieval.
    xlsx_path : str, optional
        Override path to USSoyValueChain.xlsx.

    Returns
    -------
    dict
        Keys:
          'soy_yields'        → pd.DataFrame (county yields)
          'corn_yields'       → pd.DataFrame (county yields)
          'fertilizer_ppi'    → float
          'diesel_price'      → float
          'facilities'        → dict (crushers, export_terminals, etc.)
          'county_centroids'  → pd.DataFrame
          'ndvi'              → pd.DataFrame (if use_gee=True)
          'smap'              → pd.DataFrame (if use_gee=True)
    """
    logger.info("=== Starting Harvest Squeeze Data Acquisition ===")
    logger.info("State: %s | Year: %d | GEE: %s", state, year, use_gee)

    result = {}

    # USDA yields
    result["soy_yields"] = fetch_usda_soybean_yields(state_name=state, year=year)
    result["corn_yields"] = fetch_usda_corn_yields(state_name=state, year=year)

    # Macro indices
    result["fertilizer_ppi"] = fetch_fred_fertilizer_ppi()
    result["diesel_price"] = fetch_eia_diesel_price()

    # Spatial facility data
    result["facilities"] = load_value_chain_facilities(xlsx_path=xlsx_path)

    # County centroids
    result["county_centroids"] = load_county_centroids()

    # Optional GEE satellite data
    if use_gee and not result["county_centroids"].empty:
        fips_list = result["soy_yields"]["fips_code"].tolist()
        centroids = result["county_centroids"]
        result["ndvi"] = fetch_gee_ndvi_by_county(fips_list, centroids, year=year)
        result["smap"] = fetch_gee_smap_soil_moisture(fips_list, centroids, year=year)
    else:
        result["ndvi"] = pd.DataFrame()
        result["smap"] = pd.DataFrame()

    logger.info("=== Data Acquisition Complete ===")
    logger.info(
        "Soy yields: %d counties | Corn yields: %d counties",
        len(result["soy_yields"]), len(result["corn_yields"]),
    )
    logger.info(
        "Fertilizer PPI: %.1f | Diesel: $%.3f/gal",
        result["fertilizer_ppi"], result["diesel_price"],
    )

    return result


# ---------------------------------------------------------------------------
# CLI Test Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  HARVEST SQUEEZE — Data Acquisition Test")
    print("=" * 60)

    # 1. Test facility XLSX load (no API key needed)
    try:
        facilities = load_value_chain_facilities()
        print(f"\n✅ Value Chain Facilities loaded:")
        print(f"   Crushers:         {len(facilities['crushers'])} facilities")
        print(f"   Export Terminals: {len(facilities['export_terminals'])} facilities")
        print(f"   Biodiesel Plants: {len(facilities['biodiesel_plants'])} facilities")
    except FileNotFoundError:
        print("\n⚠️  USSoyValueChain.xlsx not found in working directory.")
        print("   Place the file in the same directory as this script.")

    # 2. Test USDA API
    print("\n--- USDA QuickStats ---")
    try:
        soy = fetch_usda_soybean_yields("IOWA", 2023)
        print(f"✅ Iowa soybean yields: {len(soy)} counties | Sample:")
        print(soy.head(3).to_string(index=False))
    except EnvironmentError as e:
        print(f"⚠️  {e}")

    # 3. Test FRED API
    print("\n--- FRED Fertilizer PPI ---")
    try:
        ppi = fetch_fred_fertilizer_ppi()
        print(f"✅ Nitrogenous Fertilizer PPI: {ppi:.2f}")
    except EnvironmentError as e:
        print(f"⚠️  {e}")

    # 4. Test EIA API
    print("\n--- EIA Diesel Price ---")
    try:
        diesel = fetch_eia_diesel_price()
        print(f"✅ Weekly US No.2 Diesel: ${diesel:.3f}/gallon")
    except EnvironmentError as e:
        print(f"⚠️  {e}")

    # 5. Test county centroid cache
    print("\n--- Census County Centroids ---")
    try:
        centroids = load_county_centroids()
        print(f"✅ County centroids: {len(centroids)} CONUS counties")
        print(centroids.head(3).to_string(index=False))
    except Exception as e:
        print(f"⚠️  {e}")

    print("\n" + "=" * 60)
    print("  Test complete. See logs above for details.")
    print("=" * 60 + "\n")
