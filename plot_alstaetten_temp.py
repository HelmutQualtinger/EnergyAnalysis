#!/usr/bin/env python3
"""
Daily average temperature dashboard for Altstätten SG (OpenWeatherMap DB).
Generates: alstaetten_temperature.html
"""

import os
import subprocess
from pathlib import Path
from datetime import datetime
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import calendar
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")
DB_HOST = os.environ["DB_HOST"]
DB_PORT = int(os.environ.get("DB_PORT", 3306))
DB_USER = os.environ["DB_USER"]
DB_PASS = os.environ["DB_PASS"]
DB_NAME = "OpenWeatherMap"
CITY    = "Altstätten SG"

MONTH_NAMES = ["Jan","Feb","Mär","Apr","Mai","Jun",
               "Jul","Aug","Sep","Okt","Nov","Dez"]


def sql(query: str) -> list[list[str]]:
    r = subprocess.run(
        ["mysql", "-h", DB_HOST, "-P", str(DB_PORT),
         "-u", DB_USER, f"-p{DB_PASS}", DB_NAME,
         "--batch", "--silent", "-e", query],
        capture_output=True, text=True, check=True,
    )
    return [line.split("\t") for line in r.stdout.splitlines() if line.strip()]


def fetch_daily():
    rows = sql(f"""
        SELECT DATE(dt) AS day,
               ROUND(AVG(temperature), 2)     AS avg_t,
               ROUND(MIN(temperature_min), 2) AS min_t,
               ROUND(MAX(temperature_max), 2) AS max_t,
               ROUND(AVG(humidity), 1)        AS humidity
        FROM weather_data
        WHERE city = '{CITY}'
        GROUP BY day ORDER BY day
    """)
    days, avg, lo, hi, hum = [], [], [], [], []
    for r in rows:
        if len(r) != 5:
            continue
        days.append(datetime.strptime(r[0], "%Y-%m-%d"))
        avg.append(float(r[1]))
        lo.append(float(r[2]))
        hi.append(float(r[3]))
        hum.append(float(r[4]))
    return (np.array(days),
            np.array(avg), np.array(lo), np.array(hi), np.array(hum))


def rolling(arr, w=30):
    out = np.full_like(arr, np.nan, dtype=float)
    for i in range(w - 1, len(arr)):
        out[i] = np.nanmean(arr[i - w + 1:i + 1])
    return out


def temp_color(t):
    """Map temperature to a CSS colour (cold=blue → warm=red)."""
    if t <= -5:   return "#1565c0"
    if t <= 0:    return "#42a5f5"
    if t <= 5:    return "#80deea"
    if t <= 10:   return "#a5d6a7"
    if t <= 15:   return "#fff176"
    if t <= 20:   return "#ffb74d"
    if t <= 25:   return "#ef6c00"
    return "#b71c1c"


