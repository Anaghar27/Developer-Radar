# DevPulse Platform

DevPulse is an end-to-end developer intelligence platform that ingests discussions from Reddit and Hacker News, classifies them with LLMs, builds analytical marts with dbt, and serves the results through a FastAPI backend and a Streamlit dashboard.

It is structured like a production-style data product rather than a single app: ingestion, enrichment, storage, transformation, retrieval, APIs, and UI are separate layers connected by scheduled workflows.

## What The Project Does

The platform answers questions like:

- What topics are developers discussing right now?
- Which tools are receiving positive vs negative sentiment?
- Where do Reddit and Hacker News disagree?
- Which topics suddenly spiked in volume?
- What grounded narrative report can be generated from the underlying posts?

## Full Project Flow

This is the core flow implemented in the repository.

### 1. Source ingestion

The ingestion layer pulls raw developer discussions from:

- Reddit via `praw` in [`ingestion/reddit_producer.py`](ingestion/reddit_producer.py)
- Hacker News via the Firebase API in [`ingestion/hackernews_producer.py`](ingestion/hackernews_producer.py)

Each producer:

- fetches recent posts
- applies a `since` cutoff based on the latest stored timestamp for that source
- maps the source payload into a shared raw-post schema
- publishes messages to the Kafka topic `raw_posts`

The ingestion DAG starts this process every 6 hours in [`pipeline/ingestion_dag.py`](pipeline/ingestion_dag.py).

### 2. Kafka consumption and raw storage

The Kafka consumer in [`ingestion/consumer.py`](ingestion/consumer.py) reads from `raw_posts` and processes each message in this order:

1. Coerce and normalize the incoming payload.
2. Validate that the post matches the expected schema.
3. Skip duplicates already present in PostgreSQL.
4. Insert valid posts into `raw_posts`.
5. Route invalid or failed records to the `failed_events` topic and `failed_events` table.

This gives the project a durable operational store in PostgreSQL before any LLM processing happens.

### 3. LLM classification

After raw posts are stored, the same ingestion DAG runs the classification step in [`processing/llm_processor.py`](processing/llm_processor.py).

For each unprocessed post, the processor:

- builds a classification prompt from title and body
- calls the configured LLM provider
- parses and validates structured JSON output
- writes the result to `processed_posts`

The expected enrichment output includes:

- `sentiment`
- `emotion`
- `topic`
- `tool_mentioned`
- `controversy_score`
- `reasoning`

There is provider failover built into the batch processor: it probes OpenRouter first and falls back to `gpt-4o-mini` for the full batch if needed.

### 4. Embedding generation

Once classification finishes, the DAG runs embeddings in [`processing/embedder.py`](processing/embedder.py).

For each post without an embedding:

- title and body are combined into one text input
- OpenAI embeddings are generated
- vectors are stored in `post_embeddings`

These embeddings support the semantic side of the RAG pipeline later.

### 5. Pipeline bookkeeping

The ingestion DAG also records operational metadata in PostgreSQL through [`storage/db_client.py`](storage/db_client.py), including:

- pipeline run start and end timestamps
- inserted vs failed counts
- batch ids used to scope processing and embeddings

This supports health checks and run monitoring.

### 6. dbt transformation layer

The second Airflow DAG in [`pipeline/transformation_dag.py`](pipeline/transformation_dag.py) waits for ingestion to finish, then runs dbt against the transformed warehouse layer.

dbt reads operational data and builds analytical models in DuckDB. The documented layers are described in [`transform/docs/overview.md`](transform/docs/overview.md):

- staging models: cleaned and typed source data
- intermediate models: joined and enriched records
- marts: dashboard-facing aggregates

The main marts used by the app are:

- `mart_daily_sentiment`
- `mart_tool_comparison`
- `mart_community_divergence`
- `mart_trending_topics`

The transformation DAG uses:

- `--full-refresh` on the midnight UTC run
- incremental dbt runs for the other 6-hour windows
- `dbt test` after each build

### 7. Cache invalidation and spike alerts

After dbt completes, the transformation DAG:

- calls `/cache/invalidate` on the API so stale Redis responses are cleared
- detects unusual topic-volume spikes from `mart_trending_topics`
- stores those spikes in the `alerts` table

This is what powers the alert section in the dashboard.

### 8. Weekly insight report generation

On Sundays, the transformation DAG runs the weekly reporting job through [`rag/corrective_rag.py`](rag/corrective_rag.py).

That flow is:

1. Expand the user query into related variants.
2. Retrieve candidate posts with hybrid search.
3. Grade relevance with the LLM in batches.
4. Retry with a wider search if relevance is too low.
5. Rerank results.
6. Generate a grounded report with citations.
7. Persist the report to `insight_reports`.

