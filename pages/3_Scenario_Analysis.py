"""
pages/3_Scenario_Analysis.py
-----------------------------
Sensitivity analysis: tornado chart, price heat map,
breakeven calculator, Monte Carlo simulation.

v2.4 fixes:
  - plotly update_layout duplicate 'margin' and 'legend' kwargs resolved
  - use_container_width → width="stretch" (Streamlit 1.56+ migration)
"""

import warnings

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

warnings.filterwarnings("ignore")
load_dotenv()

from config import SOY_COSTS, CORN_COSTS, LOGISTICS, RISK
from styles import (
    apply_theme, page_header, section_label, footer,
    plotly_layout_defaults, RISK_COLORS,
)
from data_acquisition import load_value_chain_facilities, load_county_centroids
from data_processing import (
    calculate_spatial_logistics, calculate_transport_cost,
    calculate_production_costs,
)

st.set_page_config(
    page_title="Scenario Analysis | Harvest Squeeze",
    layout="wide", initial_sidebar_state="expanded",
)
apply_theme()

page_header(
    "Scenario and Sensitivity Analysis",
    "What-if modeling: price shocks, input cost spikes, logistics stress, Monte Carlo simulation",
)
st.divider()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown(
        "<div style='padding:1.2rem 0 0.6rem'>"
        "<span style='font-family:Georgia,serif;font-size:1rem;"
        "font-weight:700;color:#f0f4ee'>Scenario Controls</span></div>",
        unsafe_allow_html=True,
    )
    st.divider()

    commodity = st.selectbox("Commodity", ["soybean","corn"],
        format_func=lambda x: "Soybeans" if x == "soybean" else "Corn",
        key="sc_comm")
    state_sel = st.selectbox("State", [
        ("Iowa","19"),("Illinois","17"),("Indiana","18"),
        ("Ohio","39"),("Minnesota","27"),("Nebraska","31"),
    ], format_func=lambda x: x[0], key="sc_state")
    state_label, state_fips = state_sel

    st.divider()
    st.markdown(
        "<div style='font-size:0.72rem;font-weight:600;text-transform:uppercase;"
        "letter-spacing:0.1em;color:#a0b09a'>Base Scenario</div>",
        unsafe_allow_html=True,
    )
    st.markdown("")
    base_cbot   = st.number_input("Base CBOT ($/bu)",
        value=10.50 if commodity == "soybean" else 4.35, step=0.25, key="sc_cbot")
    base_diesel = st.number_input("Base Diesel ($/gal)", value=3.82, step=0.10, key="sc_d")
    base_ppi    = st.number_input("Base Fertilizer PPI",  value=115.0, step=5.0,  key="sc_ppi")
    base_lr     = st.number_input("Base Land Rent ($/ac)", value=248.0, step=10.0, key="sc_lr")

    st.divider()
    st.markdown(
        "<div style='font-size:0.72rem;font-weight:600;text-transform:uppercase;"
        "letter-spacing:0.1em;color:#a0b09a'>Monte Carlo</div>",
        unsafe_allow_html=True,
    )
    st.markdown("")
    n_sims     = st.slider("Simulations",    200, 2000, 500, step=100, key="sc_nsims")
    cbot_vol   = st.slider("CBOT vol (+-$/bu)",   0.25, 3.00, 1.25, step=0.25, key="sc_cv")
    diesel_vol = st.slider("Diesel vol (+-$/gal)", 0.10, 1.50, 0.50, step=0.10, key="sc_dv")
    ppi_vol    = st.slider("Fert PPI vol (+-pts)", 5.0, 40.0, 15.0, step=5.0,  key="sc_pv")

    st.markdown("")
    run_btn = st.button("Run Scenario Suite", type="primary", use_container_width=True)

# ---------------------------------------------------------------------------
# Cached model
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def _base_model(fips, diesel, ppi, cm):
    fac  = load_value_chain_facilities()
    cent = load_county_centroids()
    sc   = cent[cent["state_fips"] == fips].copy()
    if sc.empty:
        return pd.DataFrame()
    df = calculate_spatial_logistics(sc, fac)
    df = calculate_transport_cost(df, diesel, commodity=cm)
    df = calculate_production_costs(df, fertilizer_ppi=ppi, commodity=cm)
    return df

