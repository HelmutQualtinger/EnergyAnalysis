#!/usr/bin/env python3
"""
Interactive daily-consumption dashboard for 3PM_present_values / 3PM_total_values.
Generates: daily_consumption.html
"""

import os
import subprocess
from pathlib import Path
from datetime import datetime
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
DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def sql(query: str) -> list[list[str]]:
    r = subprocess.run(
        ["mysql", "-h", DB_HOST, "-P", str(DB_PORT),
         "-u", DB_USER, f"-p{DB_PASS}", DB_NAME,
         "--batch", "--silent", "-e", query],
        capture_output=True, text=True, check=True,
    )
    return [line.split("\t") for line in r.stdout.splitlines() if line.strip()]


# ── 1. Daily kWh from cumulative totals ──────────────────────────────────────
def fetch_daily_kwh() -> dict:
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


# ── 2. Hourly × DOW heatmap (Allgemein) ──────────────────────────────────────
def fetch_hourly_heatmap() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows = sql(f"""
        SELECT HOUR(time) AS hr, DAYOFWEEK(time) AS dow,
               AVG(total_act_power) AS avg_w
        FROM `3PM_present_values`
        WHERE meter_name='Allgemein' AND DATE(time) >= '{SINCE}'
        GROUP BY hr, dow ORDER BY dow, hr
    """)
    # dow: 1=Sun … 7=Sat
    grid = np.full((7, 24), np.nan)
    for r in rows:
        if len(r) != 3:
            continue
        hr, dow, w = int(r[0]), int(r[1]) - 1, float(r[2])
        grid[dow, hr] = w
    return grid


# ── 3. Daily stats: peak & avg power, voltage ────────────────────────────────
def fetch_daily_stats() -> dict:
    rows = sql(f"""
        SELECT DATE(time) AS day, meter_name,
               MAX(total_act_power) AS peak_w,
               AVG(total_act_power) AS avg_w,
               AVG(a_voltage) AS va, AVG(b_voltage) AS vb, AVG(c_voltage) AS vc,
               AVG(a_pf) AS pf_a, AVG(b_pf) AS pf_b, AVG(c_pf) AS pf_c
        FROM `3PM_present_values`
        WHERE DATE(time) >= '{SINCE}'
        GROUP BY day, meter_name ORDER BY day, meter_name
    """)
    data: dict = {m: {"days": [], "peak": [], "avg": [],
                       "va": [], "vb": [], "vc": [],
                       "pf_a": [], "pf_b": [], "pf_c": []}
                  for m in ("Allgemein", "EG", "OG")}
    for r in rows:
        if len(r) != 10:
            continue
        day, meter = datetime.strptime(r[0], "%Y-%m-%d"), r[1]
        if meter not in data:
            continue
        d = data[meter]
        d["days"].append(day)
        d["peak"].append(float(r[2]) if r[2] != "NULL" else float("nan"))
        d["avg"].append(float(r[3])  if r[3] != "NULL" else float("nan"))
        d["va"].append(float(r[4])   if r[4] != "NULL" else float("nan"))
        d["vb"].append(float(r[5])   if r[5] != "NULL" else float("nan"))
        d["vc"].append(float(r[6])   if r[6] != "NULL" else float("nan"))
        d["pf_a"].append(float(r[7]) if r[7] != "NULL" else float("nan"))
        d["pf_b"].append(float(r[8]) if r[8] != "NULL" else float("nan"))
        d["pf_c"].append(float(r[9]) if r[9] != "NULL" else float("nan"))
    for m in data:
        for k in data[m]:
            data[m][k] = np.array(data[m][k])
    return data


def rolling(arr: np.ndarray, w: int = 7) -> np.ndarray:
    out = np.full_like(arr, np.nan)
    for i in range(w - 1, len(arr)):
        window = arr[i - w + 1:i + 1]
        out[i] = np.nanmean(window)
    return out


def rgba(h: str, a: float) -> str:
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return f"rgba({r},{g},{b},{a})"


