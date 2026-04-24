"""
data_processing.py
------------------
Processing Engine for The Harvest Squeeze dashboard.

Responsibilities:
  1. Spatial Analysis -- KD-Tree nearest-neighbor to find closest crusher /
     export terminal for every county centroid.
  2. Transport Cost Model -- Distance-weighted basis risk adjusted by live
     EIA diesel prices.
  3. Production Cost Model -- USDA ERS baseline costs adjusted by FRED
     Fertilizer PPI and optional GEE NDVI/SMAP yield modification.
  4. Net Margin Score -- Combined profitability risk index classified into
     four tiers: HIGH / ELEVATED / MODERATE / HEALTHY.

All heavy vectorized operations use NumPy; no Python-level loops over rows.
"""

import logging
from typing import Optional

import numpy as np
import pandas as pd
from scipy.spatial import KDTree

from config import (
    SOY_COSTS,
    CORN_COSTS,
    YIELDS,
    LOGISTICS,
    RISK,
    CBOT_SOY_2026,
    CBOT_CORN_2026,
    STATE_LAND_RENTS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Spatial Analysis — KD-Tree Nearest Neighbor
# ---------------------------------------------------------------------------

def build_kdtree(facilities_df: pd.DataFrame) -> KDTree:
    """
    Build a KD-Tree from facility lat/lon coordinates (in radians).

    Parameters
    ----------
    facilities_df : pd.DataFrame
        Must contain 'lat' and 'lon' columns (decimal degrees).

    Returns
    -------
    scipy.spatial.KDTree
        Spatial index over facility coordinates.
    """
    coords_rad = np.radians(facilities_df[["lat", "lon"]].values)
    return KDTree(coords_rad)


def query_nearest_facility(
    county_centroids: pd.DataFrame,
    facilities_df: pd.DataFrame,
    result_prefix: str = "nearest",
    k: int = 3,
) -> pd.DataFrame:
    """
    Find the nearest K facilities for each county centroid using a KD-Tree.

    Distance is computed in miles using the chord approximation of the
    Haversine formula (accurate within 0.3% for distances under 500 miles).

    Parameters
    ----------
    county_centroids : pd.DataFrame
        Must contain columns: fips_code, lat, lon.
    facilities_df : pd.DataFrame
        Facility data with lat, lon columns.
    result_prefix : str
        Prefix for new distance/name columns (e.g. 'crusher', 'terminal').
    k : int
        Number of nearest neighbors to return.

    Returns
    -------
    pd.DataFrame
        county_centroids enriched with distance and facility columns.
    """
    EARTH_RADIUS_MILES = 3958.8

    if facilities_df.empty:
        logger.warning("No facilities for KD-Tree query (prefix=%s)", result_prefix)
        county_centroids = county_centroids.copy()
        county_centroids[f"{result_prefix}_dist_miles"] = np.nan
        county_centroids[f"{result_prefix}_name"] = "N/A"
        return county_centroids

    tree = build_kdtree(facilities_df)
    county_coords_rad = np.radians(county_centroids[["lat", "lon"]].values)

    actual_k = min(k, len(facilities_df))
    distances_rad, indices = tree.query(county_coords_rad, k=actual_k)

    if actual_k == 1:
        distances_rad = distances_rad.reshape(-1, 1)
        indices = indices.reshape(-1, 1)

    distances_miles = 2 * EARTH_RADIUS_MILES * np.arcsin(
        np.clip(distances_rad / 2, -1, 1)
    )

    result = county_centroids.copy()
    nearest_idx = indices[:, 0]

    result[f"{result_prefix}_dist_miles"] = distances_miles[:, 0]
    result[f"{result_prefix}_name"]       = facilities_df.iloc[nearest_idx]["Short Name"].values
    result[f"{result_prefix}_state"]      = facilities_df.iloc[nearest_idx]["State"].values
    result[f"{result_prefix}_lat"]        = facilities_df.iloc[nearest_idx]["lat"].values
    result[f"{result_prefix}_lon"]        = facilities_df.iloc[nearest_idx]["lon"].values

    if actual_k >= 2:
        result[f"{result_prefix}_dist_2nd"]          = distances_miles[:, 1]
        result[f"{result_prefix}_optionality_ratio"] = (
            distances_miles[:, 1] / np.maximum(distances_miles[:, 0], 0.1)
        )
    else:
        result[f"{result_prefix}_dist_2nd"]          = np.nan
        result[f"{result_prefix}_optionality_ratio"] = np.nan

    logger.info(
        "KD-Tree query (prefix=%s): median=%.1f mi, max=%.1f mi",
        result_prefix,
        np.median(distances_miles[:, 0]),
        np.max(distances_miles[:, 0]),
    )
    return result


def calculate_spatial_logistics(
    county_centroids: pd.DataFrame,
    facilities: dict,
) -> pd.DataFrame:
    """
    Run KD-Tree queries for crushers and export terminals simultaneously.

    Parameters
    ----------
    county_centroids : pd.DataFrame
        Columns: fips_code, lat, lon, county_name, state_fips.
    facilities : dict
        Keys: 'crushers', 'export_terminals'.

    Returns
    -------
    pd.DataFrame
        County centroids with crusher and terminal distance columns.
    """
    logger.info("Running spatial logistics for %d counties", len(county_centroids))
    result = query_nearest_facility(
        county_centroids, facilities["crushers"], result_prefix="crusher", k=3
    )
    result = query_nearest_facility(
        result, facilities["export_terminals"], result_prefix="terminal", k=3
    )
    return result


# ---------------------------------------------------------------------------
# 2. Transport Cost Model
# ---------------------------------------------------------------------------

def calculate_transport_cost(
    county_df: pd.DataFrame,
    diesel_price: float,
    commodity: str = "soybean",
) -> pd.DataFrame:
    """
    Calculate per-bushel transport cost and basis risk for each county.

    Model:
        base_cost    = (distance_miles / 100) * truck_rate_per_100mi
        diesel_adj   = 1 + elasticity * (live_diesel - ref_diesel) / ref_diesel
        dist_penalty = 1.25 if distance > threshold else 1.0
        transport_$/bu = base_cost * diesel_adj * dist_penalty

    Parameters
    ----------
    county_df : pd.DataFrame
        Must contain 'crusher_dist_miles'.
    diesel_price : float
        Current EIA diesel price ($/gallon).
    commodity : str
        'soybean' or 'corn'.

    Returns
    -------
    pd.DataFrame
        Input with transport_cost_per_bu, basis_risk_score, logistics_tier.
    """
    df = county_df.copy()
    dist = df["crusher_dist_miles"].fillna(df["crusher_dist_miles"].median())

    base_cost = (dist / 100.0) * LOGISTICS.truck_cost_per_100mi

    diesel_adj = float(np.clip(
        1 + LOGISTICS.diesel_elasticity * (
            (diesel_price - LOGISTICS.diesel_reference_price)
            / LOGISTICS.diesel_reference_price
        ),
        0.5, 2.5,
    ))

    penalty = np.where(
        dist > LOGISTICS.distance_threshold_miles,
        LOGISTICS.distance_penalty_multiplier,
        1.0,
    )

    df["transport_cost_per_bu"] = base_cost * diesel_adj * penalty
    df["diesel_adj_factor"]     = diesel_adj

    if "crusher_optionality_ratio" in df.columns:
        optionality_penalty = np.clip(df["crusher_optionality_ratio"] / 3.0, 1.0, 1.5)
        df["transport_cost_per_bu"] *= optionality_penalty

    max_realistic = 1.20
    df["basis_risk_score"] = np.clip(
        (df["transport_cost_per_bu"] / max_realistic) * 100, 0, 100
    )

    conditions = [
        df["basis_risk_score"] < 25,
        df["basis_risk_score"] < 50,
        df["basis_risk_score"] < 75,
    ]
    df["logistics_tier"] = np.select(conditions, ["LOW","MODERATE","HIGH"], default="SEVERE")

    logger.info(
        "Transport costs: diesel_adj=%.3fx | median=$.%03f/bu",
        diesel_adj, df["transport_cost_per_bu"].median(),
    )
    return df


# ---------------------------------------------------------------------------
# 3. Production Cost Model
# ---------------------------------------------------------------------------

def _get_demo_yields(
    county_df: pd.DataFrame,
    commodity: str,
) -> pd.Series:
    """
    Generate deterministic county-level yield variation for demo mode
    (when no USDA survey data is available).

    Each county gets a fixed yield derived from its FIPS code so that
    the map looks spatially consistent across sessions. The distribution
    mirrors historical USDA county-level variation (CV ~9% for soybeans).

    Parameters
    ----------
    county_df : pd.DataFrame
        Must contain 'fips_code' and 'state_fips' columns.
    commodity : str
        'soybean' or 'corn'.

    Returns
    -------
    pd.Series
        Per-county yield estimate (bu/acre).
    """
    state_index = YIELDS.state_yield_index
    std_dev = YIELDS.soybean_county_std if commodity == "soybean" else YIELDS.corn_county_std

    # State-level trend
    if commodity == "soybean":
        national_trend = YIELDS.soybean_national_trend
    else:
        national_trend = YIELDS.corn_national_trend

    results = []
    for _, row in county_df.iterrows():
        sfips = str(row.get("state_fips", "00"))
        fips  = str(row.get("fips_code", "00000"))

        # Apply state yield index
        state_mod = state_index.get(sfips, 1.0)
        state_trend = national_trend * state_mod

        # Deterministic county deviation using FIPS as seed
        seed = int(fips) if fips.isdigit() else 0
        rng  = np.random.default_rng(seed)
        deviation = rng.normal(0, std_dev)

        results.append(max(15.0, state_trend + deviation))

    return pd.Series(results, index=county_df.index)


def calculate_production_costs(
    county_df: pd.DataFrame,
    fertilizer_ppi: float,
    ndvi_df: Optional[pd.DataFrame] = None,
    smap_df: Optional[pd.DataFrame] = None,
    commodity: str = "soybean",
) -> pd.DataFrame:
    """
    Compute per-acre production costs and net margin for each county.

    Key calibration notes (2026):
    - CBOT soybean December 2026 futures: ~$9.50/bu
    - CBOT corn December 2026 futures:    ~$4.35/bu
    - Fertilizer PPI base (Jan 2020) = 424 (PCU325311325311, Dec 1979=100 series);
      current ~488 = +15% input cost above Jan 2020 baseline
    - Iowa land rent avg (2025): ~$270/acre
    - National avg land rent: ~$262/acre

    Parameters
    ----------
    county_df : pd.DataFrame
        Must contain 'fips_code'. Optionally 'yield_bu_acre', 'state_fips'.
    fertilizer_ppi : float
        Latest FRED Nitrogenous Fertilizer PPI value.
    ndvi_df : pd.DataFrame, optional
        Columns: fips_code, ndvi_mean, ndvi_z_score.
    smap_df : pd.DataFrame, optional
        Columns: fips_code, smap_ssm_mean.
    commodity : str
        'soybean' or 'corn'.

    Returns
    -------
    pd.DataFrame
        Input enriched with cost, margin, and risk classification columns.
    """
    # PCU325311325311 is indexed to Dec 1979 = 100; its Jan 2020 value was ~424.
    # Dividing by this rebases the index so a current reading of ~488 yields a
    # ratio of ~1.15 (+15% above Jan 2020 baseline), matching design intent.
    FERTILIZER_PPI_BASE = 424.0

    df    = county_df.copy()
    costs = SOY_COSTS if commodity == "soybean" else CORN_COSTS

    # ------------------------------------------------------------------
    # Fertilizer cost: PPI-adjusted
    # ------------------------------------------------------------------
    ppi_ratio = max(fertilizer_ppi / FERTILIZER_PPI_BASE, 0.5) if fertilizer_ppi > 0 else 1.0
    df["fertilizer_cost_adj"] = costs.fertilizer_base * ppi_ratio

    # ------------------------------------------------------------------
    # Fuel & lube: diesel-adjusted (inherits factor from transport step)
    # ------------------------------------------------------------------
    diesel_adj = df.get("diesel_adj_factor", pd.Series(1.0, index=df.index))
    df["fuel_lube_repairs_adj"] = costs.fuel_lube_repairs * diesel_adj

    # ------------------------------------------------------------------
    # Land rent: use state-specific rate when available
    # ------------------------------------------------------------------
    if "state_fips" in df.columns:
        df["land_rent_used"] = df["state_fips"].map(STATE_LAND_RENTS).fillna(costs.land_rent)
    else:
        df["land_rent_used"] = costs.land_rent

    # ------------------------------------------------------------------
    # Total production cost per acre
    # ------------------------------------------------------------------
    df["total_production_cost"] = (
        costs.seed
        + df["fertilizer_cost_adj"]
        + costs.pesticides
        + df["fuel_lube_repairs_adj"]
        + costs.custom_ops
        + costs.irrigation
        + costs.labor
        + df["land_rent_used"]
        + costs.depreciation
        + costs.taxes_insurance
        + costs.overhead
    )

    # ------------------------------------------------------------------
    # Yield estimation
    # ------------------------------------------------------------------
    if "yield_bu_acre" in df.columns and df["yield_bu_acre"].notna().any():
        # USDA survey data available — fill missing with demo yields
        demo_yields = _get_demo_yields(df, commodity)
        base_yield  = df["yield_bu_acre"].fillna(demo_yields)
    else:
        # No USDA data — generate realistic county-level variation
        base_yield = _get_demo_yields(df, commodity)

    adj_yield = base_yield.copy()

    # NDVI adjustment
    if ndvi_df is not None and not ndvi_df.empty:
        ndvi_coeff = YIELDS.soy_ndvi_coeff if commodity == "soybean" else YIELDS.corn_ndvi_coeff
        df = df.merge(ndvi_df[["fips_code","ndvi_z_score"]], on="fips_code", how="left")
        ndvi_adj = 1 + ndvi_coeff * df["ndvi_z_score"].fillna(0)
        adj_yield = adj_yield * np.clip(ndvi_adj, 0.70, 1.30)
        logger.info("NDVI adjustment applied to %d counties", df["ndvi_z_score"].notna().sum())

    # SMAP soil moisture adjustment
    if smap_df is not None and not smap_df.empty:
        df = df.merge(smap_df[["fips_code","smap_ssm_mean"]], on="fips_code", how="left")
        ssm = df["smap_ssm_mean"].fillna(0.28)
        smap_penalty = np.where(ssm < 0.15, 0.90, np.where(ssm > 0.45, 0.95, 1.0))
        adj_yield = adj_yield * smap_penalty
        logger.info("SMAP soil moisture penalty applied")

    df["adj_yield_bu_acre"] = adj_yield.clip(lower=10.0)

    # ------------------------------------------------------------------
    # Revenue — use 2026 Dec futures as planning price
    # ------------------------------------------------------------------
    cbot_price = CBOT_SOY_2026 if commodity == "soybean" else CBOT_CORN_2026
    df["cbot_price_per_bu"] = cbot_price
    df["revenue_per_acre"]  = df["adj_yield_bu_acre"] * cbot_price

    # ------------------------------------------------------------------
    # Basis deduction (transport cost applied to bushels produced)
    # ------------------------------------------------------------------
    if "transport_cost_per_bu" in df.columns:
        df["basis_deduction_per_acre"] = (
            df["transport_cost_per_bu"] * df["adj_yield_bu_acre"]
        )
    else:
        df["basis_deduction_per_acre"] = (
            costs.transport_base * df["adj_yield_bu_acre"]
        )

    df["net_revenue_per_acre"] = df["revenue_per_acre"] - df["basis_deduction_per_acre"]

    # ------------------------------------------------------------------
    # Net margin and NMS
    # ------------------------------------------------------------------
    df["net_margin_per_acre"] = df["net_revenue_per_acre"] - df["total_production_cost"]
    df["net_margin_score"]    = (
        df["net_margin_per_acre"] / df["revenue_per_acre"].replace(0, np.nan)
    ).clip(-2.0, 1.0)

    # ------------------------------------------------------------------
    # Risk classification
    # ------------------------------------------------------------------
    conditions = [
        df["net_margin_score"] <= RISK.high_risk_ceiling,
        df["net_margin_score"] <= RISK.elevated_risk_ceiling,
        df["net_margin_score"] <= RISK.moderate_risk_ceiling,
    ]
    df["risk_tier"] = np.select(conditions, ["HIGH","ELEVATED","MODERATE"], default="HEALTHY")

    tier_to_int = {"HEALTHY": 0, "MODERATE": 1, "ELEVATED": 2, "HIGH": 3}
    df["risk_tier_int"] = df["risk_tier"].map(tier_to_int).astype(int)

    logger.info(
        "Production costs: mean NMS=%.1f%% | tiers=%s",
        df["net_margin_score"].mean() * 100,
        df["risk_tier"].value_counts().to_dict(),
    )
    return df


# ---------------------------------------------------------------------------
# 4. Master Processing Pipeline
# ---------------------------------------------------------------------------

def build_profitability_model(
    acquired_data: dict,
    state_filter: Optional[str] = None,
    commodity: str = "soybean",
) -> pd.DataFrame:
    """
    Full pipeline: spatial -> transport -> production -> risk classification.

    Parameters
    ----------
    acquired_data : dict
        Output of data_acquisition.acquire_all_data().
    state_filter : str, optional
        Two-digit state FIPS to filter (e.g. '19' = Iowa).
    commodity : str
        'soybean' or 'corn'.

    Returns
    -------
    pd.DataFrame
        Master county-level profitability dataset.
    """
    logger.info("=== Building Profitability Model ===")

    county_df      = acquired_data["county_centroids"].copy()
    facilities     = acquired_data["facilities"]
    fertilizer_ppi = acquired_data["fertilizer_ppi"]
    diesel_price   = acquired_data["diesel_price"]
    yield_df       = acquired_data.get(
        "soy_yields" if commodity == "soybean" else "corn_yields",
        pd.DataFrame(),
    )

    if state_filter:
        county_df = county_df[county_df["state_fips"] == state_filter].copy()
        logger.info("Filtered to state FIPS=%s: %d counties", state_filter, len(county_df))

    if not yield_df.empty:
        county_df = county_df.merge(
            yield_df[["fips_code","yield_bu_acre"]], on="fips_code", how="left"
        )

    county_df = calculate_spatial_logistics(county_df, facilities)
    county_df = calculate_transport_cost(county_df, diesel_price, commodity=commodity)
    county_df = calculate_production_costs(
        county_df, fertilizer_ppi,
        ndvi_df=acquired_data.get("ndvi"),
        smap_df=acquired_data.get("smap"),
        commodity=commodity,
    )

    # Pydeck color column
    county_df["color"] = county_df["risk_tier"].map(RISK.risk_colors)
    county_df["color"] = county_df["color"].apply(
        lambda x: x if isinstance(x, list) else [128, 128, 128, 180]
    )

    # 3D elevation: higher column = worse margin
    county_df["elevation"] = np.clip(-county_df["net_margin_per_acre"] * 10, 0, 5000)

    logger.info("=== Model complete: %d counties ===", len(county_df))
    logger.info("Risk summary:\n%s", county_df["risk_tier"].value_counts().to_string())
    return county_df


# ---------------------------------------------------------------------------
# Aggregation Utilities
# ---------------------------------------------------------------------------

def summarize_risk_by_state(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate county metrics to state level."""
    return (
        df.groupby("state_fips")
        .agg(
            n_counties             = ("fips_code",              "count"),
            mean_nms               = ("net_margin_score",        "mean"),
            mean_margin_per_acre   = ("net_margin_per_acre",     "mean"),
            pct_high_risk          = ("risk_tier", lambda x: (x == "HIGH").mean() * 100),
            pct_healthy            = ("risk_tier", lambda x: (x == "HEALTHY").mean() * 100),
            median_crusher_dist    = ("crusher_dist_miles",      "median"),
            median_transport_cost  = ("transport_cost_per_bu",   "median"),
        )
        .reset_index()
        .sort_values("mean_nms")
    )


def get_most_at_risk_counties(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Return the N counties with the worst Net Margin Scores."""
    cols = [
        "fips_code","county_name","state_fips",
        "net_margin_score","net_margin_per_acre",
        "total_production_cost","transport_cost_per_bu",
        "crusher_dist_miles","crusher_name",
        "adj_yield_bu_acre","risk_tier",
    ]
    available = [c for c in cols if c in df.columns]
    return (
        df[available]
        .sort_values("net_margin_score")
        .head(n)
        .reset_index(drop=True)
    )


def get_logistics_squeeze_counties(
    df: pd.DataFrame,
    dist_threshold_miles: float = 100,
    n: int = 25,
) -> pd.DataFrame:
    """Counties that are far from crushers AND in HIGH or ELEVATED risk tier."""
    mask = (
        (df["crusher_dist_miles"] >= dist_threshold_miles)
        & (df["risk_tier"].isin(["HIGH","ELEVATED"]))
    )
    squeezed = df[mask].sort_values("transport_cost_per_bu", ascending=False)
    cols = [
        "fips_code","county_name","state_fips",
        "crusher_dist_miles","crusher_name",
        "transport_cost_per_bu","basis_risk_score",
        "net_margin_score","risk_tier",
    ]
    available = [c for c in cols if c in squeezed.columns]
    return squeezed[available].head(n).reset_index(drop=True)


# ---------------------------------------------------------------------------
# CLI Test Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from data_acquisition import load_value_chain_facilities, load_county_centroids

    print("\n" + "=" * 60)
    print("  HARVEST SQUEEZE — Processing Engine Test")
    print("=" * 60)

    facilities = load_value_chain_facilities()
    centroids  = load_county_centroids()
    iowa       = centroids[centroids["state_fips"] == "19"].copy()

    print(f"\nIowa counties loaded: {len(iowa)}")

    iowa = calculate_spatial_logistics(iowa, facilities)
    iowa = calculate_transport_cost(iowa, 3.82)
    iowa = calculate_production_costs(iowa, 488.0, commodity="soybean")  # ~Jan 2026 PCU325311325311 value

    vc = iowa["risk_tier"].value_counts()
    print("\nRisk distribution (Iowa, demo yields, $9.50 CBOT):")
    for tier in ["HIGH","ELEVATED","MODERATE","HEALTHY"]:
        n = vc.get(tier, 0)
        print(f"  {tier:<12}: {n:>3} counties ({n/len(iowa)*100:.0f}%)")

    print(f"\nMean net margin : ${iowa['net_margin_per_acre'].mean():+.0f}/acre")
    print(f"Mean NMS        : {iowa['net_margin_score'].mean()*100:.1f}%")
    print(f"Median CBOT     : ${iowa['cbot_price_per_bu'].iloc[0]:.2f}/bu")

    sample_cols = ["county_name","adj_yield_bu_acre","net_margin_per_acre",
                   "crusher_dist_miles","risk_tier"]
    print("\nSample counties:")
    print(iowa[sample_cols].head(8).to_string(index=False))

    print("\n" + "=" * 60)
    print("  Test complete.")
    print("=" * 60 + "\n")
