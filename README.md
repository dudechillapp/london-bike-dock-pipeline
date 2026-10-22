# London Bike Dock Pipeline

**Work in progress.** A data pipeline that collects live Transport for London (TfL) bike-dock data every 15 minutes, stores it in TimescaleDB, orchestrates it with Airflow, forecasts which docks will run empty, and exposes the results to an AI agent through MCP (Model Context Protocol).

## Question
Which London docks run out of bikes on weekday mornings, how much does rain change that, and can we warn operators 1 hour ahead?

## Stack
Python 3.13 · TimescaleDB (PostgreSQL 16) · Airflow · SQL · pandas · scikit-learn · Power BI · MCP · Docker

## Run it
1. Install Docker Desktop and Python 3.13.
2. Copy `.env.example` to `.env` and set `DB_PASSWORD` (use the same password inside `WAREHOUSE_URL`).
3. Start the warehouse:
   ```
   docker compose up -d
   ```
4. Create the Python environment:
   ```
   py -3.13 -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

## Progress
- [x] Step 0: project setup and warehouse
- [ ] Step 1: business question and KPIs
- [ ] Step 2: extract (TfL BikePoint API, journey files, Open-Meteo weather)
- [ ] Step 3: load into Timescale hypertables
- [ ] Step 4: orchestrate with Airflow
- [ ] Step 5: transform into marts
- [ ] Step 6: data quality tests
- [ ] Step 7: explore and forecast
- [ ] Step 8: MCP agent layer
- [ ] Step 9: dashboard and findings
