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
    is_paused_upon_creation=False,
    tags=["devpulse", "transformation"],
)

def _ingestion_execution_date(execution_date, **kwargs):
    """
    Resolve which ingestion_pipeline execution date to wait on.

    - Scheduled runs: execution_date falls on a 6-hour boundary (00/06/12/18 UTC,
      minute=0, second=0). Use exact match so the sensor waits for the ingestion
      run that belongs to the same slot — not a stale previous run.

    - Manual triggers: execution_date is an arbitrary timestamp. Fall back to the
      most recent successful ingestion run so the pipeline can proceed immediately.
    """
    from airflow.models import DagRun
    from airflow.utils.state import State

    is_scheduled = (
        execution_date.minute == 0
        and execution_date.second == 0
        and execution_date.microsecond == 0
        and execution_date.hour % 6 == 0
    )

    if is_scheduled:
        return execution_date

    # Manual trigger: find the most recent successful ingestion run
    runs = DagRun.find(dag_id="ingestion_pipeline", state=State.SUCCESS)
    if not runs:
        return execution_date
    return max(r.execution_date for r in runs)

wait_for_ingestion = ExternalTaskSensor(
    task_id="wait_for_ingestion",
    external_dag_id="ingestion_pipeline",
    external_task_id="write_pipeline_run_task",
    allowed_states=["success"],
    failed_states=["failed", "skipped"],
    execution_date_fn=_ingestion_execution_date,
    mode="poke",
    poke_interval=30,
    timeout=3600,
    dag=dag,
)


def _run_dbt(**context):
    """Run all dbt models."""
    dbt_dir = os.getenv("DBT_PROJECT_DIR", os.path.join(os.path.dirname(__file__), "..", "transform"))
    result = subprocess.run(
        ["dbt", "run", "--profiles-dir", ".", "--no-use-colors"],
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
    dbt_dir = os.getenv("DBT_PROJECT_DIR", os.path.join(os.path.dirname(__file__), "..", "transform"))
    result = subprocess.run(
        ["dbt", "test", "--profiles-dir", ".", "--no-use-colors"],
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
    Invalidate Redis cache by calling POST /cache/invalidate on the FastAPI service.
    Uses the INTERNAL_API_KEY for authentication.
    """
    import requests
    import os

    api_url = os.getenv("API_BASE_URL", "http://localhost:8000")
    internal_key = os.getenv("INTERNAL_API_KEY", "")

    if not internal_key:
        logging.warning("INTERNAL_API_KEY not set — skipping cache invalidation")
        return

    try:
        response = requests.post(
            f"{api_url}/cache/invalidate",
            headers={"X-API-Key": internal_key},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            logging.info(f"Cache invalidated — {data.get('keys_deleted', 0)} keys deleted")
        else:
            logging.warning(f"Cache invalidation returned {response.status_code}: {response.text}")
    except requests.exceptions.ConnectionError:
        logging.warning("FastAPI not reachable — skipping cache invalidation (API may not be running)")
    except Exception as e:
        logging.warning(f"Cache invalidation failed: {e}")


invalidate_cache_task = PythonOperator(
    task_id="invalidate_cache_task",
    python_callable=_invalidate_cache,
    dag=dag,
)


def _detect_alerts(**context):
    """Detect volume spikes from mart_trending_topics and write to alerts table."""
    from pipeline.aggregator import detect_volume_spikes
    from storage.db_client import insert_alert

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
    """Only proceed to weekly report on Sundays (UTC)."""
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
