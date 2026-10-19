"""
charts.py
=========
Embedded Chart.js renderers for the Streamlit admin dashboard, styled to match
the "Feedback Intelligence" high-fidelity design (editorial theme, muted earthy
sentiment palette). Supports both a light and a dark theme.

Each function streams a single self-contained HTML document (via
`streamlit.components.v1.html`) that renders a full **card** — header (title +
subtitle) plus the Chart.js <canvas> — so the chart reads as one native panel
inside the Streamlit page.

Chart.js is VENDORED locally (components/vendor/chart.umd.min.js) and inlined
into each iframe (no CDN), because the dashboard host has broken IPv6 egress to
public CDNs — a browser `<script src="cdn…">` would silently fail. This means
the charts do NOT depend on any network at all at render time.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, Sequence, Tuple

import streamlit.components.v1 as components

# Chart.js is vendored locally (components/vendor/chart.umd.min.js) and inlined.
_VENDOR_JS = os.path.join(os.path.dirname(__file__), "vendor", "chart.umd.min.js")
try:
    with open(_VENDOR_JS, "r", encoding="utf-8") as _fh:
        _CHARTJS_SRC = _fh.read()
except OSError:
    _CHARTJS_SRC = ""
# Guard against an accidental "</script>" sequence closing our inline block early.
_CHARTJS_INLINE = _CHARTJS_SRC.replace("</script>", "<\\/script>")

# Outfit is self-hosted and base64-inlined into each chart iframe (these render
# in isolated <iframe>s that can't see the parent page's @font-face, and public
# CDNs are blocked on this host). Empty string if the file is missing — the
# charts then fall back to the system stack.
_FONT_WOFF2 = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "assets", "outfit-latin.woff2"
)
try:
    with open(_FONT_WOFF2, "rb") as _ff:
        _OUTFIT_B64 = base64.b64encode(_ff.read()).decode("ascii")
    _FONT_FACE_CSS = (
        "@font-face { font-family: 'Outfit'; font-style: normal; "
        "font-weight: 300 800; font-display: swap; "
        f"src: url(data:font/woff2;base64,{_OUTFIT_B64}) format('woff2'); }}"
    )
except OSError:
    _FONT_FACE_CSS = ""

# ── Sentiment / accent palette (identical in both themes, so the charts match
#    the CSS sentiment bars on the page exactly) ──────────────────────────────
POSITIVE = "#5B8A6A"   # muted sage
NEGATIVE = "#B55944"   # terracotta
NEUTRAL = "#C49340"    # mustard / ochre
ACCENT = "#4255A4"     # indigo-blue
_ACCENT2 = "#6375C4"   # lighter indigo (gradient end)

_SENTIMENT_COLORS = {"POSITIVE": POSITIVE, "NEUTRAL": NEUTRAL, "NEGATIVE": NEGATIVE}
_JS_FONT = "Outfit, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
_FONT_STACK = "'Outfit', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"

# ── Per-theme neutral chrome (surfaces, text, gridlines, tooltip) ────────────
_LIGHT = {
    "card": "#F5F5F4", "border": "rgba(0,0,0,0.07)", "fg": "#111111",
    "muted": "#6B6B6B", "axis": "#BBBBBB", "grid": "rgba(0,0,0,0.05)",
    "tooltip_bg": "#FFFFFF", "tooltip_border": "rgba(0,0,0,0.08)",
}
_DARK = {
    "card": "#1A1A1F", "border": "rgba(255,255,255,0.09)", "fg": "#F3F3F1",
    "muted": "#9A9A9F", "axis": "#5A5A5A", "grid": "rgba(255,255,255,0.07)",
    "tooltip_bg": "#232329", "tooltip_border": "rgba(255,255,255,0.12)",
}


def _theme(dark: bool) -> Dict[str, str]:
    return _DARK if dark else _LIGHT


def _card_html(
    canvas_id: str,
    title: str,
    subtitle: str,
    legend: Sequence[Tuple[str, str]],
    script_body: str,
    canvas_height: int,
    theme: Dict[str, str],
) -> str:
    """Wrap a Chart.js snippet in a full editorial-style card document."""
    legend_markup = ""
    if legend:
        dots = "".join(
            f'<div class="lg"><span class="dot" style="background:{c}"></span>'
            f"<span>{l}</span></div>"
            for l, c in legend
        )
        legend_markup = f'<div class="legend">{dots}</div>'
    sub_markup = f'<div class="sub">{subtitle}</div>' if subtitle else ""
    return f"""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8" />
        <script>{_CHARTJS_INLINE}</script>
        <style>
          {_FONT_FACE_CSS}
          * {{ box-sizing: border-box; }}
          html, body {{ margin: 0; padding: 0; background: transparent;
                        font-family: {_FONT_STACK}; }}
          .card {{ background: {theme['card']}; border: 1px solid {theme['border']};
                   border-radius: 10px; padding: 18px 20px 14px; }}
          .head {{ display: flex; align-items: flex-start;
                   justify-content: space-between; gap: 12px; margin-bottom: 12px; }}
          .h2 {{ font-size: 13px; font-weight: 600; color: {theme['fg']}; margin: 0; }}
          .sub {{ font-size: 11px; color: {theme['muted']}; margin-top: 3px; }}
          .legend {{ display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }}
          .lg {{ display: flex; align-items: center; gap: 6px;
                 font-size: 11px; color: {theme['muted']}; }}
          .dot {{ width: 8px; height: 8px; border-radius: 50%; flex: none; }}
          .cwrap {{ height: {canvas_height}px; position: relative; }}
          canvas {{ max-width: 100%; }}
          .err {{ color: {theme['muted']}; font-size: 12px; padding: 20px 0; }}
        </style>
      </head>
      <body>
        <div class="card">
          <div class="head">
            <div><div class="h2">{title}</div>{sub_markup}</div>
            {legend_markup}
          </div>
          <div class="cwrap"><canvas id="{canvas_id}"></canvas></div>
        </div>
        <script>
          (function() {{
            if (typeof Chart === "undefined") {{
              document.querySelector('.cwrap').innerHTML =
                "<p class='err'>Chart.js failed to load.</p>";
              return;
            }}
            Chart.defaults.font.family = {json.dumps(_FONT_STACK)};
            {script_body}
          }})();
        </script>
      </body>
    </html>
    """


def _tooltip_cfg(theme: Dict[str, str]) -> str:
    """Shared tooltip options. Emits SINGLE braces so it drops cleanly into the
    caller's ``tooltip: {{ ... }}`` (which itself resolves to single braces)."""
    return f"""
      backgroundColor: '{theme['tooltip_bg']}', borderColor: '{theme['tooltip_border']}',
      borderWidth: 1, padding: 10, cornerRadius: 8,
      titleColor: '{theme['muted']}', bodyColor: '{theme['fg']}',
      titleFont: {{ size: 10 }}, bodyFont: {{ size: 12 }}, usePointStyle: true,
      boxPadding: 4
    """


