"""
RAG Engine – 3-layer Retrieval-Augmented Generation cho MIMIC-IV Text-to-SQL.

Pipeline đầy đủ: NL (tiếng Việt) → SQL → Kết quả → NL (tiếng Việt)

Các hàm chính:
  retrieve_icd_codes(question)              → tìm mã ICD liên quan
  retrieve_schema(question)                 → tìm DDL bảng liên quan
  retrieve_examples(question)               → tìm cặp Q-SQL mẫu tương đồng
  build_prompt(question, mode)              → tạo prompt đa tầng
  generate_sql(question, mode)              → gọi LLM sinh SQL (1 lần)
  generate_sql_with_correction(...)         → Agentic: sinh SQL + tự sửa nếu lỗi
  interpret_result(question, sql, df)       → SQL-to-Text: diễn giải kết quả thành tiếng Việt
  rewrite_question(question, chat_history)  → Multi-turn: viết lại câu hỏi đầy đủ
  run_query(sql)                            → thực thi SQL trên PostgreSQL

mode options (dùng cho ablation):
  "base"     – không RAG, chỉ prompt tĩnh với toàn bộ schema cứng
  "icd"      – chỉ ICD retrieval
  "schema"   – chỉ schema retrieval
  "examples" – chỉ example retrieval
  "full"     – cả 3 tầng RAG (mặc định, khuyến nghị)
"""

import sys
import os
import json
import hashlib
import random
import time
from functools import lru_cache
from collections.abc import Callable
import chromadb

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd
from groq import Groq
from sqlalchemy import create_engine, text
from sqlglot import parse_one
from config import (
    CHROMA_DIR,
    EXAMPLES_FILE,
    LOCK_TIMEOUT_MS,
    MAX_QUERY_ROWS,
    QUERY_TIMEOUT_MS,
    SCHEMA_FILE,
    TEST_FILE,
    database_url,
)
from embedding_config import DEFAULT_EMBEDDING_MODEL, get_embedding_function
from sql_validator import validate_sql_schema, get_validator_prompt_hint

# ── Kết nối PostgreSQL ────────────────────────────────────────
engine = create_engine(database_url(), pool_pre_ping=True, connect_args={"connect_timeout": 5})

# ── Groq LLM ────────────────────────────────────────────────
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
LLM_MODEL = os.getenv("LLM_MODEL", "qwen/qwen3.8-27b")
ICD_MAX_DISTANCE = float(os.getenv("ICD_MAX_DISTANCE", "0.90"))
SCHEMA_MAX_DISTANCE = float(os.getenv("SCHEMA_MAX_DISTANCE", "0.95"))
EXAMPLE_MAX_DISTANCE = float(os.getenv("EXAMPLE_MAX_DISTANCE", "0.85"))

SCHEMA_JOIN_NEIGHBORS = {
    "diagnoses_icd": {"d_icd_diagnoses", "admissions"},
    "procedures_icd": {"d_icd_procedures", "admissions"},
    "labevents": {"d_labitems", "admissions"},
    "hcpcsevents": {"d_hcpcs", "admissions"},
    "chartevents": {"d_items", "icustays"},
    "inputevents": {"d_items", "icustays"},
    "outputevents": {"d_items", "icustays"},
    "datetimeevents": {"d_items", "icustays"},
    "procedureevents": {"d_items", "icustays"},
    "ingredientevents": {"d_items", "icustays"},
    "emar": {"emar_detail", "admissions"},
    "poe": {"poe_detail", "admissions"},
}

DIRECT_ICD_TERMS = {
    "viêm phổi": ("9_486", "10_J189"),
    "suy tim": ("9_4280", "10_I509"),
    "đái tháo đường type 2": ("9_25000", "10_E119"),
    "tiểu đường type 2": ("9_25000", "10_E119"),
    "tăng huyết áp": ("9_4011", "10_I10"),
    "cao huyết áp": ("9_4011", "10_I10"),
    "nhiễm khuẩn huyết": ("9_0389", "10_A419"),
    "đột quỵ": ("9_43491", "10_I639"),
    "suy thận cấp": ("9_5849", "10_N179"),
    "bệnh phổi tắc nghẽn mạn tính": ("9_496", "10_J449"),
    "copd": ("9_496", "10_J449"),
}

# ── ChromaDB Collections ─────────────────────────────────────
_chroma = chromadb.PersistentClient(path=str(CHROMA_DIR))

def _get_collection(name: str):
    try:
        collection = _chroma.get_collection(name, embedding_function=get_embedding_function())
        metadata = collection.metadata or {}
        built_model = metadata.get("embedding_model")
        if built_model and built_model != DEFAULT_EMBEDDING_MODEL:
            raise RuntimeError(
                f"Collection '{name}' dùng embedding '{built_model}', cấu hình hiện tại là "
                f"'{DEFAULT_EMBEDDING_MODEL}'."
            )
        expected = metadata.get("expected_count")
        if expected is not None and collection.count() != int(expected):
            raise RuntimeError(
                f"Collection '{name}' chưa hoàn chỉnh: {collection.count()}/{expected} records."
            )
        expected_hash = _expected_source_hash(name)
        built_hash = metadata.get("source_hash")
        if expected_hash and built_hash != expected_hash:
            raise RuntimeError(
                f"Collection '{name}' đã cũ so với file nguồn. Hãy rebuild collection."
            )
        return collection
    except Exception as exc:
        raise RuntimeError(
            f"Collection '{name}' chưa được tạo. "
            f"Hãy chạy build_vector_db.py trước. Chi tiết: {exc}"
        ) from exc


