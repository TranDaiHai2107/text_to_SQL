"""Schema-aware SQLite validation and read-only execution for this benchmark."""
from contextlib import closing
from pathlib import Path
import sqlite3
import time
from sqlglot import exp, parse
from settings import DB
from baseline_core import post_process_sql


def clean_sql(raw):
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip()=="```" else lines[1:]).strip()
    if text.casefold() == "null":
        return "null"
    return post_process_sql(text)


def validate(sql, db=DB):
    try:
        trees = [x for x in parse(sql, read="sqlite") if x is not None]
        if len(trees) != 1 or not isinstance(trees[0], exp.Query):
            return "Only a single read-only SELECT/WITH query is allowed"
        tree = trees[0]
        if any(tree.find(t) for t in (exp.Into, exp.Insert, exp.Update, exp.Delete, exp.Create,
                                      exp.Drop, exp.Alter, exp.Merge, exp.Lock)):
            return "Mutating/locking statements are forbidden"
        for f in tree.find_all(exp.Func):
            name = f.name.lower() if isinstance(f, exp.Anonymous) else f.sql_name().lower()
            if name in {"load_extension", "writefile", "readfile"}:
                return "External/file functions are forbidden"
        with closing(sqlite3.connect(Path(db).resolve().as_uri()+"?mode=ro", uri=True)) as con:
            con.execute("PRAGMA query_only=ON")
            con.execute("EXPLAIN QUERY PLAN "+sql).fetchall()
        return None
    except Exception as error:
        return str(error).splitlines()[0][:500]


def execute(sql, db=DB, timeout_s=30):
    error = validate(sql, db)
    if error:
        raise ValueError(error)
    with closing(sqlite3.connect(Path(db).resolve().as_uri()+"?mode=ro", uri=True)) as con:
        con.execute("PRAGMA query_only=ON")
        deadline = time.monotonic()+timeout_s
        con.set_progress_handler(lambda: int(time.monotonic()>deadline), 10000)
        rows = con.execute(sql).fetchmany(100001)
        if len(rows) > 100000:
            raise ValueError("Operational result budget exceeded (100000 rows)")
        return rows


def outcome(sql, db=DB):
    if sql == "null":
        return {"valid": False, "abstained": True, "empty": None, "error": None}
    try:
        rows = execute(sql, db)
        return {"valid": True, "abstained": False, "empty": not rows, "error": None}
    except Exception as error:
        return {"valid": False, "abstained": False, "empty": None, "error": str(error)[:500]}

