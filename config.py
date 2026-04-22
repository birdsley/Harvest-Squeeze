"""
config.py
---------
Central configuration hub for The Harvest Squeeze dashboard.
All 2026 cost assumptions, API endpoints, and column mappings live here.
Edit this file to run sensitivity scenarios without touching model logic.

v2.4 fix: FRED series PCU3253113253111 was DISCONTINUED Dec 2014.
          Updated to PCU325311325311 (industry-level, active through 2026).
"""

from dataclasses import dataclass, field
from typing import Dict


# ---------------------------------------------------------------------------
# 2026 Market Price Assumptions
# Sources: CBOT December 2026 futures, April 2026 settlement
# ---------------------------------------------------------------------------

# Soybean December 2026 futures: ~$9.50/bu (Apr 2026 forward curve)
# Corn December 2026 futures:    ~$4.35/bu
CBOT_SOY_2026:  float = 9.50
CBOT_CORN_2026: float = 4.35

# State-level cash rent ($/acre) — USDA NASS 2025 averages
# Used to override the national baseline when state-specific data is available
STATE_LAND_RENTS: Dict[str, float] = {
    "19": 248.0,   # Iowa
    "17": 238.0,   # Illinois
    "18": 195.0,   # Indiana
    "39": 185.0,   # Ohio
    "27": 178.0,   # Minnesota
    "31": 165.0,   # Nebraska
    "20": 165.0,   # Kansas
    "29": 155.0,   # Missouri
    "38": 85.0,    # North Dakota
    "46": 90.0,    # South Dakota
    "55": 175.0,   # Wisconsin
    "26": 162.0,   # Michigan
}


# ---------------------------------------------------------------------------
# 2026 Production Cost Assumptions (per acre, unless noted)
# Sources: USDA ERS Cost of Production Forecasts, 2024 Actuals + trend
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SoybeanCosts2026:
    """Fixed-cost baseline for soybean production ($/acre)."""

    # Operating costs
    seed:               float = 65.00   # USDA ERS 2024 avg, +5% seed inflation
    fertilizer_base:    float = 47.00   # Baseline P&K; N adjusted by FRED PPI
    pesticides:         float = 40.00
    fuel_lube_repairs:  float = 23.00   # Adjusted by EIA diesel index
    custom_ops:         float = 13.00
    irrigation:         float = 9.00    # Weighted national avg (many dryland farms)
    labor:              float = 19.00   # Hired + operator, 2026 USDA estimate

    # Overhead / ownership costs
    land_rent:          float = 262.00  # USDA NASS 2025 national avg (up from $248)
    depreciation:       float = 37.00
    taxes_insurance:    float = 13.00
    overhead:           float = 16.00

    # Logistics / basis (placeholder; overridden by spatial model)
    transport_base:     float = 0.35    # $/bushel flat rate before distance adj.

    # All-in total at national avg land rent: ~$547/acre
    # Breakeven at 57.6 bu/acre @ $9.50/bu


@dataclass(frozen=True)
class CornCosts2026:
    """Fixed-cost baseline for corn production ($/acre)."""

    seed:               float = 115.00
    fertilizer_base:    float = 112.00
    pesticides:         float = 55.00
    fuel_lube_repairs:  float = 30.00
    custom_ops:         float = 16.00
    irrigation:         float = 13.00
    labor:              float = 22.00
    land_rent:          float = 262.00
    depreciation:       float = 42.00
    taxes_insurance:    float = 14.00
    overhead:           float = 18.00
    transport_base:     float = 0.28    # $/bushel


@dataclass(frozen=True)
class YieldAssumptions2026:
    """Trend yield benchmarks (bu/acre) for 2026 planning."""

    soybean_national_trend: float = 52.5    # USDA WASDE Feb 2026 projection
    soybean_iowa_trend:     float = 59.0
    corn_national_trend:    float = 181.0
    corn_iowa_trend:        float = 202.0

    # County-level yield standard deviation for demo mode (no USDA data)
    # Derived from 10-year USDA county yield coefficient of variation
    soybean_county_std:     float = 5.5     # bu/acre
    corn_county_std:        float = 18.0    # bu/acre

    # State yield modifiers relative to national trend
    # Source: USDA NASS 5-year state average yield index
    state_yield_index: Dict = field(default_factory=lambda: {
        "19": 1.124,   # Iowa      — highest soy yields nationally
        "17": 1.076,   # Illinois
        "18": 1.029,   # Indiana
        "39": 1.000,   # Ohio      — baseline
        "27": 0.943,   # Minnesota
        "31": 0.924,   # Nebraska  — more variable, drought-prone
        "20": 0.886,   # Kansas
        "29": 0.952,   # Missouri
        "38": 0.876,   # North Dakota
        "46": 0.895,   # South Dakota
        "55": 0.971,   # Wisconsin
        "26": 0.952,   # Michigan
    })

    # NDVI-to-yield regression coefficients (calibrated vs USDA actuals)
    soy_ndvi_coeff:     float = 0.12
    corn_ndvi_coeff:    float = 0.15


