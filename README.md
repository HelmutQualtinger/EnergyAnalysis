# EnergyAnalysis

Interactive Plotly dashboards for home energy consumption and weather data, backed by a MySQL database at `beker.club`.

The main focus is on analyzing energy usage patterns across three meters (whole-house, ground floor, upper floor) and correlating them with local weather conditions in Alstätten, Switzerland. The dashboards include cumulative energy totals, daily consumption patterns, temperature correlations, and more.

## Scripts

| Script | Output | Description |
| --- | --- | --- |
| `plot_shellies.py` | `shellies_energy.html` | Cumulative kWh totals + daily bar chart for all three meters |
| `plot_3pm_daily.py` | `daily_consumption.html` | 5-panel dashboard: daily kWh, hourly heatmap, peak/avg power, phase voltages, power factor |
| `plot_alstaetten_temp.py` | `alstaetten_temperature.html` | 4-panel weather dashboard: daily temps, year×DOY heatmap, monthly comparison, humidity |
| `plot_temp_vs_energy.py` | `temp_vs_energy.html` | Temperature vs. energy correlation (Allgemein only) with density contour and Oct–Apr linear regression |

## Usage

```bash
# With optional date filter and output path
python3 plot_shellies.py --since 2025-01-01 --out my_output.html

# All other scripts use hard-coded defaults — just run them
python3 plot_3pm_daily.py
python3 plot_alstaetten_temp.py
python3 plot_temp_vs_energy.py
```

Each script opens the generated HTML file in the default browser automatically.

## Requirements

- Python 3.10+
- `mysql` CLI client on `PATH` (used to query `beker.club:3306`)

Install Python dependencies with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Run scripts via:

```bash
uv run python3 plot_shellies.py
```

## Configuration

Copy `.env.example` to `.env` and fill in credentials — `.env` is gitignored.

```ini
DB_HOST=beker.club
DB_PORT=3306
DB_USER=root
DB_PASS=your_password
```

## Latest results (21 Apr 2026)

| Dashboard | Coverage | Key finding |
| --- | --- | --- |
| Energy totals | 567 days (Oct 2024 – Apr 2026) | All three meters tracked |
| Daily consumption | 475 days (Jan 2025 – Apr 2026) | Hourly & day-of-week patterns |
| Temperature | 787 days (Feb 2024 – Apr 2026) | Ø 11.0 °C · min −12.3 °C · max 36.0 °C |
| Temp vs. energy | 566 overlapping days | r = −0.805 · r² = 0.648 · slope −1.24 kWh/°C (Oct–Apr) |

## Meters

- **Allgemein** — whole-house main meter
- **EG** — ground floor (Erdgeschoss)
- **OG** — upper floor (Obergeschoss)
