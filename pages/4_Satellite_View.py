"""
pages/4_Satellite_View.py
--------------------------
Google Earth Engine satellite data visualization.
MODIS NDVI growing-season health and NASA SMAP soil moisture
mapped at county level with yield modifier integration.
Requires authenticated GEE account.
"""

import warnings

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import pydeck as pdk
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
load_dotenv()

from styles import (
    apply_theme, page_header, section_label, footer,
    plotly_layout_defaults,
)
from data_acquisition import load_value_chain_facilities, load_county_centroids
from data_processing import (
    calculate_spatial_logistics, calculate_transport_cost,
    calculate_production_costs,
)
from gee_pipeline import GEEPipeline, GROWING_WINDOWS

st.set_page_config(
    page_title="Satellite View | Harvest Squeeze",
    layout="wide", initial_sidebar_state="expanded",
)
apply_theme()

page_header(
    "Satellite Growing Conditions",
    "MODIS NDVI and NASA SMAP soil moisture by county &mdash; "
    "growing-season health and yield modifier integration",
)
st.divider()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        "<div style='padding:1.2rem 0 0.6rem'>"
        "<span style='font-family:Georgia,serif;font-size:1rem;"
        "font-weight:700;color:#f0f4ee'>GEE Satellite Controls</span></div>",
        unsafe_allow_html=True,
    )
    st.divider()

    commodity = st.selectbox("Commodity", ["soybean","corn"],
        format_func=lambda x: "Soybeans" if x == "soybean" else "Corn",
        key="sat_comm")
    state_sel = st.selectbox("State", [
        ("Iowa","19"),("Illinois","17"),("Indiana","18"),
        ("Ohio","39"),("Minnesota","27"),("Nebraska","31"),
    ], format_func=lambda x: x[0], key="sat_state")
    state_label, state_fips = state_sel

    year_sel    = st.selectbox("Growing Season Year", [2025, 2024, 2023], key="sat_year")
    season_sel  = st.selectbox("NDVI Season Window",
        [("Peak season (Jul-Aug)","peak"),
         ("Early season (Jun)","early"),
         ("Late season (Sep)","late")],
        format_func=lambda x: x[0], key="sat_season")
    season_label, season_key = season_sel

    smap_month  = st.slider("SMAP Month (1-12)", 6, 9, 7, key="sat_smap_month")

    st.divider()
    gee_project = st.text_input(
        "GEE Project ID (optional)",
        value="",
        help="Leave blank for personal accounts. Required for commercial/cloud GEE.",
        key="sat_project",
    )

    st.markdown("")
    run_btn  = st.button("Fetch Satellite Data", type="primary", width="stretch")
    demo_btn = st.button("Load Demo Data",        width="stretch")

# ---------------------------------------------------------------------------
# Cached loaders
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def _fac():
    return load_value_chain_facilities()

@st.cache_data(ttl=3600, show_spinner=False)
def _cent():
    return load_county_centroids()

# ---------------------------------------------------------------------------
# Demo data generator
# ---------------------------------------------------------------------------

