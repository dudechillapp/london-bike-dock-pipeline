# Builds the whole warehouse from scratch on Windows (PowerShell).
# Run from the project folder, with Docker running and .env filled in:
#     .\scripts\build_warehouse.ps1
# Takes about 15-25 minutes, mostly downloading 12 months of TfL journey files.

$ErrorActionPreference = "Stop"

function Run-Sql($file) {
    Write-Host "SQL  $file"
    Get-Content "sql\$file" -Raw | docker exec -i bikes-warehouse psql -U bikes -d bikes -v ON_ERROR_STOP=1 -q
    if ($LASTEXITCODE -ne 0) { throw "sql\$file failed" }
}

function Run-Py($module, $extra = @()) {
    Write-Host "PY   $module $extra"
    python -m $module @extra
    if ($LASTEXITCODE -ne 0) { throw "$module failed" }
}

docker compose up -d warehouse

# 1. Schemas and tables
"001_schemas.sql", "002_weather_schema.sql", "003_journeys_schema.sql",
"004_staging_journeys_schema.sql", "005_journeys_quality.sql" | ForEach-Object { Run-Sql $_ }

# 2. Extract: live docks, weather from June 2025, 12 months of journeys
Run-Py "src.extract.bikepoints"
Run-Py "src.extract.weather"
Run-Py "src.extract.weather" @("--start", "2025-06-01")
Run-Py "src.extract.journeys"

# 3. Transform: staging, then marts
"010_stage_dock_status.sql", "020_stage_weather.sql", "030_stage_journeys.sql",
"040_marts_hires_weather.sql", "050_marts_dock_hourly_hires.sql" | ForEach-Object { Run-Sql $_ }

# 4. Agent layer: read-only login, views and metric catalog (password from .env)
$agentPw = (Select-String '^AGENT_DB_PASSWORD=' .env).Line.Split('=', 2)[1]
Write-Host "SQL  070_agent_layer.sql"
Get-Content "sql\070_agent_layer.sql" -Raw | docker exec -i bikes-warehouse psql -U bikes -d bikes -v ON_ERROR_STOP=1 -q -v "agent_password=$agentPw"
if ($LASTEXITCODE -ne 0) { throw "sql\070_agent_layer.sql failed" }

# 5. Checks, analysis, forecast and charts
Run-Py "src.checks.journeys_check"
Run-Py "src.analysis.rain_effect"
Run-Py "src.analysis.rain_charts"
Run-Py "src.analysis.forecast_hires"
Run-Py "src.analysis.forecast_windows"
Run-Py "src.analysis.forecast_charts"

Write-Host "Done. Start Airflow with: docker compose up -d"
