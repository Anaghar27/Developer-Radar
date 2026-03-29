from datetime import datetime, timezone
from airflow import DAG
from airflow.operators.python import PythonOperator, ShortCircuitOperator
from airflow.sensors.external_task import ExternalTaskSensor
import logging
import subprocess
import os

default_args = {
    "owner": "devpulse",
    "retries": 1,
    "retry_delay": 300,
}

dag = DAG(
    dag_id="transformation_pipeline",
    default_args=default_args,
    schedule_interval="0 */6 * * *",   # same schedule as DAG 1
    start_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    catchup=False,
    tags=["devpulse", "transformation"],
)

wait_for_ingestion = ExternalTaskSensor(
    task_id="wait_for_ingestion",
    external_dag_id="ingestion_pipeline",
    external_task_id="write_pipeline_run_task",
    allowed_states=["success"],
    failed_states=["failed", "skipped"],
    execution_delta=None,
    mode="poke",
    poke_interval=30,
    timeout=3600,
    dag=dag,
)


def _run_dbt(**context):
    """Run all dbt models."""
    dbt_dir = os.path.join(os.path.dirname(__file__), "..", "transform")
    result = subprocess.run(
        ["dbt", "run", "--profiles-dir", "."],
        cwd=dbt_dir,
        capture_output=True,
        text=True,
    )
    logging.info(result.stdout)
    if result.returncode != 0:
        logging.error(result.stderr)
        raise Exception(f"dbt run failed:\n{result.stderr}")
    logging.info("dbt run completed successfully")


run_dbt_task = PythonOperator(
    task_id="run_dbt_task",
    python_callable=_run_dbt,
    dag=dag,
)


def _test_dbt(**context):
    """Run dbt tests — fail the task if any test fails."""
    dbt_dir = os.path.join(os.path.dirname(__file__), "..", "transform")
    result = subprocess.run(
        ["dbt", "test", "--profiles-dir", "."],
        cwd=dbt_dir,
        capture_output=True,
        text=True,
    )
    logging.info(result.stdout)
    if result.returncode != 0:
        logging.error(result.stderr)
        raise Exception(f"dbt test failed:\n{result.stderr}")
    logging.info("dbt test passed successfully")


test_dbt_task = PythonOperator(
    task_id="test_dbt_task",
    python_callable=_test_dbt,
    dag=dag,
)


def _invalidate_cache(**context):
    """
    Invalidate Redis cache after dbt run.
    Stub for now — full implementation in Day 9 when FastAPI + Redis are wired.
    """
    logging.info("Cache invalidation stub — Redis not yet wired. Skipping.")


invalidate_cache_task = PythonOperator(
    task_id="invalidate_cache_task",
    python_callable=_invalidate_cache,
    dag=dag,
)


def _detect_alerts(**context):
    """Detect volume spikes from mart_trending_topics and write to alerts table."""
    from pipeline.aggregator import detect_volume_spikes
    from storage.db_client import insert_alert
    from datetime import datetime, timezone

    spikes = detect_volume_spikes()
    for spike in spikes:
        insert_alert(
            topic=spike["topic"],
            today_count=spike["today_count"],
            rolling_avg=float(spike["rolling_avg"]),
            pct_increase=float(spike["pct_increase"]),
        )
        logging.info(f"Alert inserted for topic: {spike['topic']} ({spike['pct_increase']}% spike)")

    logging.info(f"Alert detection complete — {len(spikes)} spikes found")


detect_alerts_task = PythonOperator(
    task_id="detect_alerts_task",
    python_callable=_detect_alerts,
    dag=dag,
)


def _is_sunday(**context):
    """Only proceed to weekly report on Sundays."""
    return datetime.now(timezone.utc).weekday() == 6


is_sunday_task = ShortCircuitOperator(
    task_id="is_sunday_task",
    python_callable=_is_sunday,
    dag=dag,
)


def _weekly_report(**context):
    """
    Generate weekly insight report via Corrective RAG.
    Stub for now — full implementation in Day 10 when RAG is wired.
    """
    logging.info("Weekly report stub — RAG not yet wired. Skipping.")


weekly_report_task = PythonOperator(
    task_id="weekly_report_task",
    python_callable=_weekly_report,
    dag=dag,
)

wait_for_ingestion >> run_dbt_task >> test_dbt_task >> invalidate_cache_task >> detect_alerts_task >> is_sunday_task >> weekly_report_task
