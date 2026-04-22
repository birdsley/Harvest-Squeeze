"""
styles.py  --  The Harvest Squeeze  v2.3
-----------------------------------------
v2.3 fixes:
  - Sidebar selectbox value text ("Soybeans", "Iowa") was invisible because
    the blanket `[data-testid="stSidebar"] * { color: #C8D5C0 }` rule was
    too weak against Streamlit's internal component color resets.  Added
    targeted high-specificity overrides for select, input, and toggle values.
  - Sidebar primary-style buttons (Load Data, Fetch Satellite Data) now show
    dark ink text on the gold/yellow background rather than light grey.
  - Expander arrow icons no longer render as raw text ("arrow_right" etc.)
    in the sidebar — fixed by targeting the summary element more precisely.
  - Removed star-selector rules that were leaking into component internals.
"""

import streamlit as st
from typing import Dict


# ---------------------------------------------------------------------------
# Color tokens
# ---------------------------------------------------------------------------

COLORS: Dict[str, str] = {
    "ink":       "#0F2419",
    "growing":   "#2D5A27",
    "moving":    "#1E293B",
    "green_dk":  "#1A472A",
    "green_md":  "#2D6A4F",
    "green_lt":  "#D1FAE5",
    "gold":      "#C8A951",
    "gold_lt":   "#FEF3C7",
    "parchment": "#F8F7F4",
    "white":     "#FFFFFF",
    "border":    "#E5E2DC",
    "slate":     "#5A5A52",
    "slate_lt":  "#9A9A90",
    "red":       "#B91C1C",
    "red_lt":    "#FEE2E2",
    "orange":    "#C2410C",
    "orange_lt": "#FFEDD5",
    "amber":     "#B45309",
    "amber_lt":  "#FEF3C7",
    "emerald":   "#15803D",
    "emerald_lt":"#DCFCE7",
}

GROWING_COLOR:       str = "rgba(45,90,39,0.82)"
GROWING_COLOR_LIGHT: str = "rgba(45,90,39,0.12)"
MOVING_COLOR:        str = "rgba(30,41,59,0.82)"
MOVING_COLOR_LIGHT:  str = "rgba(30,41,59,0.10)"

RISK_COLORS: Dict[str, str] = {
    "HIGH":     "#B91C1C",
    "ELEVATED": "#C2410C",
    "MODERATE": "#B45309",
    "HEALTHY":  "#15803D",
}
RISK_COLORS_LIGHT: Dict[str, str] = {
    "HIGH":     "#FEE2E2",
    "ELEVATED": "#FFEDD5",
    "MODERATE": "#FEF3C7",
    "HEALTHY":  "#DCFCE7",
}
RISK_RGBA: Dict[str, list] = {
    "HIGH":     [185, 28,  28,  210],
    "ELEVATED": [194, 65,  12,  210],
    "MODERATE": [180, 83,  9,   210],
    "HEALTHY":  [21,  128, 61,  210],
}


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

/* ── Design tokens ─────────────────────────────────────────────────── */
:root {
  --ink:       #0F2419;
  --growing:   #2D5A27;
  --moving:    #1E293B;
  --gold:      #C8A951;
  --parchment: #F8F7F4;
  --white:     #FFFFFF;
  --border:    #E5E2DC;
  --slate:     #5A5A52;
  --slate-lt:  #9A9A90;
  --font-sans:  'IBM Plex Sans', 'Helvetica Neue', system-ui, sans-serif;
  --font-mono:  'IBM Plex Mono', 'Courier New', monospace;
  --font-serif: Georgia, 'Times New Roman', serif;
}

/* ── App shell ─────────────────────────────────────────────────────── */
.stApp { background-color: var(--parchment); font-family: var(--font-sans); }
.block-container {
  padding-top: 1.6rem !important;
  padding-bottom: 3rem !important;
  max-width: 1500px !important;
}
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }

/* ── Body typography ───────────────────────────────────────────────── */
h1, h2, h3 {
  font-family: var(--font-serif) !important;
  color: var(--ink) !important;
  letter-spacing: -0.02em;
}
h1 { font-size: 1.95rem !important; font-weight: 700 !important; }
h2 { font-size: 1.40rem !important; font-weight: 600 !important; }
h3 { font-size: 1.10rem !important; font-weight: 600 !important; }
p, li {
  font-family: var(--font-sans) !important;
  color: var(--slate) !important;
  font-size: 0.90rem;
  line-height: 1.65;
}

