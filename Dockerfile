FROM apache/airflow:2.8.1-python3.11

ENV AIRFLOW__CORE__LOAD_EXAMPLES=false

COPY requirements-airflow.txt /tmp/requirements-airflow.txt
COPY requirements-dbt.txt /tmp/requirements-dbt.txt

# Install Airflow-compatible packages with official constraints
RUN pip install --no-cache-dir \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.8.1/constraints-3.11.txt" \
    -r /tmp/requirements-airflow.txt

# Install dbt separately — dbt-core requires sqlparse>=0.5.0 which conflicts
# with the Airflow 2.8.1 constraint pinning sqlparse==0.4.4
RUN pip install --no-cache-dir -r /tmp/requirements-dbt.txt