# ==========================================================================
# Sentiment Distribution — doughnut with running total in the hole
# ==========================================================================
def sentiment_doughnut(
    distribution: Dict[str, int], height: int = 230, dark: bool = False
) -> None:
    """
    Doughnut chart of the sentiment split with the total drawn in the centre.

    :param distribution: {"POSITIVE": 6, "NEUTRAL": 2, "NEGATIVE": 3}
    :param dark: render with the dark-theme chrome.
    """
    th = _theme(dark)
    order = [k for k in ("POSITIVE", "NEGATIVE", "NEUTRAL") if k in distribution]
    order = order or list(distribution.keys())
    label_map = {"POSITIVE": "Positive", "NEGATIVE": "Negative", "NEUTRAL": "Neutral"}
    labels = [label_map.get(k, k.title()) for k in order]
    values = [int(distribution.get(k, 0)) for k in order]
    colors = [_SENTIMENT_COLORS.get(k, "#999999") for k in order]
    total = sum(values)

    script = f"""
      const ctx = document.getElementById('sentimentDoughnut');
      const centerText = {{
        id: 'centerText',
        afterDraw(chart) {{
          const a = chart.chartArea;
          const cx = (a.left + a.right) / 2, cy = (a.top + a.bottom) / 2;
          const c = chart.ctx;
          c.save(); c.textAlign = "center"; c.textBaseline = "middle";
          c.fillStyle = "{th['fg']}";
          c.font = "600 30px {_JS_FONT}";
          c.fillText(String({total}), cx, cy - 6);
          c.fillStyle = "{th['muted']}";
          c.font = "500 11px {_JS_FONT}";
          c.fillText("TOTAL", cx, cy + 16);
          c.restore();
        }}
      }};
      new Chart(ctx, {{
        type: 'doughnut',
        data: {{
          labels: {json.dumps(labels)},
          datasets: [{{
            data: {json.dumps(values)},
            backgroundColor: {json.dumps(colors)},
            borderColor: "{th['card']}", borderWidth: 3, hoverOffset: 8
          }}]
        }},
        options: {{
          responsive: true, maintainAspectRatio: false, cutout: '66%',
          animation: {{ animateRotate: true, duration: 800 }},
          plugins: {{
            legend: {{ position: 'bottom',
              labels: {{ color: "{th['muted']}", padding: 14, usePointStyle: true,
                         pointStyle: 'circle', font: {{ size: 11 }} }} }},
            tooltip: {{ {_tooltip_cfg(th)} }}
          }}
        }},
        plugins: [centerText]
      }});
    """
    html = _card_html("sentimentDoughnut", "Sentiment Distribution",
                      "Across the current view", [], script, height, th)
    components.html(html, height=height + 118)


