#!/usr/bin/env python3
"""
Weekly consumption (kWh) for all three meters: Allgemein, EG, OG.
Daily data smoothed to ISO-week averages.
Generates: weekly_consumption_all_meters.html
"""

import os
import subprocess
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
DB_HOST = os.environ["DB_HOST"]
DB_PORT = int(os.environ.get("DB_PORT", 3306))
DB_USER = os.environ["DB_USER"]
DB_PASS = os.environ["DB_PASS"]
DB_NAME = "Shellies"
SINCE   = "2025-01-01"

COLORS = {
    "Allgemein": "#4fc3f7",
    "EG":        "#66bb6a",
    "OG":        "#ff8a65",
}


def sql(query: str) -> list[list[str]]:
    r = subprocess.run(
        ["mysql", "-h", DB_HOST, "-P", str(DB_PORT),
         "-u", DB_USER, f"-p{DB_PASS}", DB_NAME,
         "--batch", "--silent", "-e", query],
        capture_output=True, text=True, check=True,
    )
    return [line.split("\t") for line in r.stdout.splitlines() if line.strip()]


def fetch_daily_kwh() -> dict:
    """Get daily consumption (kWh) for all three meters."""
    rows = sql(f"""
        SELECT DATE(time) AS day,
          MAX(CASE WHEN meter_name='Allgemein' THEN total_act END) AS allgemein,
          MAX(CASE WHEN meter_name='EG'        THEN total_act END) AS eg,
          MAX(CASE WHEN meter_name='OG'        THEN total_act END) AS og
        FROM `3PM_total_values`
        WHERE meter_name IN ('Allgemein','EG','OG')
          AND DATE(time) >= '{SINCE}'
        GROUP BY day ORDER BY day
    """)
    days, a, eg, og = [], [], [], []
    for r in rows:
        if len(r) != 4:
            continue
        days.append(datetime.strptime(r[0], "%Y-%m-%d"))
        a.append(float(r[1]) if r[1] != "NULL" else float("nan"))
        eg.append(float(r[2]) if r[2] != "NULL" else float("nan"))
        og.append(float(r[3]) if r[3] != "NULL" else float("nan"))

    days = np.array(days)
    a_kwh  = np.maximum(np.diff(np.array(a))  / 1000, 0)
    eg_kwh = np.maximum(np.diff(np.array(eg)) / 1000, 0)
    og_kwh = np.maximum(np.diff(np.array(og)) / 1000, 0)
    d = days[1:]

    return {"days": d, "Allgemein": a_kwh, "EG": eg_kwh, "OG": og_kwh}


def weekly_avg(daily: dict) -> dict:
    """Collapse daily arrays into ISO-week averages (only complete 7-day weeks)."""
    days = daily["days"]
    a_daily = daily["Allgemein"]
    eg_daily = daily["EG"]
    og_daily = daily["OG"]

    buckets = defaultdict(lambda: {
        "dates": [],
        "Allgemein": [],
        "EG": [],
        "OG": [],
    })

    for d, a, eg, og in zip(days, a_daily, eg_daily, og_daily):
        key = d.isocalendar()[:2]  # (year, week)
        buckets[key]["dates"].append(d)
        buckets[key]["Allgemein"].append(a)
        buckets[key]["EG"].append(eg)
        buckets[key]["OG"].append(og)

    w_days = []
    w_allgemein = []
    w_eg = []
    w_og = []

    for key in sorted(buckets):
        b = buckets[key]
        if len(b["dates"]) < 7:  # skip incomplete weeks at the boundaries
            continue
        w_days.append(b["dates"][0])  # Monday of that week
        w_allgemein.append(float(np.nanmean(b["Allgemein"])))
        w_eg.append(float(np.nanmean(b["EG"])))
        w_og.append(float(np.nanmean(b["OG"])))

    return {
        "days": np.array(w_days),
        "Allgemein": np.array(w_allgemein),
        "EG": np.array(w_eg),
        "OG": np.array(w_og),
    }