def _short_file_hash(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _expected_source_hash(name: str) -> str | None:
    if name == "schema_dictionary":
        return _short_file_hash(SCHEMA_FILE)
    if name == "sql_examples":
        return _short_file_hash(EXAMPLES_FILE)
    if name == "sql_examples_eval":
        return hashlib.sha256(
            f"{_short_file_hash(EXAMPLES_FILE)}:{_short_file_hash(TEST_FILE)}".encode()
        ).hexdigest()[:16]
    return None


@lru_cache(maxsize=1)
def _schema_records() -> dict[str, dict]:
    with SCHEMA_FILE.open(encoding="utf-8") as handle:
        return {item["table"]: item for item in json.load(handle)}

# Schema tĩnh dự phòng (dùng khi mode='base' hoặc schema_col chưa sẵn sàng)
_STATIC_SCHEMA = """
-- ═══ HOSP MODULE (22 bảng) ═══
CREATE TABLE patients (subject_id INT, gender VARCHAR(1), anchor_age INT, anchor_year INT, anchor_year_group VARCHAR(20), dod DATE);
CREATE TABLE admissions (subject_id INT, hadm_id INT, admittime TIMESTAMP, dischtime TIMESTAMP, deathtime TIMESTAMP, admission_type VARCHAR(50), admission_location VARCHAR(60), discharge_location VARCHAR(60), insurance VARCHAR(50), language VARCHAR(10), marital_status VARCHAR(30), race VARCHAR(80), edregtime TIMESTAMP, edouttime TIMESTAMP, hospital_expire_flag INT);
CREATE TABLE transfers (subject_id INT, hadm_id INT, transfer_id INT, eventtype VARCHAR(20), careunit VARCHAR(60), intime TIMESTAMP, outtime TIMESTAMP);
CREATE TABLE services (subject_id INT, hadm_id INT, transfertime TIMESTAMP, prev_service VARCHAR(20), curr_service VARCHAR(20));
CREATE TABLE provider (provider_id VARCHAR(10));
CREATE TABLE diagnoses_icd (subject_id INT, hadm_id INT, seq_num INT, icd_code VARCHAR(10), icd_version INT);
CREATE TABLE d_icd_diagnoses (icd_code VARCHAR(10), icd_version INT, long_title VARCHAR(300));
CREATE TABLE procedures_icd (subject_id INT, hadm_id INT, seq_num INT, chartdate DATE, icd_code VARCHAR(10), icd_version INT);
CREATE TABLE d_icd_procedures (icd_code VARCHAR(10), icd_version INT, long_title VARCHAR(300));
CREATE TABLE hcpcsevents (subject_id INT, hadm_id INT, chartdate DATE, hcpcs_cd VARCHAR(10), seq_num INT, short_description VARCHAR(200));
CREATE TABLE d_hcpcs (code VARCHAR(10), category INT, long_description VARCHAR(500), short_description VARCHAR(200));
CREATE TABLE drgcodes (subject_id INT, hadm_id INT, drg_type VARCHAR(4), drg_code VARCHAR(10), description VARCHAR(300), drg_severity INT, drg_mortality INT);
CREATE TABLE labevents (labevent_id BIGINT, subject_id INT, hadm_id INT, itemid INT, charttime TIMESTAMP, value VARCHAR(200), valuenum FLOAT, valueuom VARCHAR(20), ref_range_lower FLOAT, ref_range_upper FLOAT, flag VARCHAR(10), priority VARCHAR(20));
CREATE TABLE d_labitems (itemid INT, label VARCHAR(100), fluid VARCHAR(50), category VARCHAR(50));
CREATE TABLE microbiologyevents (microevent_id BIGINT, subject_id INT, hadm_id INT, chartdate DATE, spec_type_desc VARCHAR(100), org_name VARCHAR(100), interpretation VARCHAR(5));
CREATE TABLE prescriptions (subject_id INT, hadm_id INT, starttime TIMESTAMP, stoptime TIMESTAMP, drug_type VARCHAR(20), drug VARCHAR(200), dose_val_rx VARCHAR(50), dose_unit_rx VARCHAR(50), route VARCHAR(50));
CREATE TABLE pharmacy (subject_id INT, hadm_id INT, pharmacy_id INT, medication VARCHAR(200), proc_type VARCHAR(20), status VARCHAR(20), route VARCHAR(50), frequency VARCHAR(50), doses_per_24_hrs FLOAT);
CREATE TABLE poe (poe_id VARCHAR(20), poe_seq INT, subject_id INT, hadm_id INT, ordertime TIMESTAMP, order_type VARCHAR(30), order_subtype VARCHAR(50), transaction_type VARCHAR(20), order_status VARCHAR(20));
CREATE TABLE poe_detail (poe_id VARCHAR(20), poe_seq INT, subject_id INT, field_name VARCHAR(50), field_value VARCHAR(200));
CREATE TABLE emar (emar_id VARCHAR(25), subject_id INT, hadm_id INT, emar_seq INT, poe_id VARCHAR(20), pharmacy_id INT, charttime TIMESTAMP, medication VARCHAR(200), event_txt VARCHAR(50), scheduletime TIMESTAMP);
CREATE TABLE emar_detail (emar_id VARCHAR(25), emar_seq INT, dose_due VARCHAR(20), dose_given VARCHAR(20), dose_given_unit VARCHAR(20), route VARCHAR(20), site VARCHAR(50));
CREATE TABLE omr (subject_id INT, chartdate DATE, seq_num INT, result_name VARCHAR(50), result_value VARCHAR(50));
-- ═══ ICU MODULE (9 bảng) ═══
CREATE TABLE icustays (subject_id INT, hadm_id INT, stay_id INT, first_careunit VARCHAR(60), last_careunit VARCHAR(60), intime TIMESTAMP, outtime TIMESTAMP, los FLOAT);
CREATE TABLE chartevents (subject_id INT, hadm_id INT, stay_id INT, caregiver_id INT, charttime TIMESTAMP, itemid INT, value VARCHAR(200), valuenum FLOAT, valueuom VARCHAR(20), warning INT);
CREATE TABLE d_items (itemid INT, label VARCHAR(200), abbreviation VARCHAR(100), linksto VARCHAR(30), category VARCHAR(50), unitname VARCHAR(50), param_type VARCHAR(30), lownormalvalue FLOAT, highnormalvalue FLOAT);
CREATE TABLE inputevents (subject_id INT, hadm_id INT, stay_id INT, starttime TIMESTAMP, endtime TIMESTAMP, itemid INT, amount FLOAT, amountuom VARCHAR(20), rate FLOAT, rateuom VARCHAR(20), ordercategoryname VARCHAR(50), patientweight FLOAT, statusdescription VARCHAR(30));
CREATE TABLE outputevents (subject_id INT, hadm_id INT, stay_id INT, charttime TIMESTAMP, itemid INT, value FLOAT, valueuom VARCHAR(20));
CREATE TABLE datetimeevents (subject_id INT, hadm_id INT, stay_id INT, charttime TIMESTAMP, itemid INT, value TIMESTAMP, valueuom VARCHAR(20));
CREATE TABLE procedureevents (subject_id INT, hadm_id INT, stay_id INT, starttime TIMESTAMP, endtime TIMESTAMP, itemid INT, value FLOAT, valueuom VARCHAR(20), location VARCHAR(50), ordercategoryname VARCHAR(50), statusdescription VARCHAR(30));
CREATE TABLE ingredientevents (subject_id INT, hadm_id INT, stay_id INT, starttime TIMESTAMP, endtime TIMESTAMP, itemid INT, amount FLOAT, amountuom VARCHAR(20), rate FLOAT, rateuom VARCHAR(20));
CREATE TABLE caregiver (caregiver_id INT);
-- ═══ JOIN RULES ═══
-- JOIN patients ↔ admissions: ON subject_id
-- JOIN admissions ↔ diagnoses_icd: ON hadm_id
-- JOIN diagnoses_icd ↔ d_icd_diagnoses: ON icd_code AND icd_version
-- JOIN labevents ↔ d_labitems: ON itemid
-- JOIN procedures_icd ↔ d_icd_procedures: ON icd_code AND icd_version
-- JOIN hcpcsevents ↔ d_hcpcs: ON hcpcs_cd = code
-- JOIN admissions ↔ icustays: ON hadm_id
-- JOIN icustays ↔ chartevents/inputevents/outputevents: ON stay_id
-- JOIN chartevents/inputevents/outputevents/procedureevents ↔ d_items: ON itemid
-- Tính LOS (ngày): EXTRACT(EPOCH FROM (dischtime::TIMESTAMP - admittime::TIMESTAMP))/86400
"""

# Keep base-mode schema synchronized with the JSON source of truth.
_STATIC_SCHEMA = "\n\n".join(
    record["ddl"] for record in _schema_records().values()
)



# ══════════════════════════════════════════════════════════════
# TẦNG 1 – ICD RETRIEVAL
# ══════════════════════════════════════════════════════════════
def retrieve_icd_codes(question: str, n_results: int = 3) -> dict:
    """
    Trả về dict:
      text    – chuỗi mô tả (để nhét vào prompt)
      codes   – list[dict] với keys: icd_code, icd_version, long_title
      found   – bool
    """
    try:
        col = _get_collection("icd_dictionary")
        codes = []
        lines = []
        seen: set[tuple[str, int]] = set()

        direct_ids = []
        normalized_question = question.casefold()
        for term, ids in DIRECT_ICD_TERMS.items():
            if term in normalized_question:
                direct_ids.extend(ids)
        if direct_ids:
            direct = col.get(
                ids=list(dict.fromkeys(direct_ids)),
                include=["documents", "metadatas"],
            )
            for doc, meta in zip(direct["documents"], direct["metadatas"]):
                key = (str(meta["icd_code"]), int(meta["icd_version"]))
                if key in seen or len(codes) >= n_results:
                    continue
                seen.add(key)
                codes.append({
                    "icd_code": key[0],
                    "icd_version": key[1],
                    "long_title": meta.get("long_title", doc),
                    "distance": 0.0,
                })

        results = (
            {"documents": [[]], "metadatas": [[]], "distances": [[]]}
            if direct_ids
            else col.query(query_texts=[question], n_results=n_results)
        )
        distances = results.get("distances", [[]])[0]
        for doc, meta, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            distances,
        ):
            if distance is not None and distance > ICD_MAX_DISTANCE:
                continue
            key = (str(meta["icd_code"]), int(meta["icd_version"]))
            if key in seen or len(codes) >= n_results:
                continue
            seen.add(key)
            codes.append({
                "icd_code": key[0],
                "icd_version": key[1],
                "long_title": meta.get("long_title", doc),
                "distance": distance,
            })
        for code in codes:
            lines.append(
                f"  - Bệnh '{code['long_title'][:80]}' → "
                f"ICD-{code['icd_version']} code: '{code['icd_code']}'"
            )
        return {"text": "\n".join(lines), "codes": codes, "found": bool(codes)}
    except Exception as e:
        return {"text": f"  (Không tra được ICD: {e})", "codes": [], "found": False}


