# Build guide: UK Grid Carbon Tracker

Step-by-step instructions for building this project. Total time: roughly a weekend for the pipeline and first dashboard, then a week or two of evenings for analysis and polish.

---

## The project in one paragraph

Great Britain's electricity gets cleaner or dirtier every half hour depending on how much wind, solar, gas and nuclear is running. The National Energy System Operator (NESO) publishes this live through a free API, with forecasts up to 48 hours ahead and a breakdown by region. You will build a pipeline that collects it automatically every 30 minutes, then a Power BI dashboard that answers practical questions such as *"When is the greenest time to charge an EV in Scotland tomorrow?"* and *"How accurate is the national forecast?"*

```
NESO Carbon Intensity API  ──►  Python (collect.py)  ──►  CSVs in GitHub  ──►  Power BI Service
   (free, no key)              run every 30 min by         (public repo,        (scheduled refresh,
                               GitHub Actions              raw file URLs)        no gateway needed)
```

**Why this design:** no server, no database bill, no gateway on your laptop. GitHub Actions runs the script for free, GitHub stores the history, and Power BI reads the files over the web. It also shows employers a small but real data-engineering pipeline, not just a dashboard.

---

## Part 1: Get the pipeline running (about 1 hour)

1. **Create a public GitHub repo** called `uk-grid-carbon`. It must be public so Power BI can read the files without a login.
2. **Upload these files**, keeping the folder structure:
   ```
   collect.py
   requirements.txt
   README.md
   BUILD_GUIDE.md
   .github/workflows/collect.yml
   ```
   Tip: the `.github` folder is hidden on Mac/Windows. Using GitHub Desktop or `git` from the terminal is easier than drag-and-drop.
3. **Test locally first** (optional but recommended):
   ```bash
   pip install -r requirements.txt
   python collect.py --backfill 30
   ```
   You should see four CSVs appear in `data/`.
4. **Allow the workflow to push.** In the repo: *Settings → Actions → General → Workflow permissions →* choose **Read and write permissions** → Save.
5. **Load history.** Go to *Actions → Collect grid carbon data → Run workflow*, enter `60` in "Days of history" and run it. When it finishes (green tick), the `data/` folder will appear in the repo.
6. **Leave it running.** From now on it runs at :05 and :35 past every hour. Check the Actions tab after a day to confirm. If GitHub ever pauses the schedule (it can for quiet public repos), re-enable it from the same tab.

---

## Part 2: Connect Power BI (about 30 minutes)

1. Open any CSV in your repo on GitHub and click **Raw**. Copy that URL. It will look like:
   `https://raw.githubusercontent.com/YOUR-USERNAME/uk-grid-carbon/main/data/national_intensity.csv`
