"""Docker lifecycle and metadata checks; never launch an experiment implicitly."""
from __future__ import annotations

import json
from pathlib import Path
import platform
import signal
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parent
STATUS = Path("/tmp/probgate-ready.json")


def database_path():
    manifest = json.loads((ROOT / "source_manifest.json").read_text(encoding="utf-8"))
    return ROOT / manifest["database_path"]


def inspect_runtime():
    db = database_path()
    connection = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        if len(tables) != 17:
            raise RuntimeError("Expected the pinned 17-table ProbGate database")
        count = connection.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
        return {"ready": True, "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
            "database": str(db), "database_uri_mode": "ro", "query_only": connection.execute("PRAGMA query_only").fetchone()[0],
            "table_count": len(tables), "patient_count": count, "benchmark_clock": "2100-12-31 23:59:00",
            "clock_mechanism": "upstream post_process_sql, not operating-system clock",
            "training_started": False, "inference_started": False, "benchmark_scoring_started": False}
    finally:
        connection.close()


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if command == "health":
        if not STATUS.is_file() or not json.loads(STATUS.read_text())["ready"]:
            raise RuntimeError("Container initialization not complete")
        connection = sqlite3.connect(database_path().resolve().as_uri() + "?mode=ro", uri=True)
        try:
            connection.execute("SELECT 1").fetchone()
        finally:
            connection.close()
    elif command in {"serve", "check"}:
        from reproduce import verify
        verify()
        status = inspect_runtime()
        print(json.dumps(status, ensure_ascii=False, indent=2), flush=True)
        if command == "serve":
            STATUS.write_text(json.dumps(status), encoding="utf-8")
            # SIGTERM is handled so Docker stop does not need to kill the worker.
            signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
            while True:
                time.sleep(30)
    else:
        # Explicit commands only, e.g. `docker compose exec ... python reproduce.py`.
        raise ValueError("Use serve, check or health; experiments run through reproduce.py explicitly")


if __name__ == "__main__":
    main()
