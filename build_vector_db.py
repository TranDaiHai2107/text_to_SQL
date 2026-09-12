"""
Xây dựng Vector Database (ChromaDB) với 3 collections:
  1. icd_dictionary   – từ điển mã ICD chẩn đoán (tra cứu bệnh → mã ICD)
  2. schema_dictionary – DDL + mô tả 31 bảng MIMIC-IV (tra cứu bảng liên quan)
  3. sql_examples     – 101 cặp (câu hỏi tiếng Việt, SQL gold) (few-shot retrieval)

Chạy một lần sau khi đã chạy build_mimic_mini.py.
"""

import sys
import os
import json
import pandas as pd
import chromadb
from sqlalchemy import create_engine
from embedding_config import get_embedding_function
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "password123")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "mimiciv")

engine = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")
chroma_client = chromadb.PersistentClient(path="./mimic_chroma_db")


# ══════════════════════════════════════════════════════
# COLLECTION 1: ICD DICTIONARY
# ══════════════════════════════════════════════════════
def build_icd_collection():
    print("\n[1/3] Building icd_dictionary ...")

    # Xóa collection cũ nếu tồn tại để rebuild từ đầu
    try:
        chroma_client.delete_collection("icd_dictionary")
    except Exception:
        pass

    collection = chroma_client.create_collection(
        name="icd_dictionary",
        metadata={"hnsw:space": "cosine"},
        embedding_function=get_embedding_function(),
    )

    df_icd = pd.read_sql(
        "SELECT icd_code, icd_version, long_title FROM d_icd_diagnoses WHERE long_title IS NOT NULL",
        engine,
    )

    # Tối đa 10 000 mã để tránh quá nặng; ưu tiên mã ICD-10 vì mới hơn
    df_icd10 = df_icd[df_icd["icd_version"] == 10].head(6000)
    df_icd9  = df_icd[df_icd["icd_version"] == 9].head(4000)
    df_icd = pd.concat([df_icd10, df_icd9], ignore_index=True)

    batch_size = 500
    total = len(df_icd)
    for start in range(0, total, batch_size):
        chunk = df_icd.iloc[start : start + batch_size]
        collection.add(
            documents=chunk["long_title"].tolist(),
            ids=[f"{row.icd_version}_{row.icd_code}" for row in chunk.itertuples()],
            metadatas=[
                {"icd_code": str(row.icd_code), "icd_version": int(row.icd_version)}
                for row in chunk.itertuples()
            ],
        )
        print(f"  icd_dictionary: {min(start + batch_size, total)}/{total}", end="\r")

    print(f"  [OK] icd_dictionary: {total} mã ICD đã nạp.     ")


# ══════════════════════════════════════════════════════
# COLLECTION 2: SCHEMA DICTIONARY
# ══════════════════════════════════════════════════════
def build_schema_collection():
    print("\n[2/3] Building schema_dictionary ...")

    try:
        chroma_client.delete_collection("schema_dictionary")
    except Exception:
        pass

    collection = chroma_client.create_collection(
        name="schema_dictionary",
        metadata={"hnsw:space": "cosine"},
        embedding_function=get_embedding_function(),
    )

    with open("mimic_schema.json", encoding="utf-8") as f:
        schemas = json.load(f)

    documents, ids, metadatas = [], [], []
    for s in schemas:
        # Document = mô tả song ngữ + DDL (để embedding hiểu cả tiếng Việt lẫn tên cột)
        doc = f"{s['document']}\n\n{s['ddl']}"
        documents.append(doc)
        ids.append(s["id"])
        metadatas.append({
            "table": s["table"],
            "description_vi": s["description_vi"][:200],
            "ddl": s["ddl"][:1500],          # ChromaDB giới hạn metadata string
        })

    collection.add(documents=documents, ids=ids, metadatas=metadatas)
    print(f"  [OK] schema_dictionary: {len(schemas)} bảng đã nạp.")


# ══════════════════════════════════════════════════════
# COLLECTION 3: SQL EXAMPLES
# ══════════════════════════════════════════════════════
def build_examples_collection():
    print("\n[3/3] Building sql_examples ...")

    try:
        chroma_client.delete_collection("sql_examples")
    except Exception:
        pass

    collection = chroma_client.create_collection(
        name="sql_examples",
        metadata={"hnsw:space": "cosine"},
        embedding_function=get_embedding_function(),
    )

    with open("mimic_examples.json", encoding="utf-8") as f:
        examples = json.load(f)

    documents, ids, metadatas = [], [], []
    for ex in examples:
        # Document là câu hỏi tiếng Việt – dùng để embedding matching
        documents.append(ex["question_vi"])
        ids.append(ex["id"])
        metadatas.append({
            "question_vi": ex["question_vi"],
            "sql": ex["sql"],
            "tables": ", ".join(ex["tables"]),
            "type": ex.get("type", ""),
        })

    collection.add(documents=documents, ids=ids, metadatas=metadatas)
    print(f"  [OK] sql_examples: {len(examples)} cặp Q-SQL đã nạp.")


# ══════════════════════════════════════════════════════
# KIỂM TRA NHANH
# ══════════════════════════════════════════════════════
def quick_test():
    print("\n── Quick Test ──────────────────────────────")
    test_query = "bệnh nhân bị viêm phổi nhập viện cấp cứu"

    icd_col    = chroma_client.get_collection("icd_dictionary", embedding_function=get_embedding_function())
    schema_col = chroma_client.get_collection("schema_dictionary", embedding_function=get_embedding_function())
    ex_col     = chroma_client.get_collection("sql_examples", embedding_function=get_embedding_function())

    r1 = icd_col.query(query_texts=[test_query], n_results=3)
    print("ICD top-3:")
    for i, (doc, meta) in enumerate(zip(r1["documents"][0], r1["metadatas"][0])):
        print(f"  {i+1}. [{meta['icd_version']}] {meta['icd_code']}: {doc[:60]}")

    r2 = schema_col.query(query_texts=[test_query], n_results=3)
    print("Schema top-3:")
    for i, meta in enumerate(r2["metadatas"][0]):
        print(f"  {i+1}. {meta['table']}: {meta['description_vi'][:60]}")

    r3 = ex_col.query(query_texts=[test_query], n_results=3)
    print("Example top-3:")
    for i, meta in enumerate(r3["metadatas"][0]):
        print(f"  {i+1}. Q: {meta['question_vi'][:60]}")
        print(f"     SQL: {meta['sql'][:80].strip()}")


if __name__ == "__main__":
    print("=" * 55)
    print("  Building MIMIC-IV Vector Database (3 collections)")
    print("=" * 55)
    build_icd_collection()
    build_schema_collection()
    build_examples_collection()
    quick_test()
    print("\n[DONE] Vector DB ready at ./mimic_chroma_db")