# ══════════════════════════════════════════════════════════════
# TẦNG 2 – SCHEMA RETRIEVAL
# ══════════════════════════════════════════════════════════════
def retrieve_schema(question: str, n_results: int = 4) -> dict:
    """
    Trả về dict:
      text   – chuỗi DDL các bảng liên quan (cho prompt)
      tables – list[str] tên bảng tìm được
      found  – bool
    """
    CORE_TABLES = {"patients", "admissions"}

    try:
        col = _get_collection("schema_dictionary")
        results = col.query(query_texts=[question], n_results=n_results)
        ddl_parts = []
        tables_found = list(CORE_TABLES)
        schemas = _schema_records()
        retrieved_tables: set[str] = set()

        distances = results.get("distances", [[]])[0]
        for meta, distance in zip(results["metadatas"][0], distances):
            if distance is not None and distance > SCHEMA_MAX_DISTANCE:
                continue
            tbl = meta["table"]
            retrieved_tables.add(tbl)
            if tbl not in tables_found:
                tables_found.append(tbl)
            schema = schemas.get(tbl)
            if schema:
                ddl_parts.append(
                    f"-- [{tbl}] {schema['description_vi']}\n{schema['ddl']}"
                )

        # Add direct join partners so the model sees dictionary keys and bridge
        # tables even when semantic retrieval returns only one side of a JOIN.
        expanded_tables = set(retrieved_tables)
        for table in retrieved_tables:
            expanded_tables.update(SCHEMA_JOIN_NEIGHBORS.get(table, set()))
        for table in sorted(expanded_tables - retrieved_tables - CORE_TABLES):
            schema = schemas.get(table)
            if schema:
                tables_found.append(table)
                ddl_parts.append(
                    f"-- [{table}] {schema['description_vi']}\n{schema['ddl']}"
                )

        core_parts = []
        for tbl in CORE_TABLES:
            if tbl in schemas and tbl not in retrieved_tables:
                s = schemas[tbl]
                core_parts.append(f"-- [{tbl}] {s['description_vi']}\n{s['ddl']}")

        all_ddl = "\n\n".join(core_parts + ddl_parts)
        return {"text": all_ddl, "tables": tables_found, "found": True}
    except Exception as e:
        return {"text": _STATIC_SCHEMA, "tables": list(CORE_TABLES), "found": False}