The same RAG pipeline also powers the on-demand query endpoint exposed by the API.

### 9. FastAPI serving layer

The API entrypoint is [`api/main.py`](api/main.py).

On startup it initializes:

- an async PostgreSQL pool
- Redis for caching
- CORS and rate limiting middleware

The main route groups are:

- auth and email verification in [`api/auth/router.py`](api/auth/router.py)
- health checks in [`api/routes/health.py`](api/routes/health.py)
- recent classified posts in [`api/routes/posts.py`](api/routes/posts.py)
- sentiment trends from DuckDB marts in [`api/routes/trends.py`](api/routes/trends.py)
- tool comparisons in [`api/routes/tools.py`](api/routes/tools.py)
- Reddit vs HN divergence in [`api/routes/community.py`](api/routes/community.py)
- volume spike alerts in [`api/routes/alerts.py`](api/routes/alerts.py)
- natural-language insight generation in [`api/routes/query.py`](api/routes/query.py)

The API mixes PostgreSQL and DuckDB on purpose:

- PostgreSQL is the operational system of record
- DuckDB serves analytical marts generated by dbt
- Redis caches expensive or repeated reads

### 10. Streamlit dashboard

The dashboard entrypoint is [`dashboard/app.py`](dashboard/app.py).

It uses the FastAPI backend as its data source and exposes these user-facing workflows:

- `Live Feed`: latest classified posts
- `Sentiment Trends`: daily aggregated sentiment over time
- `Tool Tracker`: side-by-side tool comparison
- `Community Comparison`: Reddit vs Hacker News divergence
- `Intelligence Reports`: natural-language RAG reports plus volume spike alerts

Authentication happens through the API first, then the dashboard stores the JWT in Streamlit session state and browser cookies for the session experience.

## Architecture Summary

At a high level, the system looks like this:

```text
Reddit + Hacker News
        |
        v
   Kafka raw_posts
        |
        v
 PostgreSQL raw_posts
        |
        +--> LLM classification --> processed_posts
        |
        +--> Embedding generation --> post_embeddings
        |
        v
   dbt transformations
        |
        v
 DuckDB analytical marts
        |
        +--> FastAPI endpoints
        |       |
        |       +--> Redis cache
        |       +--> Streamlit dashboard
        |
        +--> Alert detection
        +--> Corrective RAG reports
```

## Repository Layout

```text
api/          FastAPI app, auth, caching, and data routes
dashboard/    Streamlit frontend and UI tabs
ingestion/    Reddit/Hacker News producers and Kafka consumer
pipeline/     Airflow DAGs and downstream orchestration logic
processing/   LLM classification, prompts, validation, embeddings
rag/          Hybrid retrieval, reranking, corrective RAG reporting
storage/      PostgreSQL access layer and CRUD helpers
transform/    dbt project and warehouse documentation
tests/        Unit and integration-style test coverage
```

## Local Environment

Environment variables are defined in [`.env.example`](.env.example). The main services and credentials expected by the project are:

- Reddit API credentials
- one or more LLM provider keys
- PostgreSQL
- Kafka
- Redis
- JWT/auth settings
- dbt / DuckDB paths
- Airflow settings

Typical setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

If you are running Airflow- or dbt-specific environments separately, the repo also includes:

- [`requirements-airflow.txt`](requirements-airflow.txt)
- [`requirements-dbt.txt`](requirements-dbt.txt)

## Running The Project

### Start the API

```bash
uvicorn api.main:app --reload
```

### Start the dashboard

```bash
streamlit run dashboard/app.py
```

### Run the LLM processor manually

```bash
python -m processing.llm_processor
```

### Run embeddings manually

```bash
python -m processing.embedder
```

### Run dbt manually

```bash
cd transform
dbt run
dbt test
```

### Run tests

```bash
pytest
```

## dbt Documentation

Live dbt docs are published on every push to `main`:

https://anaghar27.github.io/Devpulse-Platform/

They include lineage, model descriptions, and test coverage for the transformation layer.

## Why The Design Is Split This Way

The project intentionally separates concerns:

- Kafka decouples collection from storage.
- PostgreSQL keeps a reliable operational record of raw and enriched posts.
- dbt + DuckDB provide fast analytical models without overloading the transactional store.
- Redis reduces repeated API cost and latency.
- FastAPI centralizes auth, caching, and query logic.
- Streamlit provides a fast way to surface intelligence to end users.
- Corrective RAG adds grounded narrative reporting on top of the same underlying data.

In short: DevPulse is not just a dashboard. It is a scheduled developer-intelligence pipeline with a serving layer on top.
