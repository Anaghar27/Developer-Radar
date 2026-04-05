"""Tests for the ingestion Airflow DAG shape."""

from unittest.mock import patch

from pipeline.ingestion_dag import dag


def test_dag_id():
    assert dag.dag_id == "ingestion_pipeline"


def test_dag_tasks():
    expected_tasks = {
        "ingest_task",
        "consume_task",
        "process_task",
        "embed_task",
        "write_pipeline_run_task",
    }
    actual_tasks = {t.task_id for t in dag.tasks}
    assert actual_tasks == expected_tasks


def test_dag_task_dependencies():
    from pipeline.ingestion_dag import dag

    task_dict = {t.task_id: t for t in dag.tasks}

    assert "consume_task" in {
        t.task_id for t in task_dict["ingest_task"].downstream_list
    }
    assert "process_task" in {
        t.task_id for t in task_dict["consume_task"].downstream_list
    }
    assert "embed_task" in {
        t.task_id for t in task_dict["process_task"].downstream_list
    }
    assert "write_pipeline_run_task" in {
        t.task_id for t in task_dict["embed_task"].downstream_list
    }


def test_run_processing_uses_airflow_run_id():
    from pipeline.ingestion_dag import _run_processing

    with patch("processing.llm_processor.process_batch") as mock_process_batch:
        _run_processing(run_id="manual__2026-04-05T20:00:00+00:00")

    mock_process_batch.assert_called_once_with(
        limit=1000,
        ingest_batch_id="manual__2026-04-05T20:00:00+00:00",
    )


def test_run_embeddings_uses_airflow_run_id():
    from pipeline.ingestion_dag import _run_embeddings

    with patch("processing.embedder.run_embeddings") as mock_run_embeddings:
        _run_embeddings(run_id="manual__2026-04-05T20:00:00+00:00")

    mock_run_embeddings.assert_called_once_with(
        limit=1000,
        ingest_batch_id="manual__2026-04-05T20:00:00+00:00",
    )
