"""Minimal DAG to verify the Airflow install (Medha monorepo)."""

from __future__ import annotations

from datetime import datetime

from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG


def _hello() -> None:
    print("OK — Medha Airflow example task")


with DAG(
    dag_id="example_medha_hello",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["medha", "example"],
) as dag:
    PythonOperator(task_id="hello", python_callable=_hello)