def _make_demo(fips, cm, year, season):
    """Generate plausible synthetic satellite data for offline demonstration."""
    fac  = _fac()
    cent = _cent()
    sc   = cent[cent["state_fips"] == fips].copy()
    if sc.empty:
        return pd.DataFrame()

    rng   = np.random.default_rng(int(fips) + year)
    n     = len(sc)

    sc    = calculate_spatial_logistics(sc, fac)
    sc    = calculate_transport_cost(sc, 3.82, commodity=cm)

    # Simulate NDVI: healthy crop baseline with spatial variation
    ndvi_mean  = rng.uniform(0.50, 0.78, n)
    mu, sigma  = ndvi_mean.mean(), ndvi_mean.std()
    ndvi_z     = (ndvi_mean - mu) / max(sigma, 0.001)

    # Simulate SMAP: reasonable July soil moisture
    smap_ssm   = rng.uniform(0.15, 0.42, n)
    stress     = np.select(
        [smap_ssm < 0.10, smap_ssm < 0.20, smap_ssm > 0.50, smap_ssm > 0.40],
        ["SEVERE_DROUGHT","DRY_STRESS","WATERLOGGED","WET_STRESS"], default="OPTIMAL",
    )

    # Yield modifier
    ndvi_mod = np.select(
        [ndvi_z > 1.5, ndvi_z > 0.5, ndvi_z < -1.5, ndvi_z < -0.5],
        [1.15, 1.07, 0.82, 0.92], default=1.0,
    )
    smap_map = {"OPTIMAL":1.0,"WET_STRESS":0.97,"DRY_STRESS":0.93,
                "SEVERE_DROUGHT":0.88,"WATERLOGGED":0.91}
    smap_mod = np.array([smap_map[s] for s in stress])
    yield_mod = np.clip(ndvi_mod * smap_mod, 0.70, 1.25)

    ndvi_cat = pd.cut(
        ndvi_mean,
        bins=[-np.inf, 0.30, 0.55, 0.85, np.inf],
        labels=["Very Stressed","Stressed","Healthy","Dense Canopy"],
    )

    sc["ndvi_mean"]        = ndvi_mean
    sc["ndvi_z_score"]     = ndvi_z
    sc["ndvi_category"]    = ndvi_cat.astype(str)
    sc["smap_ssm_mean"]    = smap_ssm
    sc["smap_stress_flag"] = stress
    sc["yield_modifier"]   = yield_mod
    sc["satellite_risk"]   = np.clip(
        (1 - ndvi_mod) * 60 + (1 - smap_mod) * 40, 0, 100,
    )

    # Apply modifier to production cost model
    sc["yield_bu_acre"] = (59.0 if cm == "soybean" else 202.0) * yield_mod
    sc = calculate_production_costs(sc, 115.0, commodity=cm)
    return sc

# ---------------------------------------------------------------------------
# Session state + run
# ---------------------------------------------------------------------------

if "sat_df" not in st.session_state:
    st.session_state.sat_df = None
if "sat_mode" not in st.session_state:
    st.session_state.sat_mode = None

def fetch_live():
    pipeline = GEEPipeline(project_id=gee_project or None)
    if not pipeline.authenticate():
        st.error(
            "GEE authentication failed. Run the following once in a terminal: "
            "`import ee; ee.Authenticate(); ee.Initialize()`. "
            "Then return here and click Fetch Satellite Data."
        )
        return

    cent  = _cent()
    sc    = cent[cent["state_fips"] == state_fips]
    fips_list = sc["fips_code"].tolist()

    with st.spinner(f"Fetching NDVI and SMAP for {len(fips_list)} counties from GEE..."):
        results  = pipeline.fetch_all(fips_list, sc, year=year_sel, crop=commodity)
        combined = results["combined"]
        modifiers= pipeline.build_yield_modifiers(combined, crop=commodity)
        combined = combined.merge(modifiers[["fips_code","yield_modifier"]], on="fips_code", how="left")

        fac = _fac()
        full = sc.copy()
        full = calculate_spatial_logistics(full, fac)
        full = calculate_transport_cost(full, 3.82, commodity=commodity)
        full = full.merge(combined, on="fips_code", how="left")

        if "yield_modifier" in full.columns:
            base_yield = 59.0 if commodity == "soybean" else 202.0
            full["yield_bu_acre"] = base_yield * full["yield_modifier"].fillna(1.0)

        full = calculate_production_costs(full, 115.0, commodity=commodity)
        st.session_state.sat_df   = full
        st.session_state.sat_mode = "live"

def load_demo():
    with st.spinner("Loading demo satellite data..."):
        df = _make_demo(state_fips, commodity, year_sel, season_key)
        st.session_state.sat_df   = df
        st.session_state.sat_mode = "demo"

if run_btn:
    fetch_live()
elif demo_btn or st.session_state.sat_df is None:
    load_demo()

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

df   = st.session_state.sat_df
mode = st.session_state.sat_mode
base = plotly_layout_defaults()

if mode == "demo":
    st.info(
        "Showing synthetic demo data. Click Fetch Satellite Data with an authenticated "
        "GEE account to load live MODIS NDVI and NASA SMAP observations."
    )

if df is None or df.empty:
    st.warning("No satellite data available. Ensure county centroids are cached.")
    st.stop()

# ---------------------------------------------------------------------------
# KPI strip
# ---------------------------------------------------------------------------

has_ndvi = "ndvi_mean" in df.columns
has_smap = "smap_ssm_mean" in df.columns
has_mod  = "yield_modifier" in df.columns

