"""
app.py  --  The Harvest Squeeze
--------------------------------
Main dashboard: county-level soybean/corn profitability risk map.
Professional multi-page Streamlit application.

Run:
    streamlit run app.py
"""

import os
import warnings
import logging

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

from config import SOY_COSTS, CORN_COSTS, LOGISTICS, RISK
from styles import (
    apply_theme, page_header, section_label, footer,
    plotly_layout_defaults, RISK_COLORS, RISK_RGBA,
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
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="The Harvest Squeeze | Profitability Risk Dashboard",
    page_icon="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>H</text></svg>",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        "<div style='padding:1.2rem 0 0.4rem'>"
        "<span style='font-family:Georgia,serif;font-size:1.15rem;"
        "font-weight:700;color:#f0f4ee;letter-spacing:-0.01em'>"
        "The Harvest Squeeze</span><br/>"
        "<span style='font-size:0.72rem;color:#6b8f74;"
        "text-transform:uppercase;letter-spacing:0.1em'>"
        "Profitability Risk &bull; 2026</span></div>",
        unsafe_allow_html=True,
    )
    st.divider()

    with st.expander("API Keys", expanded=False):
        for env, label, hint in [
            ("USDA_API_KEY", "USDA QuickStats",      "quickstats.nass.usda.gov"),
            ("FRED_API_KEY", "FRED St. Louis Fed",   "fred.stlouisfed.org"),
            ("EIA_API_KEY",  "EIA Energy",            "eia.gov/opendata"),
        ]:
            v = st.text_input(label, type="password",
                              value=os.getenv(env, ""), help=f"Free key: {hint}")
            if v:
                os.environ[env] = v

    st.divider()
    st.markdown("<div style='font-size:0.72rem;font-weight:600;text-transform:uppercase;"
                "letter-spacing:0.1em;color:#a0b09a'>Analysis Parameters</div>",
                unsafe_allow_html=True)
    st.markdown("")

    commodity = st.selectbox(
        "Commodity",
        ["soybean", "corn"],
        format_func=lambda x: "Soybeans" if x == "soybean" else "Corn",
    )
    pilot_state = st.selectbox(
        "Pilot State",
        [("Iowa","IOWA","19"),("Illinois","ILLINOIS","17"),
         ("Indiana","INDIANA","18"),("Ohio","OHIO","39"),
         ("Minnesota","MINNESOTA","27"),("Nebraska","NEBRASKA","31")],
        format_func=lambda x: x[0],
    )
    state_name, state_upper, state_fips = pilot_state
    yield_year = st.slider("USDA Yield Year", 2019, 2023, 2023)

    st.divider()
    st.markdown("<div style='font-size:0.72rem;font-weight:600;text-transform:uppercase;"
                "letter-spacing:0.1em;color:#a0b09a'>Scenario Overrides</div>",
                unsafe_allow_html=True)
    st.markdown("")

    cbot = st.slider(
        "CBOT Price ($/bu)",
        min_value=8.0 if commodity == "soybean" else 3.5,
        max_value=14.0 if commodity == "soybean" else 6.5,
        value=10.50 if commodity == "soybean" else 4.35, step=0.10,
    )
    land_rent  = st.slider("Land Rent ($/acre)", 100, 500, 248, step=10)
    diesel_man = st.slider("Diesel ($/gal)", 2.50, 6.00, 3.82, step=0.05)

    st.divider()
    st.markdown("<div style='font-size:0.72rem;font-weight:600;text-transform:uppercase;"
                "letter-spacing:0.1em;color:#a0b09a'>Map Layers</div>",
                unsafe_allow_html=True)
    st.markdown("")

    show_crush = st.toggle("NOPA Crushers",    value=True)
    show_term  = st.toggle("Export Terminals", value=True)
    show_3d    = st.toggle("3D Risk Columns",  value=False)

    st.markdown("")
    run_btn = st.button("Run Analysis", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

page_header(
    "The Harvest Squeeze",
    "Quantifying the growing vs. moving cost crisis in US soybeans and corn &mdash; 2026",
)

idx1, idx2, idx3, idx4, idx5 = st.columns(5)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

for k in ["model_df", "facilities", "fert_ppi", "diesel_live"]:
    if k not in st.session_state:
        st.session_state[k] = None

# ---------------------------------------------------------------------------
# Cached loaders
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def _load_facilities():
    return load_value_chain_facilities()

@st.cache_data(ttl=3600, show_spinner=False)
def _load_centroids():
    return load_county_centroids()

@st.cache_data(ttl=1800, show_spinner=False)
def _load_yields(state, yr, cm):
    fn = fetch_usda_soybean_yields if cm == "soybean" else fetch_usda_corn_yields
    return fn(state_name=state, year=yr)

@st.cache_data(ttl=1800, show_spinner=False)
def _load_fert_ppi():
    return fetch_fred_fertilizer_ppi()

@st.cache_data(ttl=900, show_spinner=False)
def _load_diesel():
    return fetch_eia_diesel_price()

@st.cache_data(ttl=1800, show_spinner=False)
def _load_fert_hist():
    return fetch_fred_fertilizer_history(months=24)

@st.cache_data(ttl=900, show_spinner=False)
def _load_diesel_hist():
    return fetch_eia_diesel_history(weeks=52)

# ---------------------------------------------------------------------------
# Load static data
# ---------------------------------------------------------------------------

with st.spinner("Loading facility and county data..."):
    try:
        fac = _load_facilities()
        st.session_state.facilities = fac
    except Exception as e:
        st.error(f"Facility data failed to load: {e}")
        fac = {k: pd.DataFrame() for k in ["crushers","export_terminals","biodiesel_plants","all"]}
    try:
        centroids = _load_centroids()
    except Exception as e:
        st.error(f"County centroids failed to load: {e}")
        centroids = pd.DataFrame()

# ---------------------------------------------------------------------------
# Live macro index strip
# ---------------------------------------------------------------------------

fert_ppi = diesel_live = None
try:
    with idx1:
        if os.getenv("FRED_API_KEY"):
            fert_ppi = _load_fert_ppi()
            st.metric("Fertilizer PPI", f"{fert_ppi:.1f}",
                      help="FRED series PCU3253113253111 — Nitrogenous Fertilizer PPI")
        else:
            st.metric("Fertilizer PPI", "N/A", help="Add FRED API key")
    with idx2:
        if os.getenv("EIA_API_KEY"):
            diesel_live = _load_diesel()
            st.metric("US Diesel", f"${diesel_live:.3f}/gal",
                      help="EIA Weekly No.2 Diesel Retail Price")
        else:
            st.metric("US Diesel", f"${diesel_man:.2f} (manual)")
    with idx3:
        label = "CBOT Soybeans" if commodity == "soybean" else "CBOT Corn"
        st.metric(label, f"${cbot:.2f}/bu")
    with idx4:
        st.metric("NOPA Crushers", len(fac.get("crushers", [])),
                  help="Operating soybean processors in dataset")
    with idx5:
        st.metric("Export Terminals", len(fac.get("export_terminals", [])),
                  help="River and ocean export facilities")
except Exception as e:
    st.warning(f"Could not load live indices: {e}")

st.divider()

# ---------------------------------------------------------------------------
# Analysis runner
# ---------------------------------------------------------------------------

def run_analysis():
    eff_diesel = diesel_live or diesel_man
    eff_ppi    = fert_ppi   or 115.0
    base_lr    = SOY_COSTS.land_rent if commodity == "soybean" else CORN_COSTS.land_rent

    with st.spinner(f"Running {commodity} profitability model for {state_name}..."):
        try:
            yield_df = _load_yields(state_upper, yield_year, commodity)
        except Exception:
            yield_df = pd.DataFrame()

        sc = centroids[centroids["state_fips"] == state_fips].copy()
        if not yield_df.empty:
            sc = sc.merge(yield_df[["fips_code","yield_bu_acre"]], on="fips_code", how="left")

        mdf = calculate_spatial_logistics(sc, fac)
        mdf = calculate_transport_cost(mdf, eff_diesel, commodity=commodity)
        mdf = calculate_production_costs(mdf, fertilizer_ppi=eff_ppi, commodity=commodity)

        mdf["revenue_per_acre"]       = mdf.get("adj_yield_bu_acre", 50.0) * cbot
        mdf["total_production_cost"] += land_rent - base_lr
        mdf["net_margin_per_acre"]    = (
            mdf["revenue_per_acre"]
            - mdf.get("basis_deduction_per_acre", 0)
            - mdf["total_production_cost"]
        )
        mdf["net_margin_score"] = (
            mdf["net_margin_per_acre"] / mdf["revenue_per_acre"].replace(0, np.nan)
        ).clip(-2, 1)

        conds = [
            mdf["net_margin_score"] <= RISK.high_risk_ceiling,
            mdf["net_margin_score"] <= RISK.elevated_risk_ceiling,
            mdf["net_margin_score"] <= RISK.moderate_risk_ceiling,
        ]
        mdf["risk_tier"]  = np.select(conds, ["HIGH","ELEVATED","MODERATE"], default="HEALTHY")
        mdf["color"]      = mdf["risk_tier"].map(RISK_RGBA)
        mdf["elevation"]  = np.clip(-mdf["net_margin_per_acre"] * 8, 0, 4000)

        st.session_state.model_df    = mdf
        st.session_state.fert_ppi   = eff_ppi
        st.session_state.diesel_live = eff_diesel


if run_btn:
    run_analysis()
if st.session_state.model_df is None and os.getenv("USDA_API_KEY"):
    run_analysis()

# Demo fallback
if st.session_state.model_df is None and not centroids.empty:
    st.info(
        "Demo mode: spatial model running with trend yields. "
        "Add API keys to load live USDA yield, FRED fertilizer, and EIA diesel data."
    )
    demo = centroids[centroids["state_fips"] == state_fips].copy()
    demo = calculate_spatial_logistics(demo, fac)
    demo = calculate_transport_cost(demo, diesel_man, commodity=commodity)
    trend = 59.0 if commodity == "soybean" else 202.0
    demo["yield_bu_acre"] = trend + np.random.default_rng(0).normal(0, 4, len(demo))
    demo = calculate_production_costs(demo, 115.0, commodity=commodity)
    demo["color"]     = demo["risk_tier"].map(RISK_RGBA)
    demo["elevation"] = np.clip(-demo["net_margin_per_acre"] * 8, 0, 4000)
    st.session_state.model_df = demo

# ---------------------------------------------------------------------------
# KPI strip
# ---------------------------------------------------------------------------

if st.session_state.model_df is not None:
    df = st.session_state.model_df

    section_label(f"{state_name} — Profitability Risk Summary")

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    n  = len(df)
    vc = df["risk_tier"].value_counts()
    with k1: st.metric("Total Counties", n)
    with k2: st.metric("High Risk",  vc.get("HIGH",0),     f"{vc.get('HIGH',0)/n*100:.0f}% of state")
    with k3: st.metric("Elevated",   vc.get("ELEVATED",0), f"{vc.get('ELEVATED',0)/n*100:.0f}% of state")
    with k4: st.metric("Moderate",   vc.get("MODERATE",0), f"{vc.get('MODERATE',0)/n*100:.0f}% of state")
    with k5: st.metric("Healthy",    vc.get("HEALTHY",0),  f"{vc.get('HEALTHY',0)/n*100:.0f}% of state")
    with k6:
        mm = df["net_margin_per_acre"].mean()
        st.metric(
            "Mean Net Margin", f"${mm:+.0f}/acre",
            delta="Profitable" if mm > 0 else "Loss territory",
            delta_color="normal" if mm > 0 else "inverse",
        )

    st.divider()

    # -----------------------------------------------------------------------
    # Map + Charts
    # -----------------------------------------------------------------------

    map_col, chart_col = st.columns([3, 2])

    with map_col:
        section_label("County Profitability Risk Map")
        map_data = df.dropna(subset=["lat","lon"])
        common = dict(get_position=["lon","lat"], get_fill_color="color", pickable=True)

        if show_3d:
            county_layer = pdk.Layer(
                "ColumnLayer",
                data=map_data[["lat","lon","color","elevation","county_name",
                               "net_margin_per_acre","risk_tier","crusher_dist_miles"]],
                get_elevation="elevation", elevation_scale=1,
                radius=8000, extruded=True, **common,
            )
        else:
            county_layer = pdk.Layer(
                "ScatterplotLayer",
                data=map_data[["lat","lon","color","county_name","net_margin_per_acre",
                               "risk_tier","crusher_dist_miles"]],
                get_radius=8000, opacity=0.82, **common,
            )

        layers = [county_layer]

        if show_crush and not fac["crushers"].empty:
            layers.append(pdk.Layer("ScatterplotLayer",
                data=fac["crushers"][["lat","lon","Short Name","State"]].rename(
                    columns={"Short Name":"name"}),
                get_position=["lon","lat"],
                get_fill_color=[30, 80, 140, 230],
                get_radius=12000, pickable=True))

        if show_term and not fac["export_terminals"].empty:
            layers.append(pdk.Layer("ScatterplotLayer",
                data=fac["export_terminals"][["lat","lon","Short Name","State"]].rename(
                    columns={"Short Name":"name"}),
                get_position=["lon","lat"],
                get_fill_color=[100, 50, 160, 230],
                get_radius=14000, pickable=True))

        ctrs = {
            "19":(42.0,-93.5,7), "17":(40.0,-89.2,7), "18":(40.3,-86.1,7),
            "39":(40.4,-82.5,7), "27":(46.4,-94.7,6), "31":(41.5,-99.9,6),
        }
        clat, clon, zoom = ctrs.get(state_fips, (41.5,-93.5,7))

        st.pydeck_chart(pdk.Deck(
            layers=layers,
            initial_view_state=pdk.ViewState(
                latitude=clat, longitude=clon, zoom=zoom,
                pitch=45 if show_3d else 0,
            ),
            tooltip={
                "html":
                    "<div style='font-family:\"IBM Plex Sans\",sans-serif;padding:4px'>"
                    "<b style='font-size:13px'>{county_name}</b><br/>"
                    "<span style='color:#aaa;font-size:11px'>Risk tier</span> "
                    "<b style='font-size:12px'>{risk_tier}</b><br/>"
                    "<span style='color:#aaa;font-size:11px'>Net margin</span> "
                    "<b style='font-size:12px'>${net_margin_per_acre}/acre</b><br/>"
                    "<span style='color:#aaa;font-size:11px'>Crusher distance</span> "
                    "<b style='font-size:12px'>{crusher_dist_miles} mi</b>"
                    "</div>",
                "style": {
                    "backgroundColor": "#0f2419",
                    "color": "#f0f4ee",
                    "borderRadius": "2px",
                    "padding": "10px 14px",
                },
            },
            map_style="mapbox://styles/mapbox/light-v11",
        ), use_container_width=True)

        # Legend
        leg = st.columns(4)
        legend_items = [
            ("High Risk", "loss territory",       "#b91c1c"),
            ("Elevated",  "0 to 5% margin",       "#c2410c"),
            ("Moderate",  "5 to 12% margin",      "#b45309"),
            ("Healthy",   "above 12% margin",     "#15803d"),
        ]
        for col, (label, note, color) in zip(leg, legend_items):
            col.markdown(
                f"<div style='display:flex;align-items:center;gap:6px;margin-top:4px'>"
                f"<div style='width:10px;height:10px;border-radius:50%;"
                f"background:{color};flex-shrink:0'></div>"
                f"<span style='font-size:0.76rem;color:#5a5a52'>"
                f"<b style='color:#0f2419'>{label}</b> &mdash; {note}</span></div>",
                unsafe_allow_html=True,
            )
        if show_crush:
            st.markdown(
                "<div style='font-size:0.76rem;color:#5a5a52;margin-top:6px'>"
                "<span style='color:#1e508c;font-weight:600'>&#9679;</span> NOPA Crusher &nbsp;&nbsp;"
                "<span style='color:#643296;font-weight:600'>&#9679;</span> Export Terminal"
                "</div>",
                unsafe_allow_html=True,
            )

    # -----------------------------------------------------------------------
    # Chart panel
    # -----------------------------------------------------------------------

    with chart_col:
        t1, t2, t3, t4 = st.tabs(["Margin Breakdown","Logistics","Squeeze List","Macro Trends"])
        base = plotly_layout_defaults()

        with t1:
            med   = df.median(numeric_only=True)
            costs = SOY_COSTS if commodity == "soybean" else CORN_COSTS
            ci = {
                "Land Rent":       land_rent,
                "Fertilizer":      float(med.get("fertilizer_cost_adj", costs.fertilizer_base)),
                "Seed":            costs.seed,
                "Pesticides":      costs.pesticides,
                "Fuel & Repairs":  costs.fuel_lube_repairs,
                "Labor":           costs.labor,
                "Depreciation":    costs.depreciation,
                "Transport Basis": float(med.get("basis_deduction_per_acre", costs.transport_base*50)),
                "Overhead":        costs.overhead + costs.taxes_insurance + costs.custom_ops,
            }
            rev = float(med.get("revenue_per_acre", cbot * 52))
            net = rev - sum(ci.values())

            fig = go.Figure(go.Waterfall(
                orientation="v",
                measure=["relative"] * len(ci) + ["total"],
                x=list(ci.keys()) + ["Net Margin"],
                y=[-v for v in ci.values()] + [net],
                base=rev,
                connector={"line": {"color": "#e5e2dc", "width": 1}},
                decreasing={"marker": {"color": "#b91c1c", "opacity": 0.85}},
                increasing={"marker": {"color": "#15803d", "opacity": 0.85}},
                totals={"marker": {"color": "#15803d" if net >= 0 else "#b91c1c"}},
                text=[f"${v:.0f}" for v in ci.values()] + [f"${net:+.0f}"],
                textposition="auto",
                textfont={"size": 9, "family": "IBM Plex Mono"},
            ))
            fig.update_layout(
                **base,
                title=f"Cost stack vs. revenue — median county (CBOT ${cbot:.2f}/bu)",
                height=390,
                yaxis_title="$/acre",
                showlegend=False,
            )
            fig.update_xaxes(tickfont=dict(size=9))
            st.plotly_chart(fig, use_container_width=True)

        with t2:
            if "crusher_dist_miles" in df.columns:
                fig_h = px.histogram(
                    df, x="crusher_dist_miles", color="risk_tier", nbins=28,
                    color_discrete_map=RISK_COLORS,
                    labels={"crusher_dist_miles": "Miles to Nearest Crusher", "count": "Counties"},
                )
                fig_h.add_vline(
                    x=LOGISTICS.distance_threshold_miles, line_dash="dash",
                    line_color="#9a9a90",
                    annotation_text=f"Penalty threshold ({LOGISTICS.distance_threshold_miles:.0f} mi)",
                    annotation_font_size=9,
                )
                fig_h.update_layout(
                    **base, title="Crusher distance distribution by risk tier",
                    height=210, showlegend=True,
                    legend=dict(orientation="h", y=-0.35, font_size=9),
                )
                st.plotly_chart(fig_h, use_container_width=True)

            if "transport_cost_per_bu" in df.columns:
                fig_s = px.scatter(
                    df.dropna(subset=["crusher_dist_miles","transport_cost_per_bu"]),
                    x="crusher_dist_miles", y="transport_cost_per_bu", color="risk_tier",
                    hover_data=["county_name"],
                    color_discrete_map=RISK_COLORS,
                    labels={"crusher_dist_miles": "Miles to Crusher",
                            "transport_cost_per_bu": "Transport cost ($/bu)"},
                    opacity=0.75,
                )
                fig_s.update_layout(**base, height=195, showlegend=False)
                st.plotly_chart(fig_s, use_container_width=True)

        with t3:
            section_label("Most At-Risk Counties")
            ar = get_most_at_risk_counties(df, n=15)
            dc = [c for c in ["county_name","risk_tier","net_margin_per_acre",
                               "crusher_dist_miles","transport_cost_per_bu"] if c in ar.columns]

            def _bg(v):
                return {
                    "HIGH":     "background-color:#fee2e2;color:#7f1d1d",
                    "ELEVATED": "background-color:#ffedd5;color:#7c2d12",
                    "MODERATE": "background-color:#fef3c7;color:#78350f",
                    "HEALTHY":  "background-color:#dcfce7;color:#14532d",
                }.get(v, "")

            if not ar.empty:
                st.dataframe(
                    ar[dc].style.applymap(_bg, subset=["risk_tier"] if "risk_tier" in dc else [])
                    .format({
                        "net_margin_per_acre":    "${:.0f}",
                        "crusher_dist_miles":     "{:.0f} mi",
                        "transport_cost_per_bu":  "${:.3f}",
                    }),
                    use_container_width=True, height=260,
                )

            section_label("Logistics Squeeze Counties")
            sq = get_logistics_squeeze_counties(df, dist_threshold_miles=80)
            sc_cols = [c for c in ["county_name","crusher_dist_miles",
                                    "transport_cost_per_bu","basis_risk_score"] if c in sq.columns]
            if not sq.empty:
                st.dataframe(sq[sc_cols], use_container_width=True, height=165)
            else:
                st.caption("No extreme logistics squeeze counties for this state and scenario.")

        with t4:
            section_label("Fertilizer PPI — FRED")
            if os.getenv("FRED_API_KEY"):
                try:
                    fh = _load_fert_hist()
                    if not fh.empty:
                        fig_f = go.Figure(go.Scatter(
                            x=fh["date"], y=fh["value"],
                            mode="lines", line=dict(color="#1a472a", width=1.8),
                            fill="tozeroy", fillcolor="rgba(26,71,42,0.07)",
                        ))
                        fig_f.update_layout(**base, height=155, showlegend=False,
                                            yaxis_title="Index")
                        st.plotly_chart(fig_f, use_container_width=True)
                except Exception:
                    st.caption("FRED API key required.")
            else:
                st.caption("Add FRED API key to enable fertilizer PPI trend.")

            section_label("Diesel Price — EIA")
            if os.getenv("EIA_API_KEY"):
                try:
                    dh = _load_diesel_hist()
                    if not dh.empty:
                        fig_d = go.Figure(go.Scatter(
                            x=dh["period"], y=dh["value"],
                            mode="lines", line=dict(color="#c2410c", width=1.8),
                            fill="tozeroy", fillcolor="rgba(194,65,12,0.07)",
                        ))
                        fig_d.update_layout(**base, height=155, showlegend=False,
                                            yaxis_title="$/gal")
                        st.plotly_chart(fig_d, use_container_width=True)
                except Exception:
                    st.caption("EIA API key required.")
            else:
                st.caption("Add EIA API key to enable diesel price trend.")

    st.divider()

    with st.expander("Full County Data Table", expanded=False):
        out = df.copy()
        float_cols = out.select_dtypes(include=[np.floating]).columns
        out[float_cols] = out[float_cols].round(3)
        out = out.drop(columns=[c for c in ["color","elevation"] if c in out.columns])
        st.dataframe(out, use_container_width=True, height=280)
        st.download_button(
            "Download CSV",
            data=out.to_csv(index=False),
            file_name=f"harvest_squeeze_{state_name.lower()}_{commodity}_{yield_year}.csv",
            mime="text/csv",
        )

else:
    st.info(
        "Click Run Analysis in the sidebar to generate the profitability map. "
        "The spatial and logistics model runs without API keys — "
        "only USDA yield, FRED fertilizer PPI, and EIA diesel require keys for live data."
    )
    if not fac["crushers"].empty:
        section_label("Value Chain Infrastructure Preview — All NOPA Facilities")
        all_f = fac["all"].copy()
        fc_rgba = {
            "Soybean Processor - Operating": [30, 80, 140, 220],
            "Export Facility":               [100, 50, 160, 220],
            "Biodiesel":                     [194, 65, 12, 200],
            "Renewable Diesel - Operating":  [21, 128, 61, 200],
        }
        all_f["color"] = all_f["Type"].map(lambda t: fc_rgba.get(t, [128,128,128,180]))
        st.pydeck_chart(pdk.Deck(
            layers=[pdk.Layer("ScatterplotLayer",
                data=all_f[["lat","lon","color","Short Name","Type","State"]].rename(
                    columns={"Short Name":"name","Type":"facility_type"}),
                get_position=["lon","lat"], get_fill_color="color",
                get_radius=18000, pickable=True)],
            initial_view_state=pdk.ViewState(latitude=39.5, longitude=-95.5, zoom=4),
            tooltip={"html":"<b>{name}</b><br/>{facility_type} &bull; {State}"},
            map_style="mapbox://styles/mapbox/light-v11",
        ), use_container_width=True)

footer()
