#!/usr/bin/env python3
"""
Average consumption by hour of day for all three meters: Allgemein, EG, OG.
Generates: hourly_consumption.html
"""

import os
import subprocess
from pathlib import Path
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


def fetch_hourly_power() -> dict:
    """Get average power (W) by hour of day for all three meters."""
    rows = sql("""
        SELECT HOUR(time) AS hour, meter_name,
               AVG(total_act_power) AS avg_w
        FROM `3PM_present_values`
        WHERE meter_name IN ('Allgemein','EG','OG')
        GROUP BY hour, meter_name ORDER BY hour, meter_name
    """)

    data = {m: [None] * 24 for m in ("Allgemein", "EG", "OG")}

    for r in rows:
        if len(r) != 3:
            continue
        hour, meter, w = int(r[0]), r[1], float(r[2])
        if meter in data:
            data[meter][hour] = w

    for m in data:
        data[m] = np.array(data[m])

    return data


def fetch_hourly_consumption() -> dict:
    """Get average kWh by hour of day for all three meters (derived from W)."""
    power_data = fetch_hourly_power()
    # Convert W to kWh/hour: W * 1h / 1000
    consumption = {}
    for meter, watts in power_data.items():
        consumption[meter] = watts / 1000
    return consumption


def build(consumption: dict, power: dict) -> go.Figure:
    hours = np.arange(24)

    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.5, 0.5],
        vertical_spacing=0.10,
        subplot_titles=[
            "① Durchschnittlicher Stromverbrauch je Stunde (kWh/h)",
            "② Durchschnittliche Leistung je Stunde (W)",
        ],
    )

    # ── Plot 1: Consumption (kWh) ─────────────────────────────────────────────
    for meter in ("Allgemein", "EG", "OG"):
        fig.add_trace(go.Bar(
            x=hours,
            y=consumption[meter],
            name=meter,
            marker_color=COLORS[meter],
            opacity=0.8,
            hovertemplate=f"<b>{meter}</b> %{{x:02d}}:00: %{{y:.3f}} kWh<extra></extra>",
        ), row=1, col=1)

    # ── Plot 2: Power (W) ─────────────────────────────────────────────────────
    for meter in ("Allgemein", "EG", "OG"):
        fig.add_trace(go.Scatter(
            x=hours,
            y=power[meter],
            mode="lines+markers",
            name=meter,
            line=dict(color=COLORS[meter], width=2.5),
            marker=dict(size=6),
            hovertemplate=f"<b>{meter}</b> %{{x:02d}}:00: %{{y:.0f}} W<extra></extra>",
            showlegend=False,
        ), row=2, col=1)

    # ── Layout ────────────────────────────────────────────────────────────────
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0f1117",
        plot_bgcolor="#1a1d27",
        font=dict(color="#cccccc", size=11),
        height=900,
        title=dict(
            text="Durchschnittlicher Stromverbrauch nach Tageszeit",
            font=dict(size=16), x=0.5,
        ),
        legend=dict(
            orientation="h", y=1.02, x=0,
            bgcolor="rgba(30,33,48,0.8)", bordercolor="#444", borderwidth=1,
        ),
        barmode="group",
        margin=dict(l=70, r=30, t=80, b=60),
        hovermode="x unified",
    )

    for row in range(1, 3):
        fig.update_xaxes(
            tickvals=list(range(24)),
            ticktext=[f"{h:02d}" for h in range(24)],
            title_text="Stunde",
            gridcolor="#2a2d3a", showgrid=True,
            row=row, col=1,
        )
        fig.update_yaxes(gridcolor="#2a2d3a", row=row, col=1)

    fig.update_yaxes(title_text="kWh/Stunde", row=1, col=1)
    fig.update_yaxes(title_text="Watt (W)", row=2, col=1)

    return fig


def main():
    print("Fetching hourly consumption …")
    consumption = fetch_hourly_consumption()
    print(f"  24 hours processed")

    print("Fetching hourly power …")
    power = fetch_hourly_power()

    print("Building figure …")
    fig = build(consumption, power)

    out = "hourly_consumption.html"
    fig.write_html(out, include_plotlyjs="cdn")
    print(f"Saved → {out}")

    pdf_out = out.replace(".html", ".pdf")
    fig.write_image(pdf_out, format="pdf")
    print(f"Saved → {pdf_out}")

    import webbrowser, os
    webbrowser.open(f"file://{os.path.abspath(out)}")


if __name__ == "__main__":
    main()