def compute_nms(df_in, cbot, lr, cm):
    df = df_in.copy()
    base_lr = SOY_COSTS.land_rent if cm == "soybean" else CORN_COSTS.land_rent
    df["revenue_per_acre"]       = df.get("adj_yield_bu_acre", 50.0) * cbot
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
# Session state + load
# ---------------------------------------------------------------------------

if "sc_base_df" not in st.session_state:
    st.session_state.sc_base_df = None

def load_base():
    with st.spinner(f"Building base model for {state_label}..."):
        df = _base_model(state_fips, base_diesel, base_ppi, commodity)
        if not df.empty:
            df = compute_nms(df, base_cbot, base_lr, commodity)
        st.session_state.sc_base_df = df

if run_btn or st.session_state.sc_base_df is None:
    load_base()

bdf = st.session_state.sc_base_df
if bdf is None or bdf.empty:
    st.error("Base model could not be built. Ensure county centroids are cached.")
    st.stop()

med_county = bdf.median(numeric_only=True)
med_yield  = float(med_county.get("adj_yield_bu_acre", 52.0))
med_transp = float(med_county.get("basis_deduction_per_acre", 18.0))
base       = plotly_layout_defaults()
costs      = SOY_COSTS if commodity == "soybean" else CORN_COSTS

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

t1, t2, t3, t4 = st.tabs([
    "Tornado Chart",
    "Price Sensitivity Grid",
    "Breakeven Calculator",
    "Monte Carlo Simulation",
])

