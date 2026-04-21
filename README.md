# EnergyAnalysis

Interactive Plotly dashboards for home energy consumption and weather data, backed by a MySQL database at `beker.club`.

The main focus is on analyzing energy usage patterns across three meters (whole-house, ground floor, upper floor) and correlating them with local weather conditions in Alstätten, Switzerland. The dashboards include cumulative energy totals, daily consumption patterns, temperature correlations, and more.

The energy measurements are performed with [Shelly Pro 3EM](https://www.shelly.com/en-ch/products/product-overview/pro-3-em) meters — DIN-rail mounted Wi-Fi/LAN three-phase energy meters with 1% measurement accuracy. They report present and cumulative counter values via MQTT to `mqtt.beker.club:1883`, where a Node-RED instance collects and writes them to the MySQL database on `beker.club:3306`. Weather data is fetched from OpenWeatherMap and stored on the same server at hourly resolution.

[![Shelly Pro 3EM](https://us.shelly.com/cdn/shop/files/Shelly-Pro-3EM-120-main-image_db4e0c04-4467-4527-af27-15ebf47e0b37_grande.png)](https://www.shelly.com/en-ch/products/product-overview/pro-3-em)


## Scripts

| Script | Output | Description |
| --- | --- | --- |
| `plot_shellies.py` | `shellies_energy.html` | Cumulative kWh totals + daily bar chart for all three meters |
| `plot_3pm_daily.py` | `daily_consumption.html` | 5-panel dashboard: daily kWh, hourly heatmap, peak/avg power, phase voltages, power factor |
| `plot_alstaetten_temp.py` | `alstaetten_temperature.html` | 4-panel weather dashboard: daily temps, year×DOY heatmap, monthly comparison, humidity |
| `plot_temp_vs_energy.py` | `temp_vs_energy.html` | Temperature vs. energy correlation with density contour and Oct–Apr linear regression |

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

## Meters

- **Allgemein** — whole-house main meter
- **EG** — ground floor (Erdgeschoss)
- **OG** — upper floor (Obergeschoss)

## Results

We use on average 26 kWh/day for the heat pump when it is 0 degrees outside on average over the day. Every degree more or less in ambient temperature cause the energy consumption to go up by 1.3 kWh or down by 1.3 kWh/d on average. The correlation is very strong in the heating season (Oct–Apr) with R² = 0.92, but much weaker in the summer months (R² = 0.24) when the heat pump is mostly off and other factors dominate energy usage.  The main usage in summer is warm water production, which is not directly weather-dependent. The dashboard [`temp_vs_energy.html`](temp_vs_energy.html) visualizes this relationship with a density contour plot and a linear regression line for the heating season. A static export is available as [temp_vs_energy.pdf](temp_vs_energy.pdf).