k1, k2, k3, k4, k5 = st.columns(5)

with k1:
    val = f"{df['ndvi_mean'].mean():.3f}" if has_ndvi else "N/A"
    st.metric("Mean NDVI", val, help="MODIS MOD13A2 — growing-season composite")
with k2:
    if has_ndvi:
        stressed = (df["ndvi_mean"] < 0.55).mean() * 100
        st.metric("Counties Stressed", f"{stressed:.1f}%", help="NDVI below 0.55 threshold")
    else:
        st.metric("Counties Stressed", "N/A")
with k3:
    if has_smap:
        st.metric("Soil Moisture", f"{df['smap_ssm_mean'].mean():.3f} m³/m³",
                  help="NASA SMAP root-zone surface soil moisture — county mean for selected month")
    else:
        st.metric("Soil Moisture", "N/A")
with k4:
    if has_smap:
        drought = df.get("smap_stress_flag","").isin(["DRY_STRESS","SEVERE_DROUGHT"]).mean()*100
        st.metric("Drought Stress", f"{drought:.1f}%")
    else:
        st.metric("Drought Stress", "N/A")
with k5:
    if has_mod:
        avg_mod = df["yield_modifier"].mean()
        st.metric("Yield Modifier", f"{avg_mod:.3f}x",
                  delta=f"{(avg_mod-1)*100:+.1f}% vs. trend",
                  delta_color="normal" if avg_mod >= 1 else "inverse",
                  help="Combined NDVI + SMAP yield modifier applied to trend yield. Values >1.0 indicate above-trend growing conditions.")
    else:
        st.metric("Yield Modifier", "N/A")

st.divider()

# ---------------------------------------------------------------------------
# Map + charts
# ---------------------------------------------------------------------------

map_col, chart_col = st.columns([3, 2])

with map_col:
    section_label("NDVI Health Map by County")

    if has_ndvi:
        ndvi_df = df.dropna(subset=["lat","lon","ndvi_mean"])

        # Color scale: deep red (stressed) -> dark green (healthy)
        def _ndvi_color(v):
            if v < 0.30: return [185, 28, 28, 210]
            if v < 0.45: return [194, 65, 12, 210]
            if v < 0.55: return [180, 83, 9, 210]
            if v < 0.70: return [74, 222, 128, 210]
            return [21, 128, 61, 210]

        ndvi_df = ndvi_df.copy()
        ndvi_df["ndvi_color"] = ndvi_df["ndvi_mean"].apply(_ndvi_color)

        ndvi_layer = pdk.Layer(
            "ScatterplotLayer",
            data=ndvi_df[["lat","lon","ndvi_color","county_name","ndvi_mean",
                           "ndvi_z_score","yield_modifier"]].dropna(subset=["lat","lon"]),
            get_position=["lon","lat"],
            get_fill_color="ndvi_color",
            get_line_color=[255, 255, 255, 60],
            stroked=True,
            line_width_min_pixels=1,
            get_radius=8000,
            pickable=True,
            opacity=0.88,
        )

        ctrs = {
            "19":(42.0,-93.5,7),"17":(40.0,-89.2,7),"18":(40.3,-86.1,7),
            "39":(40.4,-82.5,7),"27":(46.4,-94.7,6),"31":(41.5,-99.9,6),
        }
        clat, clon, zoom = ctrs.get(state_fips, (41.5,-93.5,7))

        st.pydeck_chart(pdk.Deck(
            layers=[ndvi_layer],
            initial_view_state=pdk.ViewState(latitude=clat, longitude=clon, zoom=zoom),
            tooltip={
                "html":
                    "<div style='font-family:\"IBM Plex Sans\",sans-serif;padding:4px'>"
                    "<b>{county_name}</b><br/>"
                    "<span style='color:#aaa;font-size:11px'>NDVI mean:</span> "
                    "<b>{ndvi_mean}</b><br/>"
                    "<span style='color:#aaa;font-size:11px'>NDVI z-score:</span> "
                    "<b>{ndvi_z_score}</b><br/>"
                    "<span style='color:#aaa;font-size:11px'>Yield modifier:</span> "
                    "<b>{yield_modifier}x</b></div>",
                "style": {
                    "backgroundColor":"#0f2419","color":"#f0f4ee",
                    "borderRadius":"2px","padding":"10px 14px",
                },
            },
            map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        ), width="stretch")

        # NDVI legend
        leg = st.columns(5)
        leg_items = [
            ("< 0.30", "Very Stressed",  "#b91c1c"),
            ("0.30-0.45","Stressed",     "#c2410c"),
            ("0.45-0.55","Moderate",     "#b45309"),
            ("0.55-0.70","Healthy",      "#4ade80"),
            ("> 0.70", "Dense Canopy",   "#15803d"),
        ]
        for col, (val, label, color) in zip(leg, leg_items):
            col.markdown(
                f"<div style='display:flex;align-items:center;gap:5px;margin-top:4px'>"
                f"<div style='width:9px;height:9px;border-radius:50%;background:{color}'></div>"
                f"<span style='font-size:0.72rem;color:#5a5a52'>{val}<br/>{label}</span></div>",
                unsafe_allow_html=True,
            )
    else:
        st.info("NDVI data not available. Run satellite fetch to populate the map.")

