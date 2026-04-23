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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=IBM+Plex+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

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
  --font-sans:  'Inter', 'IBM Plex Sans', 'Helvetica Neue', system-ui, sans-serif;
  --font-mono:  'IBM Plex Mono', 'Courier New', monospace;
  --font-serif: Georgia, 'Times New Roman', serif;
}

/* ── App shell — maximum density ───────────────────────────────── */
.stApp { background-color: var(--parchment); font-family: var(--font-sans); }
.block-container {
  padding-top: 1.5rem !important;
  padding-bottom: 1.2rem !important;
  max-width: 1500px !important;
}
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }

/* Vertical gap — slightly tightened but not crushed */
.stVerticalBlock { gap: 0.55rem !important; }
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] {
  gap: 0.4rem !important;
}
/* Horizontal column gaps */
[data-testid="stHorizontalBlock"] { gap: 0.75rem !important; }

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
/* Use a solid dark background — rgba values can be overridden by
   Streamlit's base theme, causing white-on-white. #1C3828 matches the
   sidebar's dark green palette and gives clear contrast for light text. */
[data-testid="stSidebar"] input[type="number"],
[data-testid="stSidebar"] input[type="text"],
[data-testid="stSidebar"] .stNumberInput input {
  color: #EDF3EB !important;
  -webkit-text-fill-color: #EDF3EB !important;
  background: #1C3828 !important;
  background-color: #1C3828 !important;
  border: 1px solid rgba(255,255,255,0.18) !important;
  border-radius: 4px !important;
  font-family: var(--font-mono) !important;
  font-size: 0.84rem !important;
  caret-color: #EDF3EB !important;
}
[data-testid="stSidebar"] .stNumberInput button {
  color: #8AAA84 !important;
  background-color: #1C3828 !important;
  border-color: rgba(255,255,255,0.12) !important;
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

/* ── Metric cards — tight institutional style ──────────────────────── */
[data-testid="stMetric"] {
  background: var(--white) !important;
  border: 1px solid var(--border) !important;
  border-top: 2px solid var(--growing) !important;
  border-radius: 2px !important;
  padding: 0.5rem 0.75rem 0.4rem !important;
  height: auto !important;
  overflow: visible !important;
}
[data-testid="stMetricLabel"] {
  font-family: var(--font-sans) !important;
  font-size: 0.70rem !important;
  font-weight: 700 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.05em !important;
  color: var(--slate) !important;
  white-space: normal !important;
  overflow: visible !important;
  overflow-wrap: break-word !important;
  word-break: break-word !important;
  text-overflow: clip !important;
  line-height: 1.3 !important;
  height: auto !important;
}
/* Allow label's inner elements to wrap too */
[data-testid="stMetricLabel"] p,
[data-testid="stMetricLabel"] div,
[data-testid="stMetricLabel"] span {
  white-space: normal !important;
  overflow: visible !important;
  text-overflow: clip !important;
  overflow-wrap: break-word !important;
}
[data-testid="stMetricValue"] {
  font-family: var(--font-mono) !important;
  font-size: 1.10rem !important;
  font-weight: 500 !important;
  color: var(--ink) !important;
  line-height: 1.1 !important;
}
[data-testid="stMetricDelta"] {
  font-family: var(--font-mono) !important;
  font-size: 0.68rem !important;
  line-height: 1.2 !important;
}
/* Terminal financial delta colors */
[data-testid="stMetricDelta"].positive,
[data-testid="stMetricDelta"][class*="positive"] {
  color: #10B981 !important;
}
[data-testid="stMetricDelta"].negative,
[data-testid="stMetricDelta"][class*="negative"] {
  color: #FF3B30 !important;
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

/* ── DataFrames — condensed monospace ──────────────────────────────── */
[data-testid="stDataFrame"] {
  border: 1px solid var(--border) !important;
  border-radius: 2px !important;
  font-family: 'IBM Plex Mono', 'Roboto Mono', 'Courier New', monospace !important;
  font-size: 0.75rem !important;
}
/* Column headers */
[data-testid="stDataFrame"] th,
[data-testid="stDataFrame"] [data-testid="glideDataEditor"] .dvn-stack {
  font-family: var(--font-sans) !important;
  font-size: 0.67rem !important;
  font-weight: 700 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.05em !important;
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
  line-height: 1.2;
  margin-bottom: 0.45rem;
}
.hs-page-subtitle {
  font-family: var(--font-sans);
  font-size: 0.87rem;
  color: var(--slate);
  margin-bottom: 0.35rem;
  line-height: 1.5;
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
[data-testid="stSidebarNav"] span,
[data-testid="stSidebarNav"] li,
[data-testid="stSidebarNav"] p,
[data-testid="stSidebarNav"] div {
  font-family: var(--font-sans) !important;
  font-size: 0.84rem !important;
  color: #E2E8F0 !important;
}
[data-testid="stSidebarNav"] a:hover,
[data-testid="stSidebarNav"] a:hover span {
  color: #F8FAFC !important;
}
[data-testid="stSidebarNav"] [aria-current="page"],
[data-testid="stSidebarNav"] [aria-current="page"] span,
[data-testid="stSidebarNav"] [aria-selected="true"],
[data-testid="stSidebarNav"] [aria-selected="true"] span {
  color: var(--gold) !important;
  font-weight: 600 !important;
}

/* ── HIGH-CONTRAST SIDEBAR TEXT (v2.5) ────────────────────────── */
/* Target only text-bearing elements — NOT * which breaks icon fonts.
   Streamlit expanders use Material Symbols glyphs; overriding font-family
   on their span/svg containers renders the glyph as literal text ("arrow_right"). */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stMarkdown div,
[data-testid="stSidebar"] [data-testid="stSidebarContent"] div:not([class*="material"]):not([data-testid*="icon"]) {
  color: #F8FAFC;
  font-family: var(--font-sans);
}
/* Section labels (widget labels) — muted uppercase tone */
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stSlider label,
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stNumberInput label,
[data-testid="stSidebar"] .stToggle label,
[data-testid="stSidebar"] .stMultiSelect label,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
  color: #94A3B8 !important;
  font-family: var(--font-sans) !important;
}
/* Input values, select values, slider tick marks — full brightness */
[data-testid="stSidebar"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-baseweb="select"] div[class*="singleValue"],
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] .stNumberInput input,
[data-testid="stSidebar"] [data-testid="stSlider"] [data-testid="stTickBarMin"],
[data-testid="stSidebar"] [data-testid="stSlider"] [data-testid="stTickBarMax"],
[data-testid="stSidebar"] [data-testid="stSlider"] [data-testid="stThumbValue"] {
  color: #F8FAFC !important;
  -webkit-text-fill-color: #F8FAFC !important;
  font-family: var(--font-sans) !important;
}
/* Expander summary — only the text node, not the icon span */
[data-testid="stSidebar"] [data-testid="stExpander"] summary p,
[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stExpanderToggleIcon"] + p {
  color: #94A3B8 !important;
  font-family: var(--font-sans) !important;
}
/* Expander body text */
[data-testid="stSidebar"] [data-testid="stExpander"] .stMarkdown p {
  color: #CBD5E1 !important;
  font-size: 0.80rem !important;
  font-family: var(--font-sans) !important;
}

/* ── Brand header above nav links ─────────────────────────────── */
/* Title: injected via ::before on the nav container itself        */
[data-testid="stSidebarNav"]::before {
  content: "The Harvest Squeeze";
  display: block;
  font-family: Georgia, 'Times New Roman', serif !important;
  font-size: 1.05rem;
  font-weight: 700;
  color: #F0F4EE !important;
  letter-spacing: -0.01em;
  line-height: 1.2;
  padding: 0.55rem 0.9rem 0.1rem;
}
/* Subtitle: injected once, on the nav's <ul> child only.
   Avoid > div::before / nav::before — those match multiple children
   and cause the subtitle to repeat for each section.              */
[data-testid="stSidebarNav"] > ul::before {
  content: "PROFITABILITY RISK MONITOR \\B7 2026";
  display: block;
  font-family: 'Inter', 'IBM Plex Sans', sans-serif !important;
  font-size: 0.62rem;
  font-weight: 600;
  color: #6B8F74 !important;
  letter-spacing: 0.12em;
  padding: 0.15rem 0.9rem 0.65rem;
  border-bottom: 1px solid #1F3A2A;
  margin-bottom: 0.2rem;
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
    Base Plotly layout dict — Harvest Squeeze dark theme.

    Uses template='plotly_dark' for professional chart styling with fully
    transparent backgrounds so charts sit cleanly on the app background.

    Axis grid styles use Plotly dot-notation keys (xaxis_gridcolor, etc.)
    rather than nested dict keys (xaxis=dict(...)) so callers can safely
    pass explicit xaxis=dict(...) in the same update_layout() call without
    triggering a duplicate-keyword TypeError.

    Contains a 'legend' key — strip it before passing an explicit legend=
    kwarg in the same update_layout() call, or use plotly_base_no_legend().
    """
    return dict(
        template="plotly_dark",
        font=dict(family="IBM Plex Sans, Helvetica Neue, system-ui", size=10, color="#A0AEC0"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=30, b=10),
        title_font=dict(family="IBM Plex Sans", size=10, color="#E2E8F0"),
        legend=dict(
            yanchor="top", y=0.99, xanchor="left", x=0.01,
            bgcolor="rgba(15,36,25,0.70)",
            bordercolor="rgba(255,255,255,0.08)",
            borderwidth=1,
            font=dict(size=9, color="#A0AEC0"),
        ),
        # Dot-notation axis styles — safe to combine with explicit xaxis=/yaxis= kwargs
        xaxis_gridcolor="#222222",
        xaxis_showgrid=True,
        xaxis_zeroline=False,
        xaxis_gridwidth=0.5,
        xaxis_color="#A0AEC0",
        yaxis_gridcolor="#222222",
        yaxis_showgrid=True,
        yaxis_zeroline=False,
        yaxis_gridwidth=0.5,
        yaxis_color="#A0AEC0",
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
