"""
Giao diện Streamlit – Chat-based Text-to-SQL Y tế (MIMIC-IV)
Tính năng:
  - RAG đa tầng (ICD + Schema + Examples)
  - Agentic Self-Correction (tự sửa SQL lỗi)
  - Multi-turn Context (viết lại câu hỏi từ lịch sử chat)
Chạy: python -m streamlit run app.py
"""

import json
import time
import pandas as pd
import streamlit as st

from rag_engine import (
    generate_sql_with_correction,
    interpret_result,
    rewrite_question,
    retrieve_icd_codes,
    retrieve_schema,
    retrieve_examples,
)

# ── Cấu hình trang ────────────────────────────────────────────
st.set_page_config(
    page_title="MIMIC-IV Text-to-SQL RAG",
    page_icon="🏥",
    layout="wide",
)

# ── CSS ────────────────────────────────────────────────────────
st.markdown("""
<style>
.rag-tag {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
    margin-right: 4px;
}
.tag-icd     { background:#fde68a; color:#92400e; }
.tag-schema  { background:#bfdbfe; color:#1e3a5f; }
.tag-example { background:#bbf7d0; color:#14532d; }
.tag-rewrite { background:#e9d5ff; color:#581c87; }
.tag-fix     { background:#fed7aa; color:#9a3412; }
</style>
""", unsafe_allow_html=True)

