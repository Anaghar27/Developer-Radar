FROM apache/airflow:2.8.1-python3.11

ENV AIRFLOW__CORE__LOAD_EXAMPLES=false

COPY requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir -r /tmp/requirements.txt
