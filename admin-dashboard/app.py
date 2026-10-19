"""
app.py
======
Streamlit Administrative Analytics Panel for the Intelligent Feedback
Analysis System.

Reads the unified feedback documents directly from MongoDB, renders the
KPIs and embedded Chart.js visualisations, and provides the Tier-D control
surface: an administrator isolates a slice of high-volume NEGATIVE comments
for a single department and requests a Gemini-synthesized immediate-action
summary from the backend.

UI is ported from the "High-Fidelity Admin Dashboard" Figma design — an
editorial light theme with a muted earthy sentiment palette, an Instrument
Serif greeting, KPI cards with sparklines, a sentiment-over-time area chart,
a stacked service-category bar, a KeyBERT keyword table with sentiment
spreads, expandable recent-feedback rows, and attention cards.

Run (from /admin-dashboard):
    streamlit run app.py
"""

from __future__ import annotations

import base64
import html
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from components.charts import (
    ACCENT,
    NEGATIVE,
    NEUTRAL,
    POSITIVE,
    category_bar,
    sentiment_doughnut,
    sentiment_trend,
)

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "feedback_analysis_db")
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Feedback Intelligence — Admin",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==========================================================================
# Design layer — fonts + full stylesheet (presentation only).
# ==========================================================================
# Sentiment + accent stay identical across themes (they match the Chart.js
# palette exactly); only the neutral chrome — surfaces, text, borders — flips.
_ROOT_LIGHT = """
  :root {
    --pos: #5B8A6A; --neg: #B55944; --neu: #C49340; --accent: #4255A4;
    --bg: #FCFCFC; --card: #F5F5F4; --border: rgba(0,0,0,0.07);
    --fg: #111111; --muted: #6B6B6B; --secondary: #EFEFEE;
  }
"""
_ROOT_DARK = """
  :root {
    --pos: #5B8A6A; --neg: #B55944; --neu: #C49340; --accent: #6D80D6;
    --bg: #0F0F12; --card: #1A1A1F; --border: rgba(255,255,255,0.09);
    --fg: #F3F3F1; --muted: #9A9A9F; --secondary: #232329;
  }
"""

# Self-hosted Outfit, base64-inlined into the stylesheet so it needs no network
# (Google Fonts is blocked on this host — a CDN @import would silently fail and
# fall back to a system font, which is exactly what was happening before).
def _outfit_font_face() -> str:
    path = Path(__file__).parent / "assets" / "outfit-latin.woff2"
    try:
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""  # graceful fallback to the system stack
    return (
        "@font-face { font-family: 'Outfit'; font-style: normal; "
        "font-weight: 300 800; font-display: swap; "
        f"src: url(data:font/woff2;base64,{b64}) format('woff2'); }}"
    )


_FONT_FACE = _outfit_font_face()