/* ── Sidebar shell ─────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
  background-color: var(--ink) !important;
  border-right: 1px solid #1A3025;
}

/* ── Sidebar labels (section headers, slider labels etc.) ──────────── */
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stSlider label,
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stNumberInput label,
[data-testid="stSidebar"] .stToggle label,
[data-testid="stSidebar"] .stMultiSelect label {
  color: #8AAA84 !important;
  font-family: var(--font-sans) !important;
  font-size: 0.72rem !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.10em !important;
}

/* ── Sidebar selectbox — SELECTED VALUE text (the important fix) ────── */
/* Target the visible value span inside BaseUI Select */
[data-testid="stSidebar"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-baseweb="select"] div[class*="singleValue"],
[data-testid="stSidebar"] [data-baseweb="select"] [class*="Input"],
[data-testid="stSidebar"] [data-baseweb="select"] input {
  color: #EDF3EB !important;
  font-family: var(--font-sans) !important;
  font-size: 0.84rem !important;
}

/* ── Sidebar select / dropdown control background ──────────────────── */
[data-testid="stSidebar"] [data-baseweb="select"] > div,
[data-testid="stSidebar"] [data-baseweb="select"] [class*="control"],
[data-testid="stSidebar"] [data-baseweb="select"] [class*="container"] {
  background-color: rgba(255,255,255,0.08) !important;
  border-color: rgba(255,255,255,0.15) !important;
}

/* ── Sidebar number input ──────────────────────────────────────────── */
[data-testid="stSidebar"] input[type="number"],
[data-testid="stSidebar"] input[type="text"],
[data-testid="stSidebar"] .stNumberInput input {
  color: #EDF3EB !important;
  background-color: rgba(255,255,255,0.08) !important;
  border-color: rgba(255,255,255,0.15) !important;
  font-family: var(--font-mono) !important;
  font-size: 0.84rem !important;
}
[data-testid="stSidebar"] .stNumberInput button {
  color: #8AAA84 !important;
  background-color: rgba(255,255,255,0.06) !important;
}

/* ── Sidebar toggle label ──────────────────────────────────────────── */
[data-testid="stSidebar"] [data-testid="stToggle"] span {
  color: #C8D5C0 !important;
  font-size: 0.82rem !important;
}

/* ── Sidebar divider ───────────────────────────────────────────────── */
[data-testid="stSidebar"] hr {
  border-color: #1F3A2A !important;
  margin: 0.9rem 0 !important;
}

/* ── Sidebar expander ──────────────────────────────────────────────── */
[data-testid="stSidebar"] [data-testid="stExpander"] {
  background: rgba(255,255,255,0.05) !important;
  border: 1px solid #1F3A2A !important;
  border-radius: 2px !important;
}
/* Expander summary text — do NOT affect the icon SVG */
[data-testid="stSidebar"] [data-testid="stExpander"] summary {
  font-family: var(--font-sans) !important;
  font-size: 0.72rem !important;
  font-weight: 700 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.10em !important;
  color: #8AAA84 !important;
}
/* Expander content text */
[data-testid="stSidebar"] [data-testid="stExpander"] p,
[data-testid="stSidebar"] [data-testid="stExpander"] span {
  color: #C8D5C0 !important;
  font-size: 0.80rem !important;
}

/* ── Sidebar PRIMARY button (Run Analysis, Load Data, Fetch Satellite) */
[data-testid="stSidebar"] button[kind="primary"],
[data-testid="stSidebar"] .stButton button[data-testid*="primary"],
[data-testid="stSidebar"] .stButton > button {
  background-color: var(--gold) !important;
  color: var(--ink) !important;        /* dark text on gold — readable */
  border: none !important;
  font-weight: 700 !important;
  font-family: var(--font-sans) !important;
  font-size: 0.80rem !important;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  border-radius: 2px !important;
  padding: 0.6rem 1rem !important;
  width: 100%;
  transition: background-color 0.15s;
}
[data-testid="stSidebar"] .stButton > button:hover {
  background-color: #B8952E !important;
  color: var(--ink) !important;
}

/* ── Sidebar inline header text (not in labels) ────────────────────── */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] small,
[data-testid="stSidebar"] div:not([data-baseweb]):not([class*="css"]) {
  color: #C8D5C0;
  font-family: var(--font-sans);
}

