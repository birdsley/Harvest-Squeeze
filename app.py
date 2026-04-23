"""
app.py  --  The Harvest Squeeze  v2.3
--------------------------------------
Navigation entry point.  Uses st.navigation so pages get proper human-readable
titles in the sidebar instead of the raw filename ("app", "1_National_Risk_View").

v2.3 changes:
  - st.navigation with explicit titles: "Home", "National Risk View", etc.
  - Home page content moved inline (this file IS the home page when default=True).
  - Metric/sparkline columns isolated with st.container so charts don't bleed
    into adjacent columns.
  - All emojis removed from UI strings.
  - Fixed overlapping text: sparklines are wrapped in a zero-margin container
    and given explicit height so they never overflow.
"""

import json
import os
import warnings
import logging
from urllib.request import urlopen

import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pydeck as pdk
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.WARNING)
load_dotenv()

from config import SOY_COSTS, CORN_COSTS, LOGISTICS, RISK, CBOT_SOY_2026, CBOT_CORN_2026
from styles import (
    apply_theme, page_header, section_label, footer,
    plotly_layout_defaults, plotly_base_no_legend,
    RISK_COLORS, RISK_RGBA,
)
from data_acquisition import (
    load_value_chain_facilities, load_county_centroids,
    fetch_usda_soybean_yields, fetch_usda_corn_yields,
    fetch_fred_fertilizer_ppi, fetch_fred_fertilizer_history,
    fetch_eia_diesel_price, fetch_eia_diesel_history,
)
from data_processing import (
    calculate_spatial_logistics, calculate_transport_cost,
    calculate_production_costs, get_most_at_risk_counties,
    get_logistics_squeeze_counties,
)


# ---------------------------------------------------------------------------
# Page config — must be the FIRST Streamlit call
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Harvest Squeeze | 2026 Profitability Risk Monitor",
    page_icon="favicon.ico",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()


# ---------------------------------------------------------------------------
# Multi-page navigation with explicit titles
# ---------------------------------------------------------------------------
# st.navigation is available in Streamlit >= 1.29 (running 1.56.0).
# Defining pages explicitly here lets us give each a clean display title
# instead of the auto-generated "1 National Risk View" from the filename.
# ---------------------------------------------------------------------------

_pages = [
    st.Page(lambda: None,                      title="Home",              default=True),
    st.Page("pages/1_National_Risk_View.py",   title="National Risk View"),
    st.Page("pages/2_Crop_Progress.py",        title="Crop Progress"),
    st.Page("pages/3_Scenario_Analysis.py",    title="Scenario Analysis"),
    st.Page("pages/4_Satellite_View.py",       title="Satellite Data"),
]

# Flat navigation — no section grouping so Home appears inline with the other pages.
pg = st.navigation(_pages)

# Run the selected page; if it's the lambda (Home), we fall through to
# the home content below.  Any other selection renders that page file.
pg.run()

# Only render home content when Home is the active page.
# When a sub-page is active, pg.run() has already rendered it and we stop.
if pg.title != "Home":
    st.stop()


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

for _k, _v in {"model_df": None, "facilities": None, "run_count": 0}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


# ---------------------------------------------------------------------------
# Cached data loaders
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3_600, show_spinner=False)
def _load_facilities():
    return load_value_chain_facilities()

@st.cache_data(ttl=3_600, show_spinner=False)
def _load_centroids():
    return load_county_centroids()

@st.cache_data(ttl=1_800, show_spinner=False)
def _load_yields(state: str, yr: int, commodity: str) -> pd.DataFrame:
    fn = fetch_usda_soybean_yields if commodity == "soybean" else fetch_usda_corn_yields
    return fn(state_name=state, year=yr)

@st.cache_data(ttl=1_800, show_spinner=False)
def _load_fert_ppi() -> float:
    return fetch_fred_fertilizer_ppi()

@st.cache_data(ttl=900, show_spinner=False)
def _load_diesel() -> float:
    return fetch_eia_diesel_price()

