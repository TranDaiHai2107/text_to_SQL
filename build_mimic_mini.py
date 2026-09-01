"""
Script nạp dữ liệu MIMIC-IV vào PostgreSQL.
Tạo subset ~500 bệnh nhân với 10 bảng nghiệp vụ quan trọng.
Chạy một lần duy nhất để khởi tạo database.
"""

import sys
import pandas as pd
from sqlalchemy import create_engine, text

# Đảm bảo stdout dùng UTF-8 trên mọi terminal Windows
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_USER = "postgres"
DB_PASS = "password123"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "mimiciv"
DATA_DIR = "D:/Github/text_to_SQL/mimic-iv-3.1/hosp"

N_PATIENTS = 500
RANDOM_STATE = 42

engine = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")


def load_table(df, table_name):
    df.to_sql(table_name, engine, if_exists="replace", index=False)
    print(f"  [OK] {table_name}: {len(df):,} rows")


def build_mimic_mini():
    print("=" * 55)
    print("  Building MIMIC-Mini Dataset")
    print("=" * 55)

    # ── BẢNG 1: PATIENTS ──────────────────────────────────────
    print("\n[1/10] patients ...")
    df_patients = pd.read_csv(f"{DATA_DIR}/patients.csv.gz", compression="gzip")
    df_patients_mini = df_patients.sample(n=N_PATIENTS, random_state=RANDOM_STATE)
    subject_ids = set(df_patients_mini["subject_id"].tolist())
    load_table(df_patients_mini, "patients")

    # ── BẢNG 2: ADMISSIONS ────────────────────────────────────
    print("\n[2/10] admissions ...")
    df_adm = pd.read_csv(f"{DATA_DIR}/admissions.csv.gz", compression="gzip")
    df_adm_mini = df_adm[df_adm["subject_id"].isin(subject_ids)]
    load_table(df_adm_mini, "admissions")
    hadm_ids = set(df_adm_mini["hadm_id"].tolist())

    # ── BẢNG 3: DIAGNOSES_ICD ─────────────────────────────────
    print("\n[3/10] diagnoses_icd ...")
    df_diag = pd.read_csv(f"{DATA_DIR}/diagnoses_icd.csv.gz", compression="gzip")
    df_diag_mini = df_diag[df_diag["subject_id"].isin(subject_ids)]
    load_table(df_diag_mini, "diagnoses_icd")

    # ── BẢNG 4: D_ICD_DIAGNOSES (từ điển - toàn bộ) ──────────
    print("\n[4/10] d_icd_diagnoses ...")
    df_d_icd = pd.read_csv(f"{DATA_DIR}/d_icd_diagnoses.csv.gz", compression="gzip")
    load_table(df_d_icd, "d_icd_diagnoses")

    # ── BẢNG 5: PROCEDURES_ICD ────────────────────────────────
    print("\n[5/10] procedures_icd ...")
    df_proc = pd.read_csv(f"{DATA_DIR}/procedures_icd.csv.gz", compression="gzip")
    df_proc_mini = df_proc[df_proc["subject_id"].isin(subject_ids)]
    load_table(df_proc_mini, "procedures_icd")

    # ── BẢNG 6: D_ICD_PROCEDURES (từ điển - toàn bộ) ─────────
    print("\n[6/10] d_icd_procedures ...")
    df_d_proc = pd.read_csv(f"{DATA_DIR}/d_icd_procedures.csv.gz", compression="gzip")
    load_table(df_d_proc, "d_icd_procedures")

    # ── BẢNG 7: LABEVENTS (đọc chunk để tiết kiệm RAM) ───────
    # labevents.csv.gz có ~158M dòng, không thể load 1 lần vào RAM.
    # Đọc từng chunk 200k dòng, chỉ giữ dòng khớp subject_id.
    print("\n[7/10] labevents  (chunk-read, lọc subject_id trong từng batch) ...")
    LAB_COLS = ["labevent_id", "subject_id", "hadm_id", "specimen_id",
                "itemid", "charttime", "storetime", "value",
                "valuenum", "valueuom", "ref_range_lower", "ref_range_upper",
                "flag", "priority", "comments"]
    CHUNK_SIZE = 200_000

    chunks_kept = []
    total_read = 0
    for chunk in pd.read_csv(
        f"{DATA_DIR}/labevents.csv.gz",
        compression="gzip",
        usecols=LAB_COLS,
        chunksize=CHUNK_SIZE,
        low_memory=False,
    ):
        total_read += len(chunk)
        filtered = chunk[chunk["subject_id"].isin(subject_ids)]
        if not filtered.empty:
            chunks_kept.append(filtered)
        print(f"  Đọc {total_read:,} dòng | Giữ {sum(len(c) for c in chunks_kept):,}",
              end="\r")

    df_lab_mini = pd.concat(chunks_kept, ignore_index=True) if chunks_kept else pd.DataFrame(columns=LAB_COLS)

    # Giữ 50 itemid phổ biến nhất để tránh bảng quá lớn
    if not df_lab_mini.empty:
        top_itemids = df_lab_mini["itemid"].value_counts().head(50).index
        df_lab_mini = df_lab_mini[df_lab_mini["itemid"].isin(top_itemids)]

    print()  # xuống dòng sau \r
    load_table(df_lab_mini, "labevents")

    # ── BẢNG 8: D_LABITEMS (từ điển - toàn bộ) ───────────────
    print("\n[8/10] d_labitems ...")
    df_lab_items = pd.read_csv(f"{DATA_DIR}/d_labitems.csv.gz", compression="gzip")
    load_table(df_lab_items, "d_labitems")

    # ── BẢNG 9: PRESCRIPTIONS ────────────────────────────────
    print("\n[9/10] prescriptions ...")
    df_rx = pd.read_csv(f"{DATA_DIR}/prescriptions.csv.gz", compression="gzip", low_memory=False)
    df_rx_mini = df_rx[df_rx["subject_id"].isin(subject_ids)]
    load_table(df_rx_mini, "prescriptions")

    # ── BẢNG 10: TRANSFERS ───────────────────────────────────
    print("\n[10/10] transfers ...")
    df_tr = pd.read_csv(f"{DATA_DIR}/transfers.csv.gz", compression="gzip")
    df_tr_mini = df_tr[df_tr["subject_id"].isin(subject_ids)]
    load_table(df_tr_mini, "transfers")

    # ── BẢNG 11: SERVICES ────────────────────────────────────
    print("\n[11/11] services ...")
    df_svc = pd.read_csv(f"{DATA_DIR}/services.csv.gz", compression="gzip")
    df_svc_mini = df_svc[df_svc["subject_id"].isin(subject_ids)]
    load_table(df_svc_mini, "services")

    # ── BẢNG 12: MICROBIOLOGYEVENTS ──────────────────────────
    print("\n[12/12] microbiologyevents ...")
    df_micro = pd.read_csv(f"{DATA_DIR}/microbiologyevents.csv.gz", compression="gzip", low_memory=False)
    df_micro_mini = df_micro[df_micro["subject_id"].isin(subject_ids)]
    load_table(df_micro_mini, "microbiologyevents")

    # ── TẠO INDEX để tăng tốc JOIN ───────────────────────────
    print("\nTạo index tăng tốc JOIN ...")
    with engine.connect() as conn:
        idx_sqls = [
            "CREATE INDEX IF NOT EXISTS idx_adm_subject ON admissions(subject_id)",
            "CREATE INDEX IF NOT EXISTS idx_diag_hadm   ON diagnoses_icd(hadm_id)",
            "CREATE INDEX IF NOT EXISTS idx_diag_icd    ON diagnoses_icd(icd_code, icd_version)",
            "CREATE INDEX IF NOT EXISTS idx_proc_hadm   ON procedures_icd(hadm_id)",
            "CREATE INDEX IF NOT EXISTS idx_lab_subject ON labevents(subject_id)",
            "CREATE INDEX IF NOT EXISTS idx_lab_itemid  ON labevents(itemid)",
            "CREATE INDEX IF NOT EXISTS idx_rx_subject  ON prescriptions(subject_id)",
            "CREATE INDEX IF NOT EXISTS idx_tr_subject  ON transfers(subject_id)",
        ]
        for sql in idx_sqls:
            conn.execute(text(sql))
        conn.commit()
    print("  [OK] Indexes created.")

    print("\n" + "=" * 55)
    print("  DONE! Database ready. Open DataGrip to verify.")
    print("=" * 55)


if __name__ == "__main__":
    build_mimic_mini()