# ---------------------------------------------------------------------------
# Logistics / Transport Parameters
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LogisticsParams:
    """Transport cost model parameters."""

    # $/bushel per 100 miles (truck), calibrated to USDA AMS grain reports
    truck_cost_per_100mi:       float = 0.18
    barge_cost_per_100mi:       float = 0.04

    # Distance decay: basis risk amplifies non-linearly beyond this threshold
    distance_threshold_miles:   float = 75.0
    distance_penalty_multiplier:float = 1.25

    # Diesel price sensitivity: 1% change in diesel → X% change in transport cost
    diesel_elasticity:          float = 0.65

    # Reference diesel price (EIA annual avg 2024, $/gallon)
    diesel_reference_price:     float = 3.82


# ---------------------------------------------------------------------------
# Risk Classification Thresholds
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RiskThresholds:
    """Net Margin Score → Risk Tier mapping."""

    # NMS = (Revenue - Total Costs - Transport Basis) / Revenue

    high_risk_ceiling:     float = 0.00   # NMS <= 0%  → loss territory
    elevated_risk_ceiling: float = 0.05   # NMS 0-5%   → razor-thin
    moderate_risk_ceiling: float = 0.12   # NMS 5-12%  → watchlist
    # NMS > 12% → healthy margin

    risk_labels: Dict = field(default_factory=lambda: {
        "HIGH":     "Loss Territory (<=0%)",
        "ELEVATED": "Razor-Thin (0-5%)",
        "MODERATE": "Watchlist (5-12%)",
        "HEALTHY":  "Healthy (>12%)",
    })

    risk_colors: Dict = field(default_factory=lambda: {
        "HIGH":     [185, 28, 28, 210],
        "ELEVATED": [194, 65, 12, 210],
        "MODERATE": [180, 83, 9, 210],
        "HEALTHY":  [21, 128, 61, 210],
    })


# ---------------------------------------------------------------------------
# API Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class APIConfig:
    """API base URLs and key FRED/EIA series IDs."""

    # USDA NASS QuickStats
    usda_base_url:           str = "https://quickstats.nass.usda.gov/api/api_GET/"
    usda_commodity_soy:      str = "SOYBEANS"
    usda_commodity_corn:     str = "CORN"
    usda_stat_cat_yield:     str = "YIELD"
    usda_agg_level:          str = "COUNTY"

    # FRED (St. Louis Fed)
    # v2.4 FIX: PCU3253113253111 was DISCONTINUED Dec 2014 (zero observations).
    #           Replaced with PCU325311325311 (industry-level, active thru 2026).
    fred_base_url:           str = "https://api.stlouisfed.org/fred/series/observations"
    fred_series_fertilizer:  str = "PCU325311325311"   # PPI: Nitrogenous Fertilizer Mfg (industry-level, active)
    fred_series_fertilizer_alt: str = "WPU0652"        # PPI: Fertilizer Materials (commodity-level fallback)
    fred_observation_start:  str = "2023-01-01"

    # EIA (Energy Information Administration)
    eia_base_url:            str = "https://api.eia.gov/v2/petroleum/pri/wfr/data/"
    eia_series_diesel:       str = "EMD_EPD2D_PTE_NUS_DPG"  # Weekly US No.2 Diesel

    # US Census TIGER/Line county shapefile (for county centroids)
    census_counties_url:     str = (
        "https://www2.census.gov/geo/tiger/TIGER2023/COUNTY/tl_2023_us_county.zip"
    )

    # GEE collection IDs
    gee_ndvi_collection:     str = "MODIS/061/MOD13A2"
    gee_smap_collection:     str = "NASA_USDA/HSL/SMAP10KM_soil_moisture"


# ---------------------------------------------------------------------------
# Value Chain Data Mapping (from USSoyValueChain.xlsx)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValueChainConfig:
    """Column mappings and type filters for the EIA/NOPA facility XLSX."""

    xlsx_path:              str = "USSoyValueChain.xlsx"
    sheet_value_chain:      str = "Value Chain"
    sheet_meal_consumption: str = "Meal Consumption"

    crusher_types: tuple = (
        "Soybean Processor - Operating",
        "Soybean Processor - Forthcoming",
    )
    export_terminal_types: tuple = (
        "Export Facility",
        "Export Company",
    )
    biodiesel_types: tuple = (
        "Biodiesel",
        "Renewable Diesel - Operating",
        "Renewable Diesel - Forthcoming",
    )

    lat_col:    str = "Lat"
    lon_col:    str = "Long"
    name_col:   str = "Short Name"
    type_col:   str = "Type"
    status_col: str = "Status"
    state_col:  str = "State"
    county_col: str = "County"


# ---------------------------------------------------------------------------
# Instantiate for import
# ---------------------------------------------------------------------------

SOY_COSTS = SoybeanCosts2026()
CORN_COSTS = CornCosts2026()
YIELDS = YieldAssumptions2026()
LOGISTICS = LogisticsParams()
RISK = RiskThresholds()
API = APIConfig()
VC = ValueChainConfig()
