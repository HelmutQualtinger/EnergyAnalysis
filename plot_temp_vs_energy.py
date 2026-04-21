#!/usr/bin/env python3
"""
Daily avg temperature (Altstätten SG) vs daily energy consumption (Allgemein kWh).
Row 2: 3D surface  temperature-bins × month → mean kWh + regression plane Oct–Apr.
Generates: temp_vs_energy.html
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
HOST   = os.environ["DB_HOST"]
PORT   = int(os.environ.get("DB_PORT", 3306))
USER   = os.environ["DB_USER"]
PASSWD = os.environ["DB_PASS"]

def sql(db, query):
    r = subprocess.run(
        ["mysql", "-h", HOST, "-P", str(PORT), "-u", USER, f"-p{PASSWD}", db,
         "--batch", "--silent", "-e", query],
        capture_output=True, text=True, check=True,
    )
    return [line.split("\t") for line in r.stdout.splitlines() if line.strip()]


def fetch_temp():
    rows = sql("OpenWeatherMap", """
        SELECT DATE(dt) AS day, ROUND(AVG(temperature), 2)
        FROM weather_data WHERE city = 'Altstätten SG'
        GROUP BY day ORDER BY day
    """)
    return {r[0]: float(r[1]) for r in rows if len(r) == 2}


def fetch_energy():
    rows = sql("Shellies", """
        SELECT DATE(time) AS day, MAX(total_act)
        FROM `3PM_total_values`
        WHERE meter_name = 'Allgemein'
        GROUP BY day ORDER BY day
    """)
    result, prev_wh, prev_day = {}, None, None
    for r in rows:
        if len(r) != 2:
            continue
        day, wh = r[0], float(r[1])
        if prev_wh is not None:
            delta = (wh - prev_wh) / 1000
            if delta >= 0:
                result[prev_day] = delta
        prev_wh, prev_day = wh, day
    return result


def align(temp, energy):
    common = sorted(set(temp) & set(energy))
    days = np.array([datetime.strptime(d, "%Y-%m-%d") for d in common])
    t = np.array([temp[d]   for d in common])
    e = np.array([energy[d] for d in common])
    return days, t, e


def weekly_avg(days, temp, energy):
    """Collapse daily arrays into ISO-week means (only complete 7-day weeks)."""
    from collections import defaultdict
    buckets: dict = defaultdict(lambda: {"t": [], "e": [], "dates": []})
    for d, t, e in zip(days, temp, energy):
        key = d.isocalendar()[:2]   # (year, week)
        buckets[key]["t"].append(t)
        buckets[key]["e"].append(e)
        buckets[key]["dates"].append(d)
    w_days, w_temp, w_energy = [], [], []
    for key in sorted(buckets):
        b = buckets[key]
        if len(b["dates"]) < 7:     # skip incomplete weeks at the boundaries
            continue
        w_days.append(b["dates"][0])   # Monday of that week
        w_temp.append(float(np.nanmean(b["t"])))
        w_energy.append(float(np.nanmean(b["e"])))
    return np.array(w_days), np.array(w_temp), np.array(w_energy)


def rolling(arr, w=7):
    out = np.full_like(arr, np.nan, dtype=float)
    for i in range(w - 1, len(arr)):
        out[i] = np.nanmean(arr[i - w + 1:i + 1])
    return out


def build_surface_grid(temp, energy, months):
    """Build month × temp-bin grid of mean daily energy."""
    t_min = np.floor(temp.min()) - 1
    t_max = np.ceil(temp.max()) + 1
    bin_w = 2.0
    t_edges = np.arange(t_min, t_max + bin_w, bin_w)
    t_centers = (t_edges[:-1] + t_edges[1:]) / 2
    month_vals = np.arange(1, 13)

    grid = np.full((len(month_vals), len(t_centers)), np.nan)
    for mi, m in enumerate(month_vals):
        for ti in range(len(t_centers)):
            mask = (months == m) & (temp >= t_edges[ti]) & (temp < t_edges[ti + 1])
            if mask.sum() >= 2:
                grid[mi, ti] = np.nanmean(energy[mask])

    return t_centers, month_vals, grid


def build(days, temp, energy):
    months = np.array([d.month for d in days])
    valid  = ~np.isnan(temp) & ~np.isnan(energy)
    winter = valid & np.isin(months, [10, 11, 12, 1, 2, 3, 4])

    # ── Linear fit Oct–Apr ────────────────────────────────────────────────────
    coef = np.polyfit(temp[winter], energy[winter], 1)
    slope, intercept = float(coef[0]), float(coef[1])
    corr  = float(np.corrcoef(temp[winter], energy[winter])[0, 1])

    roll_t = rolling(temp, w=4)
    roll_e = rolling(energy, w=4)

    # ── Subplots: row1=2D dual, row2=3D scene, row3=2D dual ──────────────────
    fig = make_subplots(
        rows=3, cols=1,
        row_heights=[0.28, 0.52, 0.20],
        vertical_spacing=0.05,
        subplot_titles=[
            "① Wochenmittel: Temperatur (°C) vs. Verbrauch Allgemein (kWh)",
            (f"② Dichte-Kontur: Temperatur (°C) × Verbrauch (kWh)"
             f"   |   Fit Okt–Apr: y = {slope:.3f}·T + {intercept:.2f}  "
             f"r = {corr:.3f}  r² = {corr**2:.3f}"),
            "③ 4-Wochen Glättung: Verbrauch & Temperatur",
        ],
        specs=[[{"secondary_y": True}],
               [{"secondary_y": False}],
               [{"secondary_y": True}]],
    )

    # ── Row 1: time-series dual axis ──────────────────────────────────────────
    fig.add_trace(go.Bar(
        x=days, y=energy, name="Verbrauch (kWh)",
        marker_color="#ff8a65", opacity=0.5,
        hovertemplate="KW %{x|%d %b %Y}: %{y:.1f} kWh<extra></extra>",
    ), row=1, col=1, secondary_y=False)

    fig.add_trace(go.Scatter(
        x=days, y=roll_e, name="4-Wochen Ø Verbrauch",
        line=dict(color="#ef6c00", width=2),
        hovertemplate="4W-Ø: %{y:.1f} kWh<extra></extra>",
    ), row=1, col=1, secondary_y=False)

    fig.add_trace(go.Scatter(
        x=days, y=temp, name="Ø Temperatur (°C)",
        line=dict(color="#4fc3f7", width=1.2), opacity=0.7,
        hovertemplate="KW %{x|%d %b %Y}: %{y:.1f} °C<extra></extra>",
    ), row=1, col=1, secondary_y=True)

    fig.add_trace(go.Scatter(
        x=days, y=roll_t, name="4-Wochen Ø Temperatur",
        line=dict(color="#ffe082", width=2, dash="dash"),
        hovertemplate="4W-Ø: %{y:.1f} °C<extra></extra>",
    ), row=1, col=1, secondary_y=True)

    fig.add_hline(y=0, row=1, col=1,
                  line=dict(color="#ef5350", width=1, dash="dot"),
                  annotation_text="0 °C", annotation_position="top right",
                  annotation_font=dict(color="#ef5350", size=9))

    # ── Row 2: density contour  x=temperature, y=energy ─────────────────────
    month_labels = ["Jan","Feb","Mär","Apr","Mai","Jun",
                    "Jul","Aug","Sep","Okt","Nov","Dez"]

    # all-data density contour
    fig.add_trace(go.Histogram2dContour(
        x=temp[valid],
        y=energy[valid],
        colorscale=[
            [0.0, "#0f1117"], [0.15, "#1565c0"], [0.40, "#42a5f5"],
            [0.65, "#a5d6a7"], [0.85, "#ffb74d"], [1.0,  "#b71c1c"],
        ],
        contours=dict(
            showlabels=True,
            labelfont=dict(size=9, color="white"),
        ),
        colorbar=dict(title="Tage", len=0.28, x=1.01, thickness=14,
                      tickfont=dict(size=9)),
        nbinsx=40, nbinsy=40,
        hovertemplate="Temp: %{x:.1f} °C<br>Verbr: %{y:.1f} kWh<br>Dichte: %{z}<extra></extra>",
        name="Alle Monate",
        showlegend=False,
    ), row=2, col=1)

    # scatter points coloured by month underneath
    month_colors = [
        "#90caf9","#80cbc4","#a5d6a7","#c5e1a5","#fff176","#ffcc02",
        "#ffb74d","#ef6c00","#ff7043","#ce93d8","#80deea","#90caf9",
    ]
    for m in range(1, 13):
        mask_m = (months == m) & valid
        if not mask_m.any():
            continue
        fig.add_trace(go.Scatter(
            x=temp[mask_m], y=energy[mask_m],
            mode="markers",
            name=month_labels[m - 1],
            marker=dict(color=month_colors[m - 1], size=4, opacity=0.5,
                        line=dict(width=0)),
            hovertemplate=(f"<b>{month_labels[m-1]}</b><br>"
                           "Temp: %{x:.1f} °C<br>"
                           "Verbr: %{y:.1f} kWh<extra></extra>"),
        ), row=2, col=1)

    # regression line Oct–Apr
    reg_t = np.linspace(temp[winter].min(), temp[winter].max(), 200)
    reg_e = slope * reg_t + intercept
    fig.add_trace(go.Scatter(
        x=reg_t, y=reg_e,
        mode="lines",
        name=f"Regression Okt–Apr ({slope:.3f} kWh/°C)",
        line=dict(color="#ffe082", width=2.5, dash="dash"),
        hovertemplate="Fit: %{y:.1f} kWh @ %{x:.1f} °C<extra></extra>",
    ), row=2, col=1)

    eq_label = (f"<b>Fit Okt–Apr</b><br>"
                f"y = {slope:.3f}·T + {intercept:.2f} kWh<br>"
                f"r = {corr:.3f}   r² = {corr**2:.3f}<br>"
                f"Steigung: {slope:.3f} kWh/°C")
    fig.add_annotation(
        row=2, col=1,
        x=temp[winter].max() - 1,
        y=energy[valid].max() * 0.93,
        text=eq_label,
        showarrow=False,
        font=dict(color="#ffe082", size=11),
        bgcolor="#1e2130", bordercolor="#ffe082", borderwidth=1,
        align="left",
        xanchor="right",
    )

    # ── Row 3: smoothed overlay ───────────────────────────────────────────────
    fig.add_trace(go.Scatter(
        x=days, y=roll_e, name="7d Ø Verbr",
        line=dict(color="#ff8a65", width=2), showlegend=False,
        hovertemplate="7d-Ø Verbr: %{y:.1f} kWh<extra></extra>",
    ), row=3, col=1, secondary_y=False)

    fig.add_trace(go.Scatter(
        x=days, y=roll_t, name="7d Ø Temp",
        line=dict(color="#4fc3f7", width=2), showlegend=False,
        hovertemplate="7d-Ø Temp: %{y:.1f} °C<extra></extra>",
    ), row=3, col=1, secondary_y=True)

    # ── Global layout ─────────────────────────────────────────────────────────
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0f1117",
        plot_bgcolor="#1a1d27",
        font=dict(color="#cccccc", size=11),
        height=1350,
        title=dict(
            text=(f"Altstätten SG — Wochenmittel: Temperatur vs. Energieverbrauch Allgemein"
                  f"   (Fit Okt–Apr: r = {corr:.3f},  r² = {corr**2:.3f})"),
            font=dict(size=15), x=0.5,
        ),
        legend=dict(
            orientation="h", y=-0.04, x=0,
            bgcolor="rgba(30,33,48,0.8)", bordercolor="#444", borderwidth=1,
        ),
        barmode="overlay",
        margin=dict(l=65, r=80, t=80, b=60),
        hovermode="x unified",
    )

    for row in (1, 3):
        fig.update_xaxes(gridcolor="#2a2d3a", showgrid=True, row=row, col=1)
    fig.update_xaxes(title_text="Temperatur (°C)", gridcolor="#2a2d3a",
                     showgrid=True, row=2, col=1)
    fig.update_yaxes(title_text="kWh", gridcolor="#2a2d3a",
                     row=1, col=1, secondary_y=False)
    fig.update_yaxes(title_text="°C",  gridcolor="#2a2d3a",
                     row=1, col=1, secondary_y=True)
    fig.update_yaxes(title_text="Verbrauch (kWh)", gridcolor="#2a2d3a",
                     scaleanchor="x2", scaleratio=1,
                     row=2, col=1)
    fig.update_yaxes(title_text="kWh", gridcolor="#2a2d3a",
                     row=3, col=1, secondary_y=False)
    fig.update_yaxes(title_text="°C",  gridcolor="#2a2d3a",
                     row=3, col=1, secondary_y=True)

    return fig, corr, slope, intercept, winter.sum()


def main():
    print("Fetching temperature …")
    temp = fetch_temp()
    print("Fetching energy …")
    energy = fetch_energy()

    days, t, e = align(temp, energy)
    days, t, e = weekly_avg(days, t, e)
    print(f"  {len(days)} complete weeks  "
          f"({days[0].strftime('%d %b %Y')} – {days[-1].strftime('%d %b %Y')})")

    fig, corr, slope, intercept, n_winter = build(days, t, e)

    print(f"\nFit on {n_winter} winter weeks (Okt–Apr)")
    print(f"Pearson r = {corr:.3f}   r² = {corr**2:.3f}")
    print(f"y = {slope:.3f}·T + {intercept:.2f} kWh")

    out = "temp_vs_energy.html"
    fig.write_html(out, include_plotlyjs="cdn")
    print(f"Saved → {out}")

    pdf_out = out.replace(".html", ".pdf")
    fig.write_image(pdf_out, format="pdf")
    print(f"Saved → {pdf_out}")

    import webbrowser, os
    webbrowser.open(f"file://{os.path.abspath(out)}")


if __name__ == "__main__":
    main()