# ── Build figure ──────────────────────────────────────────────────────────────
def build(kwh: dict, heatmap: np.ndarray, stats: dict) -> go.Figure:
    fig = make_subplots(
        rows=5, cols=1,
        shared_xaxes=False,
        row_heights=[0.22, 0.18, 0.22, 0.20, 0.18],
        vertical_spacing=0.055,
        subplot_titles=[
            "① Täglicher Verbrauch (kWh) mit 7-Tage-Mittel",
            "② Ø-Leistung nach Stunde × Wochentag — Allgemein (W)",
            "③ Tägliche Spitzen- und Ø-Leistung — Allgemein (W)",
            "④ Phasenspannungen — Allgemein (V)",
            "⑤ Leistungsfaktor je Phase — Allgemein",
        ],
    )

    # ── Plot 1: daily kWh bars + rolling avg ─────────────────────────────────
    for meter in ("EG", "OG"):
        color = COLORS[meter]
        fig.add_trace(go.Bar(
            x=kwh["days"], y=kwh[meter],
            name=meter,
            marker_color=color, opacity=0.75,
            legendgroup=meter,
            hovertemplate=f"<b>{meter}</b> %{{x|%d %b}}: %{{y:.1f}} kWh<extra></extra>",
        ), row=1, col=1)

    fig.add_trace(go.Bar(
        x=kwh["days"], y=kwh["Allgemein"],
        name="Allgemein",
        marker_color=COLORS["Allgemein"], opacity=0.55,
        legendgroup="Allgemein",
        hovertemplate="<b>Allgemein</b> %{x|%d %b}: %{y:.1f} kWh<extra></extra>",
    ), row=1, col=1)

    roll = rolling(kwh["Allgemein"])
    fig.add_trace(go.Scatter(
        x=kwh["days"], y=roll,
        mode="lines", name="7-Tage Ø",
        line=dict(color="#ffe082", width=2, dash="dash"),
        hovertemplate="7d-Ø: %{y:.1f} kWh<extra></extra>",
    ), row=1, col=1)

    # ── Plot 2: heatmap ───────────────────────────────────────────────────────
    fig.add_trace(go.Heatmap(
        z=heatmap,
        x=list(range(24)),
        y=DAYS,
        colorscale="Viridis",
        colorbar=dict(title="W", len=0.18, y=0.62, thickness=12,
                      tickfont=dict(size=9)),
        hovertemplate="<b>%{y} %{x}:00</b><br>Ø %{z:.0f} W<extra></extra>",
        showscale=True,
    ), row=2, col=1)

    # ── Plot 3: peak + avg power ──────────────────────────────────────────────
    d_a = stats["Allgemein"]
    fig.add_trace(go.Scatter(
        x=d_a["days"], y=d_a["peak"],
        mode="lines", name="Spitze (W)",
        line=dict(color="#ef5350", width=1),
        fill="tozeroy", fillcolor="rgba(239,83,80,0.08)",
        hovertemplate="%{x|%d %b}: Spitze %{y:.0f} W<extra></extra>",
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=d_a["days"], y=d_a["avg"],
        mode="lines", name="Ø-Leistung (W)",
        line=dict(color=COLORS["Allgemein"], width=1.5),
        hovertemplate="%{x|%d %b}: Ø %{y:.0f} W<extra></extra>",
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=d_a["days"], y=rolling(d_a["avg"]),
        mode="lines", name="7d Ø-Leistung",
        line=dict(color="#ffe082", width=2, dash="dot"),
        hovertemplate="7d-Ø: %{y:.0f} W<extra></extra>",
    ), row=3, col=1)

    # ── Plot 4: phase voltages ────────────────────────────────────────────────
    phase_colors = {"a": "#ce93d8", "b": "#80cbc4", "c": "#ffcc80"}
    for ph, col in phase_colors.items():
        fig.add_trace(go.Scatter(
            x=d_a["days"], y=d_a[f"v{ph}"],
            mode="lines", name=f"Phase {ph.upper()}",
            line=dict(color=col, width=1.2),
            hovertemplate=f"Phase {ph.upper()}: %{{y:.1f}} V<extra></extra>",
        ), row=4, col=1)
    # EU nominal band 230 ±10%
    fig.add_hrect(y0=207, y1=253, row=4, col=1,
                  fillcolor="rgba(255,255,255,0.03)",
                  line_width=0, annotation_text="±10% EU-Band",
                  annotation_position="top right",
                  annotation_font=dict(size=9, color="#888"))

    # ── Plot 5: power factor ──────────────────────────────────────────────────
    pf_colors = {"a": "#ce93d8", "b": "#80cbc4", "c": "#ffcc80"}
    for ph, col in pf_colors.items():
        fig.add_trace(go.Scatter(
            x=d_a["days"], y=d_a[f"pf_{ph}"],
            mode="lines", name=f"PF Phase {ph.upper()}",
            line=dict(color=col, width=1),
            hovertemplate=f"PF {ph.upper()}: %{{y:.3f}}<extra></extra>",
        ), row=5, col=1)

    # ── Layout ────────────────────────────────────────────────────────────────
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0f1117",
        plot_bgcolor="#1a1d27",
        font=dict(color="#cccccc", size=11),
        height=1300,
        title=dict(
            text=f"Energieverbrauch Dashboard — Allgemein / EG / OG  (ab {SINCE})",
            font=dict(size=16), x=0.5,
        ),
        legend=dict(
            orientation="h", y=-0.03, x=0,
            bgcolor="rgba(30,33,48,0.8)", bordercolor="#444", borderwidth=1,
        ),
        barmode="overlay",
        margin=dict(l=60, r=30, t=80, b=60),
        hovermode="x unified",
    )
    for row in range(1, 6):
        fig.update_xaxes(gridcolor="#2a2d3a", showgrid=True, row=row, col=1)
        fig.update_yaxes(gridcolor="#2a2d3a", row=row, col=1)

    fig.update_yaxes(title_text="kWh",   row=1, col=1)
    fig.update_xaxes(
        tickvals=list(range(24)),
        ticktext=[f"{h:02d}" for h in range(24)],
        title_text="Stunde", row=2, col=1,
    )
    fig.update_yaxes(title_text="Wochentag", row=2, col=1)
    fig.update_yaxes(title_text="W",         row=3, col=1)
    fig.update_yaxes(title_text="V",         row=4, col=1,
                     range=[220, 245])
    fig.update_yaxes(title_text="PF",        row=5, col=1,
                     range=[0, 1.05])

    return fig


def main():
    print("Fetching daily kWh …")
    kwh = fetch_daily_kwh()
    print(f"  {len(kwh['days'])} days")

    print("Fetching hourly heatmap …")
    heatmap = fetch_hourly_heatmap()

    print("Fetching daily stats …")
    stats = fetch_daily_stats()

    print("Building figure …")
    fig = build(kwh, heatmap, stats)

    out = "daily_consumption.html"
    fig.write_html(out, include_plotlyjs="cdn")
    print(f"Saved → {out}")

    pdf_out = out.replace(".html", ".pdf")
    fig.write_image(pdf_out, format="pdf")
    print(f"Saved → {pdf_out}")

    import webbrowser, os
    webbrowser.open(f"file://{os.path.abspath(out)}")


if __name__ == "__main__":
    main()
