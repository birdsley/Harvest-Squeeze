"""
pages/1_National_Risk_View.py
------------------------------
National corn belt profitability risk overview.
Six-state simultaneous scan with choropleth and risk distribution charts.

v2.4 fixes:
  - plotly update_layout duplicate 'margin' and 'legend' kwargs resolved
  - use_container_width → width="stretch" (Streamlit 1.56+ migration)
"""

import os
import warnings

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
load_dotenv()

from config import SOY_COSTS, CORN_COSTS, RISK, LOGISTICS
from styles import (
    apply_theme, page_header, section_label, footer,
    plotly_layout_defaults, RISK_COLORS,
)
from data_acquisition import (
    load_value_chain_facilities, load_county_centroids,
    fetch_eia_diesel_price, fetch_fred_fertilizer_ppi,
)
from data_processing import (
    calculate_spatial_logistics, calculate_transport_cost,
    calculate_production_costs, summarize_risk_by_state,
)

st.set_page_config(
    page_title="National Risk View | Harvest Squeeze",
    layout="wide", initial_sidebar_state="expanded",
)
apply_theme()

page_header(
    "National Corn Belt Risk Overview",
    "Six-state simultaneous profitability scan &mdash; soybeans and corn, 2026",
)
st.divider()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        "<div style='padding:1.2rem 0 0.6rem'>"
        "<span style='font-family:Georgia,serif;font-size:1rem;"
        "font-weight:700;color:#f0f4ee'>National Risk Scan</span></div>",
        unsafe_allow_html=True,
    )
    st.divider()

    commodity = st.selectbox(
        "Commodity", ["soybean","corn"],
        format_func=lambda x: "Soybeans" if x == "soybean" else "Corn",
        key="natl_comm",
    )
    cbot = st.slider(
        "CBOT Price ($/bu)",
        min_value=8.0 if commodity == "soybean" else 3.5,
        max_value=14.0 if commodity == "soybean" else 6.5,
        value=10.50 if commodity == "soybean" else 4.35, step=0.10, key="natl_cbot",
    )
    land_rent  = st.slider("Land Rent ($/acre)",  100,  500, 248, step=10,   key="natl_lr")
    diesel_man = st.slider("Diesel ($/gal)",      2.50, 6.00, 3.82, step=0.05, key="natl_d")
    run_btn    = st.button("Run National Scan", type="primary", width="stretch")

STATES = [
    ("Iowa","19"), ("Illinois","17"), ("Indiana","18"),
    ("Ohio","39"), ("Minnesota","27"), ("Nebraska","31"),
]

FIPS_TO_ABBR = {
    "19":"IA","17":"IL","18":"IN","39":"OH","27":"MN","31":"NE",
}

# ---------------------------------------------------------------------------
# Cached loaders
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def _fac():
    return load_value_chain_facilities()

@st.cache_data(ttl=3600, show_spinner=False)
def _cent():
    return load_county_centroids()

@st.cache_data(ttl=1800, show_spinner=False)
def _run_state(fips, diesel, ppi, cm, cb, lr):
    fac  = _fac()
    cent = _cent()
    sc   = cent[cent["state_fips"] == fips].copy()
    if sc.empty:
        return pd.DataFrame()
    df = calculate_spatial_logistics(sc, fac)
    df = calculate_transport_cost(df, diesel, commodity=cm)
    df = calculate_production_costs(df, fertilizer_ppi=ppi, commodity=cm)

    base_lr = SOY_COSTS.land_rent if cm == "soybean" else CORN_COSTS.land_rent
    df["revenue_per_acre"]       = df.get("adj_yield_bu_acre", 50.0) * cb
    df["total_production_cost"] += lr - base_lr
    df["net_margin_per_acre"]    = (
        df["revenue_per_acre"]
        - df.get("basis_deduction_per_acre", 0)
        - df["total_production_cost"]
    )
    df["net_margin_score"] = (
        df["net_margin_per_acre"] / df["revenue_per_acre"].replace(0, np.nan)
    ).clip(-2, 1)

    conds = [
        df["net_margin_score"] <= RISK.high_risk_ceiling,
        df["net_margin_score"] <= RISK.elevated_risk_ceiling,
        df["net_margin_score"] <= RISK.moderate_risk_ceiling,
    ]
    df["risk_tier"] = np.select(conds, ["HIGH","ELEVATED","MODERATE"], default="HEALTHY")
    return df