# ── Tornado ──────────────────────────────────────────────────────────────────
with t1:
    section_label(f"{state_label} — Input Sensitivity (Median County Net Margin)")
    st.markdown(
        "<p>Each bar shows how much the median county net margin changes when "
        "a single input shifts by one standard deviation above or below the base case.</p>",
        unsafe_allow_html=True,
    )

    base_margin = float(bdf["net_margin_per_acre"].median())

    inputs = {
        "CBOT Price":      {"base": base_cbot,   "delta": 1.50 if commodity=="soybean" else 0.60},
        "Land Rent":       {"base": base_lr,      "delta": 50.0},
        "Fertilizer PPI":  {"base": base_ppi,     "delta": 20.0},
        "Diesel Price":    {"base": base_diesel,  "delta": 0.60},
        "Yield (bu/acre)": {"base": med_yield,    "delta": 5.0},
        "Transport Basis": {"base": med_transp,   "delta": 10.0},
    }

    rows = []
    for name, cfg in inputs.items():
        if name == "CBOT Price":
            hi = compute_nms(bdf, base_cbot + cfg["delta"], base_lr, commodity)["net_margin_per_acre"].median()
            lo = compute_nms(bdf, base_cbot - cfg["delta"], base_lr, commodity)["net_margin_per_acre"].median()
        elif name == "Land Rent":
            hi = compute_nms(bdf, base_cbot, base_lr - cfg["delta"], commodity)["net_margin_per_acre"].median()
            lo = compute_nms(bdf, base_cbot, base_lr + cfg["delta"], commodity)["net_margin_per_acre"].median()
        elif name == "Fertilizer PPI":
            h = _base_model(state_fips, base_diesel, base_ppi - cfg["delta"], commodity)
            l = _base_model(state_fips, base_diesel, base_ppi + cfg["delta"], commodity)
            hi = compute_nms(h, base_cbot, base_lr, commodity)["net_margin_per_acre"].median() if not h.empty else base_margin
            lo = compute_nms(l, base_cbot, base_lr, commodity)["net_margin_per_acre"].median() if not l.empty else base_margin
        elif name == "Diesel Price":
            h = _base_model(state_fips, base_diesel - cfg["delta"], base_ppi, commodity)
            l = _base_model(state_fips, base_diesel + cfg["delta"], base_ppi, commodity)
            hi = compute_nms(h, base_cbot, base_lr, commodity)["net_margin_per_acre"].median() if not h.empty else base_margin
            lo = compute_nms(l, base_cbot, base_lr, commodity)["net_margin_per_acre"].median() if not l.empty else base_margin
        else:
            margin_per_bu = base_cbot - costs.transport_base
            if name == "Yield (bu/acre)":
                hi = base_margin + cfg["delta"] * margin_per_bu
                lo = base_margin - cfg["delta"] * margin_per_bu
            else:
                hi = base_margin - cfg["delta"]
                lo = base_margin + cfg["delta"]

        hi, lo = float(hi), float(lo)
        rows.append({
            "Input":    name,
            "High ($)": max(hi,lo) - base_margin,
            "Low ($)":  min(hi,lo) - base_margin,
            "Span":     abs(hi - lo),
            "High_abs": max(hi,lo),
            "Low_abs":  min(hi,lo),
        })

    torn = pd.DataFrame(rows).sort_values("Span", ascending=True)

    fig_t = go.Figure()
    fig_t.add_trace(go.Bar(
        y=torn["Input"], x=torn["High ($)"], orientation="h",
        name="Upside", marker_color="#15803d", base=0,
        text=torn["High_abs"].map(lambda v: f"${v:+.0f}"),
        textposition="outside", textfont=dict(size=9, family="IBM Plex Mono"),
    ))
    fig_t.add_trace(go.Bar(
        y=torn["Input"], x=torn["Low ($)"], orientation="h",
        name="Downside", marker_color="#b91c1c", base=0,
        text=torn["Low_abs"].map(lambda v: f"${v:+.0f}"),
        textposition="outside", textfont=dict(size=9, family="IBM Plex Mono"),
    ))
    fig_t.add_vline(x=0, line_width=1.5, line_color="#0f2419")
    # v2.4 FIX: strip margin AND legend from base to avoid duplicate kwarg TypeError
    _base_clean = {k: v for k, v in base.items() if k not in ("margin", "legend")}
    fig_t.update_layout(
        **_base_clean,
        title=f"Base case: median county net margin = ${base_margin:+.0f}/acre",
        height=420, barmode="overlay",
        margin=dict(l=5, r=90, t=50, b=5),
        xaxis=dict(title="Delta vs. base case ($/acre)"),
        legend=dict(orientation="h", y=-0.12, font_size=9),
    )
    st.plotly_chart(fig_t, width="stretch", config={"displayModeBar": False})

    top3 = torn.sort_values("Span", ascending=False).head(3)["Input"].tolist()
    st.markdown(
        f"<p><b>Key finding:</b> {', '.join(top3)} are the three largest drivers of "
        f"profitability risk in {state_label} under the current base scenario.</p>",
        unsafe_allow_html=True,
    )