# ══════════════════════════════════════════════════════════════
# TẦNG 3 – EXAMPLE RETRIEVAL
# ══════════════════════════════════════════════════════════════
def retrieve_examples(
    question: str,
    n_results: int = 3,
    collection_name: str = "sql_examples",
) -> dict:
    """
    Trả về dict:
      text   – chuỗi các cặp Q-SQL mẫu (cho prompt)
      items  – list[dict] với keys: question_vi, sql
      found  – bool
    """
    try:
        col = _get_collection(collection_name)
        results = col.query(query_texts=[question], n_results=n_results)
        items, lines = [], []
        distances = results.get("distances", [[]])[0]
        accepted = [
            (meta, distance)
            for meta, distance in zip(results["metadatas"][0], distances)
            if distance is None or distance <= EXAMPLE_MAX_DISTANCE
        ]
        for i, (meta, distance) in enumerate(accepted, 1):
            items.append({"question_vi": meta["question_vi"], "sql": meta["sql"]})
            lines.append(
                f"  Ví dụ {i}:\n"
                f"    Câu hỏi: {meta['question_vi']}\n"
                f"    SQL:\n{meta['sql']}"
            )
        return {"text": "\n\n".join(lines), "items": items, "found": bool(items)}
    except Exception as e:
        return {"text": f"  (Không lấy được ví dụ: {e})", "items": [], "found": False}