_GLOBAL_CSS = """
<style>
  /*FONTFACE*/

  /*ROOTVARS*/

  /* ---- base typography + chrome ---- */
  html, body, .stApp, [class*="css"] {
    font-family: 'Outfit', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  }
  .stApp { background: var(--bg); }
  #MainMenu, footer { visibility: hidden; }
  /* Keep the header AND its toolbar PRESENT — when the sidebar is collapsed,
     Streamlit renders the reopen button (stExpandSidebarButton) INSIDE the
     toolbar, so hiding the whole toolbar (as we used to) made the sidebar
     impossible to reopen. Instead hide only the Deploy button + main menu +
     the decoration bar, and leave the toolbar itself visible. */
  header[data-testid="stHeader"] { background: transparent; }
  [data-testid="stDecoration"] { display: none !important; }
  [data-testid="stToolbarActions"],
  [data-testid="stAppDeployButton"],
  [data-testid="stMainMenu"] { display: none !important; }
  /* SIDEBAR — collapsible at every screen size (earlier we pinned it open and
     hid the toggle, which trapped a 19rem panel on phones). Instead we now:
       1. keep the collapse/expand toggle ALWAYS visible, and
       2. force its icon colour to the theme foreground — a transparent/white
          glyph on our transparent header is why it looked "missing", and
       3. pin the width to 19rem ONLY while the sidebar is open, so collapsing
          actually reclaims the space instead of leaving a blank strip. */
  [data-testid="stSidebarCollapseButton"],
  [data-testid="stExpandSidebarButton"],
  [data-testid="collapsedControl"] {
    display: inline-flex !important; visibility: visible !important; opacity: 1 !important;
    z-index: 1000 !important;
  }
  [data-testid="stSidebarCollapseButton"] svg,
  [data-testid="stExpandSidebarButton"] svg,
  [data-testid="collapsedControl"] svg {
    fill: var(--fg) !important; color: var(--fg) !important; opacity: 1 !important;
  }
  section[data-testid="stSidebar"][aria-expanded="true"] {
    width: 19rem !important; min-width: 19rem !important; max-width: 19rem !important;
  }
  section[data-testid="stSidebar"][aria-expanded="true"] > div { width: 19rem !important; }
  .block-container { padding-top: 2.6rem; padding-bottom: 3rem; max-width: 1200px; }

  /* ---- theme-adaptive Streamlit widgets (drive off the CSS vars so one set
          of rules covers BOTH light and dark) ---- */
  .stApp, .stMarkdown, [data-testid="stCaptionContainer"],
  [data-testid="stExpander"] summary { color: var(--fg); }
  [data-baseweb="select"] > div, [data-baseweb="input"], .stTextInput input {
    background: var(--secondary) !important; border-color: var(--border) !important;
    color: var(--fg) !important;
  }
  [data-baseweb="select"] svg { fill: var(--muted) !important; }
  [data-baseweb="popover"] [role="listbox"], [data-baseweb="menu"] {
    background: var(--card) !important; border: 1px solid var(--border) !important;
  }
  [data-baseweb="menu"] li { color: var(--fg) !important; }
  [data-testid="stMetricValue"] { color: var(--fg) !important; }
  [data-testid="stMetricLabel"] { color: var(--muted) !important; }
  .stTextInput label, [data-testid="stWidgetLabel"] label { color: var(--muted) !important; }

  /* Date-range picker: Streamlit's base="light" keeps this widget light, so in
     dark mode its value text/surface must be re-driven off our theme vars. */
  [data-testid="stDateInput"] [data-baseweb="input"],
  [data-testid="stDateInput"] > div > div {
    background: var(--secondary) !important; border-color: var(--border) !important;
  }
  [data-testid="stDateInput"] input {
    color: var(--fg) !important; -webkit-text-fill-color: var(--fg) !important;
    background: transparent !important;
  }

  /* Sidebar radio (Dashboard / All Feedback): recolour option text + dot. */
  [data-testid="stRadio"] label, [data-testid="stRadio"] label p,
  [data-testid="stRadio"] div[role="radiogroup"] label { color: var(--fg) !important; }

  /* Download / Export button: match the dark surface instead of a stark white. */
  [data-testid="stDownloadButton"] button {
    background: var(--secondary) !important; color: var(--fg) !important;
    border: 1px solid var(--border) !important;
  }
  [data-testid="stDownloadButton"] button:hover {
    border-color: var(--accent) !important; color: var(--accent) !important;
  }

  /* Expander header (Recent Feedback rows): the <summary> carries Streamlit's
     own light background that only cleared on hover — pin it to our card colour
     so the collapsed header is visible in dark mode without hovering. */
  [data-testid="stExpander"] details,
  [data-testid="stExpander"] summary { background: var(--card) !important; }
  [data-testid="stExpander"] summary:hover { background: var(--secondary) !important; }
  [data-testid="stExpander"] summary,
  [data-testid="stExpander"] summary * { color: var(--fg) !important; }
  [data-testid="stExpander"] svg { fill: var(--muted) !important; }

  /* ---- serif greeting ---- */
  .greeting {
    font-family: 'Instrument Serif', Georgia, serif; font-weight: 400;
    font-size: 27px; line-height: 1.25; color: var(--fg);
    letter-spacing: -0.01em; margin: 0;
  }
  .greeting-sub { font-size: 13px; color: var(--muted); margin-top: 6px;
                  line-height: 1.55; max-width: 760px; }

  /* ---- section heading ---- */
  .sec { display: flex; align-items: baseline; justify-content: space-between;
         margin: 26px 0 12px; }
  .sec h2 { font-size: 13px; font-weight: 600; color: var(--fg); margin: 0; }
  .sec .meta { font-size: 9px; letter-spacing: 0.09em; text-transform: uppercase;
               color: var(--muted); }

  /* ---- KPI cards ---- */
  .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
  .kpi {
    background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; padding: 15px 16px 13px;
  }
  .kpi-top { display: flex; align-items: flex-start; justify-content: space-between;
             margin-bottom: 8px; }
  .kpi-label { font-size: 9px; letter-spacing: 0.1em; text-transform: uppercase;
               color: var(--muted); font-weight: 500;
               display: inline-flex; align-items: center; gap: 5px; }
  .kpi-ic { display: inline-flex; }
  .kpi-ic svg { display: block; }
  .kpi-value { font-size: 26px; font-weight: 600; color: var(--fg);
               line-height: 1; font-variant-numeric: tabular-nums; }
  .kpi-sub { display: flex; align-items: center; gap: 6px; margin-top: 9px;
             font-size: 11px; color: var(--muted); }
  .kpi-sub .dot { width: 7px; height: 7px; border-radius: 50%; flex: none; }
  .kpi-sub b { color: var(--fg); font-weight: 600; font-variant-numeric: tabular-nums; }

  /* ---- keyword table ---- */
  .panel { background: var(--card); border: 1px solid var(--border);
           border-radius: 10px; overflow: hidden; }
  .panel-head { padding: 15px 18px; border-bottom: 1px solid var(--border);
                display: flex; align-items: baseline; justify-content: space-between; }
  .panel-head h3 { font-size: 13px; font-weight: 600; color: var(--fg); margin: 0; }
  .panel-head p { font-size: 11px; color: var(--muted); margin: 3px 0 0; }
  .panel-head .cnt { font-size: 9px; letter-spacing: 0.09em; text-transform: uppercase;
                     color: var(--muted); }
  .kw-row { display: grid; grid-template-columns: 22px 1fr 54px 150px 96px;
            gap: 14px; align-items: center; padding: 11px 18px;
            border-bottom: 1px solid var(--border); }
  .kw-row:last-child { border-bottom: none; }
  .kw-head { padding: 7px 18px; }
  .kw-head span { font-size: 9px; letter-spacing: 0.09em; text-transform: uppercase;
                  color: var(--muted); font-weight: 500; }
  .kw-idx { font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; }
  .kw-name { font-size: 12px; font-weight: 500; color: var(--fg); }
  .kw-score { font-size: 12px; font-weight: 600; color: var(--accent);
              font-variant-numeric: tabular-nums; }
  .kw-bar { display: flex; height: 5px; border-radius: 3px; overflow: hidden; }
  .kw-bar span { display: block; }
  .kw-counts { display: flex; align-items: center; gap: 11px;
               font-variant-numeric: tabular-nums; }
  .kw-counts .c { display: flex; align-items: center; gap: 5px;
                  font-size: 11px; color: var(--muted); }
  .kw-counts .d { width: 6px; height: 6px; border-radius: 50%; flex: none; }

  /* ---- attention cards ---- */
  .attn-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
  .attn { background: var(--card); border: 1px solid var(--border);
          border-radius: 10px; padding: 15px 16px; display: flex; gap: 12px; }
  .attn.high { border-color: rgba(181,89,68,0.28); }
  .attn-ic { width: 32px; height: 32px; border-radius: 8px; flex: none;
             display: grid; place-items: center; font-size: 15px; }
  .attn-ic svg { display: block; }
  .attn-body { flex: 1; min-width: 0; }
  .attn-title { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
  .attn-title b { font-size: 12px; font-weight: 600; color: var(--fg); }
  .attn-chip { font-size: 10px; font-weight: 500; padding: 1px 6px; border-radius: 4px; }
  .attn-body p { font-size: 11px; color: var(--muted); line-height: 1.5; margin: 0; }

  /* ---- sidebar ---- */
  section[data-testid="stSidebar"] { background: var(--card);
                                     border-right: 1px solid var(--border); }
  section[data-testid="stSidebar"] .block-container { padding-top: 1.3rem; }
  .brand { display: flex; align-items: center; gap: 10px; padding-bottom: 14px;
           margin-bottom: 6px; border-bottom: 1px solid var(--border); }
  .brand .mark { width: 32px; height: 32px; border-radius: 8px; flex: none;
                 display: grid; place-items: center; background: var(--accent);
                 color: #fff; font-size: 10px; font-weight: 700; letter-spacing: -0.02em; }
  .brand .name { font-size: 12px; font-weight: 600; color: var(--fg); line-height: 1.3; }
  .brand .tag { font-size: 10px; color: var(--muted); line-height: 1.3; }
  .side-label { font-size: 9px; letter-spacing: 0.1em; text-transform: uppercase;
                color: var(--muted); font-weight: 500; margin: 14px 0 2px; }
  .profile { display: flex; align-items: center; gap: 10px; padding: 12px 0 4px;
             margin-top: 10px; border-top: 1px solid var(--border); }
  .profile .av { width: 28px; height: 28px; border-radius: 50%; flex: none;
                 display: grid; place-items: center; background: #7C8DB0;
                 color: #fff; font-size: 11px; font-weight: 600; }
  .profile .who { font-size: 12px; font-weight: 500; color: var(--fg); line-height: 1.3; }
  .profile .role { font-size: 10px; color: var(--muted); line-height: 1.3; }

  /* ---- inputs / buttons ---- */
  [data-testid="stSidebar"] .stSelectbox label { font-size: 11px !important;
                                                  color: var(--muted) !important; }
  .stButton > button, .stFormSubmitButton > button {
    border-radius: 8px; font-weight: 500; font-size: 12px;
    border: 1px solid var(--border);
  }
  /* secondary (non-primary) buttons follow the theme surface */
  .stButton > button:not([kind*="primary"]),
  .stFormSubmitButton > button:not([kind*="primary"]) {
    background: var(--secondary); color: var(--fg);
  }
  .mono { font-family: 'JetBrains Mono', ui-monospace, monospace; }

  /* ---- expanders (recent feedback rows) ---- */
  [data-testid="stExpander"] { border: 1px solid var(--border); border-radius: 10px;
                               background: var(--card); margin-bottom: 8px; }
  [data-testid="stExpander"] summary { font-size: 12px; }
  .fb-full { font-size: 13px; color: var(--fg); line-height: 1.6; }
  .chip { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: 6px;
          border: 1px solid var(--border); color: var(--muted); margin: 0 4px 4px 0; }

  /* ---- All Feedback browser ---- */
  .fb-card { background: var(--card); border: 1px solid var(--border);
             border-radius: 10px; padding: 14px 16px; margin-bottom: 10px; }
  .fb-meta { display: flex; align-items: center; gap: 9px; flex-wrap: wrap;
             margin-bottom: 9px; font-size: 11px; color: var(--muted);
             font-variant-numeric: tabular-nums; }
  .fb-pill { font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 5px; }
  .fb-gem { font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 5px;
            background: rgba(66,85,164,0.15); color: var(--accent); }
  .fb-text { font-size: 13px; color: var(--fg); line-height: 1.55; }
  .fb-kws { margin-top: 9px; }

  /* ---- login ---- */
  .login-card { max-width: 380px; margin: 7vh auto 0; background: var(--card);
                border: 1px solid var(--border); border-radius: 14px;
                padding: 30px 30px 6px; }
  .login-mark { width: 40px; height: 40px; border-radius: 10px; margin: 0 auto 14px;
                display: grid; place-items: center; background: var(--accent);
                color: #fff; font-size: 12px; font-weight: 700; }
  .login-card h2 { font-family: 'Instrument Serif', Georgia, serif; font-weight: 400;
                   text-align: center; font-size: 23px; margin: 0 0 2px; color: var(--fg); }
  .login-card .sub { text-align: center; color: var(--muted); font-size: 12px;
                     margin-bottom: 16px; }

  /* Wide keyword table scrolls inside its own container on narrow screens. */
  .kw-scroll { overflow-x: auto; }
  .kw-headrow { display: grid; grid-template-columns: 22px 1fr 54px 150px 96px;
                gap: 14px; }
  .kw-row, .kw-headrow { min-width: 500px; }

  @media (max-width: 900px) { .kpi-grid { grid-template-columns: repeat(2, 1fr); } }
  @media (max-width: 560px) { .kpi-grid { grid-template-columns: 1fr; } }
  @media (max-width: 760px) { .attn-grid { grid-template-columns: 1fr; } }
</style>
"""