# ---------------------------------------------------------------------------
# Session state + run
# ---------------------------------------------------------------------------

if "natl_df" not in st.session_state:
    st.session_state.natl_df = None

def run_national():
    eff_d = (fetch_eia_diesel_price() if os.getenv("EIA_API_KEY") else None) or diesel_man
    eff_p = (fetch_fred_fertilizer_ppi() if os.getenv("FRED_API_KEY") else None) or 115.0

    frames = []
    bar = st.progress(0, text="Running state models...")
    for i, (sname, sfips) in enumerate(STATES):
        bar.progress((i+1)/len(STATES), text=f"Modeling {sname}...")
        df = _run_state(sfips, eff_d, eff_p, commodity, cbot, land_rent)
        if not df.empty:
            df["state_label"] = sname
            frames.append(df)
    bar.empty()
    if frames:
        st.session_state.natl_df = pd.concat(frames, ignore_index=True)

if run_btn:
    run_national()
if st.session_state.natl_df is None:
    with st.spinner("Building demo model..."):
        run_national()

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

if st.session_state.natl_df is not None:
    ndf = st.session_state.natl_df
    base = plotly_layout_defaults()

    state_sum = summarize_risk_by_state(ndf)
    state_sum["state_abbr"]  = state_sum["state_fips"].map(FIPS_TO_ABBR)
    state_sum["state_label"] = ndf.groupby("state_fips")["state_label"].first().reindex(
        state_sum["state_fips"].values).values

    # KPIs
    n          = len(ndf)
    pct_high   = (ndf["risk_tier"] == "HIGH").mean() * 100
    pct_elev   = (ndf["risk_tier"] == "ELEVATED").mean() * 100
    pct_hlthy  = (ndf["risk_tier"] == "HEALTHY").mean() * 100
    worst      = state_sum.sort_values("mean_nms").iloc[0]["state_label"]
    best       = state_sum.sort_values("mean_nms").iloc[-1]["state_label"]

    k1,k2,k3,k4,k5,k6 = st.columns(6)
    k1.metric("Counties Modeled",    n)
    k2.metric("High Risk",  f"{pct_high:.1f}%",  help="6-state share of counties in loss territory (net margin < 0)")
    k3.metric("Elevated",   f"{pct_elev:.1f}%",  help="6-state share of counties with razor-thin margins (NMS 0–5%)")
    k4.metric("Healthy",    f"{pct_hlthy:.1f}%", help="6-state share of counties with healthy margins (NMS > 12%)")
    k5.metric("Most At-Risk",       worst,               help="State with lowest mean Net Margin Score")
    k6.metric("Strongest State",     best,                help="State with highest mean Net Margin Score")
    st.divider()

    # Choropleth + stacked bar
    map_col, bar_col = st.columns([3, 2])

    with map_col:
        section_label("State-Level Mean Net Margin ($/acre)")
        fig_map = px.choropleth(
            state_sum,
            locations="state_abbr",
            locationmode="USA-states",
            color="mean_margin_per_acre",
            hover_name="state_label",
            hover_data={
                "mean_margin_per_acre": ":.0f",
                "pct_high_risk":        ":.1f",
                "median_crusher_dist":  ":.0f",
                "state_abbr": False,
            },
            color_continuous_scale=[
                [0.0, "#b91c1c"], [0.25, "#c2410c"],
                [0.5,  "#b45309"], [0.75, "#86efac"],
                [1.0,  "#15803d"],
            ],
            scope="usa",
            labels={
                "mean_margin_per_acre": "Mean Margin ($/acre)",
                "pct_high_risk":        "High Risk (%)",
                "median_crusher_dist":  "Median Crusher Dist (mi)",
            },
        )
        # v2.4 FIX: strip margin/legend from base to avoid duplicate kwarg TypeError
        _base_clean = {k: v for k, v in base.items() if k not in ("margin", "legend")}
        fig_map.update_layout(
            **_base_clean,
            height=400,
            margin=dict(l=0, r=0, t=10, b=0),
            coloraxis_colorbar=dict(
                title="$/acre", thickness=12,
                tickfont=dict(size=9, family="IBM Plex Mono"),
            ),
            geo=dict(bgcolor="rgba(0,0,0,0)", lakecolor="#f8f7f4"),
        )
        st.plotly_chart(fig_map, width="stretch", config={"displayModeBar": False})

    with bar_col:
        section_label("Risk Distribution by State")
        risk_order = ["HIGH","ELEVATED","MODERATE","HEALTHY"]
        bar_data = []
        for _, row in state_sum.sort_values("mean_nms").iterrows():
            state_rows = ndf[ndf["state_fips"] == row["state_fips"]]
            vc = state_rows["risk_tier"].value_counts(normalize=True) * 100
            for tier in risk_order:
                bar_data.append({
                    "state":  row["state_label"],
                    "tier":   tier,
                    "pct":    vc.get(tier, 0),
                })
        bar_df = pd.DataFrame(bar_data)

        fig_bar = px.bar(
            bar_df, x="pct", y="state", color="tier",
            orientation="h",
            color_discrete_map=RISK_COLORS,
            category_orders={"tier": risk_order},
            labels={"pct": "% of counties", "state": "", "tier": "Risk Tier"},
        )
        fig_bar.update_layout(
            **base, height=400, barmode="stack",
            xaxis=dict(range=[0,100], ticksuffix="%"),
        )
        st.plotly_chart(fig_bar, width="stretch", config={"displayModeBar": False})

    st.divider()

    # Scatter: margin vs crusher distance across all states
    section_label("County-Level Net Margin vs. Crusher Distance — All Six States")
    fig_sc = px.scatter(
        ndf.dropna(subset=["crusher_dist_miles","net_margin_per_acre"]),
        x="crusher_dist_miles", y="net_margin_per_acre",
        color="risk_tier", symbol="state_label",
        hover_data=["county_name","state_label"],
        color_discrete_map=RISK_COLORS,
        labels={
            "crusher_dist_miles":    "Miles to Nearest Crusher",
            "net_margin_per_acre":   "Net Margin ($/acre)",
            "state_label":           "State",
        },
        opacity=0.72,
    )
    fig_sc.add_hline(y=0, line_dash="dash", line_color="#9a9a90",
                     annotation_text="Break-even", annotation_font_size=9)
    fig_sc.add_vline(
        x=LOGISTICS.distance_threshold_miles, line_dash="dot", line_color="#c8c4be",
        annotation_text=f"Distance penalty >{LOGISTICS.distance_threshold_miles:.0f} mi",
        annotation_font_size=9,
    )
    fig_sc.update_layout(**base, height=360)
    st.plotly_chart(fig_sc, width="stretch", config={"displayModeBar": False})

    st.divider()

    # State summary table
    section_label("State Summary")
    disp = state_sum[[
        "state_label","n_counties","mean_margin_per_acre","pct_high_risk",
        "pct_healthy","median_crusher_dist","median_transport_cost",
    ]].rename(columns={
        "state_label":           "State",
        "n_counties":            "Counties",
        "mean_margin_per_acre":  "Mean Margin ($/ac)",
        "pct_high_risk":         "High Risk (%)",
        "pct_healthy":           "Healthy (%)",
        "median_crusher_dist":   "Median Crusher (mi)",
        "median_transport_cost": "Median Transport ($/bu)",
    })

    def _row_hl(row):
        mm = row["Mean Margin ($/ac)"]
        c  = ("#fee2e2" if mm < 0 else "#ffedd5" if mm < 20
               else "#fef3c7" if mm < 50 else "#dcfce7")
        return [f"background-color:{c}"] * len(row)

    st.dataframe(
        disp.style.apply(_row_hl, axis=1).format({
            "Mean Margin ($/ac)":      "${:.0f}",
            "High Risk (%)":           "{:.1f}%",
            "Healthy (%)":             "{:.1f}%",
            "Median Crusher (mi)":     "{:.0f}",
            "Median Transport ($/bu)": "${:.3f}",
        }),
        width="stretch", height=260,
    )

    st.download_button(
        "Download 6-State CSV",
        data=ndf.drop(columns=[c for c in ["color","elevation"] if c in ndf.columns])
                .to_csv(index=False),
        file_name=f"harvest_squeeze_national_{commodity}.csv",
        mime="text/csv",
    )

footer()