2. In **Power BI Desktop**: *Get data → Web →* paste the URL → *Anonymous* access. Repeat for each of the four files.
3. In Power Query, set column types: `from_uk` → **Date/Time**, `loaded_at_utc` → **Date/Time/Timezone**, the `_gco2` and `_pct` columns → **Decimal number**. Leave `from_utc` as text (it's the unique key). Or use the advanced editor:

   ```powerquery
   let
       Source   = Csv.Document(
                    Web.Contents("https://raw.githubusercontent.com/YOUR-USERNAME/uk-grid-carbon/main/data/regional_intensity.csv"),
                    [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
       Headers  = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
       Typed    = Table.TransformColumnTypes(Headers, {
                    {"from_uk", type datetime}, {"region_id", Int64.Type},
                    {"forecast_gco2", type number}, {"wind_pct", type number},
                    {"solar_pct", type number}, {"gas_pct", type number},
                    {"nuclear_pct", type number}}),
       AddHour  = Table.AddColumn(Typed, "Hour", each Time.Hour([from_uk]), Int64.Type),
       AddDay   = Table.AddColumn(AddHour, "Weekday", each Date.DayOfWeekName([from_uk]), type text),
       AddDate  = Table.AddColumn(AddDay, "Date", each DateTime.Date([from_uk]), type date)
   in
       AddDate
   ```
4. **Publish** to your Power BI workspace.
5. **Turn on scheduled refresh:** in the Power BI Service, open the semantic model → *Settings → Data source credentials* (set Web to *Anonymous*, privacy level *Public*) → *Scheduled refresh → On* → add times.

### How "live" can it be?

| Your licence | Scheduled refreshes per day | What that means |
|---|---|---|
| Power BI Pro | Up to 8 | e.g. 07:00, 09:00, 11:00 … 21:00 |
| Premium Per User / Fabric capacity | Up to 48 | Every 30 minutes, fully in step with the data |

The CSVs on GitHub update every 30 minutes whatever your licence. With Pro you can also press **Refresh now** in the Service at any time; manual refreshes don't count towards the 8.

---

## Part 3: Build the dashboard (a few evenings)

### Measures to create (DAX)

```dax
-- Latest national intensity (KPI card)
Latest Intensity =
VAR LatestTime = CALCULATE ( MAX ( national_intensity[from_uk] ), ALL ( national_intensity ) )
RETURN
    CALCULATE ( MAX ( national_intensity[forecast_gco2] ), national_intensity[from_uk] = LatestTime )

-- Average intensity for whatever is filtered
Avg Intensity = AVERAGE ( regional_intensity[forecast_gco2] )

-- Renewable share (wind + solar + hydro)
Renewable % =
AVERAGE ( regional_intensity[wind_pct] )
    + AVERAGE ( regional_intensity[solar_pct] )
    + AVERAGE ( regional_intensity[hydro_pct] )

-- Forecast accuracy: mean absolute error, only where an actual exists
Forecast MAE =
AVERAGEX (
    FILTER ( national_intensity, NOT ISBLANK ( national_intensity[actual_gco2] ) ),
    ABS ( national_intensity[actual_gco2] - national_intensity[forecast_gco2] )
)

-- Greenest half-hour in the next 48h for the selected region
Greenest Slot =
VAR MinVal = MIN ( regional_forecast_48h[forecast_gco2] )
RETURN
    FORMAT (
        CALCULATE ( MIN ( regional_forecast_48h[from_uk] ), regional_forecast_48h[forecast_gco2] = MinVal ),
        "ddd d mmm, hh:nn"
    )

-- Data freshness (show this on every page)
Last Updated =
"Data as of " & FORMAT ( MAX ( national_intensity[loaded_at_utc] ), "d mmm yyyy, hh:nn" ) & " UTC"
```

### Suggested report pages

1. **Right now:** KPI cards (latest intensity, renewable %, last updated), a donut of the current generation mix, and a line chart of the last 48 hours.
2. **Plan ahead:** a region slicer, the 48-hour forecast line for that region, and the *Greenest Slot* card. Colour the line by `intensity_index` (very low → very high).
3. **Scotland vs GB:** bar chart of average intensity by region, and a matrix of Hour × Weekday coloured by intensity (a heatmap). Scotland is usually far cleaner because of wind and hydro, so quantify by how much.
4. **Forecast accuracy:** forecast vs actual over time, *Forecast MAE* by hour of day. Is the forecast worse at certain times?

---

## Part 4: Analysis in Python (stretch, but strongly recommended)

Once you have 4+ weeks of data, add a Jupyter notebook (`analysis.ipynb`) that answers one question properly. Good options:

- **What drives carbon intensity?** Scatter wind % vs intensity, fit a simple linear regression, and report the R².
- **Is there a predictable daily pattern?** Group by hour and weekday, then show the cleanest and dirtiest times with confidence intervals.
- **How much CO₂ could flexible demand save?** Compare charging an EV at a fixed 18:00 versus at the greenest slot in the next 12 hours, across every day you've collected.

Write up two or three findings in plain English in the README. That's what hiring managers actually read.

---

## Things to know

- **Times:** the API is in UTC. The script adds `from_uk` (Europe/London, handles BST). On clock-change days you'll see one repeated hour, which is correct. Always use `from_utc` as the unique key.
- **Regional data has forecasts only.** "Actual" values exist only at national level.
- **Repo growth:** the regional file grows by roughly 4–5 MB per month. That's fine for many months; after a year, consider splitting by month.
- **Licence:** the data is CC BY 4.0. Credit "NESO Carbon Intensity API" on the dashboard and in the README.
