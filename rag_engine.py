"""
RAG Engine – 3-layer Retrieval-Augmented Generation cho MIMIC-IV Text-to-SQL.

Các hàm chính:
  retrieve_icd_codes(question)              → tìm mã ICD liên quan
  retrieve_schema(question)                 → tìm DDL bảng liên quan
  retrieve_examples(question)               → tìm cặp Q-SQL mẫu tương đồng
  build_prompt(question, mode)              → tạo prompt đa tầng
  generate_sql(question, mode)              → gọi LLM sinh SQL (1 lần)
  generate_sql_with_correction(...)         → Agentic: sinh SQL + tự sửa nếu lỗi
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
import chromadb

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd
from groq import Groq
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from embedding_config import get_embedding_function
from sql_validator import validate_sql_schema, get_validator_prompt_hint

load_dotenv()

# ── Kết nối PostgreSQL ────────────────────────────────────────
DB_USER = "postgres"
DB_PASS = "password123"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "mimiciv"
engine = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

# ── Groq LLM ────────────────────────────────────────────────
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
LLM_MODEL = "qwen/qwen3.8-27b"

# ── ChromaDB Collections ─────────────────────────────────────
_chroma = chromadb.PersistentClient(path="./mimic_chroma_db")

def _get_collection(name: str):
    try:
        return _chroma.get_collection(name, embedding_function=get_embedding_function())
    except Exception:
        raise RuntimeError(
            f"Collection '{name}' chưa được tạo. "
            "Hãy chạy build_vector_db.py trước."
        )

# Schema tĩnh dự phòng (dùng khi mode='base' hoặc schema_col chưa sẵn sàng)
_STATIC_SCHEMA = """
CREATE TABLE patients (subject_id INT, gender VARCHAR(1), anchor_age INT, anchor_year INT, anchor_year_group VARCHAR(20), dod DATE);
CREATE TABLE admissions (subject_id INT, hadm_id INT, admittime TIMESTAMP, dischtime TIMESTAMP, deathtime TIMESTAMP, admission_type VARCHAR(50), admission_location VARCHAR(60), discharge_location VARCHAR(60), insurance VARCHAR(50), language VARCHAR(10), marital_status VARCHAR(30), race VARCHAR(80), edregtime TIMESTAMP, edouttime TIMESTAMP, hospital_expire_flag INT);
CREATE TABLE diagnoses_icd (subject_id INT, hadm_id INT, seq_num INT, icd_code VARCHAR(10), icd_version INT);
CREATE TABLE d_icd_diagnoses (icd_code VARCHAR(10), icd_version INT, long_title VARCHAR(300));
CREATE TABLE procedures_icd (subject_id INT, hadm_id INT, seq_num INT, chartdate DATE, icd_code VARCHAR(10), icd_version INT);
CREATE TABLE d_icd_procedures (icd_code VARCHAR(10), icd_version INT, long_title VARCHAR(300));
CREATE TABLE labevents (labevent_id BIGINT, subject_id INT, hadm_id INT, itemid INT, charttime TIMESTAMP, value VARCHAR(200), valuenum FLOAT, valueuom VARCHAR(20), ref_range_lower FLOAT, ref_range_upper FLOAT, flag VARCHAR(10), priority VARCHAR(20));
CREATE TABLE d_labitems (itemid INT, label VARCHAR(100), fluid VARCHAR(50), category VARCHAR(50));
CREATE TABLE prescriptions (subject_id INT, hadm_id INT, starttime TIMESTAMP, stoptime TIMESTAMP, drug_type VARCHAR(20), drug VARCHAR(200), dose_val_rx VARCHAR(50), dose_unit_rx VARCHAR(50), route VARCHAR(50));
CREATE TABLE transfers (subject_id INT, hadm_id INT, transfer_id INT, eventtype VARCHAR(20), careunit VARCHAR(60), intime TIMESTAMP, outtime TIMESTAMP);
CREATE TABLE services (subject_id INT, hadm_id INT, transfertime TIMESTAMP, prev_service VARCHAR(20), curr_service VARCHAR(20));
CREATE TABLE microbiologyevents (microevent_id BIGINT, subject_id INT, hadm_id INT, chartdate DATE, spec_type_desc VARCHAR(100), org_name VARCHAR(100), interpretation VARCHAR(5));
-- JOIN patients ↔ admissions: ON subject_id
-- JOIN admissions ↔ diagnoses_icd: ON hadm_id
-- JOIN diagnoses_icd ↔ d_icd_diagnoses: ON icd_code AND icd_version
-- JOIN labevents ↔ d_labitems: ON itemid
-- JOIN procedures_icd ↔ d_icd_procedures: ON icd_code AND icd_version
-- Tính LOS (ngày): EXTRACT(EPOCH FROM (dischtime::TIMESTAMP - admittime::TIMESTAMP))/86400
"""


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
        results = col.query(query_texts=[question], n_results=n_results)
        codes = []
        lines = []
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            codes.append({
                "icd_code": meta["icd_code"],
                "icd_version": meta["icd_version"],
                "long_title": doc,
            })
            lines.append(
                f"  - Bệnh '{doc[:80]}' → ICD-{meta['icd_version']} code: '{meta['icd_code']}'"
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

        for meta in results["metadatas"][0]:
            tbl = meta["table"]
            if tbl not in tables_found:
                tables_found.append(tbl)
            ddl_parts.append(f"-- [{tbl}] {meta['description_vi']}\n{meta['ddl']}")

        all_schema = json.load(open("mimic_schema.json", encoding="utf-8"))
        core_ddls = {s["table"]: s for s in all_schema}
        core_parts = []
        for tbl in CORE_TABLES:
            if tbl in core_ddls and not any(tbl in p for p in ddl_parts):
                s = core_ddls[tbl]
                core_parts.append(f"-- [{tbl}] {s['description_vi']}\n{s['ddl']}")

        all_ddl = "\n\n".join(core_parts + ddl_parts)
        return {"text": all_ddl, "tables": tables_found, "found": True}
    except Exception as e:
        return {"text": _STATIC_SCHEMA, "tables": list(CORE_TABLES), "found": False}


# ══════════════════════════════════════════════════════════════
# TẦNG 3 – EXAMPLE RETRIEVAL
# ══════════════════════════════════════════════════════════════
def retrieve_examples(question: str, n_results: int = 3) -> dict:
    """
    Trả về dict:
      text   – chuỗi các cặp Q-SQL mẫu (cho prompt)
      items  – list[dict] với keys: question_vi, sql
      found  – bool
    """
    try:
        col = _get_collection("sql_examples")
        results = col.query(query_texts=[question], n_results=n_results)
        items, lines = [], []
        for i, meta in enumerate(results["metadatas"][0], 1):
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
    "  3. Nếu câu hỏi nhắc đến bệnh, BẮT BUỘC dùng mã ICD đã tra cứu trong mệnh đề WHERE.\n"
    "  4. JOIN luôn dùng điều kiện đúng: diagnoses_icd ↔ d_icd_diagnoses phải JOIN cả icd_code AND icd_version.\n"
    "  5. Tính thời gian nằm viện bằng: EXTRACT(EPOCH FROM (dischtime::TIMESTAMP - admittime::TIMESTAMP))/86400.\n"
    "  6. Các cột thời gian (admittime, dischtime, charttime, starttime, stoptime) lưu dạng TEXT, "
    "luôn CAST sang TIMESTAMP trước khi dùng: cột::TIMESTAMP.\n"
    "  7. Dùng ILIKE thay cho LIKE khi so sánh chuỗi (không phân biệt hoa thường)."
)


def build_prompt(question: str, mode: str = "full") -> tuple[str, dict]:
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
        ctx["examples"] = retrieve_examples(question)
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
def _call_llm(messages: list[dict]) -> str:
    """Gọi Groq LLM, trả về raw content."""
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=0,
        max_tokens=1024,
    )
    return response.choices[0].message.content.strip()


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
def generate_sql(question: str, mode: str = "full") -> tuple[str, dict]:
    """Trả về (sql_string, context_dict). Gọi LLM 1 lần."""
    user_prompt, ctx = build_prompt(question, mode)
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
    on_attempt: callable = None,
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
    user_prompt, ctx = build_prompt(question, mode)

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
            df = run_query(sql)
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
# MULTI-TURN: QUERY REWRITING
# ══════════════════════════════════════════════════════════════
_REWRITE_SYSTEM = (
    "Bạn là trợ lý viết lại câu hỏi. "
    "Nhiệm vụ: nếu câu hỏi mới bị thiếu ngữ cảnh (dùng đại từ 'đó', 'trong số đó', "
    "'họ', 'bệnh nhân đó', 'kết quả trên'...), hãy viết lại thành câu hoàn chỉnh, "
    "độc lập, dựa trên lịch sử hội thoại. "
    "Nếu câu đã đủ ý, trả về nguyên văn câu hỏi đó. "
    "CHỈ trả về câu hỏi đã viết lại, không giải thích gì thêm."
)


def rewrite_question(question: str, chat_history: list[dict]) -> str:
    """
    Viết lại câu hỏi để giải quyết coreference / ellipsis trong multi-turn.

    chat_history: list[dict] với keys "role" ("user"/"assistant") và "content".
                  Chỉ dùng 6 message gần nhất (3 lượt) để tiết kiệm token.

    Trả về câu hỏi đã viết lại (hoặc nguyên văn nếu đã đầy đủ).
    """
    if not chat_history:
        return question

    recent = chat_history[-6:]
    history_str = "\n".join(
        f"{'Người dùng' if m['role'] == 'user' else 'Hệ thống'}: {m['content'][:200]}"
        for m in recent
    )

    prompt = (
        f"Lịch sử hội thoại:\n{history_str}\n\n"
        f"Câu hỏi mới của người dùng: \"{question}\"\n\n"
        f"Câu hỏi đã viết lại:"
    )

    rewritten = _call_llm([
        {"role": "system", "content": _REWRITE_SYSTEM},
        {"role": "user",   "content": prompt},
    ])

    # Xóa dấu ngoặc kép bao quanh nếu LLM thêm vào
    if rewritten.startswith('"') and rewritten.endswith('"'):
        rewritten = rewritten[1:-1]

    return rewritten.strip() or question


# ══════════════════════════════════════════════════════════════
# THỰC THI SQL
# ══════════════════════════════════════════════════════════════
def run_query(sql: str) -> pd.DataFrame:
    """Thực thi SQL trên PostgreSQL, trả về DataFrame."""
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)


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
    else:
        print(f"\nThất bại sau {result['attempts']} lần thử.")


if __name__ == "__main__":
    ask_medical_question(
        "Có bao nhiêu bệnh nhân bị viêm phổi nhập viện qua cấp cứu?",
        mode="full",
    )