def build(weekly: dict) -> go.Figure:
    days = weekly["days"]
    a_kwh = weekly["Allgemein"]
    eg_kwh = weekly["EG"]
    og_kwh = weekly["OG"]
    total_kwh = a_kwh + eg_kwh + og_kwh

    fig = make_subplots(
        rows=3, cols=1,
        row_heights=[0.35, 0.35, 0.30],
        vertical_spacing=0.08,
        subplot_titles=[
            "① Wöchentlicher Durchschnittsverbrauch pro Zähler (kWh)",
            "② Kumulative Summe (kWh)",
            "③ Anteil am Gesamtverbrauch (%)",
        ],
    )

    # ── Plot 1: Weekly consumption bars ───────────────────────────────────────
    fig.add_trace(go.Bar(
        x=days, y=a_kwh,
        name="Allgemein",
        marker_color=COLORS["Allgemein"], opacity=0.8,
        hovertemplate="<b>Allgemein</b> KW %{x|%d %b}: %{y:.1f} kWh/Tag<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Bar(
        x=days, y=eg_kwh,
        name="EG",
        marker_color=COLORS["EG"], opacity=0.8,
        hovertemplate="<b>EG</b> KW %{x|%d %b}: %{y:.1f} kWh/Tag<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Bar(
        x=days, y=og_kwh,
        name="OG",
        marker_color=COLORS["OG"], opacity=0.8,
        hovertemplate="<b>OG</b> KW %{x|%d %b}: %{y:.1f} kWh/Tag<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=days, y=total_kwh,
        mode="lines+markers", name="Gesamt (wöchentlich)",
        line=dict(color="#ffe082", width=2),
        marker=dict(size=5),
        hovertemplate="Gesamt: %{y:.1f} kWh/Tag<extra></extra>",
    ), row=1, col=1)

    # ── Plot 2: Cumulative sum ────────────────────────────────────────────────
    a_cum = np.nancumsum(a_kwh * 7)  # Convert daily avg to weekly total
    eg_cum = np.nancumsum(eg_kwh * 7)
    og_cum = np.nancumsum(og_kwh * 7)

    fig.add_trace(go.Scatter(
        x=days, y=a_cum, name="Allgemein (kumulativ)",
        line=dict(color=COLORS["Allgemein"], width=2.5),
        hovertemplate="Allgemein: %{y:.0f} kWh<extra></extra>",
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=days, y=eg_cum, name="EG (kumulativ)",
        line=dict(color=COLORS["EG"], width=2.5),
        hovertemplate="EG: %{y:.0f} kWh<extra></extra>",
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=days, y=og_cum, name="OG (kumulativ)",
        line=dict(color=COLORS["OG"], width=2.5),
        hovertemplate="OG: %{y:.0f} kWh<extra></extra>",
    ), row=2, col=1)

    # ── Plot 3: Stacked percentage ────────────────────────────────────────────
    pct_a = np.nan_to_num((a_kwh / total_kwh * 100), nan=0)
    pct_eg = np.nan_to_num((eg_kwh / total_kwh * 100), nan=0)
    pct_og = np.nan_to_num((og_kwh / total_kwh * 100), nan=0)

    # Cumulative stacking
    pct_a_stack = pct_a
    pct_eg_stack = pct_a + pct_eg
    pct_og_stack = pct_a + pct_eg + pct_og

    fig.add_trace(go.Scatter(
        x=days, y=pct_a_stack,
        name="Allgemein",
        fill="tozeroy", fillcolor=COLORS["Allgemein"],
        line=dict(color=COLORS["Allgemein"], width=1), opacity=0.8,
        hovertemplate="Allgemein: %{y:.1f}%<extra></extra>",
    ), row=3, col=1)

    fig.add_trace(go.Scatter(
        x=days, y=pct_eg_stack,
        name="EG",
        fill="tonexty", fillcolor=COLORS["EG"],
        line=dict(color=COLORS["EG"], width=1), opacity=0.8,
        hovertemplate="EG: %{y:.1f}%<extra></extra>",
    ), row=3, col=1)

    fig.add_trace(go.Scatter(
        x=days, y=pct_og_stack,
        name="OG",
        fill="tonexty", fillcolor=COLORS["OG"],
        line=dict(color=COLORS["OG"], width=1), opacity=0.8,
        hovertemplate="OG: %{y:.1f}%<extra></extra>",
    ), row=3, col=1)

    # ── Layout ────────────────────────────────────────────────────────────────
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0f1117",
        plot_bgcolor="#1a1d27",
        font=dict(color="#cccccc", size=11),
        height=1100,
        title=dict(
            text=f"Wöchentlicher Stromverbrauch — Allgemein / EG / OG  (ab {SINCE})",
            font=dict(size=16), x=0.5,
        ),
        legend=dict(
            orientation="h", y=-0.04, x=0,
            bgcolor="rgba(30,33,48,0.8)", bordercolor="#444", borderwidth=1,
        ),
        barmode="group",
        margin=dict(l=60, r=30, t=80, b=60),
        hovermode="x unified",
    )

    for row in range(1, 4):
        fig.update_xaxes(gridcolor="#2a2d3a", showgrid=True, row=row, col=1)
        fig.update_yaxes(gridcolor="#2a2d3a", row=row, col=1)

    fig.update_yaxes(title_text="kWh/Tag (Wochendurchschnitt)", row=1, col=1)
    fig.update_yaxes(title_text="kWh (Summe)", row=2, col=1)
    fig.update_yaxes(title_text="Anteil (%)", row=3, col=1, range=[0, 100])

    return fig


def main():
    print("Fetching daily consumption …")
    daily = fetch_daily_kwh()
    print(f"  {len(daily['days'])} days")

    print("Smoothing to weekly averages …")
    weekly = weekly_avg(daily)
    print(f"  {len(weekly['days'])} complete weeks  "
          f"({weekly['days'][0].strftime('%d %b %Y')} – {weekly['days'][-1].strftime('%d %b %Y')})")

    print("Building figure …")
    fig = build(weekly)

    out = "weekly_consumption_all_meters.html"
    fig.write_html(out, include_plotlyjs="cdn")
    print(f"Saved → {out}")

    pdf_out = out.replace(".html", ".pdf")
    fig.write_image(pdf_out, format="pdf")
    print(f"Saved → {pdf_out}")

    import webbrowser, os
    webbrowser.open(f"file://{os.path.abspath(out)}")


if __name__ == "__main__":
    main()