def is_dark() -> bool:
    """Current theme preference (persisted via the sidebar toggle's key)."""
    return bool(st.session_state.get("dark_mode", False))


def inject_css(dark: bool) -> None:
    root = _ROOT_DARK if dark else _ROOT_LIGHT
    css = _GLOBAL_CSS.replace("/*FONTFACE*/", _FONT_FACE).replace("/*ROOTVARS*/", root)
    st.markdown(css, unsafe_allow_html=True)


def esc(text: Any) -> str:
    return html.escape(str(text))


def cat_label(row: Any) -> str:
    """Category for display: 'Other — Transport' when the student named it."""
    cat = row.get("category", "Other")
    custom = (row.get("custom_category") or "").strip()
    return f"{cat} — {custom}" if custom else cat

def fmt_day(ts: Any, with_year: bool = False) -> str:
    """Format a timestamp as '3 Jul' / '3 Jul 2026' with no zero-padded day.

    The `%-d` directive used for this is a glibc extension that Windows'
    strftime rejects with `ValueError: Invalid format string`, so the day is
    interpolated directly instead of via a format code.
    """
    t = pd.Timestamp(ts)
    return f"{t.day} {t.strftime('%b %Y' if with_year else '%b')}"


def sparkline_svg(data: List[float], color: str, w: int = 72, h: int = 26) -> str:
    """Inline SVG sparkline — lightweight, no extra iframe."""
    pts = [float(v) for v in data if v is not None]
    if len(pts) < 2:
        pts = [0.0, 0.0]
    mn, mx = min(pts), max(pts)
    rng = (mx - mn) or 1.0
    n = len(pts)
    coords = []
    for i, v in enumerate(pts):
        x = (i / (n - 1)) * w
        y = h - ((v - mn) / rng) * (h - 4) - 2
        coords.append(f"{x:.1f},{y:.1f}")
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none">'
        f'<polyline points="{" ".join(coords)}" stroke="{color}" '
        f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )


# ==========================================================================
# Data aggregation (feed the ported design from real documents)
# ==========================================================================
# Shortest span the trend chart will draw. A line needs at least two points to
# be a line, so a brand-new deployment with one day of feedback still gets a
# readable week-long axis instead of a single floating dot.
_MIN_TREND_DAYS = 7


def build_daily_series(df: pd.DataFrame) -> Dict[str, Any]:
    """Per-day sentiment counts for the area chart + KPI sparklines."""
    d = df.copy()
    d["dt"] = pd.to_datetime(d["date_submitted"], errors="coerce", utc=True)
    d = d.dropna(subset=["dt"])
    empty = {"labels": [], "Positive": [], "Negative": [], "Neutral": [], "Total": []}
    if d.empty:
        return empty
    d["day"] = d["dt"].dt.normalize()

    # Use a CONTINUOUS run of days, not just the days that happen to have
    # feedback. Two things go wrong otherwise:
    #   * a single day of data yields one point, and a line chart with one point
    #     draws no line at all — the panel looks broken rather than sparse;
    #   * days with no submissions are dropped, so 1 Sep and 16 Sep render side
    #     by side as though they were consecutive, which misstates the trend.
    first, last = d["day"].min(), d["day"].max()
    # Always show at least a week so a new deployment has a readable axis.
    start = min(first, last - pd.Timedelta(days=_MIN_TREND_DAYS - 1))
    days = pd.date_range(start=start, end=last, freq="D")

    out: Dict[str, Any] = {
        "labels": [fmt_day(x) for x in days],
        "Positive": [], "Negative": [], "Neutral": [], "Total": [],
    }
    for x in days:
        day_mask = d["day"] == x
        p = int((day_mask & (d["label"] == "POSITIVE")).sum())
        n = int((day_mask & (d["label"] == "NEGATIVE")).sum())
        u = int((day_mask & (d["label"] == "NEUTRAL")).sum())
        out["Positive"].append(p)
        out["Negative"].append(n)
        out["Neutral"].append(u)
        out["Total"].append(p + n + u)
    return out


