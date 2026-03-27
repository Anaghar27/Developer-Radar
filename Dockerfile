FROM apache/airflow:2.8.1-python3.11

ENV AIRFLOW__CORE__LOAD_EXAMPLES=false

COPY requirements-airflow.txt /tmp/requirements-airflow.txt

RUN pip install --no-cache-dir \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.8.1/constraints-3.11.txt" \
    -r /tmp/requirements-airflow.txt
