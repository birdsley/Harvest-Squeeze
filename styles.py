"""
styles.py
---------
Shared visual theme for The Harvest Squeeze dashboard.

Design language: institutional agricultural finance.
  - Typography: Playfair Display serif for authority;
                IBM Plex Sans for data clarity;
                IBM Plex Mono for numeric values.
  - Palette:    forest ink on warm parchment, harvest gold accents.
  - Tone:       Bloomberg terminal meets USDA annual report.

Import and call apply_theme() at the top of every page.
"""

import streamlit as st
from typing import Dict


# ---------------------------------------------------------------------------
# Color tokens (Python-side, for Plotly and Pydeck)
# ---------------------------------------------------------------------------

COLORS: Dict[str, str] = {
    "ink":        "#0f2419",
    "green_dk":   "#1a472a",
    "green_md":   "#2d6a4f",
    "green_lt":   "#d1fae5",
    "gold":       "#c8a951",
    "gold_lt":    "#fef3c7",
    "parchment":  "#f8f7f4",
    "white":      "#ffffff",
    "border":     "#e5e2dc",
    "slate":      "#5a5a52",
    "slate_lt":   "#9a9a90",
    "red":        "#b91c1c",
    "red_lt":     "#fee2e2",
    "orange":     "#c2410c",
    "orange_lt":  "#ffedd5",
    "amber":      "#b45309",
    "amber_lt":   "#fef3c7",
    "emerald":    "#15803d",
    "emerald_lt": "#dcfce7",
}

# Risk-tier color maps used across charts and tables
RISK_COLORS: Dict[str, str] = {
    "HIGH":     "#b91c1c",
    "ELEVATED": "#c2410c",
    "MODERATE": "#b45309",
    "HEALTHY":  "#15803d",
}

RISK_COLORS_LIGHT: Dict[str, str] = {
    "HIGH":     "#fee2e2",
    "ELEVATED": "#ffedd5",
    "MODERATE": "#fef3c7",
    "HEALTHY":  "#dcfce7",
}

# Pydeck RGBA map layer colors
RISK_RGBA: Dict[str, list] = {
    "HIGH":     [185, 28, 28, 210],
    "ELEVATED": [194, 65, 12, 210],
    "MODERATE": [180, 83, 9,  210],
    "HEALTHY":  [21, 128, 61, 210],
}


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

:root {
  --ink:       #0f2419;
  --green-dk:  #1a472a;
  --green-md:  #2d6a4f;
  --gold:      #c8a951;
  --parchment: #f8f7f4;
  --white:     #ffffff;
  --border:    #e5e2dc;
  --slate:     #5a5a52;
  --slate-lt:  #9a9a90;
  --font-serif: 'Playfair Display', Georgia, serif;
  --font-sans:  'IBM Plex Sans', 'Helvetica Neue', system-ui, sans-serif;
  --font-mono:  'IBM Plex Mono', 'Courier New', monospace;
}

/* App shell */
.stApp { background-color: var(--parchment); font-family: var(--font-sans); }
.block-container { padding-top: 2rem !important; padding-bottom: 3rem !important; max-width: 1440px !important; }

/* Headings */
h1, h2, h3 { font-family: var(--font-serif) !important; color: var(--ink) !important; letter-spacing: -0.02em; }
h1 { font-size: 2.0rem !important; font-weight: 700 !important; }
h2 { font-size: 1.45rem !important; font-weight: 600 !important; }
h3 { font-size: 1.15rem !important; font-weight: 600 !important; }
p, li, label { font-family: var(--font-sans) !important; color: var(--slate) !important; font-size: 0.91rem; line-height: 1.6; }