# ══════════════════════════════════════════════════════════════
# PROMPT BUILDER
# ══════════════════════════════════════════════════════════════
SYSTEM_PROMPT = (
    "Bạn là chuyên gia Data Engineer y tế chuyên phân tích dữ liệu MIMIC-IV trên PostgreSQL. "
    "Nhiệm vụ: chuyển câu hỏi y khoa tiếng Việt thành câu lệnh SQL PostgreSQL hợp lệ. "
    "Quy tắc bắt buộc:\n"
    "  1. CHỈ trả về câu lệnh SQL, không giải thích, không markdown.\n"
    "  2. Chỉ dùng bảng và cột được liệt kê trong schema cung cấp.\n"
    "  3. Nếu câu hỏi nhắc đến bệnh, dùng các mã ICD đã tra cứu trong WHERE; khi có cả ICD-9 và ICD-10, nối hai điều kiện bằng OR và giữ đúng icd_version.\n"
    "  4. JOIN luôn dùng điều kiện đúng: diagnoses_icd ↔ d_icd_diagnoses phải JOIN cả icd_code AND icd_version.\n"
    "  5. Tính thời gian nằm viện bằng: EXTRACT(EPOCH FROM (dischtime - admittime))/86400.\n"
    "  6. Các cột thời gian trong schema là DATE hoặc TIMESTAMP; dùng phép toán thời gian PostgreSQL tương ứng.\n"
    "  7. Dùng ILIKE thay cho LIKE khi so sánh chuỗi (không phân biệt hoa thường).\n"
    "  8. QUAN TRỌNG – Câu hỏi multi-turn: nếu câu hỏi đề cập đến một nhóm kết quả trước "
    "(VD: 'trong số N bệnh nhân nữ', 'trong nhóm bệnh nhân trên 60 tuổi', "
    "'trong đó có bao nhiêu...'), PHẢI dùng subquery hoặc CTE để lọc đúng nhóm đó TRƯỚC, "
    "rồi mới áp thêm điều kiện. "
    "Ví dụ: 'Trong số bệnh nhân nữ, có bao nhiêu nam?' → "
    "SELECT COUNT(*) FROM patients WHERE gender = 'M' AND subject_id IN "
    "(SELECT subject_id FROM patients WHERE gender = 'F') — kết quả đúng phải là 0."
)


def build_prompt(
    question: str,
    mode: str = "full",
    examples_collection: str = "sql_examples",
) -> tuple[str, dict]:
    """
    Trả về (user_prompt, context_dict).
    context_dict chứa kết quả RAG từng tầng để hiển thị trên UI.
    """
    ctx = {"icd": None, "schema": None, "examples": None}

    if mode in ("icd", "full"):
        ctx["icd"] = retrieve_icd_codes(question)
        icd_section = (
            "## Mã ICD tra cứu được (BẮT BUỘC dùng trong WHERE nếu câu hỏi liên quan đến bệnh):\n"
            + ctx["icd"]["text"]
        )
    else:
        icd_section = ""

    if mode in ("schema", "full"):
        ctx["schema"] = retrieve_schema(question)
        schema_section = (
            "## Cấu trúc các bảng liên quan (chỉ dùng các bảng này):\n"
            + ctx["schema"]["text"]
        )
    else:
        schema_section = (
            "## Cấu trúc Database MIMIC-IV:\n" + _STATIC_SCHEMA
        )

    if mode in ("examples", "full"):
        ctx["examples"] = retrieve_examples(
            question,
            collection_name=examples_collection,
        )
        ex_section = (
            "## Câu SQL mẫu tương đồng (học theo cấu trúc SQL này):\n"
            + ctx["examples"]["text"]
        )
    else:
        ex_section = ""

    sections = [s for s in [schema_section, icd_section, ex_section] if s]
    user_prompt = "\n\n".join(sections)
    user_prompt += f"\n\n## Câu hỏi của người dùng:\n{question}\n\nSQL Query:"

    return user_prompt, ctx


# ══════════════════════════════════════════════════════════════
# LLM CALL + SQL CLEAN (helper nội bộ)
# ══════════════════════════════════════════════════════════════
def _call_llm(messages: list[dict], max_tokens: int = 900) -> str:
    """Call Groq with short exponential backoff for transient failures."""
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                temperature=0,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            if not content:
                raise RuntimeError("LLM trả về nội dung rỗng.")
            return content.strip()
        except Exception as exc:
            last_error = exc
            if attempt == 2:
                break
            time.sleep((0.8 * (2**attempt)) + random.uniform(0, 0.25))
    raise RuntimeError(f"Gọi Groq thất bại sau 3 lần: {last_error}") from last_error


def _clean_sql(raw: str) -> str:
    """Xóa markdown fence nếu LLM vô tình thêm vào."""
    sql = raw.strip()
    if sql.startswith("```"):
        lines = sql.split("\n")
        end_idx = next(
            (i for i in range(len(lines) - 1, 0, -1) if lines[i].strip() == "```"),
            len(lines),
        )
        sql = "\n".join(lines[1:end_idx])
    return sql.strip()