# ==========================================================================
# Feedback by Category — horizontal bar
# ==========================================================================
def category_bar(counts: Dict[str, int], title: str = "Feedback by Category",
                 subtitle: str = "Volume per service", height: int = 230,
                 dark: bool = False) -> None:
    """
    Horizontal bar chart of feedback volume per category (sorted descending).

    :param counts: {"Wi-Fi": 3, "Library": 2, ...}
    :param dark: render with the dark-theme chrome.
    """
    th = _theme(dark)
    ordered = dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))
    labels = list(ordered.keys())
    values = list(ordered.values())

    script = f"""
      const ctx = document.getElementById('categoryBar');
      const g = ctx.getContext('2d').createLinearGradient(0, 0, ctx.width || 600, 0);
      g.addColorStop(0, "{ACCENT}"); g.addColorStop(1, "{_ACCENT2}");
      new Chart(ctx, {{
        type: 'bar',
        data: {{
          labels: {json.dumps(labels)},
          datasets: [{{
            data: {json.dumps(values)},
            backgroundColor: g, hoverBackgroundColor: "#7C8DB0",
            borderRadius: 6, barThickness: 'flex', maxBarThickness: 22
          }}]
        }},
        options: {{
          indexAxis: 'y', responsive: true, maintainAspectRatio: false,
          animation: {{ duration: 800, easing: 'easeOutQuart' }},
          scales: {{
            x: {{ beginAtZero: true,
                  ticks: {{ color: "{th['axis']}", font: {{ size: 10 }}, precision: 0 }},
                  grid: {{ color: "{th['grid']}" }}, border: {{ display: false }} }},
            y: {{ ticks: {{ color: "{th['muted']}", font: {{ size: 11 }} }},
                  grid: {{ display: false }}, border: {{ display: false }} }}
          }},
          plugins: {{
            legend: {{ display: false }},
            tooltip: {{ {_tooltip_cfg(th)} }}
          }}
        }}
      }});
    """
    html = _card_html("categoryBar", title, subtitle, [], script, height, th)
    components.html(html, height=height + 118)


# ==========================================================================
# Sentiment over time — multi-line trend
# ==========================================================================
def sentiment_trend(daily: Dict[str, Any], height: int = 250, dark: bool = False) -> None:
    """
    Line chart of daily sentiment volume.

    :param daily: {"labels": [...], "Positive": [...], "Negative": [...], "Neutral": [...]}
                  as produced by ``build_daily_series``.
    """
    th = _theme(dark)
    labels = daily.get("labels", [])
    series = [
        ("Positive", daily.get("Positive", []), POSITIVE),
        ("Negative", daily.get("Negative", []), NEGATIVE),
        ("Neutral", daily.get("Neutral", []), NEUTRAL),
    ]
    datasets = ", ".join(
        f"""{{
          label: {json.dumps(name)}, data: {json.dumps([int(v) for v in vals])},
          borderColor: "{color}", backgroundColor: "{color}22",
          borderWidth: 2, tension: 0.35, fill: true,
          pointRadius: 3, pointHoverRadius: 5, pointBackgroundColor: "{color}",
          pointBorderColor: "{th['card']}", pointBorderWidth: 1.5
        }}"""
        for name, vals, color in series
    )
    legend = [(name, color) for name, _, color in series]

    script = f"""
      const ctx = document.getElementById('sentimentTrend');
      new Chart(ctx, {{
        type: 'line',
        data: {{ labels: {json.dumps(labels)}, datasets: [{datasets}] }},
        options: {{
          responsive: true, maintainAspectRatio: false,
          interaction: {{ mode: 'index', intersect: false }},
          animation: {{ duration: 700, easing: 'easeOutQuart' }},
          scales: {{
            x: {{ ticks: {{ color: "{th['muted']}", font: {{ size: 10 }},
                            maxRotation: 0, autoSkipPadding: 12 }},
                  grid: {{ color: "{th['grid']}" }}, border: {{ display: false }} }},
            y: {{ beginAtZero: true,
                  ticks: {{ color: "{th['axis']}", font: {{ size: 10 }}, precision: 0 }},
                  grid: {{ color: "{th['grid']}" }}, border: {{ display: false }} }}
          }},
          plugins: {{
            legend: {{ display: false }},
            tooltip: {{ {_tooltip_cfg(th)} }}
          }}
        }}
      }});
    """
    html = _card_html("sentimentTrend", "Sentiment Over Time",
                      "Daily volume by sentiment", legend, script, height, th)
    components.html(html, height=height + 118)
