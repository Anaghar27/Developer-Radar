"""Ingestion-only Airflow DAG for the developer sentiment pipeline."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

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


def _produce(**context) -> int:
    from ingestion import hackernews_producer, reddit_producer
    from storage.db_client import get_latest_ingested_timestamp, insert_pipeline_run

    batch_id = context["run_id"]
    ti = context.get("ti")
    start_time = datetime.now(UTC)
    insert_pipeline_run(
        run_id=batch_id,
        dag_id="ingestion_pipeline",
        start_time=start_time,
    )

    reddit_since = get_latest_ingested_timestamp("reddit")
    hn_since = get_latest_ingested_timestamp("hackernews")

    r_count = reddit_producer.run(ingest_batch_id=batch_id, since=reddit_since)
    hn_count = hackernews_producer.run(ingest_batch_id=batch_id, since=hn_since)
    total_published = (r_count or 0) + (hn_count or 0)
    logging.info("Published %s messages to Kafka", total_published)
    if ti is not None:
        ti.xcom_push(key="pipeline_start_time", value=start_time.isoformat())
        ti.xcom_push(key="posts_published", value=total_published)
    return total_published


def _consume(**context):
    batch_id = context["run_id"]
    ti = context.get("ti")
    from ingestion.consumer import consume_failed_events
    from ingestion.consumer import run as consume

    summary = consume(ingest_batch_id=batch_id)
    logging.info(f"Consumer summary: {summary}")
    dl_count = consume_failed_events(ingest_batch_id=batch_id)
    logging.info(f"Dead letter events written: {dl_count}")
    if ti is not None:
        ti.xcom_push(key="consume_summary", value=summary)
    return summary


def _run_processing(**context) -> int:
    """Run LLM processing over a batch of posts."""
    ingest_batch_id = context["run_id"]
    ti = context.get("ti")
    try:
        from processing import llm_processor

        log.info(
            "Starting process_task - batch_id=%s time=%s",
            ingest_batch_id,
            datetime.now(UTC).isoformat(),
        )
        result = llm_processor.process_batch(
            limit=PIPELINE_BATCH_SIZE,
            ingest_batch_id=ingest_batch_id,
        )
        classified = result if isinstance(result, int) else 0
        if ti is not None:
            ti.xcom_push(key="posts_classified", value=classified)
        log.info("Classified %s posts", classified)
        log.info(
            "Summary - processed a batch of up to %s posts for batch_id=%s",
            PIPELINE_BATCH_SIZE,
            ingest_batch_id,
        )
        log.info("Finished process_task - %s", datetime.now(UTC).isoformat())
        return classified
    except Exception:
        log.exception("Task process_task failed")
        raise


def _run_embeddings(**context) -> None:
    """Run embedding generation over a batch of posts."""
    ingest_batch_id = context["run_id"]
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
    ti = context["ti"]
    end_time = datetime.now(UTC)
    consume_summary = ti.xcom_pull(task_ids="consume_task", key="consume_summary") or {}
    posts_classified = ti.xcom_pull(task_ids="process_task", key="posts_classified") or 0

    posts_ingested = consume_summary.get("inserted", 0)
    posts_failed = consume_summary.get("failed", 0)
    duplicates = consume_summary.get("duplicates", 0)
    total_attempted = posts_ingested + posts_failed
    error_rate = round(posts_failed / total_attempted, 4) if total_attempted > 0 else 0.0

    start_time_raw = ti.xcom_pull(task_ids="ingest_task", key="pipeline_start_time")
    start_time = (
        datetime.fromisoformat(start_time_raw)
        if start_time_raw
        else context["data_interval_start"]
    )
    duration = (end_time - start_time).total_seconds()

    update_pipeline_run(
        run_id=run_id,
        end_time=end_time,
        duration_seconds=round(duration, 2),
        posts_ingested=posts_ingested,
        posts_classified=posts_classified,
        posts_failed=posts_failed,
        error_rate=error_rate,
    )
    logging.info(
        "Pipeline run %s recorded - ingested=%s, classified=%s, failed=%s, "
        "duplicates=%s, error_rate=%.4f, duration=%.1fs",
        run_id,
        posts_ingested,
        posts_classified,
        posts_failed,
        duplicates,
        error_rate,
        duration,
    )


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
    dag=dag,
)

embed_task = PythonOperator(
    task_id="embed_task",
    python_callable=_run_embeddings,
    dag=dag,
)

write_pipeline_run_task = PythonOperator(
    task_id="write_pipeline_run_task",
    python_callable=_write_pipeline_run,
    dag=dag,
)

ingest_task >> consume_task >> process_task >> embed_task >> write_pipeline_run_task
