"""
Script nạp dữ liệu MIMIC-IV vào PostgreSQL.
Tạo subset ~500 bệnh nhân với toàn bộ 31 bảng (22 hosp + 9 icu).
Chạy một lần duy nhất để khởi tạo database.
"""

import json
import os
import random
import re
import sys
import pandas as pd
from sqlalchemy import Date, DateTime, create_engine, text
from sqlglot import exp, parse_one

from config import EXAMPLES_FILE, MIMIC_DATA_DIR, TEST_FILE, database_url

# Đảm bảo stdout dùng UTF-8 trên mọi terminal Windows
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA_DIR = MIMIC_DATA_DIR / "hosp"
ICU_DIR = MIMIC_DATA_DIR / "icu"

N_PATIENTS = int(os.getenv("N_PATIENTS", "500"))
RANDOM_STATE = int(os.getenv("RANDOM_STATE", "42"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "200000"))

engine = create_engine(database_url(loader=True), pool_pre_ping=True, connect_args={"connect_timeout": 5})

DATE_COLUMNS = {
    "patients": {"dod"},
    "procedures_icd": {"chartdate"},
    "microbiologyevents": {"chartdate", "storedate"},
    "hcpcsevents": {"chartdate"},
    "omr": {"chartdate"},
}
TIMESTAMP_COLUMNS = {
    "admissions": {"admittime", "dischtime", "deathtime", "edregtime", "edouttime"},
    "transfers": {"intime", "outtime"},
    "services": {"transfertime"},
    "labevents": {"charttime", "storetime"},
    "prescriptions": {"starttime", "stoptime"},
    "microbiologyevents": {"charttime", "storetime"},
    "pharmacy": {"starttime", "stoptime", "entertime", "verifiedtime", "expirationdate"},
    "poe": {"ordertime"},
    "emar": {"charttime", "scheduletime", "storetime"},
    "icustays": {"intime", "outtime"},
    "chartevents": {"charttime", "storetime"},
    "inputevents": {"starttime", "endtime", "storetime"},
    "outputevents": {"charttime", "storetime"},
    "datetimeevents": {"charttime", "storetime", "value"},
    "procedureevents": {"starttime", "endtime", "storetime"},
    "ingredientevents": {"starttime", "endtime", "storetime"},
}


def _concat_or_empty(chunks: list[pd.DataFrame], source_path) -> pd.DataFrame:
    if chunks:
        return pd.concat(chunks, ignore_index=True)
    return pd.read_csv(source_path, compression="gzip", nrows=0)


def _priority_icd_patterns() -> tuple[set[str], set[str]]:
    """Extract ICD literals used by examples/tests for coverage-aware sampling."""
    sql_texts = []
    for path, field in ((TEST_FILE, "gold_sql"), (EXAMPLES_FILE, "sql")):
        with path.open(encoding="utf-8") as handle:
            sql_texts.extend(item.get(field, "") for item in json.load(handle))
    exact: set[str] = set()
    prefixes: set[str] = set()
    for sql in sql_texts:
        tree = parse_one(sql, read="postgres")
        for comparison in tree.find_all(exp.EQ):
            pairs = ((comparison.this, comparison.expression), (comparison.expression, comparison.this))
            for column, literal in pairs:
                if isinstance(column, exp.Column) and column.name.lower() == "icd_code" and isinstance(literal, exp.Literal):
                    exact.add(str(literal.this))
        for predicate in tree.find_all(exp.In):
            if isinstance(predicate.this, exp.Column) and predicate.this.name.lower() == "icd_code":
                exact.update(
                    str(value.this) for value in predicate.expressions if isinstance(value, exp.Literal)
                )
        for predicate_type in (exp.Like, exp.ILike):
            for predicate in tree.find_all(predicate_type):
                if (
                    isinstance(predicate.this, exp.Column)
                    and predicate.this.name.lower() == "icd_code"
                    and isinstance(predicate.expression, exp.Literal)
                ):
                    value = str(predicate.expression.this)
                    if value.endswith("%"):
                        prefixes.add(value[:-1])
    return exact, prefixes