/* ── Sidebar progress / slider track ───────────────────────────────── */
[data-testid="stSidebar"] [data-testid="stSlider"] > div > div > div > div {
  background-color: var(--gold) !important;
}

/* ── Metric cards ──────────────────────────────────────────────────── */
[data-testid="stMetric"] {
  background: var(--white) !important;
  border: 1px solid var(--border) !important;
  border-top: 3px solid var(--growing) !important;
  border-radius: 2px !important;
  padding: 0.85rem 1.0rem 0.7rem !important;
}
[data-testid="stMetricLabel"] {
  font-family: var(--font-sans) !important;
  font-size: 0.65rem !important;
  font-weight: 700 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.11em !important;
  color: var(--slate-lt) !important;
}
[data-testid="stMetricValue"] {
  font-family: var(--font-mono) !important;
  font-size: 1.25rem !important;
  font-weight: 500 !important;
  color: var(--ink) !important;
  line-height: 1.2;
}
[data-testid="stMetricDelta"] {
  font-family: var(--font-mono) !important;
  font-size: 0.70rem !important;
}

/* ── Tabs ──────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
  background: transparent !important;
  border-bottom: 2px solid var(--border) !important;
  gap: 0 !important;
}
.stTabs [data-baseweb="tab"] {
  font-family: var(--font-sans) !important;
  font-size: 0.72rem !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.08em !important;
  color: var(--slate) !important;
  border-radius: 0 !important;
  padding: 0.52rem 0.95rem !important;
  border-bottom: 2px solid transparent !important;
  margin-bottom: -2px !important;
  background: transparent !important;
}
.stTabs [aria-selected="true"] {
  color: var(--growing) !important;
  border-bottom-color: var(--growing) !important;
}

/* ── DataFrames ────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
  border: 1px solid var(--border) !important;
  border-radius: 2px !important;
  font-family: var(--font-mono) !important;
  font-size: 0.77rem !important;
}

/* ── Divider ───────────────────────────────────────────────────────── */
hr {
  border: none !important;
  border-top: 1px solid var(--border) !important;
  margin: 1.3rem 0 !important;
}

/* ── Main area expanders ───────────────────────────────────────────── */
[data-testid="stExpander"] {
  border: 1px solid var(--border) !important;
  border-radius: 2px !important;
  background: var(--white) !important;
}
[data-testid="stExpander"] summary {
  font-family: var(--font-sans) !important;
  font-size: 0.76rem !important;
  font-weight: 600 !important;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--slate) !important;
}

/* ── Component classes ─────────────────────────────────────────────── */
.hs-page-header {
  font-family: var(--font-serif);
  font-size: 1.85rem;
  font-weight: 700;
  color: var(--ink);
  letter-spacing: -0.025em;
  line-height: 1.15;
  margin-bottom: 0.2rem;
}
.hs-page-subtitle {
  font-family: var(--font-sans);
  font-size: 0.87rem;
  color: var(--slate);
  margin-bottom: 0.1rem;
}
.hs-section-label {
  font-family: var(--font-sans);
  font-size: 0.63rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.15em;
  color: var(--slate-lt);
  margin: 0.8rem 0 0.3rem;
  padding-bottom: 0.22rem;
  border-bottom: 1px solid var(--border);
}
.hs-footer {
  font-family: var(--font-sans);
  font-size: 0.71rem;
  color: var(--slate-lt);
  text-align: center;
  padding: 0.4rem 0 1.5rem;
}

/* ── Download button ───────────────────────────────────────────────── */
[data-testid="stDownloadButton"] button {
  font-family: var(--font-sans) !important;
  font-size: 0.76rem !important;
  font-weight: 600 !important;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  border-radius: 2px !important;
}

/* ── Alert / info banners ──────────────────────────────────────────── */
[data-testid="stAlert"] {
  border-radius: 2px !important;
  font-family: var(--font-sans) !important;
  font-size: 0.85rem !important;
}