def build(days, avg, lo, hi, hum):
    years = sorted({d.year for d in days})

    # ── heatmap data: month × day-of-month grid per year ─────────────────────
    # We use a single wide heatmap: x = day-of-year (1-366), y = year
    doy = np.array([d.timetuple().tm_yday for d in days])
    yr  = np.array([d.year for d in days])

    grid = np.full((len(years), 366), np.nan)
    for i, (y, d, t) in enumerate(zip(yr, doy, avg)):
        yi = years.index(y)
        grid[yi, d - 1] = t

    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=False,
        row_heights=[0.30, 0.22, 0.26, 0.22],
        vertical_spacing=0.07,
        subplot_titles=[
            f"① Tägliche Durchschnittstemperatur — {CITY} (°C)",
            "② Tagestemperatur-Heatmap nach Jahr × Jahrestag",
            "③ Monatliche Mittelwerte im Jahresvergleich (°C)",
            "④ Relative Luftfeuchtigkeit (%) & 30-Tage-Mittel",
        ],
    )

    # ── Plot 1: line + min-max band ───────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=list(days) + list(days[::-1]),
        y=list(hi) + list(lo[::-1]),
        fill="toself",
        fillcolor="rgba(100,181,246,0.15)",
        line=dict(color="rgba(0,0,0,0)"),
        name="Min–Max Bereich",
        hoverinfo="skip",
        showlegend=True,
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=days, y=avg,
        mode="lines",
        name="Ø-Temperatur",
        line=dict(color="#4fc3f7", width=1.2),
        hovertemplate="%{x|%d %b %Y}: %{y:.1f} °C<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=days, y=rolling(avg),
        mode="lines",
        name="30-Tage Glättung",
        line=dict(color="#ffe082", width=2.5, dash="dash"),
        hovertemplate="30d-Ø: %{y:.1f} °C<extra></extra>",
    ), row=1, col=1)

    # 0 °C reference
    fig.add_hline(y=0, row=1, col=1,
                  line=dict(color="#ef5350", width=1, dash="dot"),
                  annotation_text="0 °C", annotation_position="right",
                  annotation_font=dict(color="#ef5350", size=9))

    # ── Plot 2: heatmap ───────────────────────────────────────────────────────
    # month tick positions (approx mid-month DOY)
    month_ticks = [15,46,74,105,135,166,196,227,258,288,319,349]
    fig.add_trace(go.Heatmap(
        z=grid,
        x=list(range(1, 367)),
        y=[str(y) for y in years],
        colorscale=[
            [0.0,  "#1565c0"],
            [0.25, "#42a5f5"],
            [0.42, "#a5d6a7"],
            [0.55, "#fff176"],
            [0.70, "#ffb74d"],
            [0.85, "#ef6c00"],
            [1.0,  "#b71c1c"],
        ],
        zmid=10,
        colorbar=dict(title="°C", len=0.22, y=0.515, thickness=12,
                      tickfont=dict(size=9)),
        hovertemplate="Jahr %{y}, Tag %{x}: %{z:.1f} °C<extra></extra>",
    ), row=2, col=1)

    fig.update_xaxes(
        tickvals=month_ticks,
        ticktext=MONTH_NAMES,
        row=2, col=1,
        title_text="Monat",
    )

    # ── Plot 3: monthly averages per year (grouped bars) ─────────────────────
    year_colors = ["#4fc3f7", "#ff8a65", "#66bb6a", "#ce93d8"]
    for yi, year in enumerate(years):
        mask = yr == year
        d_y  = days[mask]
        a_y  = avg[mask]
        # group by month
        monthly_avg = []
        for m in range(1, 13):
            vals = a_y[[d.month == m for d in d_y]]
            monthly_avg.append(float(np.nanmean(vals)) if len(vals) else float("nan"))

        fig.add_trace(go.Bar(
            x=MONTH_NAMES,
            y=monthly_avg,
            name=str(year),
            marker_color=year_colors[yi % len(year_colors)],
            opacity=0.8,
            hovertemplate=f"<b>{year}</b> %{{x}}: %{{y:.1f}} °C<extra></extra>",
        ), row=3, col=1)

    fig.add_hline(y=0, row=3, col=1,
                  line=dict(color="#ef5350", width=1, dash="dot"))

    # ── Plot 4: humidity ──────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=days, y=hum,
        mode="lines",
        name="Luftfeuchtigkeit",
        line=dict(color="#80cbc4", width=0.8),
        fill="tozeroy",
        fillcolor="rgba(128,203,196,0.10)",
        hovertemplate="%{x|%d %b %Y}: %{y:.0f} %%<extra></extra>",
    ), row=4, col=1)

    fig.add_trace(go.Scatter(
        x=days, y=rolling(hum),
        mode="lines",
        name="30d Ø Feuchte",
        line=dict(color="#ffe082", width=2, dash="dash"),
        hovertemplate="30d-Ø: %{y:.0f} %%<extra></extra>",
    ), row=4, col=1)

    # ── Layout ────────────────────────────────────────────────────────────────
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0f1117",
        plot_bgcolor="#1a1d27",
        font=dict(color="#cccccc", size=11),
        height=1200,
        title=dict(
            text=f"Wetter-Dashboard — {CITY}  (OpenWeatherMap)",
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

    for row in (1, 3, 4):
        fig.update_xaxes(gridcolor="#2a2d3a", showgrid=True, row=row, col=1)
        fig.update_yaxes(gridcolor="#2a2d3a", row=row, col=1)

    fig.update_yaxes(title_text="°C",  row=1, col=1)
    fig.update_yaxes(title_text="°C",  row=3, col=1)
    fig.update_yaxes(title_text="%",   row=4, col=1, range=[30, 105])

    return fig


def main():
    print(f"Fetching daily temperatures for {CITY} …")
    days, avg, lo, hi, hum = fetch_daily()
    print(f"  {len(days)} days  ({days[0].strftime('%d %b %Y')} – {days[-1].strftime('%d %b %Y')})")
    print(f"  Ø overall: {avg.mean():.1f} °C   min: {lo.min():.1f} °C   max: {hi.max():.1f} °C")

    fig = build(days, avg, lo, hi, hum)
    out = "alstaetten_temperature.html"
    fig.write_html(out, include_plotlyjs="cdn")
    print(f"Saved → {out}")

    pdf_out = out.replace(".html", ".pdf")
    fig.write_image(pdf_out, format="pdf")
    print(f"Saved → {pdf_out}")

    import webbrowser, os
    webbrowser.open(f"file://{os.path.abspath(out)}")


if __name__ == "__main__":
    main()
