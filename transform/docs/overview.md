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

## Incremental Strategy

All 4 mart models use incremental materialization:

| Model | unique_key | Lookback |
|-------|-----------|----------|
| mart_daily_sentiment | post_date + topic + tool + source | New dates only |
| mart_tool_comparison | post_date + tool + source | New dates only |
| mart_community_divergence | post_date + topic | New dates only |
| mart_trending_topics | post_date + topic | Last 8 days (7-day rolling window) |

**Why incremental?**
- Full refresh rebuilds ALL historical data on every 6-hour DAG run — wasteful at scale
- Incremental processes only new dates — 10-100x faster for mature datasets
- mart_trending_topics uses 8-day lookback to ensure rolling averages are accurate

**First run:** Use `dbt run --full-refresh` to build complete history.
**Subsequent runs:** `dbt run` processes only new data automatically.

## Live Documentation
dbt docs are automatically deployed to GitHub Pages on every push to main.

**Live docs:** https://anaghar27.github.io/Devpulse-Platform/

The docs include:
- Full lineage graph (source → staging → intermediate → marts)
- Column-level descriptions for all 7 models
- Test results and coverage
- Source freshness checks