# ── Heat map ──────────────────────────────────────────────────────────────────
with t2:
    section_label(f"{state_label} — High-Risk County Share by CBOT and Diesel Price")
    st.markdown(
        "<p>Each cell shows the percentage of counties classified as HIGH risk under that "
        "combination of CBOT price and diesel price. "
        "The base scenario is marked with a star.</p>",
        unsafe_allow_html=True,
    )

    lo_cbot   = max(7.0 if commodity == "soybean" else 3.0, base_cbot - 2.5)
    hi_cbot   = min(14.0 if commodity == "soybean" else 6.5, base_cbot + 2.6)
    cbot_r    = np.round(np.arange(lo_cbot, hi_cbot, 0.5), 2)
    diesel_r  = np.round(np.arange(max(2.5, base_diesel - 1.0), min(5.5, base_diesel + 1.1), 0.25), 2)

    with st.spinner("Building price sensitivity grid..."):
        grid = np.zeros((len(diesel_r), len(cbot_r)))
        for ci, cb in enumerate(cbot_r):
            for di, dsl in enumerate(diesel_r):
                df_g = (bdf if dsl == base_diesel
                        else _base_model(state_fips, float(dsl), base_ppi, commodity))
                if df_g.empty:
                    grid[di, ci] = np.nan
                    continue
                pct = (compute_nms(df_g, float(cb), base_lr, commodity)["risk_tier"] == "HIGH").mean() * 100
                grid[di, ci] = pct

    fig_hm = go.Figure(go.Heatmap(
        z=grid,
        x=[f"${c:.2f}" for c in cbot_r],
        y=[f"${d:.2f}" for d in diesel_r],
        colorscale=[
            [0.0,"#15803d"],[0.3,"#86efac"],
            [0.6,"#fbbf24"],[0.8,"#f97316"],
            [1.0,"#b91c1c"],
        ],
        colorbar=dict(title="% High Risk", thickness=12,
                      tickfont=dict(size=9, family="IBM Plex Mono")),
        text=np.round(grid, 0), texttemplate="%{text:.0f}%",
        textfont=dict(size=9, family="IBM Plex Mono"),
        hovertemplate="CBOT: %{x}<br>Diesel: %{y}<br>High Risk: %{z:.0f}%<extra></extra>",
    ))

    bc_idx  = int(np.argmin(np.abs(cbot_r - base_cbot)))
    bd_idx  = int(np.argmin(np.abs(diesel_r - base_diesel)))
    fig_hm.add_trace(go.Scatter(
        x=[f"${cbot_r[bc_idx]:.2f}"], y=[f"${diesel_r[bd_idx]:.2f}"],
        mode="markers", marker=dict(symbol="star", size=18, color="#f8f7f4",
                                    line=dict(color="#0f2419", width=2)),
        showlegend=False,
    ))
    fig_hm.update_layout(
        **base,
        title=f"Percentage of {state_label} counties in HIGH risk tier by price scenario",
        height=430,
        xaxis_title="CBOT Price ($/bu)",
        yaxis_title="Diesel Price ($/gal)",
    )
    st.plotly_chart(fig_hm, width="stretch", config={"displayModeBar": False})

# ── Breakeven ─────────────────────────────────────────────────────────────────
with t3:
    section_label(f"{state_label} — Breakeven CBOT Price by County")
    st.markdown(
        "<p>The minimum CBOT futures price required for each county to achieve a net margin "
        "of zero or above, given current production costs and transport basis.</p>",
        unsafe_allow_html=True,
    )

    be_df = bdf.copy()
    be_df["breakeven_cbot"] = (
        (be_df["total_production_cost"] + be_df.get("basis_deduction_per_acre", 0))
        / be_df.get("adj_yield_bu_acre", 52.0).replace(0, np.nan)
    ).clip(5, 20)
    be_df["margin_of_safety"] = base_cbot - be_df["breakeven_cbot"]

    c1, c2 = st.columns(2)

    with c1:
        fig_be = px.histogram(
            be_df, x="breakeven_cbot", color="risk_tier", nbins=24,
            color_discrete_map=RISK_COLORS,
            labels={"breakeven_cbot":"Breakeven CBOT ($/bu)"},
        )
        fig_be.add_vline(x=base_cbot, line_dash="dash", line_color="#0f2419",
                         annotation_text=f"Current CBOT: ${base_cbot:.2f}",
                         annotation_font_size=9)
        # v2.4 FIX: strip legend from base
        _base_no_legend = {k: v for k, v in base.items() if k != "legend"}
        fig_be.update_layout(
            **_base_no_legend, title="Breakeven CBOT distribution by risk tier",
            height=320, legend=dict(orientation="h", y=-0.3, font_size=9),
        )
        st.plotly_chart(fig_be, width="stretch", config={"displayModeBar": False})

    with c2:
        pct_under = (be_df["breakeven_cbot"] > base_cbot).mean() * 100
        q75       = be_df["breakeven_cbot"].quantile(0.75)
        q50       = be_df["breakeven_cbot"].quantile(0.50)
        st.metric("Median BE CBOT",   f"${q50:.2f}/bu", help="Median breakeven CBOT price across all counties")
        st.metric("75th Percentile",   f"${q75:.2f}/bu", help="75th percentile breakeven — 25% of counties need higher prices")
        st.metric("Already Underwater", f"{pct_under:.1f}%", help="Pct of counties whose breakeven exceeds current CBOT")

        st.markdown("<br/>", unsafe_allow_html=True)
        section_label("Worst Breakeven Counties")
        worst = be_df.nlargest(8,"breakeven_cbot")[
            ["county_name","breakeven_cbot","margin_of_safety","adj_yield_bu_acre"]
        ].round(2)
        worst.columns = ["County","BE Price","Safety Margin","Yield (bu/ac)"]
        st.dataframe(
            worst.style.format({
                "BE Price":       "${:.2f}",
                "Safety Margin":  "${:+.2f}",
                "Yield (bu/ac)":  "{:.1f}",
            }),
            width="stretch", height=260,
        )

    section_label("Breakeven Price vs. Crusher Distance")
    fig_be_sc = px.scatter(
        be_df.dropna(subset=["crusher_dist_miles","breakeven_cbot"]),
        x="crusher_dist_miles", y="breakeven_cbot",
        color="risk_tier", size="adj_yield_bu_acre",
        hover_data=["county_name"],
        color_discrete_map=RISK_COLORS,
        labels={"crusher_dist_miles":"Miles to Nearest Crusher",
                "breakeven_cbot":"Breakeven CBOT ($/bu)",
                "risk_tier":"Risk Tier"},
        opacity=0.78,
    )
    fig_be_sc.add_hline(y=base_cbot, line_dash="dash", line_color="#0f2419",
                        annotation_text=f"Current CBOT: ${base_cbot:.2f}",
                        annotation_font_size=9)
    # v2.4 FIX: strip legend from base
    _base_no_legend = {k: v for k, v in base.items() if k != "legend"}
    fig_be_sc.update_layout(**_base_no_legend, height=320,
                             legend=dict(orientation="h", y=-0.2, font_size=9))
    st.plotly_chart(fig_be_sc, width="stretch", config={"displayModeBar": False})