# ── Session State ─────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.header("🏥 MIMIC-IV Text-to-SQL")
    st.caption("RAG đa tầng · Self-Correction · Multi-turn")

    st.divider()
    st.subheader("⚙️ Cấu hình")
    rag_mode = st.selectbox(
        "Mode RAG:",
        options=["full", "base", "icd", "schema", "examples"],
        index=0,
        help=(
            "full: 3 tầng RAG (khuyến nghị)\n"
            "base: không RAG\n"
            "icd / schema / examples: ablation từng thành phần"
        ),
    )
    max_retries = st.slider("Số lần tự sửa tối đa", 0, 3, 2)

    st.divider()
    st.subheader("📐 Kiến trúc Pipeline")
    st.markdown("""
    ```
    Câu hỏi (tiếng Việt)
         │
         ├► [Rewrite] Viết lại nếu
         │   thiếu ngữ cảnh multi-turn
         │
         ├► [RAG-1] ICD Dictionary
         ├► [RAG-2] Schema Dictionary
         ├► [RAG-3] SQL Examples
         │
         ▼
       LLM (Text-to-SQL)
         │
         ├► PostgreSQL
         │     ├─ OK → Kết quả
         │     └─ Error → Self-Correction
         │
         ▼
       [SQL-to-Text]
       Diễn giải kết quả → Tiếng Việt
         │
         ▼
       Câu trả lời + SQL + Bảng + Biểu đồ
    ```
    """)

    st.divider()
    with st.expander("📊 Thông tin hệ thống"):
        from rag_engine import LLM_MODEL
        st.markdown(f"""
        | Thành phần | Chi tiết |
        |---|---|
        | **Database** | PostgreSQL (MIMIC-IV Subset) |
        | **Vector DB** | ChromaDB – 3 collections |
        | **LLM** | {LLM_MODEL} (Groq LPU) |
        | **Self-Correction** | Tối đa 2 lần retry |
        | **Multi-turn** | Query Rewriting via LLM |
        | **SQL-to-Text** | Natural Language Generation |
        """)

    st.divider()
    if st.button("🗑️ Xóa lịch sử chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ── Header ────────────────────────────────────────────────────
st.title("🏥 Trợ lý Truy vấn Dữ liệu Y tế (MIMIC-IV)")
st.caption(
    f"Text-to-SQL chuyên biệt · RAG đa tầng · Self-Correction · Multi-turn | "
    f"Mode: **{rag_mode.upper()}**"
)

# ── Câu hỏi mẫu ──────────────────────────────────────────────
SAMPLE_QUESTIONS = [
    "Có bao nhiêu bệnh nhân bị viêm phổi trong database?",
    "Tính tỷ lệ tử vong của bệnh nhân suy tim.",
    "Liệt kê 10 loại thuốc được kê nhiều nhất.",
    "Tìm bệnh nhân nữ trên 65 tuổi bị đái tháo đường type 2.",
    "Tính thời gian nằm viện trung bình theo loại nhập viện.",
    "Có bao nhiêu bệnh nhân tái nhập viện trong vòng 30 ngày?",
]

def _try_auto_chart(df: pd.DataFrame):
    """Tự động vẽ bar chart nếu DataFrame có 1 cột chữ + 1-2 cột số, max 20 hàng."""
    if df is None or df.empty or len(df) > 20 or len(df) < 2:
        return
    num_cols = df.select_dtypes(include="number").columns.tolist()
    str_cols = df.select_dtypes(exclude="number").columns.tolist()
    if len(str_cols) == 1 and 1 <= len(num_cols) <= 3:
        chart_df = df.set_index(str_cols[0])[num_cols]
        st.bar_chart(chart_df, use_container_width=True)


# ── Hiển thị lịch sử chat ────────────────────────────────────
for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar="🧑‍⚕️" if msg["role"] == "user" else "🤖"):
        # Hiển thị câu hỏi (user) hoặc NL answer (assistant)
        if msg["role"] == "assistant" and msg.get("nl_answer"):
            st.markdown(f"""
            <div style="
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 16px 20px;
                border-radius: 12px;
                margin: 8px 0 16px 0;
                font-size: 1.05rem;
                line-height: 1.6;
                box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
            ">
                💬 {msg["nl_answer"]}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(msg["display"])

        if msg.get("rewritten_q"):
            st.markdown(
                f'<span class="rag-tag tag-rewrite">REWRITE</span> '
                f'Câu hỏi đã mở rộng: *{msg["rewritten_q"]}*',
                unsafe_allow_html=True,
            )

        if msg.get("rag_info"):
            with st.expander("🔍 Chi tiết RAG Retrieval"):
                st.markdown(msg["rag_info"], unsafe_allow_html=True)

        if msg.get("correction_info"):
            st.markdown(msg["correction_info"], unsafe_allow_html=True)

        if msg.get("sql"):
            with st.expander("🔍 Xem câu SQL đã sinh"):
                st.code(msg["sql"], language="sql")

        if msg.get("df") is not None:
            df_display = msg["df"]
            if not df_display.empty:
                st.dataframe(df_display, use_container_width=True, height=min(350, 40 + 35 * len(df_display)))

                # Tự động vẽ biểu đồ nếu phù hợp
                _try_auto_chart(df_display)

                csv = df_display.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇️ Tải CSV",
                    data=csv,
                    file_name="query_result.csv",
                    mime="text/csv",
                    key=f"dl_{msg.get('ts', 0)}",
                )
            else:
                st.warning("Truy vấn thành công nhưng không có dữ liệu phù hợp.")


# ── Xử lý câu hỏi mới ───────────────────────────────────────
def _build_chat_history_for_rewrite() -> list[dict]:
    """Chuyển session messages thành format cho rewrite_question (chỉ text ngắn)."""
    out = []
    for m in st.session_state.messages:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["display"]})
        else:
            summary = m["display"][:200]
            out.append({"role": "assistant", "content": summary})
    return out


def process_question(question: str):
    t_start = time.time()

    # ── BƯỚC 0: Multi-turn Rewrite ─────────────────────────────
    chat_history = _build_chat_history_for_rewrite()
    rewritten = question
    did_rewrite = False

    if chat_history:
        rewritten = rewrite_question(question, chat_history)
        did_rewrite = (rewritten.strip().lower() != question.strip().lower())

    effective_q = rewritten if did_rewrite else question

    # ── Thêm message user vào chat ─────────────────────────────
    user_msg = {"role": "user", "display": question, "ts": time.time()}
    if did_rewrite:
        user_msg["rewritten_q"] = rewritten
    st.session_state.messages.append(user_msg)

    with st.chat_message("user", avatar="🧑‍⚕️"):
        st.markdown(question)
        if did_rewrite:
            st.markdown(
                f'<span class="rag-tag tag-rewrite">REWRITE</span> '
                f'Câu hỏi đã mở rộng: *{rewritten}*',
                unsafe_allow_html=True,
            )

    # ── BƯỚC 1-3: RAG + LLM + Self-Correction ─────────────────
    with st.chat_message("assistant", avatar="🤖"):
        with st.status("Đang xử lý...", expanded=True) as status:

            # RAG info preview
            rag_lines = []
            if rag_mode in ("icd", "full"):
                icd_r = retrieve_icd_codes(effective_q)
                if icd_r["found"]:
                    for c in icd_r["codes"]:
                        rag_lines.append(
                            f'<span class="rag-tag tag-icd">ICD</span> '
                            f'`{c["icd_code"]}` (v{c["icd_version"]}) – {c["long_title"][:60]}'
                        )
            if rag_mode in ("schema", "full"):
                sch_r = retrieve_schema(effective_q)
                tables_str = ", ".join(f"`{t}`" for t in sch_r["tables"])
                rag_lines.append(
                    f'<span class="rag-tag tag-schema">SCHEMA</span> Bảng: {tables_str}'
                )
            if rag_mode in ("examples", "full"):
                ex_r = retrieve_examples(effective_q)
                if ex_r["found"]:
                    for i, ex in enumerate(ex_r["items"][:3], 1):
                        rag_lines.append(
                            f'<span class="rag-tag tag-example">EX-{i}</span> '
                            f'{ex["question_vi"][:60]}'
                        )

            if rag_lines:
                st.markdown("**🔍 RAG Retrieval:**")
                for line in rag_lines:
                    st.markdown(line, unsafe_allow_html=True)
            rag_info_str = "<br>".join(rag_lines) if rag_lines else ""

            # LLM + Self-Correction
            st.markdown("**🤖 LLM đang sinh SQL...**")
            result = generate_sql_with_correction(
                effective_q,
                mode=rag_mode,
                max_retries=max_retries,
            )

            # Hiển thị correction history
            correction_info = ""
            if result["attempts"] > 1:
                correction_parts = []
                for h in result["history"]:
                    if h["error"]:
                        correction_parts.append(
                            f'<span class="rag-tag tag-fix">LẦN {h["attempt"]}</span> '
                            f'SQL lỗi → `{h["error"][:120]}...`'
                        )
                correction_parts.append(
                    f'<span class="rag-tag tag-fix">LẦN {result["attempts"]}</span> '
                    f'{"Đã tự sửa thành công!" if result["success"] else "Vẫn lỗi sau khi sửa."}'
                )
                correction_info = "<br>".join(correction_parts)
                st.markdown("**🔧 Self-Correction:**")
                st.markdown(correction_info, unsafe_allow_html=True)

            if result["success"]:
                elapsed = round(time.time() - t_start, 2)
                attempt_note = ""
                if result["attempts"] > 1:
                    attempt_note = f" (tự sửa {result['attempts']-1} lần)"
                status.update(
                    label=f"Hoàn tất trong {elapsed}s{attempt_note}",
                    state="complete",
                    expanded=True,
                )
            else:
                status.update(label="Có lỗi xảy ra", state="error", expanded=True)

        # Hiển thị SQL + kết quả
        sql = result["sql"]
        df = result.get("df")
        nl_answer = None

        display_text = ""
        if result["success"] and df is not None:
            if df.empty:
                nl_answer = "Truy vấn thành công nhưng không có dữ liệu phù hợp."
                display_text = nl_answer
                st.warning(display_text)
            else:
                # SQL-to-Text: diễn giải kết quả thành ngôn ngữ tự nhiên
                with st.spinner("📝 Đang diễn giải kết quả..."):
                    nl_answer = interpret_result(effective_q, sql, df)

                # Hiển thị câu trả lời tự nhiên NỔI BẬT nhất
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 16px 20px;
                    border-radius: 12px;
                    margin: 8px 0 16px 0;
                    font-size: 1.05rem;
                    line-height: 1.6;
                    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
                ">
                    💬 {nl_answer}
                </div>
                """, unsafe_allow_html=True)

                # Hiển thị SQL (co lại trong expander)
                with st.expander("🔍 Xem câu SQL đã sinh", expanded=False):
                    st.code(sql, language="sql")

                elapsed = round(time.time() - t_start, 2)
                c1, c2, c3 = st.columns(3)
                c1.metric("Số dòng", f"{len(df):,}")
                c2.metric("Số cột", len(df.columns))
                c3.metric("Thời gian", f"{elapsed}s")

                st.dataframe(df, use_container_width=True, height=min(350, 40 + 35 * len(df)))
                _try_auto_chart(df)

                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇️ Tải CSV",
                    data=csv,
                    file_name="query_result.csv",
                    mime="text/csv",
                    key=f"dl_new_{time.time()}",
                )

                display_text = nl_answer
        else:
            last_err = result["history"][-1]["error"] if result["history"] else "Unknown"
            display_text = f"Lỗi sau {result['attempts']} lần thử: {last_err[:200]}"
            st.code(sql, language="sql")
            st.error(display_text)

        # Lưu assistant message
        st.session_state.messages.append({
            "role": "assistant",
            "display": display_text,
            "nl_answer": nl_answer,
            "sql": sql,
            "df": df,
            "rag_info": rag_info_str,
            "correction_info": correction_info,
            "ts": time.time(),
        })