# ══════════════════════════════════════════════════════════════
# SINH SQL (1 lần, dùng cho evaluate.py / backward-compatible)
# ══════════════════════════════════════════════════════════════
def generate_sql(
    question: str,
    mode: str = "full",
    examples_collection: str = "sql_examples",
) -> tuple[str, dict]:
    """Trả về (sql_string, context_dict). Gọi LLM 1 lần."""
    user_prompt, ctx = build_prompt(question, mode, examples_collection)
    raw = _call_llm([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ])
    return _clean_sql(raw), ctx


# ══════════════════════════════════════════════════════════════
# SINH SQL + TỰ SỬA LỖI (Agentic Self-Correction)
# ══════════════════════════════════════════════════════════════
def generate_sql_with_correction(
    question: str,
    mode: str = "full",
    max_retries: int = 2,
    on_attempt: Callable[[int, str, str | None, bool], None] | None = None,
    examples_collection: str = "sql_examples",
    query_max_rows: int | None = None,
) -> dict:
    """
    Pipeline Agentic: sinh SQL → chạy thử → nếu lỗi thì gửi lỗi cho LLM sửa.

    on_attempt(attempt, sql, error, is_final):
        callback tùy chọn, gọi sau mỗi lần thử để UI hiển thị tiến trình.

    Trả về dict:
      sql        – câu SQL cuối cùng (đã sửa nếu cần)
      ctx        – context RAG
      df         – DataFrame kết quả (None nếu vẫn lỗi sau max_retries)
      attempts   – số lần thử (1 = thành công ngay, >1 = đã tự sửa)
      history    – list[dict] ghi log từng lần thử: {sql, error}
      success    – bool
    """
    user_prompt, ctx = build_prompt(question, mode, examples_collection)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]

    history = []

    for attempt in range(1, max_retries + 2):  # max_retries lần sửa + 1 lần đầu
        raw = _call_llm(messages)
        sql = _clean_sql(raw)

        # Kiểm tra trước bằng Schema-Aware SQL Validator
        val_res = validate_sql_schema(sql)
        if not val_res["valid"]:
            error_msg = get_validator_prompt_hint(val_res)
            history.append({"attempt": attempt, "sql": sql, "error": error_msg})
            if on_attempt:
                on_attempt(attempt, sql, error_msg, attempt > max_retries)
            if attempt > max_retries:
                return {
                    "sql": sql, "ctx": ctx, "df": None,
                    "attempts": attempt, "history": history, "success": False,
                }
            messages.append({"role": "assistant", "content": sql})
            messages.append({"role": "user", "content": error_msg})
            continue

        try:
            df = run_query(sql, max_rows=query_max_rows)
            history.append({"attempt": attempt, "sql": sql, "error": None})
            if on_attempt:
                on_attempt(attempt, sql, None, True)
            return {
                "sql": sql, "ctx": ctx, "df": df,
                "attempts": attempt, "history": history, "success": True,
            }
        except Exception as err:
            error_msg = str(err)[:500]
            history.append({"attempt": attempt, "sql": sql, "error": error_msg})
            if on_attempt:
                on_attempt(attempt, sql, error_msg, attempt > max_retries)

            if attempt > max_retries:
                return {
                    "sql": sql, "ctx": ctx, "df": None,
                    "attempts": attempt, "history": history, "success": False,
                }

            # Thêm vào messages multi-turn để LLM tự sửa
            messages.append({"role": "assistant", "content": sql})
            messages.append({"role": "user", "content": (
                f"Câu SQL trên bị lỗi khi chạy trên PostgreSQL.\n"
                f"Thông báo lỗi:\n{error_msg}\n\n"
                f"Hãy sửa lại câu SQL. CHỈ trả về câu SQL đã sửa, không giải thích."
            )})


# ══════════════════════════════════════════════════════════════
# DIỄN GIẢI KẾT QUẢ (SQL-to-Text / Result Interpretation)
# ══════════════════════════════════════════════════════════════
_INTERPRET_SYSTEM = (
    "Bạn là trợ lý y tế. Nhiệm vụ: diễn giải kết quả truy vấn SQL thành câu trả lời "
    "ngôn ngữ tự nhiên bằng TIẾNG VIỆT, dễ hiểu cho bác sĩ/người không biết kỹ thuật.\n"
    "Quy tắc:\n"
    "  1. Trả lời ngắn gọn, rõ ràng, đi thẳng vào kết quả.\n"
    "  2. Nêu con số cụ thể từ dữ liệu (không bịa số liệu).\n"
    "  3. Nếu dữ liệu là bảng nhiều dòng, tóm tắt xu hướng chính và highlight top kết quả.\n"
    "     Nếu prompt nói chỉ có một phần kết quả, chỉ mô tả phần được cung cấp và không suy diễn xu hướng của toàn bộ dữ liệu.\n"
    "  4. Nếu kết quả rỗng (0 dòng), nói rõ 'Không tìm thấy dữ liệu phù hợp'.\n"
    "  5. Dùng đơn vị phù hợp (ngày, %, ca, lần...).\n"
    "  6. KHÔNG giải thích SQL, KHÔNG đề cập đến bảng/cột database.\n"
    "  7. Viết như đang trả lời trực tiếp cho người hỏi.\n"
)


