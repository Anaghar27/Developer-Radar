# DevPulse dbt Project

## Overview
dbt transformation layer for DevPulse — reads from PostgreSQL operational store,
models data into DuckDB analytical warehouse.

## Model Layers
- **Staging**: Clean, typed, renamed columns from raw PostgreSQL sources
- **Intermediate**: Joined and enriched models with derived fields
- **Marts**: Aggregated analytical models for dashboard consumption

## Running
```bash
cd transform
dbt debug        # verify connections
dbt run          # build all models
dbt test         # run all tests
dbt docs generate && dbt docs serve   # view documentation
```
