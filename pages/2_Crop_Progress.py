"""
pages/2_Crop_Progress.py
-------------------------
USDA weekly crop progress and condition tracker.
Planting pace S-curves, Crop Condition Index, multi-state comparison.
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

from styles import (
    apply_theme, page_header, section_label, footer,
    plotly_layout_defaults,
)
from crop_progress import (
    fetch_crop_progress, fetch_crop_condition,
    calculate_crop_condition_index, calculate_planting_pace_score,
    get_latest_condition_snapshot, get_demo_crop_progress,
    CORN_BELT_STATES, PLANTING_PACE_BENCHMARKS,
)

st.set_page_config(
    page_title="Crop Progress | Harvest Squeeze",
    layout="wide", initial_sidebar_state="expanded",
)
apply_theme()

page_header(
    "Crop Progress and Condition Tracker",
    "USDA NASS weekly growing-season data &mdash; forward-looking stress signals",
)
st.divider()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        "<div style='padding:1.2rem 0 0.6rem'>"
        "<span style='font-family:Georgia,serif;font-size:1rem;"
        "font-weight:700;color:#f0f4ee'>Crop Progress</span></div>",
        unsafe_allow_html=True,
    )
    st.divider()

    commodity_sel  = st.selectbox("Commodity", ["soybean","corn"],
        format_func=lambda x: "Soybeans" if x == "soybean" else "Corn",
        key="cp_comm")
    usda_commodity = "SOYBEANS" if commodity_sel == "soybean" else "CORN"
    state_sel      = st.selectbox("State", CORN_BELT_STATES, key="cp_state")
    year_sel       = st.selectbox("Crop Year", [2025, 2024, 2023], key="cp_year")

    st.divider()
    st.markdown(
        "<div style='font-size:0.72rem;font-weight:600;text-transform:uppercase;"
        "letter-spacing:0.1em;color:#a0b09a'>Multi-State Comparison</div>",
        unsafe_allow_html=True,
    )
    st.markdown("")
    compare_states = st.multiselect(
        "Compare States",
        CORN_BELT_STATES,
        default=["IOWA","ILLINOIS","MINNESOTA","NEBRASKA"],
        key="cp_multi",
    )
    run_btn = st.button("Load Data", type="primary", width="stretch")

has_usda = bool(os.getenv("USDA_API_KEY"))

# ---------------------------------------------------------------------------
# Cached loaders
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def _progress(comm, state, year, unit):
    return fetch_crop_progress(comm, state, year, unit_desc=unit)

@st.cache_data(ttl=3600, show_spinner=False)
def _condition(comm, state, year):
    return fetch_crop_condition(comm, state, year)

# ---------------------------------------------------------------------------
# Session state + data loading
# ---------------------------------------------------------------------------

for k in ["cp_progress","cp_condition","cp_cci","cp_multi_df"]:
    if k not in st.session_state:
        st.session_state[k] = None

def load_data():
    if has_usda:
        prog  = _progress(usda_commodity, state_sel, year_sel, None)
        cond  = _condition(usda_commodity, state_sel, year_sel)
        cci   = calculate_crop_condition_index(cond) if not cond.empty else pd.DataFrame()
        multi = []
        for s in compare_states:
            try:
                df = _progress(usda_commodity, s, year_sel, "PCT PLANTED")
                if not df.empty:
                    multi.append(df)
            except Exception:
                pass
        multi_df = pd.concat(multi, ignore_index=True) if multi else pd.DataFrame()
    else:
        demo  = get_demo_crop_progress(commodity_sel, state_sel, year_sel)
        prog  = demo["progress"]
        cond  = demo["condition"]
        cci   = demo["cci"]
        multi = []
        for s in compare_states:
            d = get_demo_crop_progress(commodity_sel, s, year_sel)
            multi.append(d["progress"][d["progress"]["unit_desc"] == "PCT PLANTED"])
        multi_df = pd.concat(multi, ignore_index=True) if multi else pd.DataFrame()

    st.session_state.cp_progress = prog
    st.session_state.cp_condition = cond
    st.session_state.cp_cci       = cci
    st.session_state.cp_multi_df  = multi_df

if run_btn or st.session_state.cp_progress is None:
    with st.spinner("Loading crop progress data..."):
        load_data()

if not has_usda:
    st.info(
        "Demo mode: showing simulated crop progress data. "
        "Add USDA_API_KEY to .env to load live weekly NASS reports."
    )

prog_df = st.session_state.cp_progress
cond_df = st.session_state.cp_condition
cci_df  = st.session_state.cp_cci
base    = plotly_layout_defaults()

# ---------------------------------------------------------------------------
# KPI strip
# ---------------------------------------------------------------------------

if cond_df is not None and not cond_df.empty:
    snap = get_latest_condition_snapshot(cond_df)

    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        cci_val = snap.get("cci")
        st.metric("Latest CCI",
                  f"{cci_val:.1f} / 100" if cci_val else "N/A",
                  help="Crop Condition Index (0–100). EXCELLENT=100, VERY POOR=0. Score ≥65 is bullish, ≤45 is bearish.")
    with k2:
        st.metric("Good + Excellent", f"{snap.get('pct_good_excellent',0):.0f}%")
    with k3:
        st.metric("Poor + Very Poor", f"{snap.get('pct_poor_very_poor',0):.0f}%")
    with k4:
        sig = snap.get("cci_signal","N/A")
        sig_display = sig.replace("_"," ").replace("CROP","").strip().title()
        st.metric("Market Signal", sig_display)
    with k5:
        wk = snap.get("week_ending")
        st.metric("Report Week", wk.strftime("%b %d, %Y") if pd.notna(wk) else "N/A")
    st.divider()

# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------

left_col, right_col = st.columns([3, 2])

with left_col:
    if prog_df is not None and not prog_df.empty:
        section_label(f"{state_sel.title()} — {usda_commodity.title()} Progress Curves")
        available = prog_df["unit_desc"].unique().tolist()
        defaults  = [m for m in ["PCT PLANTED","PCT EMERGED","PCT BLOOMING"] if m in available]

        selected = st.multiselect(
            "Select progress stages",
            available, default=defaults, key="cp_stages",
        )
        if selected:
            plot_df = prog_df[prog_df["unit_desc"].isin(selected)]
            fig_p = px.line(
                plot_df, x="week_ending", y="pct_value", color="unit_desc",
                labels={"week_ending":"Week","pct_value":"Percent complete","unit_desc":"Stage"},
                markers=True, color_discrete_sequence=[
                    "#1a472a","#2d6a4f","#c8a951","#b91c1c","#c2410c",
                ],
            )
            if "PCT PLANTED" in selected:
                bench = PLANTING_PACE_BENCHMARKS.get(commodity_sel, {}).get(state_sel)
                if bench:
                    fig_p.add_hline(
                        y=bench, line_dash="dash", line_color="#9a9a90",
                        annotation_text=f"5-yr avg: {bench}%",
                        annotation_position="bottom right", annotation_font_size=9,
                    )     
            fig_p.update_layout(
                **base,
                height=310,
                yaxis=dict(range=[0, 105], ticksuffix="%"),
            )
            st.plotly_chart(fig_p, width="stretch", config={"displayModeBar": False})

    # CCI trend
    if cci_df is not None and not cci_df.empty:
        section_label("Crop Condition Index Trend")
        fig_cci = go.Figure()
        fig_cci.add_trace(go.Scatter(
            x=cci_df["week_ending"], y=cci_df["cci"],
            mode="lines+markers", name="CCI",
            line=dict(color="#1a472a", width=2.2),
            marker=dict(size=5),
            fill="tozeroy", fillcolor="rgba(26,71,42,0.06)",
        ))
        if "pct_good_excellent" in cci_df.columns:
            fig_cci.add_trace(go.Scatter(
                x=cci_df["week_ending"], y=cci_df["pct_good_excellent"],
                mode="lines", name="Good + Excellent (%)",
                line=dict(color="#2563eb", width=1.4, dash="dot"),
            ))
        fig_cci.add_hrect(y0=65, y1=100, fillcolor="rgba(21,128,61,0.04)", line_width=0,
                          annotation_text="Bullish zone (CCI >= 65)",
                          annotation_font_size=8, annotation_position="top right")
        fig_cci.add_hrect(y0=0, y1=45, fillcolor="rgba(185,28,28,0.04)", line_width=0,
                          annotation_text="Bearish zone (CCI <= 45)",
                          annotation_font_size=8, annotation_position="bottom right")
        fig_cci.add_hline(y=62, line_dash="dot", line_color="#c8c4be",
                          annotation_text="Historical avg ~62", annotation_font_size=8)
        fig_cci.update_layout(
            **base,
            height=310,
            yaxis=dict(range=[0, 105], ticksuffix="%"),
        )
        st.plotly_chart(fig_cci, width="stretch", config={"displayModeBar": False})

with right_col:
    # Condition breakdown — horizontal bar
    if cond_df is not None and not cond_df.empty:
        section_label("Condition Breakdown — Latest Week")
        latest_wk   = cond_df["week_ending"].max()
        latest_cond = cond_df[cond_df["week_ending"] == latest_wk].copy()
        cond_order  = ["EXCELLENT","GOOD","FAIR","POOR","VERY POOR"]
        cond_colors = {
            "EXCELLENT": "#15803d",
            "GOOD":      "#4ade80",
            "FAIR":      "#fbbf24",
            "POOR":      "#f97316",
            "VERY POOR": "#b91c1c",
        }
        fig_cd = px.bar(
            latest_cond, x="pct_value", y="condition_label",
            orientation="h", color="condition_label",
            color_discrete_map=cond_colors,
            category_orders={"condition_label": cond_order},
            labels={"pct_value":"% of Crop","condition_label":""},
            text="pct_value",
        )
        fig_cd.update_traces(texttemplate="%{text:.0f}%", textposition="inside",
                             insidetextfont=dict(size=10, family="IBM Plex Mono"))
        fig_cd.update_layout(
            **base, height=255, showlegend=False,
            xaxis=dict(range=[0,65], ticksuffix="%"),
        )
        st.plotly_chart(fig_cd, width="stretch", config={"displayModeBar": False})

    # Multi-state planting pace
    multi_df = st.session_state.cp_multi_df
    if multi_df is not None and not multi_df.empty:
        section_label("Multi-State Planting Pace")
        fig_ms = px.line(
            multi_df, x="week_ending", y="pct_value", color="state_name",
            markers=True,
            labels={"week_ending":"Week","pct_value":"% Planted","state_name":"State"},
            color_discrete_sequence=["#1a472a","#2d6a4f","#c8a951","#b91c1c","#c2410c","#15803d"],
        )
        avg_bench = np.mean([
            PLANTING_PACE_BENCHMARKS.get(commodity_sel,{}).get(s, 50) for s in compare_states
        ])
        fig_ms.add_hline(y=avg_bench, line_dash="dash", line_color="#9a9a90",
                         annotation_text=f"Avg benchmark: {avg_bench:.0f}%",
                         annotation_font_size=8)
        fig_ms.update_layout(
            **base,
            height=310,
            yaxis=dict(range=[0, 105], ticksuffix="%"),
        )
        st.plotly_chart(fig_ms, width="stretch", config={"displayModeBar": False})

        # Pace score table
        section_label("Planting Pace vs. 5-Year Average")
        planted = multi_df[multi_df["unit_desc"] == "PCT PLANTED"]
        pace    = calculate_planting_pace_score(planted, commodity_key=commodity_sel)
        if not pace.empty:
            label_map = {
                "AHEAD":           "Ahead of average",
                "ON_TRACK":        "On track",
                "BEHIND":          "Behind average",
                "SEVERELY_BEHIND": "Severely behind",
            }
            pace["Status"] = pace["pace_flag"].map(label_map)
            disp = pace[["state_name","pct_planted","benchmark_pct","pace_delta","Status"]].rename(
                columns={"state_name":"State","pct_planted":"% Planted",
                          "benchmark_pct":"Benchmark","pace_delta":"Delta (pp)"})
            st.dataframe(
                disp.style.format({
                    "% Planted":    "{:.0f}%",
                    "Benchmark":    "{:.0f}%",
                    "Delta (pp)":   "{:+.1f}",
                }),
                width="stretch", height=205,
            )

st.divider()

# ---------------------------------------------------------------------------
# CCI to yield modifier mapping
# ---------------------------------------------------------------------------

section_label("Crop Condition Index to Yield Modifier Mapping")
st.markdown(
    "<p>The CCI maps directly to a yield adjustment factor applied in the profitability model. "
    "A CCI of 65 or above applies a modest yield uplift; a CCI at or below 45 triggers a "
    "proportional haircut. The chart below shows the full mapping curve.</p>",
    unsafe_allow_html=True,
)

cci_range  = np.arange(0, 101, 5)
yield_mods = np.select(
    [cci_range >= 75, cci_range >= 60, cci_range >= 45, cci_range >= 30],
    [1.08, 1.03, 1.00, 0.95], default=0.88,
)
mod_df = pd.DataFrame({"CCI": cci_range, "Yield Modifier": yield_mods})

fig_mod = go.Figure()
fig_mod.add_trace(go.Scatter(
    x=mod_df["CCI"], y=mod_df["Yield Modifier"],
    mode="lines+markers",
    line=dict(color="#1a472a", width=2),
    marker=dict(size=5),
    fill="tozeroy", fillcolor="rgba(26,71,42,0.06)",
))
fig_mod.add_hline(y=1.0, line_dash="dash", line_color="#9a9a90",
                  annotation_text="Baseline (no adjustment)", annotation_font_size=9)

if cond_df is not None and not cond_df.empty:
    live_cci = snap.get("cci")
    if live_cci:
        live_mod = float(np.interp(live_cci, cci_range, yield_mods))
        fig_mod.add_vline(x=live_cci, line_dash="dot", line_color="#c2410c",
                          annotation_text=f"Current CCI: {live_cci:.0f} ({live_mod:.2f}x)",
                          annotation_font_size=9)

fig_mod.update_layout(
    **base, height=215,
    xaxis=dict(title="Crop Condition Index", range=[0,100]),
    yaxis=dict(title="Yield modifier (x)", range=[0.82, 1.15], tickformat=".0%"),
    showlegend=False,
)
st.plotly_chart(fig_mod, width="stretch", config={"displayModeBar": False})

footer()