with chart_col:
    t1, t2, t3 = st.tabs(["NDVI Distribution","SMAP Soil Moisture","Yield Impact"])

    with t1:
        if has_ndvi:
            fig_ndvi = px.histogram(
                df.dropna(subset=["ndvi_mean"]), x="ndvi_mean",
                nbins=30,
                color_discrete_sequence=["#1a472a"],
                labels={"ndvi_mean":"NDVI (mean growing-season value)"},
            )
            fig_ndvi.add_vline(x=0.55, line_dash="dash", line_color="#b45309",
                               annotation_text="Stress threshold (0.55)",
                               annotation_font_size=9)
            fig_ndvi.add_vline(x=0.70, line_dash="dot", line_color="#15803d",
                               annotation_text="Healthy (0.70+)",
                               annotation_font_size=9)
            fig_ndvi.update_layout(**base, height=220, showlegend=False)
            st.plotly_chart(fig_ndvi, width="stretch", config={"displayModeBar": False})

            if "ndvi_category" in df.columns:
                cat_vc = df["ndvi_category"].value_counts()
                fig_cat = go.Figure(go.Bar(
                    x=cat_vc.values, y=cat_vc.index,
                    orientation="h",
                    marker_color=["#b91c1c","#c2410c","#4ade80","#15803d"],
                    text=cat_vc.values, textposition="inside",
                    textfont=dict(size=10, family="IBM Plex Mono"),
                ))
                fig_cat.update_layout(
                    **base, height=185, showlegend=False,
                    xaxis_title="Number of counties",
                )
                st.plotly_chart(fig_cat, width="stretch", config={"displayModeBar": False})

    with t2:
        if has_smap:
            fig_smap = px.histogram(
                df.dropna(subset=["smap_ssm_mean"]),
                x="smap_ssm_mean", nbins=25,
                color_discrete_sequence=["#2563eb"],
                labels={"smap_ssm_mean":"Soil moisture (m\u00b3/m\u00b3)"},
            )
            fig_smap.add_vrect(x0=0.20, x1=0.40, fillcolor="rgba(21,128,61,0.08)",
                               line_width=0, annotation_text="Optimal zone",
                               annotation_font_size=9)
            fig_smap.update_layout(**base, height=210, showlegend=False)
            st.plotly_chart(fig_smap, width="stretch", config={"displayModeBar": False})

            if "smap_stress_flag" in df.columns:
                stress_vc = df["smap_stress_flag"].value_counts()
                stress_colors = {
                    "OPTIMAL":       "#15803d",
                    "WET_STRESS":    "#3b82f6",
                    "DRY_STRESS":    "#f97316",
                    "SEVERE_DROUGHT":"#b91c1c",
                    "WATERLOGGED":   "#2563eb",
                }
                fig_st = go.Figure(go.Bar(
                    x=stress_vc.values, y=stress_vc.index,
                    orientation="h",
                    marker_color=[stress_colors.get(s,"#9a9a90") for s in stress_vc.index],
                    text=stress_vc.values, textposition="inside",
                    textfont=dict(size=10, family="IBM Plex Mono"),
                ))
                fig_st.update_layout(
                    **base, height=200, showlegend=False,
                    xaxis_title="Number of counties",
                )
                st.plotly_chart(fig_st, width="stretch", config={"displayModeBar": False})

    with t3:
        if has_mod:
            fig_mod = px.histogram(
                df.dropna(subset=["yield_modifier"]),
                x="yield_modifier", nbins=25,
                color_discrete_sequence=["#2d6a4f"],
                labels={"yield_modifier":"Yield modifier (x)"},
            )
            fig_mod.add_vline(x=1.0, line_dash="dash", line_color="#9a9a90",
                              annotation_text="Trend yield baseline",
                              annotation_font_size=9)
            fig_mod.update_layout(**base, height=195, showlegend=False)
            st.plotly_chart(fig_mod, width="stretch", config={"displayModeBar": False})

            # Scatter: NDVI vs yield modifier
            if has_ndvi:
                fig_nv = px.scatter(
                    df.dropna(subset=["ndvi_mean","yield_modifier"]),
                    x="ndvi_mean", y="yield_modifier",
                    color="net_margin_per_acre" if "net_margin_per_acre" in df.columns else None,
                    color_continuous_scale="RdYlGn",
                    hover_data=["county_name"],
                    labels={"ndvi_mean":"NDVI mean","yield_modifier":"Yield modifier (x)"},
                    opacity=0.75,
                )
                fig_nv.add_hline(y=1.0, line_dash="dash", line_color="#9a9a90")
                fig_nv.update_layout(
                    **base, height=200,
                    coloraxis_colorbar=dict(title="Net Margin ($/ac)", thickness=10),
                )
                st.plotly_chart(fig_nv, width="stretch", config={"displayModeBar": False})