def interpret_result(
    question: str,
    sql: str,
    df: pd.DataFrame,
    max_rows_in_prompt: int = 20,
) -> str:
    """
    Diễn giải kết quả SQL thành câu trả lời tiếng Việt tự nhiên.

    Args:
        question: Câu hỏi gốc của người dùng
        sql: Câu SQL đã sinh
        df: DataFrame kết quả từ PostgreSQL
        max_rows_in_prompt: Số dòng tối đa gửi cho LLM (tránh quá dài)

    Returns:
        Câu trả lời ngôn ngữ tự nhiên bằng tiếng Việt
    """
    # Xử lý trường hợp đặc biệt
    if df is None or df.empty:
        return "Không tìm thấy dữ liệu phù hợp với câu hỏi của bạn trong cơ sở dữ liệu."

    # Chuẩn bị dữ liệu kết quả cho prompt
    num_rows = len(df)
    num_cols = len(df.columns)

    # MIMIC-derived rows stay local by default. Operators may explicitly opt in
    # after checking their data-use and Groq retention settings.
    if os.getenv("SEND_RESULTS_TO_LLM", "false").lower() not in {"1", "true", "yes"}:
        if num_rows == 1:
            values = ", ".join(
                f"{column}: {df.iloc[0][column]}" for column in df.columns
            )
            return f"Kết quả truy vấn: {values}."
        return f"Truy vấn trả về {num_rows} dòng và {num_cols} cột; chi tiết được hiển thị trong bảng bên dưới."

    if num_rows <= max_rows_in_prompt:
        data_str = df.to_string(index=False)
        data_note = f"({num_rows} dòng, {num_cols} cột — toàn bộ kết quả)"
    else:
        data_str = df.head(max_rows_in_prompt).to_string(index=False)
        data_note = (
            f"({num_rows} dòng tổng cộng, chỉ hiển thị {max_rows_in_prompt} dòng đầu, "
            f"{num_cols} cột)"
        )

    prompt = (
        f"Câu hỏi của người dùng:\n\"{question}\"\n\n"
        f"SQL đã dùng:\n{sql}\n\n"
        f"Kết quả truy vấn {data_note}:\n{data_str}\n\n"
        f"Hãy trả lời câu hỏi trên bằng tiếng Việt dựa trên kết quả truy vấn."
    )

    try:
        answer = _call_llm([
            {"role": "system", "content": _INTERPRET_SYSTEM},
            {"role": "user",   "content": prompt},
        ])
        return answer.strip()
    except Exception as e:
        # Fallback nếu LLM lỗi: trả về mô tả cơ bản
        if num_rows == 1 and num_cols == 1:
            val = df.iloc[0, 0]
            return f"Kết quả: {val}"
        return f"Truy vấn trả về {num_rows} dòng kết quả."


# ══════════════════════════════════════════════════════════════
# MULTI-TURN: QUERY REWRITING
# ══════════════════════════════════════════════════════════════
_REWRITE_SYSTEM = (
    "Bạn là trợ lý viết lại câu hỏi. "
    "Nhiệm vụ: dựa vào lịch sử hội thoại (bao gồm câu hỏi trước, SQL đã chạy, "
    "và kết quả trả về), viết lại câu hỏi mới thành câu ĐẦY ĐỦ, ĐỘC LẬP.\n"
    "Quy tắc BẮT BUỘC:\n"
    "  1. Nếu câu hỏi dùng đại từ/ngữ cảnh ẩn ('đó', 'trong số đó', 'họ', 'những người đó', "
    "'kết quả trên', 'bao nhiêu nam/nữ trong đó'...), hãy thay thế bằng ngữ cảnh cụ thể "
    "từ câu hỏi và KẾT QUẢ trước đó.\n"
    "  2. QUAN TRỌNG: 'trong đó', 'trong số đó' nghĩa là trong TẬP KẾT QUẢ của câu hỏi trước. "
    "Ví dụ: nếu câu trước hỏi 'bệnh nhân nữ' → 'trong đó có bao nhiêu nam?' phải được hiểu là "
    "'trong nhóm bệnh nhân nữ, có bao nhiêu nam?' (câu trả lời logic phải là 0).\n"
    "  3. Nếu câu hỏi mâu thuẫn logic (VD: tìm nam trong nhóm nữ), VẪN viết lại đúng ngữ cảnh "
    "để hệ thống SQL có thể cho kết quả chính xác (0 kết quả).\n"
    "  4. Nếu câu đã đủ ý và không cần ngữ cảnh, trả về nguyên văn.\n"
    "  5. CHỈ trả về câu hỏi đã viết lại, KHÔNG giải thích.\n"
)