@st.cache_data(ttl=1_800, show_spinner=False)
def _load_fert_hist(months: int = 24) -> pd.DataFrame:
    return fetch_fred_fertilizer_history(months=months)

@st.cache_data(ttl=900, show_spinner=False)
def _load_diesel_hist(weeks: int = 52) -> pd.DataFrame:
    return fetch_eia_diesel_history(weeks=weeks)

@st.cache_data(ttl=86_400, show_spinner=False)
def _load_county_geojson():
    try:
        url = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
        with urlopen(url, timeout=20) as r:
            return json.load(r)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    with st.expander("API Key Status", expanded=False):
        for _env, _label in [
            ("USDA_API_KEY", "USDA NASS QuickStats"),
            ("FRED_API_KEY", "FRED Fertilizer PPI"),
            ("EIA_API_KEY",  "EIA Diesel Price"),
        ]:
            _ok  = bool(os.getenv(_env))
            _clr = "#4ade80" if _ok else "#f87171"
            _txt = "Active" if _ok else "Missing"
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;"
                f"padding:0.25rem 0'>"
                f"<span style='font-size:0.78rem;color:#c8d5c0'>{_label}</span>"
                f"<span style='font-size:0.70rem;font-weight:700;color:{_clr};"
                f"text-transform:uppercase'>{_txt}</span></div>",
                unsafe_allow_html=True,
            )

    with st.expander("MACRO ASSUMPTIONS", expanded=True):
        land_rent = st.slider(
            "Land Rent ($/acre)",
            min_value=80, max_value=400,
            value=int(SOY_COSTS.land_rent), step=5,
            help="USDA NASS 2025 national average: $262/acre.",
        )
        fert_adj_pct = st.slider(
            "Fertilizer Adjustment (%)",
            min_value=-30, max_value=60, value=0, step=5, format="%d%%",
        )
        diesel_man = st.number_input(
            "Diesel Fallback ($/gal)",
            min_value=2.0, max_value=8.0, value=3.85, step=0.05, format="%.2f",
        )
        use_custom_cbot = st.toggle("Override CBOT Price", value=False)
        if use_custom_cbot:
            cbot_soy_ov  = st.number_input("Soybeans ($/bu)", 5.0, 18.0, CBOT_SOY_2026,  0.25, "%.2f")
            cbot_corn_ov = st.number_input("Corn ($/bu)",     2.0,  9.0, CBOT_CORN_2026, 0.10, "%.2f")
        else:
            cbot_soy_ov, cbot_corn_ov = CBOT_SOY_2026, CBOT_CORN_2026

    st.divider()

    st.markdown(
        "<div style='font-size:0.92rem;color:#E2E8F0;font-weight:700;"
        "font-family:\"Inter\",\"IBM Plex Sans\",sans-serif;"
        "letter-spacing:0.03em;margin:0.4rem 0 0.6rem'>Analysis Target</div>",
        unsafe_allow_html=True,
    )
    commodity = st.selectbox(
        "Commodity",
        ["soybean", "corn"],
        format_func=lambda x: "Soybeans" if x == "soybean" else "Corn",
    )
    state_sel = st.selectbox(
        "State",
        [("Iowa","19"),("Illinois","17"),("Indiana","18"),("Ohio","39"),
         ("Minnesota","27"),("Nebraska","31"),("Kansas","20"),("Missouri","29"),
         ("North Dakota","38"),("South Dakota","46")],
        format_func=lambda x: x[0],
    )
    state_name, state_fips = state_sel

    yield_year = st.select_slider(
        "Yield Reference Year", options=[2021, 2022, 2023, 2024], value=2023,
    )
    cbot = cbot_soy_ov if commodity == "soybean" else cbot_corn_ov

    st.divider()

    st.markdown(
        "<div style='font-size:0.92rem;color:#E2E8F0;font-weight:700;"
        "font-family:\"Inter\",\"IBM Plex Sans\",sans-serif;"
        "letter-spacing:0.03em;margin:0.4rem 0 0.6rem'>Map Overlays</div>",
        unsafe_allow_html=True,
    )
    show_crush = st.toggle("NOPA Crushers",    value=True)
    show_term  = st.toggle("Export Terminals", value=True)

    st.markdown("")
    run_btn = st.button("Run Analysis", type="primary", width="stretch")


