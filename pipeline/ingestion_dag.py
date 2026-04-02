"""Ingestion-only Airflow DAG for the developer sentiment pipeline."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta, timezone

try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
except ModuleNotFoundError:
    class DAG:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            self.dag_id = args[0] if args else kwargs.get("dag_id")
            self.tasks = []

    class PythonOperator:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            self.task_id = kwargs.get("task_id")
            self.downstream_list: list = []
            dag = kwargs.get("dag")
            if dag is not None and hasattr(dag, "tasks"):
                dag.tasks.append(self)

        def __rshift__(self, other):
            self.downstream_list.append(other)
            return other


log = logging.getLogger(__name__)
PIPELINE_BATCH_SIZE = 1000

default_args = {
    "owner": "devpulse",
    "retries": 1,
    "retry_delay": timedelta(seconds=300),
}

dag = DAG(
    dag_id="ingestion_pipeline",
    default_args=default_args,
    schedule_interval="0 */6 * * *",
    start_date=datetime(2024, 1, 1, tzinfo=UTC),
    catchup=False,
    tags=["devpulse", "ingestion"],
)


def _produce(**context) -> None:
    from ingestion import hackernews_producer, reddit_producer
    from storage.db_client import get_latest_ingested_timestamp, insert_pipeline_run

    batch_id = context["run_id"]
    insert_pipeline_run(
        run_id=batch_id,
        dag_id="ingestion_pipeline",
        start_time=datetime.now(UTC),
    )

    reddit_since = get_latest_ingested_timestamp("reddit")
    hn_since = get_latest_ingested_timestamp("hackernews")

    r_count = reddit_producer.run(ingest_batch_id=batch_id, since=reddit_since)
    hn_count = hackernews_producer.run(ingest_batch_id=batch_id, since=hn_since)
    logging.info(f"Published {r_count + hn_count} messages to Kafka")


def _consume(**context):
    batch_id = context["run_id"]
    from ingestion.consumer import consume_failed_events
    from ingestion.consumer import run as consume

    summary = consume(ingest_batch_id=batch_id)
    logging.info(f"Consumer summary: {summary}")
    dl_count = consume_failed_events(ingest_batch_id=batch_id)
    logging.info(f"Dead letter events written: {dl_count}")
    return summary


def _run_processing(ingest_batch_id: str) -> None:
    """Run LLM processing over a batch of posts."""
    try:
        import os

        from llm_client import active_provider
        from processing import llm_processor

        classification_provider = os.getenv("CLASSIFICATION_PROVIDER", "openrouter")
        log.info(
            "Starting process_task - model=%s batch_id=%s time=%s",
            active_provider(classification_provider),
            ingest_batch_id,
            datetime.now(UTC).isoformat(),
        )
        llm_processor.process_batch(limit=PIPELINE_BATCH_SIZE, ingest_batch_id=ingest_batch_id)
        log.info(
            "Summary - processed a batch of up to %s posts for batch_id=%s",
            PIPELINE_BATCH_SIZE,
            ingest_batch_id,
        )
        log.info("Finished process_task - %s", datetime.now(UTC).isoformat())
    except Exception:
        log.exception("Task process_task failed")
        raise


def _run_embeddings(ingest_batch_id: str) -> None:
    """Run embedding generation over a batch of posts."""
    try:
        from processing import embedder

        log.info("Starting embed_task - %s", datetime.now(UTC).isoformat())
        embedder.run_embeddings(limit=PIPELINE_BATCH_SIZE, ingest_batch_id=ingest_batch_id)
        log.info(
            "Summary - generated embeddings for a batch of up to %s posts for batch_id=%s",
            PIPELINE_BATCH_SIZE,
            ingest_batch_id,
        )
        log.info("Finished embed_task - %s", datetime.now(UTC).isoformat())
    except Exception:
        log.exception("Task embed_task failed")
        raise


def _write_pipeline_run(**context):
    from storage.db_client import update_pipeline_run

    run_id = context["run_id"]
    start_time = context["data_interval_start"]
    end_time = datetime.now(UTC)
    duration = (end_time - start_time).total_seconds()

    ti = context["ti"]
    consume_summary = ti.xcom_pull(task_ids="consume_task") or {}

    update_pipeline_run(
        run_id=run_id,
        end_time=end_time,
        duration_seconds=duration,
        posts_ingested=consume_summary.get("inserted", 0),
        posts_classified=consume_summary.get("inserted", 0),
        posts_failed=consume_summary.get("failed", 0),
        error_rate=0.0,
    )
    logging.info(f"Pipeline run {run_id} recorded.")


ingest_task = PythonOperator(
    task_id="ingest_task",
    python_callable=_produce,
    dag=dag,
)

consume_task = PythonOperator(
    task_id="consume_task",
    python_callable=_consume,
    dag=dag,
)

process_task = PythonOperator(
    task_id="process_task",
    python_callable=_run_processing,
    op_kwargs={"ingest_batch_id": None},
    dag=dag,
)

embed_task = PythonOperator(
    task_id="embed_task",
    python_callable=_run_embeddings,
    op_kwargs={"ingest_batch_id": None},
    dag=dag,
)

write_pipeline_run_task = PythonOperator(
    task_id="write_pipeline_run_task",
    python_callable=_write_pipeline_run,
    dag=dag,
)

ingest_task >> consume_task >> process_task >> embed_task >> write_pipeline_run_task
