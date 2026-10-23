"""Isolated English/SQLite experiment; never import the live application's clients."""
from pathlib import Path
import os
import sys
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
BASELINE = WORKSPACE / "baselines/probgate_ehrsql_2024"
DB = BASELINE / "upstream/src/data/mimic_iv/mimic_iv.sqlite"
load_dotenv(WORKSPACE / ".env")
MODEL = os.getenv("LLM_MODEL", "qwen/qwen3.8-27b")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
sys.path.insert(0, str(BASELINE))