/* ── Navigation sidebar page links ────────────────────────────────── */
[data-testid="stSidebarNav"] a,
[data-testid="stSidebarNav"] span {
  font-family: var(--font-sans) !important;
  font-size: 0.84rem !important;
  color: #C8D5C0 !important;
}
[data-testid="stSidebarNav"] a:hover { color: #EDF3EB !important; }
[data-testid="stSidebarNav"] [aria-current="page"],
[data-testid="stSidebarNav"] [aria-selected="true"] {
  color: var(--gold) !important;
  font-weight: 600 !important;
}

/* ── HIGH-CONTRAST SIDEBAR TEXT (v2.4 patch) ───────────────────── */
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stMarkdown span,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
  color: #E2E8F0 !important;
  font-family: var(--font-sans) !important;
}
[data-testid="stSidebar"] [data-testid="stMetricLabel"] {
  color: #CBD5E1 !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] span,
[data-testid="stSidebar"] input {
  color: #F8FAFC !important;
}
[data-testid="stSidebar"] [data-testid="stSlider"] [data-testid="stTickBarMin"],
[data-testid="stSidebar"] [data-testid="stSlider"] [data-testid="stTickBarMax"],
[data-testid="stSidebar"] [data-testid="stSlider"] [data-testid="stThumbValue"] {
  color: #E2E8F0 !important;
}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_theme() -> None:
    """Inject Harvest Squeeze CSS. Call once per page after set_page_config()."""
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    """Render institutional page heading — text only, no emoji."""
    st.markdown(f'<div class="hs-page-header">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="hs-page-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def section_label(text: str) -> None:
    """Render a small-caps section divider — text only."""
    st.markdown(f'<div class="hs-section-label">{text}</div>', unsafe_allow_html=True)


def footer() -> None:
    """Standard page footer with data attribution."""
    st.markdown("<hr/>", unsafe_allow_html=True)
    st.markdown(
        "<div class='hs-footer'>"
        "The Harvest Squeeze &nbsp;&bull;&nbsp; "
        "Data: USDA NASS &middot; FRED St. Louis Fed &middot; EIA "
        "&middot; NASA MODIS/SMAP &middot; NOPA/EIA Value Chain XLSX<br/>"
        "Streamlit &middot; Plotly &middot; Pydeck &middot; GeoPandas &middot; SciPy"
        " &nbsp;&bull;&nbsp; 2026 Planning Tool &mdash; Not Investment Advice"
        "</div>",
        unsafe_allow_html=True,
    )


def plotly_layout_defaults() -> dict:
    """
    Base Plotly layout dict consistent with the Harvest Squeeze theme.

    IMPORTANT: This dict contains a 'legend' key.  When using **base to
    unpack into fig.update_layout(), do NOT also pass an explicit legend=
    argument in the same call — Python raises a TypeError for duplicate
    keyword arguments.

    Instead, either:
      a) Call update_layout(**base, ...) with no legend= kwarg, then call
         fig.update_layout(legend=dict(...)) in a second call.
      b) Filter the key out: {k:v for k,v in base.items() if k != 'legend'}
    """
    return dict(
        font=dict(family="IBM Plex Sans, Helvetica Neue, system-ui", size=11, color="#5A5A52"),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=8, r=8, t=40, b=8),
        title_font=dict(family="IBM Plex Sans", size=11, color="#0F2419"),
        legend=dict(
            bgcolor="rgba(0,0,0,0)", bordercolor="#E5E2DC",
            borderwidth=1, font=dict(size=10),
        ),
        xaxis=dict(gridcolor="#E5E2DC", showgrid=True, zeroline=False, gridwidth=0.5),
        yaxis=dict(gridcolor="#E5E2DC", showgrid=True, zeroline=False, gridwidth=0.5),
        colorway=[
            "#2D5A27", "#1E293B", "#C8A951",
            "#B91C1C", "#C2410C", "#15803D",
        ],
    )


def plotly_base_no_legend() -> dict:
    """
    Like plotly_layout_defaults() but with 'legend' removed.
    Use this when you need to pass a custom legend= in the same update_layout
    call to avoid the 'multiple values for keyword argument' TypeError.
    """
    base = plotly_layout_defaults()
    base.pop("legend", None)
    return base


def risk_row_style(val: str) -> str:
    """CSS string for a risk tier cell. Use with df.style.map()."""
    return {
        "HIGH":     "background-color:#FEE2E2;color:#7F1D1D;font-weight:700",
        "ELEVATED": "background-color:#FFEDD5;color:#7C2D12;font-weight:700",
        "MODERATE": "background-color:#FEF3C7;color:#78350F;font-weight:700",
        "HEALTHY":  "background-color:#DCFCE7;color:#14532D;font-weight:700",
    }.get(val, "")
