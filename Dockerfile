FROM apache/airflow:2.10.4-python3.11

ENV AIRFLOW__CORE__LOAD_EXAMPLES=false

COPY requirements-airflow.txt /tmp/requirements-airflow.txt
COPY requirements-dbt.txt /tmp/requirements-dbt.txt

# Install Airflow-compatible packages with official constraints
RUN pip install --no-cache-dir \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.4/constraints-3.11.txt" \
    -r /tmp/requirements-airflow.txt

# Install dbt separately to avoid constraint conflicts
RUN pip install --no-cache-dir -r /tmp/requirements-dbt.txt
