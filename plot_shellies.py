#!/usr/bin/env python3
"""
Plot total_act energy data from Shellies DB (3PM_total_values).
Usage: python3 plot_shellies.py [--since YYYY-MM-DD] [--out FILE.html]
"""

import argparse
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
TABLE   = "3PM_total_values"

METERS = [
    ("Allgemein", "#4fc3f7"),   # cyan
    ("EG",        "#66bb6a"),   # green  (Erdgeschoss)
    ("OG",        "#ff8a65"),   # orange (Obergeschoss)
]


def fetch_all(since: str | None) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    meter_names = [m for m, _ in METERS]
    cases = ",\n  ".join(
        f"MAX(CASE WHEN meter_name='{m}' THEN total_act END) AS `{m}`"
        for m in meter_names
    )
    where = f"meter_name IN ({', '.join(repr(m) for m in meter_names)})"
    if since:
        where += f" AND DATE(time) >= '{since}'"
    sql = (
        f"SELECT DATE(time) AS day,\n  {cases}\n"
        f"FROM `{TABLE}` WHERE {where}\n"
        f"GROUP BY day ORDER BY day;"
    )
    result = subprocess.run(
        ["mysql", "-h", DB_HOST, "-P", str(DB_PORT),
         "-u", DB_USER, f"-p{DB_PASS}", DB_NAME,
         "--batch", "--silent", "-e", sql],
        capture_output=True, text=True, check=True,
    )
    raw: dict[str, list] = {m: [] for m in meter_names}
    date_list: list[datetime] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split("\t")
        if len(parts) != len(meter_names) + 1:
            continue
        date_list.append(datetime.strptime(parts[0], "%Y-%m-%d"))
        for i, m in enumerate(meter_names):
            raw[m].append(float(parts[i + 1]) if parts[i + 1] != "NULL" else float("nan"))
    dates = np.array(date_list)
    return {m: (dates, np.array(raw[m]) / 1000) for m in meter_names}  # Wh → kWh


def rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def build_figure(datasets: list[tuple[str, np.ndarray, np.ndarray, str]]) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        row_heights=[0.5, 0.5],
        vertical_spacing=0.06,
        subplot_titles=[
            "Kumulative Gesamtenergie (kWh)",
            "Täglicher Verbrauch (kWh)",
        ],
    )

    for meter, dates, values, color in datasets:
        daily_kwh = np.maximum(np.diff(values), 0)
        delta_dates = dates[1:]
        total = values[-1] - values[0]
        avg = float(np.mean(daily_kwh[daily_kwh > 0]))

        # Cumulative line
        fig.add_trace(go.Scatter(
            x=dates, y=values,
            mode="lines",
            name=meter,
            line=dict(color=color, width=2),
            fill="tozeroy",
            fillcolor=rgba(color, 0.07),
            legendgroup=meter,
            hovertemplate=f"<b>{meter}</b><br>%{{x|%d %b %Y}}<br>%{{y:,.0f}} kWh<extra></extra>",
        ), row=1, col=1)

        # Daily bars
        fig.add_trace(go.Bar(
            x=delta_dates, y=daily_kwh,
            name=meter,
            marker_color=color,
            opacity=0.8,
            legendgroup=meter,
            showlegend=False,
            hovertemplate=f"<b>{meter}</b><br>%{{x|%d %b %Y}}<br>%{{y:.1f}} kWh<extra></extra>",
        ), row=2, col=1)

        fig.update_yaxes(rangemode="tozero", row=2, col=1)

        # Avg dashed line per meter
        fig.add_hline(
            y=avg, row=2, col=1,
            line=dict(color=color, width=1, dash="dot"),
            annotation_text=f"{meter} Ø {avg:.1f}",
            annotation_position="top left",
            annotation_font=dict(color=color, size=10),
        )

        # Annotation on cumulative chart
        fig.add_annotation(
            x=dates[-1], y=values[-1],
            xref="x1", yref="y1",
            text=f"<b>{meter}</b> {total:,.0f} kWh",
            showarrow=True, arrowhead=0,
            arrowcolor=color, arrowwidth=1,
            ax=40, ay=-20,
            font=dict(color=color, size=10),
            bgcolor="#1e2130", bordercolor=color, borderwidth=1,
        )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0f1117",
        plot_bgcolor="#1a1d27",
        font=dict(color="#cccccc"),
        height=760,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="left", x=0,
            bgcolor="rgba(30,33,48,0.8)", bordercolor="#444", borderwidth=1,
        ),
        barmode="overlay",
        margin=dict(l=60, r=30, t=80, b=40),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="kWh (kumulativ)", row=1, col=1,
                     tickformat=",.0f", gridcolor="#2a2d3a")
    fig.update_yaxes(title_text="kWh/Tag", row=2, col=1, gridcolor="#2a2d3a")
    fig.update_xaxes(gridcolor="#2a2d3a", showgrid=True)

    return fig


def main():
    parser = argparse.ArgumentParser(description="Plot Shellies energy meter data.")
    parser.add_argument("--since", default=None, help="Start date YYYY-MM-DD (default: all data)")
    parser.add_argument("--out", default="shellies_energy.html", help="Output HTML file")
    args = parser.parse_args()

    print("Fetching all meters" + (f" since {args.since}" if args.since else " (all time)") + " ...")
    all_data = fetch_all(args.since)
    datasets = []
    for meter, color in METERS:
        dates, values = all_data[meter]
        print(f"  {meter}: {len(dates)} days ({dates[0].strftime('%d %b %Y')} – {dates[-1].strftime('%d %b %Y')})")
        datasets.append((meter, dates, values, color))

    fig = build_figure(datasets)
    fig.write_html(args.out)
    print(f"Saved → {args.out}")

    pdf_out = args.out.replace(".html", ".pdf")
    fig.write_image(pdf_out, format="pdf")
    print(f"Saved → {pdf_out}")

    import webbrowser, os
    webbrowser.open(f"file://{os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
