# ParkPulse: National Parks Intelligence System

An automated daily data pipeline and Streamlit dashboard for U.S. national parks. Built to show the
skills in a "data automation, light analysis and visualisation" role: **structure a recurring data process,
automate it, check its quality, and present it clearly.**

> **Data note.** Without an API key the pipeline generates clearly labelled **demo data** (the dashboard
> shows an orange "Demo data" badge). Set `NPS_API_KEY` for live parks/fees from the NPS API, and drop a
> Kaggle/IRMA visitation CSV at `data/raw/visitation.csv` for real visit history. Climate and "best month"
> logic uses a transparent temperature model in demo mode, replaceable with real climate normals.

## Architecture
```
NPS API / Kaggle CSV / demo generator
        |
  1 Ingest  ->  2 Validate + clean  ->  3 Weather  ->  4 Diff vs yesterday  ->  5 Load SQLite  ->  6 Daily brief
                (rules, auto-fix,       (Open-Meteo,     (new / updated /          (data/parkpulse.db)  (data/daily_brief.md)
                 quality scores)         model fallback)  removed rows)
        |
  GitHub Actions runs this every day at 06:00 UTC  ->  Streamlit dashboard reads the database
```

## Dashboard tabs
Home | Explorer (map) | Trip planner (best month, free vs paid) | Compare | Dashboards | Ask (10 saved SQL questions) | Automation | Data health | Integrations

## Run it
```bash
pip install -r requirements.txt
python pipeline.py            # builds data/parkpulse.db (re-runnable, idempotent)
pytest -q                     # 4 tests
streamlit run app.py
```
Optional: `export NPS_API_KEY=...` for live data. Add it as a GitHub secret for the scheduled job.

## Automation
`.github/workflows/daily_refresh.yml` runs tests, runs the pipeline, and commits the refreshed database daily.
Each run records step timings, data-quality scores, rows flagged, and a **what changed** log per table.

## What I personally built
_Edit this section honestly before submitting._
- Designed the pipeline stages, validation rules, and change detection
- Wrote the Streamlit dashboard and the SQL analyses
- Set up the daily GitHub Actions schedule and tests
- Note which parts you wrote yourself and which used AI assistance.

## Limitations
- Demo mode uses synthetic visits/climate; entry fees are illustrative. Verify against nps.gov before publishing.
- The NPS API and Open-Meteo calls are implemented but were not exercised in my offline build environment.