/* Sidebar */
[data-testid="stSidebar"] { background-color: var(--ink) !important; border-right: 1px solid #1a3025; }
[data-testid="stSidebar"] * { color: #c8d5c0 !important; font-family: var(--font-sans) !important; }
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
  color: #f0f4ee !important; font-family: var(--font-sans) !important;
  font-size: 0.72rem !important; font-weight: 600 !important;
  letter-spacing: 0.12em; text-transform: uppercase;
}
[data-testid="stSidebar"] hr { border-color: #1f3a2a !important; margin: 1rem 0 !important; }
[data-testid="stSidebar"] .stSlider label,
[data-testid="stSidebar"] .stSelectbox label {
  color: #8aaa84 !important; font-size: 0.74rem !important;
  text-transform: uppercase; letter-spacing: 0.08em;
}

/* Sidebar primary button */
[data-testid="stSidebar"] .stButton > button {
  background-color: var(--gold) !important; color: var(--ink) !important;
  border: none !important; font-weight: 600 !important;
  font-family: var(--font-sans) !important; font-size: 0.78rem !important;
  letter-spacing: 0.07em; text-transform: uppercase;
  border-radius: 2px !important; padding: 0.55rem 1rem !important;
  transition: background-color 0.15s;
}
[data-testid="stSidebar"] .stButton > button:hover { background-color: #b8952e !important; }

/* Metric cards */
[data-testid="stMetric"] {
  background: var(--white) !important; border: 1px solid var(--border) !important;
  border-top: 3px solid var(--green-dk) !important; border-radius: 2px !important;
  padding: 0.9rem 1.1rem !important;
}
[data-testid="stMetricLabel"] {
  font-family: var(--font-sans) !important; font-size: 0.68rem !important;
  font-weight: 600 !important; text-transform: uppercase !important;
  letter-spacing: 0.1em !important; color: var(--slate-lt) !important;
}
[data-testid="stMetricValue"] {
  font-family: var(--font-mono) !important; font-size: 1.35rem !important;
  font-weight: 500 !important; color: var(--ink) !important;
}
[data-testid="stMetricDelta"] { font-family: var(--font-mono) !important; font-size: 0.74rem !important; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
  background: transparent !important; border-bottom: 2px solid var(--border) !important; gap: 0 !important;
}
.stTabs [data-baseweb="tab"] {
  font-family: var(--font-sans) !important; font-size: 0.74rem !important;
  font-weight: 600 !important; text-transform: uppercase !important; letter-spacing: 0.08em !important;
  color: var(--slate) !important; border-radius: 0 !important; padding: 0.55rem 1.1rem !important;
  border-bottom: 2px solid transparent !important; margin-bottom: -2px !important; background: transparent !important;
}
.stTabs [aria-selected="true"] { color: var(--green-dk) !important; border-bottom-color: var(--green-dk) !important; }

/* DataFrames */
[data-testid="stDataFrame"] {
  border: 1px solid var(--border) !important; border-radius: 2px !important;
  font-family: var(--font-mono) !important; font-size: 0.78rem !important;
}

/* Divider */
hr { border: none !important; border-top: 1px solid var(--border) !important; margin: 1.4rem 0 !important; }

/* Expander */
[data-testid="stExpander"] { border: 1px solid var(--border) !important; border-radius: 2px !important; background: var(--white) !important; }
[data-testid="stExpander"] summary {
  font-family: var(--font-sans) !important; font-size: 0.76rem !important;
  font-weight: 600 !important; text-transform: uppercase !important; letter-spacing: 0.08em !important;
}

/* Alerts */
[data-testid="stAlert"] {
  border-radius: 2px !important; border-left: 4px solid var(--green-md) !important;
  font-family: var(--font-sans) !important; font-size: 0.84rem !important;
}

/* Download button */
.stDownloadButton > button {
  background: transparent !important; border: 1px solid var(--green-dk) !important;
  color: var(--green-dk) !important; font-family: var(--font-sans) !important;
  font-size: 0.74rem !important; font-weight: 600 !important;
  text-transform: uppercase !important; letter-spacing: 0.08em !important;
  border-radius: 2px !important; padding: 0.4rem 0.9rem !important; transition: all 0.15s;
}
.stDownloadButton > button:hover { background: var(--green-dk) !important; color: var(--white) !important; }

/* Progress bar */
[data-testid="stProgressBar"] > div { background-color: var(--green-md) !important; }

/* Custom layout helpers */
.page-header {
  font-family: 'Playfair Display', Georgia, serif;
  font-size: 1.95rem; font-weight: 700; color: #0f2419;
  letter-spacing: -0.02em; margin-bottom: 0.15rem; line-height: 1.15;
}
.page-subtitle {
  font-family: 'IBM Plex Sans', system-ui, sans-serif;
  font-size: 0.86rem; color: #9a9a90; font-weight: 400;
  letter-spacing: 0.02em; margin-top: 0.1rem; margin-bottom: 1.25rem;
}
.section-label {
  font-family: 'IBM Plex Sans', system-ui, sans-serif;
  font-size: 0.68rem; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.13em; color: #9a9a90;
  margin-bottom: 0.6rem; padding-bottom: 0.35rem; border-bottom: 1px solid #e5e2dc;
}
.footer-text {
  text-align: center; color: #9a9a90; font-size: 0.72rem;
  font-family: 'IBM Plex Sans', system-ui, sans-serif;
  letter-spacing: 0.03em; padding: 0.8rem 0 0.4rem;
}
"""


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def apply_theme() -> None:
    """Inject the shared CSS theme into the current Streamlit page."""
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    """Render a professional serif page header with optional subtitle."""
    st.markdown(f'<div class="page-header">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="page-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def section_label(text: str) -> None:
    """Render a small-caps section divider label."""
    st.markdown(f'<div class="section-label">{text}</div>', unsafe_allow_html=True)


def footer() -> None:
    """Render the standard page footer."""
    st.markdown("<hr/>", unsafe_allow_html=True)
    st.markdown(
        "<div class='footer-text'>"
        "The Harvest Squeeze &nbsp;&bull;&nbsp; "
        "Data: USDA NASS &middot; FRED St. Louis Fed &middot; EIA &middot; "
        "NASA MODIS/SMAP via GEE &middot; EIA/NOPA Value Chain XLSX<br/>"
        "Built with Streamlit &middot; Pydeck &middot; Plotly "
        "&nbsp;&bull;&nbsp; 2026 Planning Tool &mdash; Not Investment Advice"
        "</div>",
        unsafe_allow_html=True,
    )


def plotly_layout_defaults() -> dict:
    """
    Return a base Plotly layout dict consistent with the theme.
    Merge into any fig.update_layout() call.
    """
    return dict(
        font=dict(
            family="IBM Plex Sans, Helvetica Neue, system-ui",
            size=11,
            color="#5a5a52",
        ),
        plot_bgcolor="#ffffff",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=8, r=8, t=42, b=8),
        title_font=dict(family="IBM Plex Sans", size=11, color="#0f2419"),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            bordercolor="#e5e2dc",
            borderwidth=1,
            font=dict(size=10),
        ),
        colorway=[
            "#1a472a", "#2d6a4f", "#c8a951",
            "#b91c1c", "#c2410c", "#15803d",
        ],
    )


def risk_row_style(val: str) -> str:
    """
    Return a CSS background+color string for a risk tier value.
    Use with df.style.applymap(risk_row_style, subset=['risk_tier']).
    """
    return {
        "HIGH":     "background-color:#fee2e2;color:#7f1d1d",
        "ELEVATED": "background-color:#ffedd5;color:#7c2d12",
        "MODERATE": "background-color:#fef3c7;color:#78350f",
        "HEALTHY":  "background-color:#dcfce7;color:#14532d",
    }.get(val, "")
