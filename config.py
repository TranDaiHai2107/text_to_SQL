"""Shared paths and environment-backed settings for the project."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

SCHEMA_FILE = BASE_DIR / "mimic_schema.json"
EXAMPLES_FILE = BASE_DIR / "mimic_examples.json"
TEST_FILE = BASE_DIR / "test_dataset.json"
RESULTS_FILE = BASE_DIR / "evaluate_results.json"
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", str(BASE_DIR / "mimic_chroma_db")))
MIMIC_DATA_DIR = Path(os.getenv("MIMIC_DATA_DIR", str(BASE_DIR / "mimic-iv-3.1")))

QUERY_TIMEOUT_MS = max(1_000, int(os.getenv("QUERY_TIMEOUT_MS", "15000")))
LOCK_TIMEOUT_MS = max(100, int(os.getenv("LOCK_TIMEOUT_MS", "2000")))
MAX_QUERY_ROWS = max(1, int(os.getenv("MAX_QUERY_ROWS", "1000")))
MAX_EVAL_ROWS = max(MAX_QUERY_ROWS, int(os.getenv("MAX_EVAL_ROWS", "10000")))


def database_url(*, loader: bool = False) -> URL:
    """Build a safely escaped SQLAlchemy URL for runtime or data loading."""
    prefix = "DB_LOADER_" if loader else "DB_"
    default_user = "postgres" if loader else "mimic_reader"
    user = os.getenv(f"{prefix}USER", default_user)
    password = os.getenv(
        f"{prefix}PASS",
        os.getenv("DB_PASS", "") if loader else "",
    )
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    database = os.getenv("DB_NAME", "mimiciv")
    return URL.create(
        "postgresql+psycopg2",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database,
    )