# ── Chat Input ────────────────────────────────────────────────
sample_col1, sample_col2, sample_col3 = st.columns(3)
cols = [sample_col1, sample_col2, sample_col3]
for i, sq in enumerate(SAMPLE_QUESTIONS[:6]):
    col = cols[i % 3]
    if col.button(sq[:40] + "...", key=f"sample_{i}", use_container_width=True):
        process_question(sq)
        st.rerun()

st.divider()

if prompt := st.chat_input("Đặt câu hỏi y khoa (hỗ trợ hội thoại đa lượt)..."):
    process_question(prompt)
    st.rerun()

# ── Kết quả đánh giá (nếu có) ────────────────────────────────
try:
    with open("evaluate_results.json", encoding="utf-8") as f:
        eval_data = json.load(f)

    with st.expander("📊 Kết quả đánh giá Ablation (từ evaluate.py)"):
        st.caption(f"Thời điểm: {eval_data.get('timestamp', 'N/A')} · "
                   f"Dataset: {eval_data.get('dataset_size', '?')} câu")

        metrics = eval_data.get("metrics", {})
        if metrics:
            rows = []
            for mode_name, m in metrics.items():
                rows.append({
                    "Mode": mode_name.upper(),
                    "VSR (%)": m.get("vsr"),
                    "EX (%)": m.get("ex"),
                    "EX đúng/tổng": f"{m.get('ex_count', 0)}/{m.get('ex_eligible', 0)}",
                    "Latency TB (s)": m.get("avg_latency_s"),
                })
            st.dataframe(
                pd.DataFrame(rows).set_index("Mode"),
                use_container_width=True,
            )
            chart_df = pd.DataFrame({
                "VSR (%)": {r["Mode"]: r["VSR (%)"] for r in rows},
                "EX (%)":  {r["Mode"]: r["EX (%)"]  for r in rows if r["EX (%)"] is not None},
            })
            st.bar_chart(chart_df, use_container_width=True)

except FileNotFoundError:
    pass