# ── Monte Carlo ───────────────────────────────────────────────────────────────
with t4:
    section_label(f"Monte Carlo Simulation — Median County ({n_sims:,} Iterations)")
    st.markdown(
        f"<p>Price and cost inputs are drawn from truncated normal distributions "
        f"representing 2026 planning uncertainty. "
        f"Results show the probability distribution "
        f"of net margin outcomes for the median {state_label} county.</p>",
        unsafe_allow_html=True,
    )

    with st.spinner(f"Running {n_sims:,} simulations..."):
        rng          = np.random.default_rng(42)
        cbot_s       = np.clip(rng.normal(base_cbot,   cbot_vol,   n_sims), 5.0, 14.0)
        diesel_s     = np.clip(rng.normal(base_diesel, diesel_vol, n_sims), 2.0, 6.5)
        ppi_s        = np.clip(rng.normal(base_ppi,    ppi_vol,    n_sims), 60.0, 250.0)
        land_s       = np.clip(rng.normal(base_lr,     40.0,       n_sims), 80.0, 500.0)
        yield_s      = np.clip(rng.normal(med_yield,   6.0,        n_sims), 20.0, 90.0)

        fert_c       = costs.fertilizer_base * (ppi_s / 100.0)
        d_adj        = 1 + LOGISTICS.diesel_elasticity * (
            (diesel_s - LOGISTICS.diesel_reference_price) / LOGISTICS.diesel_reference_price)
        fuel_c       = costs.fuel_lube_repairs * d_adj
        transp_c     = (med_transp / base_cbot) * d_adj

        total_cost   = (
            costs.seed + fert_c + costs.pesticides + fuel_c
            + costs.custom_ops + costs.irrigation + costs.labor
            + land_s + costs.depreciation + costs.taxes_insurance
            + costs.overhead + transp_c
        )
        revenue      = yield_s * cbot_s
        margins      = revenue - total_cost
        nms          = margins / np.where(revenue > 0, revenue, np.nan)

        risk_labels  = np.select(
            [nms <= RISK.high_risk_ceiling, nms <= RISK.elevated_risk_ceiling,
             nms <= RISK.moderate_risk_ceiling],
            ["HIGH","ELEVATED","MODERATE"], default="HEALTHY",
        )
        mc_df = pd.DataFrame({
            "Net Margin ($/ac)": margins,
            "CBOT ($/bu)":       cbot_s,
            "Diesel ($/gal)":    diesel_s,
            "Risk Tier":         risk_labels,
        })

    col_a, col_b = st.columns([3, 2])

    with col_a:
        fig_mc = px.histogram(
            mc_df, x="Net Margin ($/ac)", color="Risk Tier", nbins=55,
            color_discrete_map=RISK_COLORS, opacity=0.82,
        )
        p5  = float(np.percentile(margins, 5))
        p95 = float(np.percentile(margins, 95))
        fig_mc.add_vline(x=0,   line_dash="dash",  line_color="#0f2419",
                         annotation_text="Break-even", annotation_font_size=9)
        fig_mc.add_vline(x=p5,  line_dash="dot",   line_color="#b91c1c",
                         annotation_text=f"5th pct: ${p5:.0f}", annotation_font_size=9)
        fig_mc.add_vline(x=p95, line_dash="dot",   line_color="#15803d",
                         annotation_text=f"95th pct: ${p95:.0f}", annotation_font_size=9)
        # v2.4 FIX: strip legend from base to avoid duplicate kwarg TypeError
        _base_no_legend = {k: v for k, v in base.items() if k != "legend"}
        fig_mc.update_layout(
            **_base_no_legend, height=340,
            title=f"Net margin distribution — {n_sims:,} simulations",
            legend=dict(orientation="h", y=-0.2, font_size=9),
        )
        st.plotly_chart(fig_mc, width="stretch", config={"displayModeBar": False})

        fig_sc2 = px.scatter(
            mc_df.sample(min(300, n_sims)),
            x="CBOT ($/bu)", y="Net Margin ($/ac)", color="Diesel ($/gal)",
            color_continuous_scale="RdYlGn_r", opacity=0.6,
        )
        fig_sc2.add_hline(y=0, line_dash="dash", line_color="#0f2419")
        fig_sc2.update_layout(
            **base, height=290,
            title="Net margin vs. CBOT price (color = diesel)",
        )
        st.plotly_chart(fig_sc2, width="stretch", config={"displayModeBar": False})

    with col_b:
        risk_vc = pd.Series(risk_labels).value_counts()
        fig_pie = go.Figure(go.Pie(
            labels=risk_vc.index, values=risk_vc.values,
            marker=dict(colors=[RISK_COLORS.get(r,"#9a9a90") for r in risk_vc.index]),
            hole=0.44,
            textfont=dict(size=10, family="IBM Plex Sans"),
        ))
        # v2.4 FIX: strip legend from base to avoid duplicate kwarg TypeError
        _base_no_legend = {k: v for k, v in base.items() if k != "legend"}
        fig_pie.update_layout(
            **_base_no_legend, height=280,
            title="Simulation risk distribution",
            legend=dict(orientation="v", font_size=9),
        )
        st.plotly_chart(fig_pie, width="stretch", config={"displayModeBar": False})

        section_label("Simulation Statistics")
        stats = [
            ("Median margin",       f"${np.median(margins):+.0f}/acre"),
            ("Mean margin",         f"${np.mean(margins):+.0f}/acre"),
            ("Std deviation",       f"${np.std(margins):.0f}/acre"),
            ("5th percentile",      f"${p5:+.0f}/acre"),
            ("95th percentile",     f"${p95:+.0f}/acre"),
            ("P(loss)",             f"{(margins<0).mean()*100:.1f}%"),
            ("P(margin > $50)",     f"{(margins>50).mean()*100:.1f}%"),
            ("P(margin > $100)",    f"{(margins>100).mean()*100:.1f}%"),
            ("HIGH risk share",     f"{(risk_labels=='HIGH').mean()*100:.1f}%"),
            ("HEALTHY share",       f"{(risk_labels=='HEALTHY').mean()*100:.1f}%"),
        ]
        for label, val in stats:
            c_l, c_r = st.columns([2, 1])
            c_l.markdown(f"<span style='font-size:0.82rem;color:#5a5a52'>{label}</span>",
                         unsafe_allow_html=True)
            c_r.markdown(
                f"<span style='font-family:IBM Plex Mono;font-size:0.82rem;"
                f"color:#0f2419;font-weight:500'>{val}</span>",
                unsafe_allow_html=True,
            )

footer()
