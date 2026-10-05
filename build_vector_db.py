"""Build verified Chroma collections for the MIMIC-IV RAG pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import chromadb
import pandas as pd
from sqlalchemy import create_engine
from sqlglot import parse_one

from config import CHROMA_DIR, EXAMPLES_FILE, MIMIC_DATA_DIR, SCHEMA_FILE, TEST_FILE, database_url
from embedding_config import DEFAULT_EMBEDDING_MODEL, get_embedding_function


sys.stdout.reconfigure(encoding="utf-8", errors="replace")
client = chromadb.PersistentClient(path=str(CHROMA_DIR))
engine = create_engine(database_url(), pool_pre_ping=True, connect_args={"connect_timeout": 5})

COLLECTIONS = ("icd_dictionary", "schema_dictionary", "sql_examples", "sql_examples_eval")

ICD_VI_SYNONYMS = {
    ("486", 9): "viêm phổi pneumonia",
    ("J189", 10): "viêm phổi pneumonia",
    ("4280", 9): "suy tim heart failure",
    ("I509", 10): "suy tim heart failure",
    ("25000", 9): "đái tháo đường tiểu đường type 2 diabetes",
    ("E119", 10): "đái tháo đường tiểu đường type 2 diabetes",
    ("4011", 9): "tăng huyết áp cao huyết áp hypertension",
    ("I10", 10): "tăng huyết áp cao huyết áp hypertension",
    ("0389", 9): "nhiễm khuẩn huyết sepsis",
    ("A419", 10): "nhiễm khuẩn huyết sepsis",
    ("43491", 9): "đột quỵ nhồi máu não stroke",
    ("I639", 10): "đột quỵ nhồi máu não stroke",
    ("5849", 9): "suy thận cấp acute kidney injury",
    ("N179", 10): "suy thận cấp acute kidney injury",
    ("496", 9): "bệnh phổi tắc nghẽn mạn tính COPD",
    ("J449", 10): "bệnh phổi tắc nghẽn mạn tính COPD",
}


def _source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _file_signature(path: Path) -> str:
    stat = path.stat()
    return f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}"


def _canonical_sql(sql: str) -> str:
    return parse_one(sql, read="postgres").sql(
        dialect="postgres",
        pretty=False,
        normalize=True,
    )


def _delete_if_exists(name: str) -> None:
    try:
        client.delete_collection(name)
    except Exception:
        pass


def _atomic_build(
    name: str,
    expected_count: int,
    source_hash: str,
    populate: Callable,
) -> None:
    """Populate a temporary collection and swap it in only after validation."""
    temp_name = f"tmp_{name}_{uuid.uuid4().hex[:8]}"
    collection = client.create_collection(
        name=temp_name,
        metadata={
            "hnsw:space": "cosine",
            "embedding_model": DEFAULT_EMBEDDING_MODEL,
            "expected_count": expected_count,
            "source_hash": source_hash,
        },
        embedding_function=get_embedding_function(),
    )
    try:
        populate(collection)
        actual = collection.count()
        if actual != expected_count:
            raise RuntimeError(f"{name}: expected {expected_count} records, built {actual}")
        _delete_if_exists(name)
        collection.modify(name=name)
    except Exception:
        _delete_if_exists(temp_name)
        raise
    print(f"  [OK] {name}: {expected_count} records")


def _load_icd_from_csv() -> tuple[pd.DataFrame, str]:
    diagnoses_path = MIMIC_DATA_DIR / "hosp" / "diagnoses_icd.csv.gz"
    dictionary_path = MIMIC_DATA_DIR / "hosp" / "d_icd_diagnoses.csv.gz"
    counts: Counter = Counter()
    for chunk in pd.read_csv(
        diagnoses_path,
        compression="gzip",
        usecols=["icd_code", "icd_version"],
        chunksize=500_000,
        dtype={"icd_code": str, "icd_version": int},
    ):
        counts.update(zip(chunk["icd_code"], chunk["icd_version"]))
    usage = pd.DataFrame(
        [(code, version, count) for (code, version), count in counts.items()],
        columns=["icd_code", "icd_version", "use_count"],
    )
    dictionary = pd.read_csv(
        dictionary_path,
        compression="gzip",
        usecols=["icd_code", "icd_version", "long_title"],
        dtype={"icd_code": str, "icd_version": int},
    )
    frame = usage.merge(dictionary, on=["icd_code", "icd_version"], how="inner")
    frame = frame.dropna(subset=["long_title"]).sort_values(
        ["use_count", "icd_version", "icd_code"],
        ascending=[False, False, True],
    )
    signature = hashlib.sha256(
        f"{_file_signature(diagnoses_path)}:{_file_signature(dictionary_path)}".encode()
    ).hexdigest()[:16]
    return frame, signature


def build_icd_collection(source: str = "database") -> None:
    print("\nBuilding icd_dictionary...")
    sql = """
        SELECT d.icd_code, d.icd_version, d.long_title, COUNT(*) AS use_count
        FROM diagnoses_icd x
        JOIN d_icd_diagnoses d
          ON x.icd_code = d.icd_code AND x.icd_version = d.icd_version
        WHERE d.long_title IS NOT NULL
        GROUP BY d.icd_code, d.icd_version, d.long_title
        ORDER BY COUNT(*) DESC, d.icd_version DESC, d.icd_code
    """
    if source == "csv":
        frame, db_signature = _load_icd_from_csv()
    else:
        frame = pd.read_sql(sql, engine)
        db_signature = hashlib.sha256(
            "\n".join(
                f"{row.icd_version}:{row.icd_code}:{row.use_count}"
                for row in frame.itertuples()
            ).encode()
        ).hexdigest()[:16]
    frame = frame.head(10_000).reset_index(drop=True)
    db_signature = hashlib.sha256(
        f"{db_signature}:{sorted(ICD_VI_SYNONYMS.items())}".encode()
    ).hexdigest()[:16]

    def populate(collection) -> None:
        for start in range(0, len(frame), 500):
            chunk = frame.iloc[start : start + 500]
            collection.add(
                documents=[
                    f"{row.long_title}. {ICD_VI_SYNONYMS.get((str(row.icd_code), int(row.icd_version)), '')}".strip()
                    for row in chunk.itertuples()
                ],
                ids=[f"{row.icd_version}_{row.icd_code}" for row in chunk.itertuples()],
                metadatas=[
                    {
                        "icd_code": str(row.icd_code),
                        "icd_version": int(row.icd_version),
                        "long_title": str(row.long_title),
                        "use_count": int(row.use_count),
                    }
                    for row in chunk.itertuples()
                ],
            )

    _atomic_build("icd_dictionary", len(frame), db_signature, populate)


def build_schema_collection() -> None:
    print("\nBuilding schema_dictionary...")
    with SCHEMA_FILE.open(encoding="utf-8") as handle:
        schemas = json.load(handle)

    def populate(collection) -> None:
        collection.add(
            documents=[f"{item['document']}\n\n{item['ddl']}" for item in schemas],
            ids=[item["id"] for item in schemas],
            metadatas=[
                {
                    "table": item["table"],
                    "description_vi": item["description_vi"],
                }
                for item in schemas
            ],
        )

    _atomic_build("schema_dictionary", len(schemas), _source_hash(SCHEMA_FILE), populate)


def _load_examples(*, exclude_test_overlap: bool) -> list[dict]:
    with EXAMPLES_FILE.open(encoding="utf-8") as handle:
        examples = json.load(handle)
    if not exclude_test_overlap:
        return examples

    with TEST_FILE.open(encoding="utf-8") as handle:
        test_items = json.load(handle)
    gold_sql = {_canonical_sql(item["gold_sql"]) for item in test_items if item.get("gold_sql")}
    return [example for example in examples if _canonical_sql(example["sql"]) not in gold_sql]


def build_examples_collection(name: str = "sql_examples") -> None:
    exclude_overlap = name == "sql_examples_eval"
    examples = _load_examples(exclude_test_overlap=exclude_overlap)
    label = " (test overlaps removed)" if exclude_overlap else ""
    print(f"\nBuilding {name}{label}...")

    def populate(collection) -> None:
        collection.add(
            documents=[example["question_vi"] for example in examples],
            ids=[example["id"] for example in examples],
            metadatas=[
                {
                    "question_vi": example["question_vi"],
                    "sql": example["sql"],
                    "tables": ", ".join(example["tables"]),
                    "type": example.get("type", ""),
                }
                for example in examples
            ],
        )

    combined_hash = _source_hash(EXAMPLES_FILE)
    if exclude_overlap:
        combined_hash = hashlib.sha256(
            f"{combined_hash}:{_source_hash(TEST_FILE)}".encode()
        ).hexdigest()[:16]
    _atomic_build(name, len(examples), combined_hash, populate)


def quick_test(names: list[str]) -> None:
    query = "bệnh nhân bị viêm phổi nhập viện cấp cứu"
    print("\nQuick retrieval test:")
    for name in names:
        collection = client.get_collection(name, embedding_function=get_embedding_function())
        result = collection.query(query_texts=[query], n_results=min(3, collection.count()))
        print(f"  {name}: {collection.count()} records, {len(result['ids'][0])} results")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build MIMIC-IV Chroma collections")
    parser.add_argument(
        "--collections",
        nargs="+",
        choices=COLLECTIONS,
        default=list(COLLECTIONS),
    )
    parser.add_argument("--skip-test", action="store_true")
    parser.add_argument(
        "--icd-source",
        choices=("database", "csv"),
        default="database",
        help="Nguồn tần suất mã ICD; csv dùng dữ liệu MIMIC gốc khi PostgreSQL chưa chạy.",
    )
    args = parser.parse_args()

    builders = {
        "icd_dictionary": lambda: build_icd_collection(args.icd_source),
        "schema_dictionary": build_schema_collection,
        "sql_examples": lambda: build_examples_collection("sql_examples"),
        "sql_examples_eval": lambda: build_examples_collection("sql_examples_eval"),
    }
    for name in args.collections:
        builders[name]()
    if not args.skip_test:
        quick_test(args.collections)
    print(f"\n[DONE] Vector DB ready at {CHROMA_DIR}")


if __name__ == "__main__":
    main()
