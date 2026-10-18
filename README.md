# UK Grid Carbon Tracker

A live analytics project tracking how clean Great Britain's electricity is, every 30 minutes, by region.

**Questions it answers**
- When is the greenest time to use electricity in my region over the next 48 hours?
- How much cleaner is Scotland's electricity than the rest of GB, and when?
- How accurate is the national carbon-intensity forecast, and when does it miss?

![Dashboard screenshot](images/dashboard.png)
<!-- Add a screenshot of your Power BI report at images/dashboard.png -->

## How it works

```
NESO Carbon Intensity API ─► Python collector ─► CSV history in this repo ─► Power BI
                             (GitHub Actions,                                 (scheduled refresh)
                              every 30 min)
```

- **Source:** [NESO Carbon Intensity API](https://carbon-intensity.github.io/api-definitions/): national and regional carbon intensity (gCO₂/kWh), generation mix, and 48-hour forecasts.
- **Pipeline:** `collect.py` pulls the latest 24 hours plus the 48-hour forecast, converts times to UK local time, and upserts into CSVs so revised forecasts and late "actual" values replace older rows without duplicates.
- **Scheduling:** a GitHub Actions workflow runs the collector every 30 minutes and commits changes.
- **Reporting:** Power BI reads the CSVs directly from GitHub, with no gateway or database needed.

## Data

| File | Grain | Contents |
|---|---|---|
| `data/national_intensity.csv` | Half hour | GB forecast and actual intensity |
| `data/national_generation.csv` | Half hour | GB generation mix by fuel (%) |
| `data/regional_intensity.csv` | Half hour × region | Regional forecast intensity and mix |
| `data/regional_forecast_48h.csv` | Half hour × region | Latest 48-hour forecast snapshot |

## Key findings

<!-- Replace with your own findings once you have a few weeks of data. Lead with numbers. -->
1. *e.g. Average intensity in North Scotland was X% lower than the GB average over the period.*
2. *e.g. The cleanest hours were typically between __ and __; the dirtiest were __.*
3. *e.g. Each 10-point rise in wind share was associated with a __ gCO₂/kWh drop (R² = __).*

## Run it yourself

```bash
pip install -r requirements.txt
python collect.py --backfill 30   # load 30 days of history
python collect.py                 # normal incremental run
```

Full setup, Power BI steps and DAX measures are in [BUILD_GUIDE.md](BUILD_GUIDE.md).

## Tools

Python (pandas, requests) · GitHub Actions · Power BI (Power Query, DAX) · REST APIs

---

Data: NESO Carbon Intensity API, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
