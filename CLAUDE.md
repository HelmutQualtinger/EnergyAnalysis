# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
uv sync                    # install dependencies from pyproject.toml
cp .env.example .env       # then fill in DB_PASS
```

Credentials are loaded from `.env` via `python-dotenv`. `.env` is gitignored.

## Running the scripts

```bash
uv run python3 plot_shellies.py [--since YYYY-MM-DD] [--out FILE.html]
uv run python3 plot_3pm_daily.py
uv run python3 plot_alstaetten_temp.py
uv run python3 plot_temp_vs_energy.py
```

Each script fetches data, builds a Plotly figure, writes an `.html` file, and opens it in the browser automatically.

## Architecture

All scripts share the same pattern:

1. **`sql(db, query)`** — runs `mysql` CLI as a subprocess against `beker.club:3306` and returns tab-separated rows as `list[list[str]]`. No ORM or connection library; the MySQL client binary must be on `PATH`.
2. **`fetch_*()`** — issue SQL, parse rows into numpy arrays, return dicts or tuples.
3. **`build()`** — assembles a multi-row Plotly `make_subplots` figure (dark theme: `paper_bgcolor="#0f1117"`, `plot_bgcolor="#1a1d27"`).
4. **`main()`** — orchestrates fetch → build → `write_html` → `webbrowser.open`.

## Hardware

[Shelly Pro 3EM](https://www.shelly.com/en-ch/products/product-overview/pro-3-em) — DIN-rail three-phase energy meter (1% accuracy, 120 A CT, Wi-Fi/LAN). Publishes cumulative Wh totals and instantaneous W readings via MQTT → Node-RED → MySQL. Three meters installed: Allgemein (whole house), EG (ground floor), OG (upper floor).

## Data sources

| Database | Tables used | Content |
| --- | --- | --- |
| `Shellies` | `3PM_total_values` | Cumulative Wh totals per meter (Allgemein / EG / OG) |
| `Shellies` | `3PM_present_values` | Instantaneous power, voltage, power factor per phase |
| `OpenWeatherMap` | `weather_data` | Hourly weather for city `'Altstätten SG'` |

Energy values in `total_act` are stored in **Wh**; scripts divide by 1000 to get kWh. Daily consumption is derived as `diff(cumulative)`, clamped to ≥ 0 to suppress meter resets.

## Conventions

- All output files are standalone `.html` with `include_plotlyjs="cdn"`.
- German-language axis labels and subplot titles throughout.
- `SINCE = "2025-01-01"` hard-coded in `plot_3pm_daily.py` — adjust there to change the analysis window.
- `plot_temp_vs_energy.py` correlates temperature against the **Allgemein** meter only (not EG/OG).
- Winter/heating season is defined as months `[10, 11, 12, 1, 2, 3, 4]` (Oct–Apr) in `plot_temp_vs_energy.py`.
- Row 2 of `plot_temp_vs_energy.py` uses `Histogram2dContour` (density contour), not a surface plot.