def build_category_rows(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Stacked sentiment counts per service category (sorted by volume)."""
    rows = []
    for cat, g in df.groupby("category"):
        rows.append({
            "name": str(cat),
            "Positive": int((g["label"] == "POSITIVE").sum()),
            "Neutral": int((g["label"] == "NEUTRAL").sum()),
            "Negative": int((g["label"] == "NEGATIVE").sum()),
        })
    rows.sort(key=lambda r: r["Positive"] + r["Neutral"] + r["Negative"], reverse=True)
    return rows


def build_keyword_spread(df: pd.DataFrame, top_n: int = 8) -> List[Dict[str, Any]]:
    """Aggregate KeyBERT keywords with per-sentiment spread + peak score."""
    agg: Dict[str, Dict[str, float]] = defaultdict(
        lambda: {"pos": 0, "neg": 0, "neu": 0, "score": 0.0}
    )
    for _, row in df.iterrows():
        label = row["label"]
        for k in row["keywords"]:
            kw = k.get("keyword", "").strip()
            if not kw:
                continue
            a = agg[kw]
            if label == "POSITIVE":
                a["pos"] += 1
            elif label == "NEGATIVE":
                a["neg"] += 1
            else:
                a["neu"] += 1
            a["score"] = max(a["score"], float(k.get("score", 0) or 0))
    items = []
    for kw, v in agg.items():
        total = v["pos"] + v["neg"] + v["neu"]
        items.append({"keyword": kw, "total": total, **v})
    items.sort(key=lambda x: (x["total"], x["score"]), reverse=True)
    return items[:top_n]


def build_attention(df: pd.DataFrame, top_n: int = 4) -> List[Dict[str, Any]]:
    """Service areas with the most negative feedback."""
    rows = []
    for cat, g in df.groupby("category"):
        neg = int((g["label"] == "NEGATIVE").sum())
        if neg == 0:
            continue
        total = len(g)
        share = (neg / total * 100) if total else 0
        rows.append({
            "category": str(cat), "neg": neg, "total": total, "share": share,
            "high": share >= 60 or neg >= 3,
        })
    rows.sort(key=lambda r: (r["neg"], r["share"]), reverse=True)
    return rows[:top_n]


# Crisp inline-SVG line icons (Lucide-style, 24×24, drawn with currentColor so
# they inherit whatever colour the surrounding card sets). Replaces emoji, which
# render inconsistently across platforms and looked generic.
_ICON_PATHS = {
    "Wi-Fi": '<path d="M12 20h.01"/><path d="M2 8.8a15 15 0 0 1 20 0"/>'
             '<path d="M5 12.9a10 10 0 0 1 14 0"/><path d="M8.5 16.4a5 5 0 0 1 7 0"/>',
    "Hostel": '<path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
              '<path d="M9 22V12h6v10"/>',
    "Library": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>'
               '<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
    "ICT": '<rect x="2" y="3" width="20" height="14" rx="2"/>'
           '<path d="M8 21h8"/><path d="M12 17v4"/>',
    "Teaching": '<path d="M22 10 12 5 2 10l10 5 10-5Z"/>'
                '<path d="M6 12v5c0 1 2.7 3 6 3s6-2 6-3v-5"/>',
    "Registration": '<rect x="8" y="2" width="8" height="4" rx="1"/>'
                    '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>'
                    '<path d="M9 12h6M9 16h6"/>',
    "Examination": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/>'
                   '<path d="M14 2v6h6"/><path d="m9 15 2 2 4-4"/>',
    "Counseling": '<path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9'
                  'L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5'
                  'a8.5 8.5 0 0 1 8 8v.5Z"/>',
    "Administration": '<line x1="3" y1="22" x2="21" y2="22"/><line x1="6" y1="18" x2="6" y2="11"/>'
                      '<line x1="10" y1="18" x2="10" y2="11"/><line x1="14" y1="18" x2="14" y2="11"/>'
                      '<line x1="18" y1="18" x2="18" y2="11"/><polygon points="12 2 20 7 4 7"/>',
    "Other": '<circle cx="12" cy="12" r="9"/><path d="M12 8v4M12 16h.01"/>',
    # KPI / sentiment glyphs
    "total": '<path d="m12 2 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5"/><path d="m3 17 9 5 9-5"/>',
    "up": '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    "down": '<polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/><polyline points="16 17 22 17 22 11"/>',
    "flat": '<path d="M5 12h14"/>',
}


def icon_svg(name: str, size: int = 15, width: float = 1.8) -> str:
    """Return an inline SVG line-icon that inherits `currentColor`."""
    path = _ICON_PATHS.get(name, _ICON_PATHS["Other"])
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="{width}" stroke-linecap="round" '
        f'stroke-linejoin="round">{path}</svg>'
    )


# ==========================================================================
# Data access (cached Mongo client + query)
# ==========================================================================
@st.cache_resource(show_spinner=False)
def get_client() -> MongoClient:
    """Create a cached synchronous Mongo client with a fail-fast timeout."""
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)


# Read-time join of the Feedback documents against the Student collection.
#
# Department is resolved from three sources, most trustworthy first:
#   1. `department` stored on the feedback record — what the student entered on
#      their own profile. Always correct for them, and present for everyone.
#   2. The Student roster, joined on `student_id` — covers records written
#      before the field existed, where the student is on the roster.
#   3. "Unknown" — an old record from someone not on the roster.
#
# The roster alone is not enough: it only contains seeded students, so every
# real submitter fell through to "Unknown". Preferring the stored value keeps
# the single-write embedded design while making the join a fallback, not the
# only path.
_DEPARTMENT_JOIN_PIPELINE: List[Dict[str, Any]] = [
    {
        "$lookup": {
            "from": "students",
            "localField": "student_id",
            "foreignField": "student_id",
            "as": "_student",
        }
    },
    {
        "$addFields": {
            # Inside $addFields, "$department" still refers to the document's
            # own value, so this reads as: stored -> roster -> "Unknown".
            "department": {
                "$ifNull": [
                    "$department",
                    {"$arrayElemAt": ["$_student.department", 0]},
                    "Unknown",
                ]
            },
            # Same precedence as department: what the student gave us, then
            # the roster, then blank.
            "student_name": {
                "$ifNull": [
                    "$student_name",
                    {"$arrayElemAt": ["$_student.name", 0]},
                    "",
                ]
            },
        }
    },
    {"$project": {"_student": 0}},
]


@st.cache_data(ttl=30, show_spinner="Loading feedback…")
def load_feedback() -> pd.DataFrame:
    """
    Pull every feedback document, join the owning student's department via
    a server-side $lookup, and flatten the embedded sub-objects into a
    tabular frame. Cached for 30s so the dashboard stays responsive.
    """
    try:
        client = get_client()
        cursor = client[MONGO_DB_NAME]["feedback"].aggregate(_DEPARTMENT_JOIN_PIPELINE)
        rows: List[Dict[str, Any]] = []
        for doc in cursor:
            sentiment = doc.get("sentiment_analysis") or {}
            keywords = doc.get("keywords_extracted") or []
            rows.append(
                {
                    "id": str(doc.get("_id")),
                    "student_id": doc.get("student_id", ""),
                    "student_name": doc.get("student_name", ""),
                    "department": doc.get("department", "Unknown"),
                    "category": doc.get("category", "Other"),
                    # What the student typed when they chose "Other". Kept
                    # separate from `category` so the closed-enum analytics
                    # stay intact, and shown beside it on the cards.
                    "custom_category": doc.get("custom_category") or "",
                    "feedback_text": doc.get("feedback_text", ""),
                    "date_submitted": doc.get("date_submitted"),
                    "label": (sentiment.get("label") or "NEUTRAL").upper(),
                    "confidence_score": sentiment.get("confidence_score", 0.0),
                    "source": (sentiment.get("source") or "distilbert").lower(),
                    "keywords": [
                        {
                            "keyword": k.get("keyword", ""),
                            "score": float(k.get("relevance_score", 0) or 0),
                        }
                        for k in keywords
                    ],
                }
            )
        return pd.DataFrame(rows)
    except (ServerSelectionTimeoutError, PyMongoError) as exc:
        st.error(f"Could not reach MongoDB: {exc}")
        return pd.DataFrame()


def backend_login(username: str, password: str) -> Dict[str, Any]:
    """Authenticate against the backend `/api/admin/login` (OAuth2 password form)."""
    resp = requests.post(
        f"{BACKEND_API_URL}/api/admin/login",
        data={"username": username, "password": password},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def _post_summary_request(url: str, token: str, **kwargs: Any) -> requests.Response:
    kwargs["headers"] = {"Authorization": "Bearer " + token}
    return requests.post(url, **kwargs)


def request_summary(
    token: str, department: str, category: str | None, comments: List[str]
) -> str:
    # Forward the authenticated administrator session to the protected API.
    """Call the protected backend Tier-D endpoint to synthesize an action summary."""
    payload = {
        "department": department,
        "category": category,
        "negative_comments": comments,
    }
    resp = _post_summary_request(
        f"{BACKEND_API_URL}/api/admin/summarize",
        token,
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=45,
    )
    resp.raise_for_status()
    return resp.json().get("action_summary", "")


# ==========================================================================
# Authentication gate
# ==========================================================================
def render_login() -> None:
    """Editorial login card, blocking the dashboard until authenticated."""
    st.markdown(
        """
        <div class="login-card">
          <div class="login-mark">IFAS</div>
          <h2>Feedback Intelligence</h2>
          <div class="sub">Administrative sign-in</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        with st.form("login_form"):
            username = st.text_input("Username", placeholder="admin")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button(
                "Sign in", type="primary", use_container_width=True
            )
        if submitted:
            try:
                data = backend_login(username, password)
                st.session_state["auth_token"] = data["access_token"]
                st.session_state["auth_role"] = data.get("role", "")
                st.session_state["auth_user"] = data.get("username", username)
                # Persist to the URL so a page reload restores the session.
                st.query_params["t"] = data["access_token"]
                st.query_params["r"] = data.get("role", "")
                st.query_params["u"] = data.get("username", username)
                st.rerun()
            except requests.HTTPError:
                st.error("Incorrect username or password.")
            except requests.RequestException as exc:
                st.error(f"Could not reach the backend API: {exc}")


def _restore_session_from_url() -> None:
    """Rehydrate the login from URL query params after a full page reload.

    st.session_state is per-session and is wiped when the browser reloads (F5),
    which otherwise forces a re-login. We stash the issued token in the query
    params on sign-in and restore it here so a reload keeps the admin logged in.
    (Local single-admin dashboard — an expired/invalid token is still rejected
    by the backend on the protected Tier-D call.)
    """
    if st.session_state.get("auth_token"):
        return
    tok = st.query_params.get("t")
    if tok:
        st.session_state["auth_token"] = tok
        st.session_state["auth_role"] = st.query_params.get("r", "")
        st.session_state["auth_user"] = st.query_params.get("u", "")


def require_auth() -> None:
    _restore_session_from_url()
    if not st.session_state.get("auth_token"):
        render_login()
        st.stop()


# ==========================================================================
# Sidebar (brand + filters + profile)
# ==========================================================================
def render_sidebar(df: pd.DataFrame) -> Dict[str, str]:
    with st.sidebar:
        st.markdown(
            """
            <div class="brand">
              <div class="mark">IFAS</div>
              <div>
                <div class="name">Feedback Intelligence</div>
                <div class="tag">Academic Services · Admin</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="side-label">View</div>', unsafe_allow_html=True)
        view = st.radio(
            "View", ["Dashboard", "All Feedback"],
            label_visibility="collapsed", key="view_mode",
        )

        st.markdown('<div class="side-label">Filters</div>', unsafe_allow_html=True)
        departments = ["All"] + sorted(df["department"].dropna().unique().tolist())
        dept = st.selectbox("Department", departments, label_visibility="collapsed")

        categories = ["All"] + sorted(df["category"].dropna().unique().tolist())
        st.markdown('<div class="side-label">Service category</div>', unsafe_allow_html=True)
        cat = st.selectbox("Category", categories, label_visibility="collapsed")

        st.markdown('<div class="side-label">Sentiment</div>', unsafe_allow_html=True)
        sent = st.selectbox(
            "Sentiment", ["All", "POSITIVE", "NEUTRAL", "NEGATIVE"],
            label_visibility="collapsed",
        )

        st.markdown('<div class="side-label">Date range</div>', unsafe_allow_html=True)
        _dts = pd.to_datetime(df["date_submitted"], errors="coerce", utc=True).dropna()
        if len(_dts):
            dmin, dmax = _dts.min().date(), _dts.max().date()
        else:
            dmin = dmax = datetime.utcnow().date()
        date_range = st.date_input(
            "Date range", value=(dmin, dmax), min_value=dmin, max_value=dmax,
            label_visibility="collapsed",
        )

        st.markdown('<div class="side-label">Appearance</div>', unsafe_allow_html=True)
        # key="dark_mode" is read by is_dark() at the top of the next rerun, so
        # flipping this re-themes the whole page (and charts) with no lag.
        st.toggle("Dark mode", key="dark_mode")

        user = st.session_state.get("auth_user", "admin")
        initials = "".join([p[0] for p in user.replace(".", " ").split()[:2]]).upper() or "AO"
        st.markdown(
            f"""
            <div class="profile">
              <div class="av">{esc(initials)}</div>
              <div>
                <div class="who">{esc(user)}</div>
                <div class="role">{esc(st.session_state.get('auth_role', ''))}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Log out", use_container_width=True):
            for key in ("auth_token", "auth_role", "auth_user"):
                st.session_state.pop(key, None)
            st.query_params.clear()
            st.rerun()

    return {"department": dept, "category": cat, "sentiment": sent, "view": view,
            "date_range": date_range}


_SENT_TINT = {
    "POSITIVE": "rgba(91,138,106,0.16)",
    "NEGATIVE": "rgba(181,89,68,0.16)",
    "NEUTRAL": "rgba(196,147,64,0.16)",
}
_SENT_PILL = {"POSITIVE": ("Positive", POSITIVE), "NEGATIVE": ("Negative", NEGATIVE),
              "NEUTRAL": ("Neutral", NEUTRAL)}


def render_all_feedback(data: pd.DataFrame) -> None:
    """Full, searchable list of every feedback entry in the current filter."""
    st.markdown(
        f'<h1 class="greeting">All Feedback</h1>'
        f'<p class="greeting-sub">Every entry in the current filter, newest first. '
        f'Use the search box or the sidebar filters to narrow the list.</p>',
        unsafe_allow_html=True,
    )
    q = st.text_input(
        "Search feedback", placeholder="Search text, student, category or department…",
        label_visibility="collapsed",
    )
    if q:
        ql = q.lower()
        data = data[
            data["feedback_text"].str.lower().str.contains(ql, na=False)
            | data["student_id"].astype(str).str.lower().str.contains(ql, na=False)
            | data["student_name"].astype(str).str.lower().str.contains(ql, na=False)
            | data["category"].astype(str).str.lower().str.contains(ql, na=False)
            | data["department"].astype(str).str.lower().str.contains(ql, na=False)
        ]

    data = data.sort_values("date_submitted", ascending=False)

    if not data.empty:
        _exp = data.copy()
        _exp["keywords"] = _exp["keywords"].apply(
            lambda ks: ", ".join(k["keyword"] for k in ks)
        )
        _exp = _exp[[
            "date_submitted", "student_id", "student_name", "department",
            "category", "custom_category", "label", "confidence_score", "source", "feedback_text",
            "keywords",
        ]]
        st.download_button(
            "📄  Export CSV", _exp.to_csv(index=False).encode("utf-8"),
            file_name="ifas_feedback.csv", mime="text/csv",
        )

    st.markdown(
        f'<div class="sec"><h2>Entries</h2>'
        f'<span class="meta">{len(data)} shown</span></div>',
        unsafe_allow_html=True,
    )
    if data.empty:
        st.info("No feedback matches your search / filters.")
        return

    cards = ""
    for _, row in data.iterrows():
        dt = pd.to_datetime(row["date_submitted"], errors="coerce", utc=True)
        date_str = fmt_day(dt, with_year=True) if pd.notna(dt) else "—"
        conf = f"{float(row['confidence_score']) * 100:.0f}%"
        plabel, pcolor = _SENT_PILL.get(row["label"], ("Neutral", NEUTRAL))
        tint = _SENT_TINT.get(row["label"], "var(--secondary)")
        chips = "".join(
            f'<span class="chip">{esc(k["keyword"])}</span>' for k in row["keywords"]
        )
        gem = ('<span class="fb-gem">✨ Refined by Gemini</span>'
               if row.get("source") == "gemini" else "")
        cards += (
            f'<div class="fb-card">'
            f'<div class="fb-meta">'
            f'<span class="fb-pill" style="background:{tint};color:{pcolor}">{plabel}</span>'
            f'{gem}'
            f'<span>{date_str}</span><span>·</span>'
            f'<span>{esc(cat_label(row))}</span><span>·</span>'
            f'<span class="mono">{esc(row["student_id"])}</span>'
            f'<span>· {esc(row["department"])}</span>'
            f'<span style="margin-left:auto">{conf} confidence</span>'
            f'</div>'
            f'<div class="fb-text">{esc(row["feedback_text"])}</div>'
            f'<div class="fb-kws">{chips}</div>'
            f'</div>'
        )
    st.markdown(cards, unsafe_allow_html=True)


# ==========================================================================
# Layout
# ==========================================================================
inject_css(is_dark())
require_auth()

if not MONGO_URI:
    st.warning("MONGO_URI is not configured. Copy `.env.example` to `.env` and set it.")
    st.stop()

df = load_feedback()
if df.empty:
    st.info("No feedback records available yet.")
    st.stop()

flt = render_sidebar(df)

filtered = df.copy()
if flt["department"] != "All":
    filtered = filtered[filtered["department"] == flt["department"]]
if flt["category"] != "All":
    filtered = filtered[filtered["category"] == flt["category"]]
if flt["sentiment"] != "All":
    filtered = filtered[filtered["label"] == flt["sentiment"]]

# Date-range filter (st.date_input returns a single date mid-selection, or a
# (start, end) tuple once both ends are picked).
_dr = flt.get("date_range")
if isinstance(_dr, (tuple, list)) and len(_dr) == 2:
    _start, _end = _dr
    _d = pd.to_datetime(filtered["date_submitted"], errors="coerce", utc=True).dt.date
    filtered = filtered[(_d >= _start) & (_d <= _end)]

# Route: the sidebar "View" nav swaps the whole main area between the analytics
# dashboard and the full feedback browser.
if flt["view"] == "All Feedback":
    render_all_feedback(filtered)
    st.stop()

total = len(filtered)
pos = int((filtered["label"] == "POSITIVE").sum())
neu = int((filtered["label"] == "NEUTRAL").sum())
neg = int((filtered["label"] == "NEGATIVE").sum())

# ── Greeting ──────────────────────────────────────────────────────────────
hour = datetime.now().hour
part = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
user = st.session_state.get("auth_user", "admin")
attention = build_attention(filtered, top_n=1)
focus = attention[0]["category"] if attention else "no single area"
if total == 0:
    summary = "No feedback matches the current filters."
else:
    summary = (
        f"{total} feedback entries in view — {pos} positive, {neg} negative, "
        f"{neu} neutral. Negative sentiment is concentrated around "
        f"<b style='color:var(--fg)'>{esc(focus)}</b>."
    )
st.markdown(
    f'<h1 class="greeting">Good {part}, {esc(user)}.</h1>'
    f'<p class="greeting-sub">{summary}</p>',
    unsafe_allow_html=True,
)

if total == 0:
    st.stop()

# ── KPI row ───────────────────────────────────────────────────────────────
daily = build_daily_series(filtered)


def kpi_card(label: str, value: int, color: str, spark: List[float], sub_html: str,
             icon: str = "") -> str:
    ic = f'<span class="kpi-ic" style="color:{color}">{icon}</span>' if icon else ""
    return (
        f'<div class="kpi"><div class="kpi-top">'
        f'<span class="kpi-label">{ic}{label}</span>{sparkline_svg(spark, color)}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-sub">{sub_html}</div></div>'
    )


def share_sub(color: str, n: int) -> str:
    pct = (100 * n / total) if total else 0
    return f'<span class="dot" style="background:{color}"></span><b>{pct:.0f}%</b> of total'


kpis_html = (
    '<div class="kpi-grid">'
    + kpi_card("Total Feedback", total, ACCENT, daily.get("Total", []),
               '<span class="dot" style="background:%s"></span>records in view' % ACCENT,
               icon=icon_svg("total", size=13))
    + kpi_card("Positive", pos, POSITIVE, daily.get("Positive", []), share_sub(POSITIVE, pos),
               icon=icon_svg("up", size=13))
    + kpi_card("Negative", neg, NEGATIVE, daily.get("Negative", []), share_sub(NEGATIVE, neg),
               icon=icon_svg("down", size=13))
    + kpi_card("Neutral", neu, NEUTRAL, daily.get("Neutral", []), share_sub(NEUTRAL, neu),
               icon=icon_svg("flat", size=13))
    + "</div>"
)
st.markdown(kpis_html, unsafe_allow_html=True)

# ── Charts ────────────────────────────────────────────────────────────────
st.markdown('<div style="height:16px"></div>', unsafe_allow_html=True)
dark = is_dark()
c1, c2 = st.columns([1, 1.4], gap="medium")
with c1:
    sentiment_doughnut({"POSITIVE": pos, "NEUTRAL": neu, "NEGATIVE": neg}, dark=dark)
with c2:
    category_bar(dict(Counter(filtered["category"].tolist())), dark=dark)

st.markdown('<div style="height:14px"></div>', unsafe_allow_html=True)
sentiment_trend(daily, dark=dark)

# ── Top keywords ──────────────────────────────────────────────────────────
keywords = build_keyword_spread(filtered, top_n=8)
st.markdown('<div class="sec"><h2>Top Extracted Keywords</h2></div>', unsafe_allow_html=True)
if keywords:
    kw_rows = (
        '<div class="panel"><div class="panel-head">'
        '<div><h3>KeyBERT keyphrases</h3>'
        '<p>Relevance score and sentiment breakdown</p></div>'
        f'<span class="cnt">{len(keywords)} keywords</span></div>'
        '<div class="kw-scroll">'
        '<div class="kw-headrow kw-head">'
        '<span>#</span><span>Keyword</span><span>Score</span>'
        '<span>Sentiment spread</span><span>Counts</span></div>'
    )
    for i, k in enumerate(keywords, 1):
        tot = k["total"] or 1
        pp, np_, up = k["pos"] / tot * 100, k["neg"] / tot * 100, k["neu"] / tot * 100
        bar = (
            f'<span style="width:{pp}%;background:{POSITIVE}"></span>'
            f'<span style="width:{up}%;background:{NEUTRAL}"></span>'
            f'<span style="width:{np_}%;background:{NEGATIVE}"></span>'
        )
        counts = (
            f'<div class="c"><span class="d" style="background:{POSITIVE}"></span>{int(k["pos"])}</div>'
            f'<div class="c"><span class="d" style="background:{NEGATIVE}"></span>{int(k["neg"])}</div>'
            f'<div class="c"><span class="d" style="background:{NEUTRAL}"></span>{int(k["neu"])}</div>'
        )
        kw_rows += (
            f'<div class="kw-row"><span class="kw-idx">{i}</span>'
            f'<span class="kw-name">{esc(k["keyword"])}</span>'
            f'<span class="kw-score">{k["score"]:.2f}</span>'
            f'<div class="kw-bar">{bar}</div>'
            f'<div class="kw-counts">{counts}</div></div>'
        )
    kw_rows += "</div></div>"  # close .kw-scroll + .panel
    st.markdown(kw_rows, unsafe_allow_html=True)
else:
    st.caption("No keywords extracted yet for this slice.")

# ── Recent feedback ───────────────────────────────────────────────────────
st.markdown('<div class="sec"><h2>Recent Feedback</h2>'
            '<span class="meta">Click a row to expand</span></div>',
            unsafe_allow_html=True)

recent = filtered.sort_values("date_submitted", ascending=False).head(6)
_pill = {"POSITIVE": ("Positive", POSITIVE), "NEGATIVE": ("Negative", NEGATIVE),
         "NEUTRAL": ("Neutral", NEUTRAL)}
for _, row in recent.iterrows():
    dt = pd.to_datetime(row["date_submitted"], errors="coerce", utc=True)
    date_str = fmt_day(dt, with_year=True) if pd.notna(dt) else "—"
    conf = f"{float(row['confidence_score']) * 100:.0f}%"
    plabel, pcolor = _pill.get(row["label"], ("Neutral", NEUTRAL))
    label = f"{date_str}  ·  {cat_label(row)}  ·  {plabel}  ·  {conf} confidence"
    if row.get("source") == "gemini":
        label += "  ·  ✨ Gemini"
    with st.expander(label):
        st.markdown(
            f'<div style="font-size:9px;letter-spacing:.09em;text-transform:uppercase;'
            f'color:var(--muted);margin-bottom:2px">Student ID</div>'
            f'<div class="mono" style="font-size:12px;margin-bottom:10px">{esc(row["student_id"])}'
            f' <span style="color:var(--muted)">· {esc(row["student_name"])} · {esc(row["department"])}</span></div>'
            f'<div style="font-size:9px;letter-spacing:.09em;text-transform:uppercase;'
            f'color:var(--muted);margin-bottom:2px">Full feedback</div>'
            f'<div class="fb-full">{esc(row["feedback_text"])}</div>'
            f'<div style="font-size:9px;letter-spacing:.09em;text-transform:uppercase;'
            f'color:var(--muted);margin:12px 0 4px">Extracted keywords</div>'
            + "".join(
                f'<span class="chip">{esc(k["keyword"])}</span>' for k in row["keywords"]
            ),
            unsafe_allow_html=True,
        )

# ── Attention items ───────────────────────────────────────────────────────
attn = build_attention(filtered, top_n=4)
if attn:
    st.markdown('<div class="sec"><h2>Service Areas Requiring Attention</h2>'
                '<span class="meta">Based on negative sentiment</span></div>',
                unsafe_allow_html=True)
    cards = '<div class="attn-grid">'
    for a in attn:
        hi = a["high"]
        clr = NEGATIVE if hi else NEUTRAL
        ic_bg = "rgba(181,89,68,0.1)" if hi else "rgba(196,147,64,0.1)"
        icon = icon_svg(a["category"], size=16)
        insight = (
            f'{a["neg"]} of {a["total"]} entries ({a["share"]:.0f}%) in '
            f'{esc(a["category"])} carry negative sentiment.'
        )
        cards += (
            f'<div class="attn {"high" if hi else ""}">'
            f'<div class="attn-ic" style="background:{ic_bg};color:{clr}">{icon}</div>'
            f'<div class="attn-body"><div class="attn-title">'
            f'<b>{esc(a["category"])}</b>'
            f'<span class="attn-chip" style="background:{ic_bg};color:{clr}">'
            f'{a["neg"]} negative</span></div><p>{insight}</p></div></div>'
        )
    cards += "</div>"
    st.markdown(cards, unsafe_allow_html=True)

# ==========================================================================
# Tier D — Gemini action synthesis
# ==========================================================================
st.markdown('<div class="sec"><h2>Immediate Action Summary — Gemini 2.5 Flash</h2>'
            '<span class="meta">Tier D synthesis</span></div>',
            unsafe_allow_html=True)
st.caption(
    "Isolate a high-volume slice of negative comments for a single service "
    "and synthesize concrete administrative actions."
)

negatives = filtered[filtered["label"] == "NEGATIVE"]
col_a, col_b = st.columns([1, 1])
with col_a:
    default_dept = flt["department"] if flt["department"] != "All" else "Academic Services"
    dept_label = st.text_input("Department / Unit under review", value=default_dept)
with col_b:
    st.metric("Negative comments in scope", len(negatives))

if len(negatives) == 0:
    st.info("No negative comments in the current filter to summarize.")
else:
    with st.expander("Preview negative comments to be sent"):
        st.write(negatives["feedback_text"].tolist())
    if st.button("Generate Action Summary", type="primary"):
        with st.spinner("Generating Summary, Please wait..."):
            try:
                summary_txt = request_summary(
                    token=st.session_state["auth_token"],
                    department=dept_label or "Academic Services",
                    category=None if flt["category"] == "All" else flt["category"],
                    comments=negatives["feedback_text"].tolist(),
                )
                st.success("Action summary generated.")
                st.markdown(f"> {summary_txt}")
            except requests.HTTPError as exc:
                detail = ""
                try:
                    detail = exc.response.json().get("detail", "")
                except Exception:  # noqa: BLE001
                    detail = str(exc)
                st.error(f"Summarization failed: {detail}")
            except requests.RequestException as exc:
                st.error(f"Could not reach the backend API: {exc}")