# ---------------------------------------------------------------------------
# Preload static data
# ---------------------------------------------------------------------------

with st.spinner("Loading facility and county data…"):
    try:
        fac = _load_facilities()
        st.session_state.facilities = fac
    except Exception as _fe:
        st.error(f"Facility data unavailable: {_fe}")
        fac = {k: pd.DataFrame() for k in ["crushers","export_terminals","biodiesel_plants","all"]}
    try:
        centroids = _load_centroids()
    except Exception as _ce:
        st.error(f"County centroids unavailable: {_ce}")
        centroids = pd.DataFrame()


# ---------------------------------------------------------------------------
# Live macro indices
# ---------------------------------------------------------------------------

fert_ppi    = None
diesel_live = None

if os.getenv("FRED_API_KEY"):
    try:
        fert_ppi = _load_fert_ppi()
    except Exception:
        pass

if os.getenv("EIA_API_KEY"):
    try:
        diesel_live = _load_diesel()
    except Exception:
        pass

_eff_diesel = diesel_live if diesel_live else diesel_man


# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

page_header(
    "The Harvest Squeeze",
    "County-level profitability risk monitor for US soybean and corn production — 2026",
)
st.markdown("<div style='margin-bottom:0.9rem'></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# KPI strip  —  5 metric columns, sparklines isolated in containers
# FIX v2.3: wrap each sparkline in a st.container with overflow:hidden
# so it cannot bleed into adjacent metric columns.
# ---------------------------------------------------------------------------

_c1, _c2, _c3, _c4, _c5 = st.columns(5)

def _mini_sparkline(df_spark: pd.DataFrame, color: str) -> None:
    """Render a 48px-tall sparkline with no axes, contained in a div."""
    if df_spark is None or df_spark.empty:
        return
    _fig = go.Figure(go.Scatter(
        x=df_spark["period"], y=df_spark["value"],
        mode="lines", line=dict(color=color, width=1.4),
        fill="tozeroy",
        fillcolor=color.replace(")", ",0.10)").replace("rgb", "rgba")
        if color.startswith("rgb") else f"rgba(0,0,0,0.06)",
    ))
    _fig.update_layout(
        height=44, margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False, fixedrange=True),
        yaxis=dict(visible=False, fixedrange=True),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    st.plotly_chart(_fig, width="stretch", config={"displayModeBar": False})


with _c1:
    st.metric(
        "Fertilizer PPI",
        f"{fert_ppi:.1f}" if fert_ppi else "N/A",
        border=True,
        help="FRED PCU3253113253111 — Nitrogenous Fertilizer PPI (base Dec 1984 = 100)",
    )
    if fert_ppi and os.getenv("FRED_API_KEY"):
        with st.container():
            try:
                _mini_sparkline(_load_fert_hist(months=18), "#2D5A27")
            except Exception:
                pass

with _c2:
    _d_delta = f"{_eff_diesel - diesel_man:+.3f} vs baseline" if diesel_live else None
    st.metric(
        "US No.2 Diesel",
        f"${_eff_diesel:.3f}/gal",
        delta=_d_delta,
        border=True,
        help="EIA Weekly No. 2 Diesel Retail Price — NUS average",
    )
    if diesel_live and os.getenv("EIA_API_KEY"):
        with st.container():
            try:
                _mini_sparkline(_load_diesel_hist(weeks=52), "#1E293B")
            except Exception:
                pass

with _c3:
    _cb_label = "Soybeans Dec 26" if commodity == "soybean" else "Corn Dec 26"
    _cb_help  = ("CBOT December 2026 Soybean futures (April 2026 forward curve)."
                 if commodity == "soybean"
                 else "CBOT December 2026 Corn futures (April 2026 forward curve).")
    _cb_ref   = CBOT_SOY_2026 if commodity == "soybean" else CBOT_CORN_2026
    _cb_d     = f"{cbot - _cb_ref:+.2f} vs forward" if use_custom_cbot else None  # noqa: F821
    st.metric(_cb_label, f"${cbot:.2f}/bu", delta=_cb_d, border=True, help=_cb_help)

with _c4:
    _fac_tmp = st.session_state.facilities or fac
    st.metric("NOPA Crushers",    len(_fac_tmp.get("crushers",         [])),
              border=True, help="Operating soybean processors in dataset.")

with _c5:
    st.metric("Export Terminals", len(_fac_tmp.get("export_terminals", [])),
              border=True, help="River and ocean export facilities in dataset.")

st.divider()


# ---------------------------------------------------------------------------
# Risk classification
# ---------------------------------------------------------------------------

def _classify_risk(net_margin: pd.Series, revenue_per_acre: float) -> pd.Series:
    """Classify $/acre net margins into risk tiers using RiskThresholds ratios."""
    _rev = max(float(revenue_per_acre), 1.0)
    return pd.cut(
        net_margin,
        bins=[-np.inf,
              RISK.high_risk_ceiling     * _rev,
              RISK.elevated_risk_ceiling * _rev,
              RISK.moderate_risk_ceiling * _rev,
              np.inf],
        labels=["HIGH", "ELEVATED", "MODERATE", "HEALTHY"],
    ).astype(str)


# ---------------------------------------------------------------------------
# Analysis runner
# ---------------------------------------------------------------------------

def run_analysis() -> pd.DataFrame:
    _eff_fert = (fert_ppi or 100.0) * (1.0 + fert_adj_pct / 100.0)

    with st.spinner(f"Fetching USDA yields — {state_name} {yield_year}…"):
        try:
            yields_df = _load_yields(state_name, yield_year, commodity)
        except Exception as _e:
            st.warning(f"USDA yield fetch failed (spatial model only): {_e}")
            yields_df = pd.DataFrame()

    with st.spinner("KD-Tree spatial logistics model…"):
        df = centroids.copy()
        if state_fips and "state_fips" in df.columns:
            df = df[df["state_fips"] == state_fips].copy()
        elif state_fips:
            st.warning("County centroids missing 'state_fips' column — showing all counties.")

        if df.empty:
            st.error("No county data available. Check that county_centroids.parquet is committed.")
            return pd.DataFrame()

        if not yields_df.empty and "fips_code" in df.columns:
            df = df.merge(yields_df[["fips_code", "yield_bu_acre"]], on="fips_code", how="left")

        df = calculate_spatial_logistics(df, fac)
        df = calculate_transport_cost(df, _eff_diesel, commodity=commodity)
        df = calculate_production_costs(
            df, _eff_fert, ndvi_df=None, smap_df=None, commodity=commodity,
        )

    # Land-rent override
    _default_rent = SOY_COSTS.land_rent if commodity == "soybean" else CORN_COSTS.land_rent
    _delta        = land_rent - _default_rent
    if _delta != 0 and "net_margin_per_acre" in df.columns:
        df["net_margin_per_acre"] = df["net_margin_per_acre"] - _delta
        if "total_cost_per_acre" in df.columns:
            df["total_cost_per_acre"] = df["total_cost_per_acre"] + _delta

    # Re-classify risk tiers
    if "net_margin_per_acre" in df.columns:
        _typ   = 52.0 if commodity == "soybean" else 175.0
        _rev   = float(df["revenue_per_acre"].median() if "revenue_per_acre" in df.columns
                       else cbot * _typ)
        df["risk_tier"] = _classify_risk(df["net_margin_per_acre"], _rev)

    df["color"] = df["risk_tier"].map(RISK_RGBA).apply(
        lambda x: x if isinstance(x, list) else [128, 128, 128, 180]
    )
    df["elevation"] = np.clip(
        -df.get("net_margin_per_acre", pd.Series(0, index=df.index)) * 10,
        0, 5_000,
    )
    if "fips_code" in df.columns:
        df["fips_str"] = df["fips_code"].astype(str).str.zfill(5)

    return df


# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------

if run_btn:
    with st.spinner("Building profitability model…"):
        st.session_state.model_df  = run_analysis()
        st.session_state.run_count += 1

df = st.session_state.model_df


# ---------------------------------------------------------------------------
# Results layout
# ---------------------------------------------------------------------------

if df is not None and not df.empty:

    # Risk pills
    _rvc   = df["risk_tier"].value_counts()
    _pcols = st.columns(4)
    for _pc, (_tier, _fg, _bg, _desc) in zip(_pcols, [
        ("HIGH",    "#B91C1C","#FEE2E2","Loss Territory — below zero"),
        ("ELEVATED","#C2410C","#FFEDD5","Razor-Thin — 0 to 5 pct"),
        ("MODERATE","#B45309","#FEF3C7","Watchlist — 5 to 12 pct"),
        ("HEALTHY", "#15803D","#DCFCE7","Healthy — above 12 pct"),
    ]):
        _n   = _rvc.get(_tier, 0)
        _pct = 100 * _n / len(df) if len(df) else 0
        _pc.markdown(
            f"<div style='background:{_bg};border-left:4px solid {_fg};"
            f"border-radius:2px;padding:0.65rem 0.85rem;margin-bottom:0.35rem'>"
            f"<div style='font-size:0.63rem;font-weight:700;color:{_fg};"
            f"text-transform:uppercase;letter-spacing:0.10em'>{_tier}</div>"
            f"<div style='font-size:1.55rem;font-weight:700;color:{_fg};"
            f"font-family:\"IBM Plex Mono\",monospace;line-height:1.1'>{_n}</div>"
            f"<div style='font-size:0.68rem;color:{_fg};opacity:0.8'>"
            f"{_pct:.0f}% of counties — {_desc}</div></div>",
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

    map_col, chart_col = st.columns([62, 38])

    # -- Choropleth map --
    with map_col:
        section_label("County Profitability Risk Map")
        _geojson = _load_county_geojson()

        if _geojson and "fips_str" in df.columns:
            _mdf = df.dropna(subset=["fips_str", "risk_tier"]).copy()
            _tier_order = ["HIGH", "ELEVATED", "MODERATE", "HEALTHY"]
            _mdf["risk_tier"] = pd.Categorical(_mdf["risk_tier"], categories=_tier_order, ordered=True)
            _mdf = _mdf.sort_values("risk_tier")

            _hover = {"county_name": True, "risk_tier": True, "net_margin_per_acre": ":.0f"}
            if "crusher_dist_miles" in _mdf.columns:
                _hover["crusher_dist_miles"] = ":.0f"
            if "yield_bu_acre" in _mdf.columns:
                _hover["yield_bu_acre"] = ":.1f"

            fig_map = px.choropleth(
                _mdf,
                geojson=_geojson,
                locations="fips_str",
                color="risk_tier",
                color_discrete_map=RISK_COLORS,
                category_orders={"risk_tier": _tier_order},
                scope="usa",
                hover_name="county_name",
                hover_data=_hover,
                labels={
                    "risk_tier":           "Risk Tier",
                    "net_margin_per_acre": "Net Margin ($/acre)",
                    "crusher_dist_miles":  "Miles to Crusher",
                    "yield_bu_acre":       "Yield (bu/acre)",
                },
            )

            if show_crush and not fac.get("crushers", pd.DataFrame()).empty:
                _cdf = fac["crushers"].dropna(subset=["lat", "lon"])
                fig_map.add_trace(go.Scattergeo(
                    lat=_cdf["lat"], lon=_cdf["lon"], mode="markers",
                    marker=dict(size=7, color="#1E4080", symbol="circle",
                                line=dict(width=1, color="#FFF")),
                    name="NOPA Crusher",
                    text=_cdf.get("Short Name", _cdf.index.astype(str)),
                    hovertemplate="<b>%{text}</b><br>NOPA Crusher<extra></extra>",
                ))

            if show_term and not fac.get("export_terminals", pd.DataFrame()).empty:
                _tdf = fac["export_terminals"].dropna(subset=["lat", "lon"])
                fig_map.add_trace(go.Scattergeo(
                    lat=_tdf["lat"], lon=_tdf["lon"], mode="markers",
                    marker=dict(size=8, color="#6D3A9C", symbol="diamond",
                                line=dict(width=1, color="#FFF")),
                    name="Export Terminal",
                    text=_tdf.get("Short Name", _tdf.index.astype(str)),
                    hovertemplate="<b>%{text}</b><br>Export Terminal<extra></extra>",
                ))

            fig_map.update_geos(fitbounds="locations", visible=False, bgcolor="rgba(0,0,0,0)")
            fig_map.update_layout(
                margin=dict(l=0, r=0, t=0, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                geo=dict(bgcolor="rgba(0,0,0,0)"),
                legend=dict(
                    title=dict(text="Risk Tier", font=dict(size=10)),
                    orientation="h", yanchor="bottom", y=-0.08,
                    xanchor="left", x=0,
                    font=dict(size=10, family="IBM Plex Sans"),
                    bgcolor="rgba(255,255,255,0.85)",
                    bordercolor="#E5E2DC", borderwidth=1,
                ),
                height=480,
                font=dict(family="IBM Plex Sans", size=10),
            )
            st.plotly_chart(fig_map, width="stretch", config={"displayModeBar": False})

        else:
            st.caption("County GeoJSON unavailable — showing centroid scatter.")
            _md  = df.dropna(subset=["lat", "lon"])
            _lyr = pdk.Layer(
                "ScatterplotLayer",
                data=_md[["lat","lon","color","county_name","net_margin_per_acre","risk_tier"]],
                get_position=["lon","lat"], get_fill_color="color",
                get_line_color=[255, 255, 255, 60],
                stroked=True,
                line_width_min_pixels=1,
                get_radius=8_000, opacity=0.88, pickable=True,
            )
            _ctrs = {
                "19":(42.0,-93.5,7),"17":(40.0,-89.2,7),"18":(40.3,-86.1,7),
                "39":(40.4,-82.5,7),"27":(46.4,-94.7,6),"31":(41.5,-99.9,6),
            }
            _lat, _lon, _z = _ctrs.get(state_fips, (41.5,-93.5,7))
            st.pydeck_chart(
                pdk.Deck(layers=[_lyr],
                         initial_view_state=pdk.ViewState(latitude=_lat, longitude=_lon, zoom=_z),
                         map_style="mapbox://styles/mapbox/dark-v11"),
                width="stretch",
            )

        st.markdown(
            "<div style='font-size:0.71rem;color:#9A9A90;margin-top:6px'>"
            "Counties shaded by Net Margin Score: revenue less all production "
            "and transport costs. Crusher and terminal data: NOPA/EIA Value Chain."
            "</div>",
            unsafe_allow_html=True,
        )

    # -- Chart panel --
    with chart_col:
        _t1, _t2, _t3, _t4 = st.tabs(["Cost Stack", "Logistics", "Risk Table", "Macro Trends"])
        _base = plotly_layout_defaults()

        with _t1:
            section_label("Production Cost Stack vs. Revenue")
            _med   = df.median(numeric_only=True)
            _costs = SOY_COSTS if commodity == "soybean" else CORN_COSTS
            _ci = {
                "Land Rent":       land_rent,
                "Fertilizer":      float(_med.get("fertilizer_cost_adj", _costs.fertilizer_base)),
                "Seed":            _costs.seed,
                "Pesticides":      _costs.pesticides,
                "Fuel & Repairs":  _costs.fuel_lube_repairs,
                "Labor":           _costs.labor,
                "Depreciation":    _costs.depreciation,
                "Transport Basis": float(_med.get("basis_deduction_per_acre",
                                                   _costs.transport_base * 50)),
                "Overhead":        _costs.overhead + _costs.taxes_insurance + _costs.custom_ops,
            }
            _rev = float(_med.get("revenue_per_acre", cbot * 52))
            _net = _rev - sum(_ci.values())
            _bar_colors = [
                "rgba(30,41,59,0.82)"  if k == "Transport Basis"
                else "rgba(45,90,39,0.82)"
                for k in _ci
            ] + ["rgba(21,128,61,0.90)" if _net >= 0 else "rgba(185,28,28,0.90)"]

            _wf = go.Figure(go.Waterfall(
                orientation="v",
                measure=["relative"] * len(_ci) + ["total"],
                x=list(_ci.keys()) + ["Net Margin"],
                y=[-v for v in _ci.values()] + [_net],
                base=_rev,
                connector={"line": {"color": "#E5E2DC", "width": 1}},
                decreasing={"marker": {"color": "rgba(185,28,28,0.82)"}},
                increasing={"marker": {"color": "rgba(21,128,61,0.82)"}},
                totals={"marker": {
                    "color": "rgba(21,128,61,0.90)" if _net >= 0 else "rgba(185,28,28,0.90)"
                }},
                text=[f"${v:.0f}" for v in _ci.values()] + [f"${_net:+.0f}"],
                textposition="auto",
                textfont={"size": 8, "family": "IBM Plex Mono"},
            ))
            _wf.data[0].update(marker_color=_bar_colors)
            _wf.update_layout(
                **_base,
                title=dict(
                    text=f"Median county — CBOT ${cbot:.2f}/bu, land ${land_rent}/acre",
                    font=dict(size=10),
                ),
                height=400, yaxis_title="$/acre", showlegend=False,
            )
            _wf.update_xaxes(tickfont=dict(size=8))
            st.plotly_chart(_wf, width="stretch", config={"displayModeBar": False})

        with _t2:
            section_label("Basis Risk — Distance to Nearest Crusher")
            if "crusher_dist_miles" in df.columns:
                _fh2 = px.histogram(
                    df, x="crusher_dist_miles", color="risk_tier", nbins=28,
                    color_discrete_map=RISK_COLORS,
                    category_orders={"risk_tier":["HIGH","ELEVATED","MODERATE","HEALTHY"]},
                    labels={"crusher_dist_miles":"Miles to Nearest Crusher","count":"Counties"},
                )
                _fh2.add_vline(
                    x=LOGISTICS.distance_threshold_miles, line_dash="dash", line_color="#9A9A90",
                    annotation_text=f"Penalty threshold ({LOGISTICS.distance_threshold_miles:.0f} mi)",
                    annotation_font_size=9,
                )
                _fh2.update_layout(
                    **_base, title="Crusher distance by risk tier",
                    height=210, showlegend=True,
                )
                st.plotly_chart(_fh2, width="stretch", config={"displayModeBar": False})

            if "transport_cost_per_bu" in df.columns and "crusher_dist_miles" in df.columns:
                _fs2 = px.scatter(
                    df.dropna(subset=["crusher_dist_miles","transport_cost_per_bu"]),
                    x="crusher_dist_miles", y="transport_cost_per_bu",
                    color="risk_tier", hover_data=["county_name"],
                    color_discrete_map=RISK_COLORS,
                )
                _fs2.update_layout(
                    **_base, title="Transport cost vs. distance", height=210, showlegend=False,
                )
                st.plotly_chart(_fs2, width="stretch", config={"displayModeBar": False})

        with _t3:
            section_label("Most Squeezed Counties")
            try:
                _ar = get_most_at_risk_counties(df, n=15)
                if not _ar.empty:
                    _dc = [c for c in ["county_name","risk_tier","net_margin_per_acre",
                                       "crusher_dist_miles","transport_cost_per_bu","yield_bu_acre"]
                           if c in _ar.columns]
                    st.dataframe(_ar[_dc].round(2), height=300, width="stretch")
            except Exception as _e:
                st.info(f"Risk table: {_e}")

        with _t4:
            section_label("Fertilizer PPI — FRED (18-month)")
            if os.getenv("FRED_API_KEY"):
                try:
                    _fh4 = _load_fert_hist(months=18)
                    if not _fh4.empty:
                        _ff4 = go.Figure(go.Scatter(
                            x=_fh4["period"], y=_fh4["value"],
                            mode="lines+markers",
                            line=dict(color="#2D5A27", width=2), marker=dict(size=3),
                            fill="tozeroy", fillcolor="rgba(45,90,39,0.08)",
                        ))
                        _ff4.update_layout(**plotly_base_no_legend(), height=180,
                                           showlegend=False, yaxis_title="PPI index")
                        st.plotly_chart(_ff4, width="stretch", config={"displayModeBar": False})
                except Exception:
                    st.caption("Fertilizer PPI trend unavailable.")
            else:
                st.caption("Add FRED_API_KEY to Streamlit Secrets.")

            section_label("US Diesel Retail Price — EIA (52-week)")
            if os.getenv("EIA_API_KEY"):
                try:
                    _dh4 = _load_diesel_hist(weeks=52)
                    if not _dh4.empty:
                        _fd4 = go.Figure(go.Scatter(
                            x=_dh4["period"], y=_dh4["value"], mode="lines",
                            line=dict(color="#1E293B", width=2),
                            fill="tozeroy", fillcolor="rgba(30,41,59,0.08)",
                        ))
                        _fd4.update_layout(**plotly_base_no_legend(), height=180,
                                           showlegend=False, yaxis_title="$/gal")
                        st.plotly_chart(_fd4, width="stretch", config={"displayModeBar": False})
                except Exception:
                    st.caption("Diesel price trend unavailable.")
            else:
                st.caption("Add EIA_API_KEY to Streamlit Secrets.")

    st.divider()

    with st.expander("Full County Data Table", expanded=False):
        _out = df.drop(columns=[c for c in ["color","elevation","fips_str"] if c in df.columns]).copy()
        _out[_out.select_dtypes(float).columns] = _out.select_dtypes(float).round(3)
        st.dataframe(_out, width="stretch", height=300)
        st.download_button(
            "Download CSV",
            data=_out.to_csv(index=False),
            file_name=f"harvest_squeeze_{state_name.lower()}_{commodity}_{yield_year}.csv",
            mime="text/csv",
        )

else:
    # Idle narrative
    st.markdown(
        "<div style='max-width:680px;margin:3.5rem auto;padding:0 1rem'>"
        "<h2 style='font-family:Georgia,serif;font-size:1.55rem;"
        "color:#0F2419;font-weight:700;margin-bottom:1rem;letter-spacing:-0.02em'>"
        "Why Margins Are Under Pressure in 2026</h2>"
        "<p style='color:#5A5A52;line-height:1.8;font-size:0.92rem'>"
        "American soybean and corn producers face a structural two-sided squeeze. "
        "On the <strong>Growing side</strong>, national cash rents have climbed "
        "above $260 per acre while nitrogenous fertilizer prices remain elevated "
        "against the 2020 baseline. On the <strong>Moving side</strong>, counties "
        "distant from NOPA crush facilities or Mississippi River export terminals "
        "carry a logistics basis penalty that compounds the input cost burden."
        "</p>"
        "<p style='color:#5A5A52;line-height:1.8;font-size:0.92rem;margin-top:1rem'>"
        "This monitor quantifies that squeeze county by county, combining USDA "
        "yield data, FRED fertilizer indices, EIA diesel prices, and a KD-Tree "
        "nearest-neighbor spatial model of the US soybean value chain. "
        "Select a state and commodity in the sidebar, then click "
        "<strong>Run Analysis</strong>."
        "</p>"
        "<div style='margin-top:2rem;padding:1.1rem 1.2rem;background:#F0F7EE;"
        "border-left:3px solid #2D5A27;border-radius:2px;font-size:0.84rem;"
        "color:#0F2419;line-height:1.6'>"
        "<strong>Data requirements:</strong> The spatial model runs without API "
        "keys. Live fertilizer PPI, diesel prices, and USDA yields require FRED, "
        "EIA, and USDA keys in Streamlit Secrets."
        "</div></div>",
        unsafe_allow_html=True,
    )

footer()