def _sample_subject_ids(
    patients: pd.DataFrame,
    diagnoses: pd.DataFrame,
    icu_stays: pd.DataFrame,
) -> set[int]:
    """Sample reproducibly while retaining coverage for benchmark ICDs and ICU."""
    rng = random.Random(RANDOM_STATE)
    available = set(patients["subject_id"].astype(int))
    selected: set[int] = set()
    exact_codes, prefixes = _priority_icd_patterns()

    normalized_codes = diagnoses["icd_code"].astype(str).str.upper().str.replace(".", "", regex=False)
    for code in sorted(exact_codes):
        normalized = code.upper().replace(".", "")
        candidates = diagnoses.loc[normalized_codes == normalized, "subject_id"].dropna().astype(int).unique().tolist()
        rng.shuffle(candidates)
        selected.update(candidates[:5])
    for prefix in sorted(prefixes):
        normalized = prefix.upper().replace(".", "")
        candidates = diagnoses.loc[normalized_codes.str.startswith(normalized), "subject_id"].dropna().astype(int).unique().tolist()
        rng.shuffle(candidates)
        selected.update(candidates[:5])

    icu_candidates = icu_stays["subject_id"].dropna().astype(int).unique().tolist()
    rng.shuffle(icu_candidates)
    selected.update(icu_candidates[: min(100, max(20, N_PATIENTS // 5))])
    selected &= available

    if len(selected) > N_PATIENTS:
        selected = set(rng.sample(sorted(selected), N_PATIENTS))
    remaining = sorted(available - selected)
    selected.update(rng.sample(remaining, N_PATIENTS - len(selected)))
    return selected


def load_table(df, table_name):
    """Load one table through a staging table, preserving real date/time types."""
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", table_name):
        raise ValueError(f"Unsafe table name: {table_name}")
    if len(df.columns) == 0:
        raise ValueError(f"Cannot create {table_name}: source columns were not detected")

    # Callers often pass a filtered DataFrame view. Work on an owned copy so
    # date conversion is deterministic and does not trigger chained-assignment
    # warnings during long-running imports.
    df = df.copy()

    dtype = {}
    for column in DATE_COLUMNS.get(table_name, set()) & set(df.columns):
        df[column] = pd.to_datetime(df[column], errors="coerce")
        dtype[column] = Date()
    for column in TIMESTAMP_COLUMNS.get(table_name, set()) & set(df.columns):
        df[column] = pd.to_datetime(df[column], errors="coerce")
        dtype[column] = DateTime()

    staging = f"_loading_{table_name}"
    df.to_sql(staging, engine, if_exists="replace", index=False, dtype=dtype, chunksize=10_000)
    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{table_name}"'))
        conn.execute(text(f'ALTER TABLE "{staging}" RENAME TO "{table_name}"'))
    print(f"  [OK] {table_name}: {len(df):,} rows")


def build_mimic_mini():
    print("=" * 60)
    print("  Building MIMIC-IV Full Dataset (31 tables)")
    print("=" * 60)

    # ══════════════════════════════════════════════════════════
    # HOSP MODULE — 22 bảng
    # ══════════════════════════════════════════════════════════

    # ── BẢNG 1: PATIENTS ──────────────────────────────────────
    print("\n[1/31] patients ...")
    df_patients = pd.read_csv(f"{DATA_DIR}/patients.csv.gz", compression="gzip")
    if N_PATIENTS > len(df_patients):
        raise ValueError(f"N_PATIENTS={N_PATIENTS} exceeds source size {len(df_patients)}")
    # Load the two small index tables first so the subset contains benchmark
    # disease codes and a useful ICU cohort instead of being purely random.
    df_diag = pd.read_csv(f"{DATA_DIR}/diagnoses_icd.csv.gz", compression="gzip")
    df_icu = pd.read_csv(f"{ICU_DIR}/icustays.csv.gz", compression="gzip")
    subject_ids = _sample_subject_ids(df_patients, df_diag, df_icu)
    df_patients_mini = df_patients[df_patients["subject_id"].isin(subject_ids)].copy()
    load_table(df_patients_mini, "patients")

    # ── BẢNG 2: ADMISSIONS ────────────────────────────────────
    print("\n[2/31] admissions ...")
    df_adm = pd.read_csv(f"{DATA_DIR}/admissions.csv.gz", compression="gzip")
    df_adm_mini = df_adm[df_adm["subject_id"].isin(subject_ids)]
    load_table(df_adm_mini, "admissions")

    # ── BẢNG 3: DIAGNOSES_ICD ─────────────────────────────────
    print("\n[3/31] diagnoses_icd ...")
    df_diag_mini = df_diag[df_diag["subject_id"].isin(subject_ids)]
    load_table(df_diag_mini, "diagnoses_icd")

    # ── BẢNG 4: D_ICD_DIAGNOSES (từ điển - toàn bộ) ──────────
    print("\n[4/31] d_icd_diagnoses ...")
    df_d_icd = pd.read_csv(f"{DATA_DIR}/d_icd_diagnoses.csv.gz", compression="gzip")
    load_table(df_d_icd, "d_icd_diagnoses")

    # ── BẢNG 5: PROCEDURES_ICD ────────────────────────────────
    print("\n[5/31] procedures_icd ...")
    df_proc = pd.read_csv(f"{DATA_DIR}/procedures_icd.csv.gz", compression="gzip")
    df_proc_mini = df_proc[df_proc["subject_id"].isin(subject_ids)]
    load_table(df_proc_mini, "procedures_icd")

    # ── BẢNG 6: D_ICD_PROCEDURES (từ điển - toàn bộ) ─────────
    print("\n[6/31] d_icd_procedures ...")
    df_d_proc = pd.read_csv(f"{DATA_DIR}/d_icd_procedures.csv.gz", compression="gzip")
    load_table(df_d_proc, "d_icd_procedures")

    # ── BẢNG 7: LABEVENTS (chunk-read do file rất lớn ~2.5GB) ─
    print("\n[7/31] labevents (chunk-read) ...")
    LAB_COLS = ["labevent_id", "subject_id", "hadm_id", "specimen_id",
                "itemid", "charttime", "storetime", "value",
                "valuenum", "valueuom", "ref_range_lower", "ref_range_upper",
                "flag", "priority", "comments"]
    chunks_kept = []
    total_read = 0
    for chunk in pd.read_csv(
        f"{DATA_DIR}/labevents.csv.gz",
        compression="gzip", usecols=LAB_COLS,
        chunksize=CHUNK_SIZE, low_memory=False,
    ):
        total_read += len(chunk)
        filtered = chunk[chunk["subject_id"].isin(subject_ids)]
        if not filtered.empty:
            chunks_kept.append(filtered)
        print(f"  Đọc {total_read:,} dòng | Giữ {sum(len(c) for c in chunks_kept):,}", end="\r")
    df_lab_mini = pd.concat(chunks_kept, ignore_index=True) if chunks_kept else pd.DataFrame(columns=LAB_COLS)
    print()
    load_table(df_lab_mini, "labevents")

    # ── BẢNG 8: D_LABITEMS (từ điển - toàn bộ) ───────────────
    print("\n[8/31] d_labitems ...")
    df_lab_items = pd.read_csv(f"{DATA_DIR}/d_labitems.csv.gz", compression="gzip")
    load_table(df_lab_items, "d_labitems")

    # ── BẢNG 9: PRESCRIPTIONS ────────────────────────────────
    print("\n[9/31] prescriptions ...")
    chunks_kept = []
    total_read = 0
    for chunk in pd.read_csv(
        f"{DATA_DIR}/prescriptions.csv.gz",
        compression="gzip", chunksize=CHUNK_SIZE, low_memory=False,
    ):
        total_read += len(chunk)
        filtered = chunk[chunk["subject_id"].isin(subject_ids)]
        if not filtered.empty:
            chunks_kept.append(filtered)
        print(f"  Đọc {total_read:,} dòng | Giữ {sum(len(c) for c in chunks_kept):,}", end="\r")
    df_rx_mini = _concat_or_empty(chunks_kept, DATA_DIR / "prescriptions.csv.gz")
    print()
    load_table(df_rx_mini, "prescriptions")

    # ── BẢNG 10: TRANSFERS ───────────────────────────────────
    print("\n[10/31] transfers ...")
    df_tr = pd.read_csv(f"{DATA_DIR}/transfers.csv.gz", compression="gzip")
    df_tr_mini = df_tr[df_tr["subject_id"].isin(subject_ids)]
    load_table(df_tr_mini, "transfers")

    # ── BẢNG 11: SERVICES ────────────────────────────────────
    print("\n[11/31] services ...")
    df_svc = pd.read_csv(f"{DATA_DIR}/services.csv.gz", compression="gzip")
    df_svc_mini = df_svc[df_svc["subject_id"].isin(subject_ids)]
    load_table(df_svc_mini, "services")

    # ── BẢNG 12: MICROBIOLOGYEVENTS ──────────────────────────
    print("\n[12/31] microbiologyevents ...")
    df_micro = pd.read_csv(f"{DATA_DIR}/microbiologyevents.csv.gz", compression="gzip", low_memory=False)
    df_micro_mini = df_micro[df_micro["subject_id"].isin(subject_ids)]
    load_table(df_micro_mini, "microbiologyevents")

    # ── BẢNG 13: DRGCODES ────────────────────────────────────
    print("\n[13/31] drgcodes ...")
    df_drg = pd.read_csv(f"{DATA_DIR}/drgcodes.csv.gz", compression="gzip")
    df_drg_mini = df_drg[df_drg["subject_id"].isin(subject_ids)]
    load_table(df_drg_mini, "drgcodes")

    # ── BẢNG 14: HCPCSEVENTS ─────────────────────────────────
    print("\n[14/31] hcpcsevents ...")
    df_hcpcs = pd.read_csv(f"{DATA_DIR}/hcpcsevents.csv.gz", compression="gzip")
    df_hcpcs_mini = df_hcpcs[df_hcpcs["subject_id"].isin(subject_ids)]
    load_table(df_hcpcs_mini, "hcpcsevents")

    # ── BẢNG 15: D_HCPCS (từ điển - toàn bộ) ─────────────────
    print("\n[15/31] d_hcpcs ...")
    df_d_hcpcs = pd.read_csv(f"{DATA_DIR}/d_hcpcs.csv.gz", compression="gzip")
    load_table(df_d_hcpcs, "d_hcpcs")

    # ── BẢNG 16: OMR ─────────────────────────────────────────
    print("\n[16/31] omr ...")
    df_omr = pd.read_csv(f"{DATA_DIR}/omr.csv.gz", compression="gzip")
    df_omr_mini = df_omr[df_omr["subject_id"].isin(subject_ids)]
    load_table(df_omr_mini, "omr")

    # ── BẢNG 17: PHARMACY (chunk-read do ~500MB) ──────────────
    print("\n[17/31] pharmacy (chunk-read) ...")
    chunks_kept = []
    total_read = 0
    for chunk in pd.read_csv(
        f"{DATA_DIR}/pharmacy.csv.gz",
        compression="gzip", chunksize=CHUNK_SIZE, low_memory=False,
    ):
        total_read += len(chunk)
        filtered = chunk[chunk["subject_id"].isin(subject_ids)]
        if not filtered.empty:
            chunks_kept.append(filtered)
        print(f"  Đọc {total_read:,} dòng | Giữ {sum(len(c) for c in chunks_kept):,}", end="\r")
    df_pha_mini = _concat_or_empty(chunks_kept, DATA_DIR / "pharmacy.csv.gz")
    print()
    load_table(df_pha_mini, "pharmacy")

    # ── BẢNG 18: POE (chunk-read do ~600MB) ───────────────────
    print("\n[18/31] poe (chunk-read) ...")
    chunks_kept = []
    total_read = 0
    for chunk in pd.read_csv(
        f"{DATA_DIR}/poe.csv.gz",
        compression="gzip", chunksize=CHUNK_SIZE, low_memory=False,
    ):
        total_read += len(chunk)
        filtered = chunk[chunk["subject_id"].isin(subject_ids)]
        if not filtered.empty:
            chunks_kept.append(filtered)
        print(f"  Đọc {total_read:,} dòng | Giữ {sum(len(c) for c in chunks_kept):,}", end="\r")
    df_poe_mini = _concat_or_empty(chunks_kept, DATA_DIR / "poe.csv.gz")
    print()
    load_table(df_poe_mini, "poe")

    # ── BẢNG 19: POE_DETAIL ──────────────────────────────────
    print("\n[19/31] poe_detail ...")
    df_poe_d = pd.read_csv(f"{DATA_DIR}/poe_detail.csv.gz", compression="gzip", low_memory=False)
    df_poe_d_mini = df_poe_d[df_poe_d["subject_id"].isin(subject_ids)]
    load_table(df_poe_d_mini, "poe_detail")

    # ── BẢNG 20: EMAR (chunk-read do ~800MB) ──────────────────
    print("\n[20/31] emar (chunk-read) ...")
    chunks_kept = []
    total_read = 0
    for chunk in pd.read_csv(
        f"{DATA_DIR}/emar.csv.gz",
        compression="gzip", chunksize=CHUNK_SIZE, low_memory=False,
    ):
        total_read += len(chunk)
        filtered = chunk[chunk["subject_id"].isin(subject_ids)]
        if not filtered.empty:
            chunks_kept.append(filtered)
        print(f"  Đọc {total_read:,} dòng | Giữ {sum(len(c) for c in chunks_kept):,}", end="\r")
    df_emar_mini = _concat_or_empty(chunks_kept, DATA_DIR / "emar.csv.gz")
    print()
    load_table(df_emar_mini, "emar")

    # ── BẢNG 21: EMAR_DETAIL (chunk-read do ~750MB) ──────────
    print("\n[21/31] emar_detail (chunk-read) ...")
    chunks_kept = []
    total_read = 0
    for chunk in pd.read_csv(
        f"{DATA_DIR}/emar_detail.csv.gz",
        compression="gzip", chunksize=CHUNK_SIZE, low_memory=False,
    ):
        total_read += len(chunk)
        # emar_detail không có subject_id trực tiếp, cần lọc qua emar_id
        # Thay vào đó ta lọc theo subject_id nếu có cột
        if "subject_id" in chunk.columns:
            filtered = chunk[chunk["subject_id"].isin(subject_ids)]
        else:
            # Lọc qua emar_id đã giữ
            emar_ids_set = set(df_emar_mini["emar_id"].tolist()) if not df_emar_mini.empty else set()
            filtered = chunk[chunk["emar_id"].isin(emar_ids_set)]
        if not filtered.empty:
            chunks_kept.append(filtered)
        print(f"  Đọc {total_read:,} dòng | Giữ {sum(len(c) for c in chunks_kept):,}", end="\r")
    df_emar_d_mini = _concat_or_empty(chunks_kept, DATA_DIR / "emar_detail.csv.gz")
    print()
    load_table(df_emar_d_mini, "emar_detail")

    # ── BẢNG 22: PROVIDER (từ điển - toàn bộ) ────────────────
    print("\n[22/31] provider ...")
    df_prov = pd.read_csv(f"{DATA_DIR}/provider.csv.gz", compression="gzip")
    load_table(df_prov, "provider")

    # ══════════════════════════════════════════════════════════
    # ICU MODULE — 9 bảng
    # ══════════════════════════════════════════════════════════
    # ── BẢNG 23: ICUSTAYS ────────────────────────────────────
    print("\n[23/31] icustays ...")
    df_icu_mini = df_icu[df_icu["subject_id"].isin(subject_ids)]
    load_table(df_icu_mini, "icustays")

    # ── BẢNG 24: D_ITEMS (từ điển ICU - toàn bộ) ─────────────
    print("\n[24/31] d_items ...")
    df_d_items = pd.read_csv(f"{ICU_DIR}/d_items.csv.gz", compression="gzip")
    load_table(df_d_items, "d_items")

    # ── BẢNG 25: CHARTEVENTS (chunk-read do ~3.5GB, rất lớn) ─
    print("\n[25/31] chartevents (chunk-read, lọc subject_id) ...")
    chunks_kept = []
    total_read = 0
    for chunk in pd.read_csv(
        f"{ICU_DIR}/chartevents.csv.gz",
        compression="gzip", chunksize=CHUNK_SIZE, low_memory=False,
    ):
        total_read += len(chunk)
        filtered = chunk[chunk["subject_id"].isin(subject_ids)]
        if not filtered.empty:
            chunks_kept.append(filtered)
        print(f"  Đọc {total_read:,} dòng | Giữ {sum(len(c) for c in chunks_kept):,}", end="\r")
    df_chart_mini = _concat_or_empty(chunks_kept, ICU_DIR / "chartevents.csv.gz")
    print()
    load_table(df_chart_mini, "chartevents")

    # ── BẢNG 26: INPUTEVENTS (chunk-read do ~400MB) ──────────
    print("\n[26/31] inputevents (chunk-read) ...")
    chunks_kept = []
    total_read = 0
    for chunk in pd.read_csv(
        f"{ICU_DIR}/inputevents.csv.gz",
        compression="gzip", chunksize=CHUNK_SIZE, low_memory=False,
    ):
        total_read += len(chunk)
        filtered = chunk[chunk["subject_id"].isin(subject_ids)]
        if not filtered.empty:
            chunks_kept.append(filtered)
        print(f"  Đọc {total_read:,} dòng | Giữ {sum(len(c) for c in chunks_kept):,}", end="\r")
    df_input_mini = _concat_or_empty(chunks_kept, ICU_DIR / "inputevents.csv.gz")
    print()
    load_table(df_input_mini, "inputevents")

    # ── BẢNG 27: OUTPUTEVENTS ────────────────────────────────
    print("\n[27/31] outputevents ...")
    df_out = pd.read_csv(f"{ICU_DIR}/outputevents.csv.gz", compression="gzip", low_memory=False)
    df_out_mini = df_out[df_out["subject_id"].isin(subject_ids)]
    load_table(df_out_mini, "outputevents")

    # ── BẢNG 28: DATETIMEEVENTS ──────────────────────────────
    print("\n[28/31] datetimeevents ...")
    df_dt = pd.read_csv(f"{ICU_DIR}/datetimeevents.csv.gz", compression="gzip", low_memory=False)
    df_dt_mini = df_dt[df_dt["subject_id"].isin(subject_ids)]
    load_table(df_dt_mini, "datetimeevents")

    # ── BẢNG 29: PROCEDUREEVENTS ─────────────────────────────
    print("\n[29/31] procedureevents ...")
    df_procev = pd.read_csv(f"{ICU_DIR}/procedureevents.csv.gz", compression="gzip", low_memory=False)
    df_procev_mini = df_procev[df_procev["subject_id"].isin(subject_ids)]
    load_table(df_procev_mini, "procedureevents")

    # ── BẢNG 30: INGREDIENTEVENTS (chunk-read do ~310MB) ─────
    print("\n[30/31] ingredientevents (chunk-read) ...")
    chunks_kept = []
    total_read = 0
    for chunk in pd.read_csv(
        f"{ICU_DIR}/ingredientevents.csv.gz",
        compression="gzip", chunksize=CHUNK_SIZE, low_memory=False,
    ):
        total_read += len(chunk)
        filtered = chunk[chunk["subject_id"].isin(subject_ids)]
        if not filtered.empty:
            chunks_kept.append(filtered)
        print(f"  Đọc {total_read:,} dòng | Giữ {sum(len(c) for c in chunks_kept):,}", end="\r")
    df_ing_mini = _concat_or_empty(chunks_kept, ICU_DIR / "ingredientevents.csv.gz")
    print()
    load_table(df_ing_mini, "ingredientevents")

    # ── BẢNG 31: CAREGIVER (từ điển - toàn bộ) ───────────────
    print("\n[31/31] caregiver ...")
    df_care = pd.read_csv(f"{ICU_DIR}/caregiver.csv.gz", compression="gzip")
    load_table(df_care, "caregiver")

    # ══════════════════════════════════════════════════════════
    # TẠO INDEX để tăng tốc JOIN
    # ══════════════════════════════════════════════════════════
    print("\nTạo index tăng tốc JOIN ...")
    with engine.connect() as conn:
        idx_sqls = [
            # hosp indexes
            "CREATE INDEX IF NOT EXISTS idx_adm_subject    ON admissions(subject_id)",
            "CREATE INDEX IF NOT EXISTS idx_diag_hadm      ON diagnoses_icd(hadm_id)",
            "CREATE INDEX IF NOT EXISTS idx_diag_icd       ON diagnoses_icd(icd_code, icd_version)",
            "CREATE INDEX IF NOT EXISTS idx_proc_hadm      ON procedures_icd(hadm_id)",
            "CREATE INDEX IF NOT EXISTS idx_lab_subject    ON labevents(subject_id)",
            "CREATE INDEX IF NOT EXISTS idx_lab_itemid     ON labevents(itemid)",
            "CREATE INDEX IF NOT EXISTS idx_rx_subject     ON prescriptions(subject_id)",
            "CREATE INDEX IF NOT EXISTS idx_tr_subject     ON transfers(subject_id)",
            "CREATE INDEX IF NOT EXISTS idx_drg_hadm       ON drgcodes(hadm_id)",
            "CREATE INDEX IF NOT EXISTS idx_hcpcs_hadm     ON hcpcsevents(hadm_id)",
            "CREATE INDEX IF NOT EXISTS idx_omr_subject    ON omr(subject_id)",
            "CREATE INDEX IF NOT EXISTS idx_pha_subject    ON pharmacy(subject_id)",
            "CREATE INDEX IF NOT EXISTS idx_poe_hadm       ON poe(hadm_id)",
            "CREATE INDEX IF NOT EXISTS idx_emar_hadm      ON emar(hadm_id)",
            "CREATE INDEX IF NOT EXISTS idx_micro_hadm     ON microbiologyevents(hadm_id)",
            # icu indexes
            "CREATE INDEX IF NOT EXISTS idx_icu_hadm       ON icustays(hadm_id)",
            "CREATE INDEX IF NOT EXISTS idx_icu_subject    ON icustays(subject_id)",
            "CREATE INDEX IF NOT EXISTS idx_chart_stayid   ON chartevents(stay_id)",
            "CREATE INDEX IF NOT EXISTS idx_chart_itemid   ON chartevents(itemid)",
            "CREATE INDEX IF NOT EXISTS idx_input_stayid   ON inputevents(stay_id)",
            "CREATE INDEX IF NOT EXISTS idx_output_stayid  ON outputevents(stay_id)",
            "CREATE INDEX IF NOT EXISTS idx_procev_stayid  ON procedureevents(stay_id)",
        ]
        for sql in idx_sqls:
            conn.execute(text(sql))
        conn.commit()
    print("  [OK] Indexes created.")

    runtime_user = database_url().username
    loader_user = database_url(loader=True).username
    if runtime_user and runtime_user != loader_user:
        with engine.begin() as conn:
            role_exists = conn.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :role"),
                {"role": runtime_user},
            ).scalar()
            if role_exists:
                quoted_role = conn.dialect.identifier_preparer.quote(runtime_user)
                conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {quoted_role}"))
                conn.execute(text(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {quoted_role}"))
                conn.execute(text(f"ALTER ROLE {quoted_role} SET default_transaction_read_only = on"))
                print(f"  [OK] Read-only grants refreshed for {runtime_user}.")
            else:
                print(
                    f"  [WARN] Runtime role '{runtime_user}' does not exist; "
                    "create it before starting the app."
                )

    print("\n" + "=" * 60)
    print("  DONE! All 31 tables loaded. Database ready.")
    print("=" * 60)


if __name__ == "__main__":
    build_mimic_mini()