st.divider()

# ---------------------------------------------------------------------------
# Profitability impact table
# ---------------------------------------------------------------------------

section_label("Net Margin with Satellite Yield Modifier vs. Trend Baseline")
if "net_margin_per_acre" in df.columns and has_mod:
    compare_cols = [c for c in [
        "county_name","ndvi_mean","ndvi_z_score","smap_ssm_mean","smap_stress_flag",
        "yield_modifier","adj_yield_bu_acre","net_margin_per_acre","risk_tier",
    ] if c in df.columns]

    top_n = st.slider("Show top N counties by absolute yield modifier deviation",
                      5, 30, 15, key="sat_topn")
    deviated = df.assign(
        abs_dev=(df["yield_modifier"] - 1.0).abs()
    ).nlargest(top_n, "abs_dev")[compare_cols].copy()

    def _hl_mod(val):
        if isinstance(val, float):
            if val < 0.92: return "background-color:#fee2e2;color:#7f1d1d"
            if val > 1.08: return "background-color:#dcfce7;color:#14532d"
        return ""

    def _hl_tier(val):
        return {
            "HIGH":"background-color:#fee2e2;color:#7f1d1d",
            "ELEVATED":"background-color:#ffedd5;color:#7c2d12",
            "MODERATE":"background-color:#fef3c7;color:#78350f",
            "HEALTHY":"background-color:#dcfce7;color:#14532d",
        }.get(val,"")

    fmt = {}
    if "ndvi_mean" in deviated.columns:
        fmt["ndvi_mean"]      = "{:.3f}"
        fmt["ndvi_z_score"]   = "{:+.2f}"
    if "smap_ssm_mean" in deviated.columns:
        fmt["smap_ssm_mean"]  = "{:.3f}"
    if "yield_modifier" in deviated.columns:
        fmt["yield_modifier"] = "{:.3f}x"
    if "adj_yield_bu_acre" in deviated.columns:
        fmt["adj_yield_bu_acre"] = "{:.1f}"
    if "net_margin_per_acre" in deviated.columns:
        fmt["net_margin_per_acre"] = "${:.0f}"

    styled = deviated.style
    if "yield_modifier" in deviated.columns:
        styled = styled.map(_hl_mod, subset=["yield_modifier"])
    if "risk_tier" in deviated.columns:
        styled = styled.map(_hl_tier, subset=["risk_tier"])
    styled = styled.format(fmt)

    st.dataframe(styled, width="stretch", height=320)

    st.download_button(
        "Download Satellite County Data",
        data=df.drop(columns=[c for c in ["color","elevation","ndvi_color"] if c in df.columns])
                .to_csv(index=False),
        file_name=f"harvest_squeeze_satellite_{state_label.lower()}_{year_sel}.csv",
        mime="text/csv",
    )

footer()