def rewrite_question(question: str, chat_history: list[dict]) -> str:
    """
    Viết lại câu hỏi để giải quyết coreference / ellipsis trong multi-turn.

    chat_history: list[dict] với keys:
      - "role" ("user"/"assistant")
      - "content" (text)
      - "sql" (optional) – câu SQL đã sinh ở lượt trước
      - "result_summary" (optional) – tóm tắt kết quả trước đó

    Chỉ dùng 8 message gần nhất (4 lượt) để vừa đủ ngữ cảnh.

    Trả về câu hỏi đã viết lại (hoặc nguyên văn nếu đã đầy đủ).
    """
    if not chat_history:
        return question

    recent = chat_history[-8:]
    history_parts = []
    for m in recent:
        role_label = 'Người dùng' if m['role'] == 'user' else 'Hệ thống'
        content = m['content'][:500]
        line = f"{role_label}: {content}"

        # Thêm thông tin SQL và kết quả nếu có (rất quan trọng cho ngữ cảnh)
        if m.get('sql'):
            line += f"\n  [SQL đã chạy: {m['sql'][:1000]}]"
        if m.get('result_summary'):
            line += f"\n  [Kết quả: {m['result_summary'][:500]}]"

        history_parts.append(line)

    history_str = "\n".join(history_parts)

    prompt = (
        f"Lịch sử hội thoại:\n{history_str}\n\n"
        f"Câu hỏi mới của người dùng: \"{question}\"\n\n"
        f"Hãy viết lại câu hỏi thành câu đầy đủ, độc lập, giữ đúng ý định của người dùng "
        f"dựa trên ngữ cảnh hội thoại. Nếu câu hỏi liên quan đến kết quả trước, "
        f"hãy chỉ rõ điều kiện lọc cụ thể.\n\n"
        f"Câu hỏi đã viết lại:"
    )

    rewritten = _call_llm(
        [
            {"role": "system", "content": _REWRITE_SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=256,  # Chỉ cần sinh 1 câu hỏi ngắn
    )

    # Xóa dấu ngoặc kép bao quanh nếu LLM thêm vào
    if rewritten.startswith('"') and rewritten.endswith('"'):
        rewritten = rewritten[1:-1]

    return rewritten.strip() or question


# ══════════════════════════════════════════════════════════════
# THỰC THI SQL
# ══════════════════════════════════════════════════════════════
def run_query(sql: str, max_rows: int | None = None) -> pd.DataFrame:
    """Validate and execute SQL in a bounded, read-only transaction."""
    validation = validate_sql_schema(sql)
    if not validation["valid"]:
        raise ValueError(get_validator_prompt_hint(validation))

    clean_sql = parse_one(sql, read="postgres").sql(dialect="postgres")
    row_limit = MAX_QUERY_ROWS if max_rows is None else max(1, min(int(max_rows), 100_000))
    bounded_sql = text(
        "SELECT * FROM (\n" + clean_sql + "\n) AS _validated_query LIMIT :_row_limit"
    )
    with engine.connect().execution_options(postgresql_readonly=True) as conn:
        with conn.begin():
            conn.execute(text(f"SET LOCAL statement_timeout = {QUERY_TIMEOUT_MS}"))
            conn.execute(text(f"SET LOCAL lock_timeout = {LOCK_TIMEOUT_MS}"))
            return pd.read_sql(
                bounded_sql,
                conn,
                params={"_row_limit": row_limit},
            )


# ══════════════════════════════════════════════════════════════
# PIPELINE ĐẦY ĐỦ (terminal mode)
# ══════════════════════════════════════════════════════════════
def ask_medical_question(question: str, mode: str = "full"):
    print(f"\n{'='*55}")
    print(f"Câu hỏi: {question}")
    print(f"Mode: {mode}")
    print("=" * 55)

    result = generate_sql_with_correction(question, mode)

    if result["ctx"].get("icd"):
        print(f"\n[RAG-1 ICD]\n{result['ctx']['icd']['text']}")
    if result["ctx"].get("schema"):
        print(f"\n[RAG-2 Schema] Bảng: {', '.join(result['ctx']['schema']['tables'])}")

    for h in result["history"]:
        tag = "OK" if h["error"] is None else "ERR"
        print(f"\n[Attempt {h['attempt']}] [{tag}]")
        print(f"SQL: {h['sql'][:200]}")
        if h["error"]:
            print(f"Error: {h['error'][:200]}")

    if result["success"]:
        print(f"\nKết quả: {len(result['df'])} dòng (sau {result['attempts']} lần thử)")
        print(result["df"].head(20).to_string())

        # SQL-to-Text: diễn giải kết quả thành ngôn ngữ tự nhiên
        print(f"\n{'─'*55}")
        print("📝 Trả lời bằng ngôn ngữ tự nhiên:")
        print("─" * 55)
        nl_answer = interpret_result(question, result["sql"], result["df"])
        print(nl_answer)
    else:
        print(f"\nThất bại sau {result['attempts']} lần thử.")


if __name__ == "__main__":
    ask_medical_question(
        "Có bao nhiêu bệnh nhân bị viêm phổi nhập viện qua cấp cứu?",
        mode="full",
    )
