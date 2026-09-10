"""
Schema-Aware SQL Validator cho MIMIC-IV RAG Engine.
Xác thực SQL trước khi thực thi để phát hiện và ngăn chặn Hallucination (Ảo giác tên bảng/cột)
và các lỗi logic phổ biến trong câu lệnh PostgreSQL.
"""

import re
import sys
from typing import Dict, List, Tuple, Set

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Danh sách 31 bảng hợp lệ trong MIMIC-IV (22 hosp + 9 icu)
VALID_TABLES: Set[str] = {
    # ── hosp module (22 bảng) ──
    "patients", "admissions", "transfers", "services", "provider",
    "diagnoses_icd", "d_icd_diagnoses", "procedures_icd", "d_icd_procedures",
    "hcpcsevents", "d_hcpcs", "drgcodes",
    "labevents", "d_labitems", "microbiologyevents",
    "prescriptions", "pharmacy", "poe", "poe_detail",
    "emar", "emar_detail", "omr",
    # ── icu module (9 bảng) ──
    "icustays", "chartevents", "d_items",
    "inputevents", "outputevents", "datetimeevents",
    "procedureevents", "ingredientevents", "caregiver",
}

# Chi tiết cột của từng bảng để kiểm tra column hallucination
VALID_COLUMNS: Dict[str, Set[str]] = {
    # ── hosp module ──
    "patients": {"subject_id", "gender", "anchor_age", "anchor_year", "anchor_year_group", "dod"},
    "admissions": {
        "subject_id", "hadm_id", "admittime", "dischtime", "deathtime",
        "admission_type", "admit_provider_id", "admission_location", "discharge_location",
        "insurance", "language", "marital_status", "race",
        "edregtime", "edouttime", "hospital_expire_flag"
    },
    "transfers": {"subject_id", "hadm_id", "transfer_id", "eventtype", "careunit", "intime", "outtime"},
    "services": {"subject_id", "hadm_id", "transfertime", "prev_service", "curr_service"},
    "provider": {"provider_id"},
    "diagnoses_icd": {"subject_id", "hadm_id", "seq_num", "icd_code", "icd_version"},
    "d_icd_diagnoses": {"icd_code", "icd_version", "long_title"},
    "procedures_icd": {"subject_id", "hadm_id", "seq_num", "chartdate", "icd_code", "icd_version"},
    "d_icd_procedures": {"icd_code", "icd_version", "long_title"},
    "hcpcsevents": {"subject_id", "hadm_id", "chartdate", "hcpcs_cd", "seq_num", "short_description"},
    "d_hcpcs": {"code", "category", "long_description", "short_description"},
    "drgcodes": {"subject_id", "hadm_id", "drg_type", "drg_code", "description", "drg_severity", "drg_mortality"},
    "labevents": {
        "labevent_id", "subject_id", "hadm_id", "specimen_id", "itemid",
        "charttime", "storetime", "value", "valuenum", "valueuom",
        "ref_range_lower", "ref_range_upper", "flag", "priority", "comments"
    },
    "d_labitems": {"itemid", "label", "fluid", "category"},
    "microbiologyevents": {
        "microevent_id", "subject_id", "hadm_id", "chartdate", "charttime",
        "spec_itemid", "spec_type_desc", "test_seq", "storedate", "storetime",
        "org_itemid", "org_name", "isolate_num", "interpretation", "comments"
    },
    "prescriptions": {
        "subject_id", "hadm_id", "pharmacy_id", "poe_id", "poe_seq",
        "starttime", "stoptime", "drug_type", "drug", "formulary_drug_cd",
        "gsn", "ndc", "prod_strength", "form_rx", "dose_val_rx",
        "dose_unit_rx", "form_val_disp", "form_unit_disp", "doses_per_24_hrs", "route"
    },
    "pharmacy": {
        "subject_id", "hadm_id", "pharmacy_id", "poe_id", "starttime", "stoptime",
        "medication", "proc_type", "status", "entertime", "verifiedtime",
        "route", "frequency", "disp_sched", "infusion_type", "sliding_scale",
        "lockout_interval", "basal_rate", "one_hr_max", "doses_per_24_hrs",
        "duration", "duration_interval", "expiration_value", "expiration_unit",
        "expirationdate", "dispensation", "fill_quantity"
    },
    "poe": {
        "poe_id", "poe_seq", "subject_id", "hadm_id", "ordertime",
        "order_type", "order_subtype", "transaction_type",
        "discontinue_of_poe_id", "discontinued_by_poe_id",
        "order_provider_id", "order_status"
    },
    "poe_detail": {"poe_id", "poe_seq", "subject_id", "field_name", "field_value"},
    "emar": {
        "emar_id", "subject_id", "hadm_id", "emar_seq", "poe_id", "pharmacy_id",
        "enter_provider_id", "charttime", "medication", "event_txt",
        "scheduletime", "storetime"
    },
    "emar_detail": {
        "emar_id", "emar_seq", "parent_field_ordinal", "administration_type",
        "pharmacy_id", "barcode_type", "reason_for_no_barcode",
        "complete_dose_not_given", "dose_due", "dose_due_unit",
        "dose_given", "dose_given_unit", "will_remainder_of_dose_be_given",
        "product_amount_given", "product_unit", "product_code",
        "product_description", "product_description_other",
        "prior_infusion_rate", "infusion_rate", "infusion_rate_adjustment",
        "infusion_rate_adjustment_amount", "infusion_rate_unit",
        "route", "infusion_complete", "completion_interval",
        "new_iv_bag_hung", "continued_infusion_in_other_location",
        "restart_interval", "side", "site", "non_formulary_visual_verification"
    },
    "omr": {"subject_id", "chartdate", "seq_num", "result_name", "result_value"},
    # ── icu module ──
    "icustays": {"subject_id", "hadm_id", "stay_id", "first_careunit", "last_careunit", "intime", "outtime", "los"},
    "chartevents": {
        "subject_id", "hadm_id", "stay_id", "caregiver_id",
        "charttime", "storetime", "itemid", "value", "valuenum", "valueuom", "warning"
    },
    "d_items": {
        "itemid", "label", "abbreviation", "linksto", "category",
        "unitname", "param_type", "lownormalvalue", "highnormalvalue"
    },
    "inputevents": {
        "subject_id", "hadm_id", "stay_id", "caregiver_id",
        "starttime", "endtime", "storetime", "itemid",
        "amount", "amountuom", "rate", "rateuom",
        "orderid", "linkorderid", "ordercategoryname",
        "secondaryordercategoryname", "ordercomponenttypedescription",
        "ordercategorydescription", "patientweight",
        "totalamount", "totalamountuom", "isopenbag",
        "continueinnextdept", "statusdescription", "originalamount", "originalrate"
    },
    "outputevents": {
        "subject_id", "hadm_id", "stay_id", "caregiver_id",
        "charttime", "storetime", "itemid", "value", "valueuom"
    },
    "datetimeevents": {
        "subject_id", "hadm_id", "stay_id", "caregiver_id",
        "charttime", "storetime", "itemid", "value", "valueuom", "warning"
    },
    "procedureevents": {
        "subject_id", "hadm_id", "stay_id", "caregiver_id",
        "starttime", "endtime", "storetime", "itemid", "value", "valueuom",
        "location", "locationcategory", "orderid", "linkorderid",
        "ordercategoryname", "ordercategorydescription", "patientweight",
        "isopenbag", "continueinnextdept", "statusdescription",
        "originalamount", "originalrate"
    },
    "ingredientevents": {
        "subject_id", "hadm_id", "stay_id", "caregiver_id",
        "starttime", "endtime", "storetime", "itemid",
        "amount", "amountuom", "rate", "rateuom",
        "orderid", "linkorderid", "statusdescription",
        "originalamount", "originalrate"
    },
    "caregiver": {"caregiver_id"},
}


# Tập hợp tất cả các cột tồn tại trong database để kiểm tra nhanh
ALL_KNOWN_COLUMNS: Set[str] = set()
for cols in VALID_COLUMNS.values():
    ALL_KNOWN_COLUMNS.update(cols)


def extract_table_names(sql: str) -> Set[str]:
    """
    Trích xuất danh sách tên bảng được tham chiếu trong câu lệnh SQL.
    Dùng regex phát hiện sau FROM và JOIN.
    """
    # Loại bỏ string literal và comment để tránh false positives
    cleaned_sql = re.sub(r"'[^']*'", "''", sql)
    cleaned_sql = re.sub(r"--.*?\n", "\n", cleaned_sql)
    cleaned_sql = re.sub(r"/\*.*?\*/", "", cleaned_sql, flags=re.DOTALL)

    # Tìm các từ khóa FROM, JOIN kèm theo tên bảng
    matches = re.findall(r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)", cleaned_sql, flags=re.IGNORECASE)
    tables = set()
    for m in matches:
        tbl = m.lower()
        # Bỏ qua subquery alias hoặc các từ khóa SQL nếu bị bắt nhầm
        if tbl not in ("select", "where", "group", "order", "limit", "having", "as", "on", "using", "left", "right", "inner", "outer"):
            tables.add(tbl)
    return tables


def extract_column_candidates(sql: str) -> List[Tuple[str, str]]:
    """
    Trích xuất các ứng viên cột trong SQL theo định dạng (table_alias_or_name, column_name)
    hoặc ("", column_name).
    """
    cleaned_sql = re.sub(r"'[^']*'", "''", sql)
    cleaned_sql = re.sub(r"--.*?\n", "\n", cleaned_sql)

    # Tìm mẫu table.column (ví dụ: p.subject_id, patients.anchor_age)
    qualified = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b", cleaned_sql)
    candidates = []
    for tbl_or_alias, col in qualified:
        candidates.append((tbl_or_alias.lower(), col.lower()))
    
    return candidates


def validate_sql_schema(sql: str) -> Dict:
    """
    Kiểm tra tính hợp lệ của câu lệnh SQL đối với Schema MIMIC-IV 12 bảng.
    
    Trả về:
      {
        "valid": bool,
        "errors": List[str],    # Lỗi nghiêm trọng (chắc chắn chạy lỗi trên PostgreSQL)
        "warnings": List[str]   # Cảnh báo logic (JOIN thiếu điều kiện, v.v.)
      }
    """
    errors: List[str] = []
    warnings: List[str] = []

    sql_lower = sql.lower()
    tables_used = extract_table_names(sql)

    # 1. Kiểm tra Table Hallucination (Ảo giác tên bảng)
    for tbl in tables_used:
        if tbl not in VALID_TABLES:
            errors.append(f"ẢO GIÁC BẢNG (Table Hallucination): Bảng '{tbl}' không tồn tại trong cơ sở dữ liệu MIMIC-IV.")

    # 2. Kiểm tra Column Hallucination cho các truy vấn có table.column rõ ràng
    # Lưu mapping từ alias -> tên bảng nếu có thể suy luận đơn giản
    alias_to_table = {}
    for tbl in tables_used:
        if tbl in VALID_TABLES:
            alias_to_table[tbl] = tbl
            # Phỏng đoán alias phổ biến
            if tbl == "patients": alias_to_table["p"] = tbl
            elif tbl == "admissions": alias_to_table["a"] = tbl
            elif tbl == "diagnoses_icd": alias_to_table["d"] = tbl
            elif tbl == "d_icd_diagnoses": alias_to_table["di"] = tbl
            elif tbl == "procedures_icd": alias_to_table["pi"] = tbl
            elif tbl == "d_icd_procedures": alias_to_table["dip"] = tbl
            elif tbl == "labevents": alias_to_table["le"] = tbl
            elif tbl == "d_labitems": alias_to_table["dl"] = tbl
            elif tbl == "prescriptions": alias_to_table["pr"] = tbl
            elif tbl == "transfers": alias_to_table["t"] = tbl
            elif tbl == "services": alias_to_table["s"] = tbl
            elif tbl == "microbiologyevents": alias_to_table["me"] = tbl

    col_candidates = extract_column_candidates(sql)
    for prefix, col in col_candidates:
        if col in ("count", "avg", "sum", "min", "max", "round", "extract", "epoch", "coalesce", "cast", "date", "timestamp"):
            continue
        if prefix in alias_to_table:
            real_table = alias_to_table[prefix]
            if col not in VALID_COLUMNS[real_table]:
                errors.append(
                    f"ẢO GIÁC CỘT (Column Hallucination): Cột '{col}' không tồn tại trong bảng '{real_table}'. "
                    f"Các cột hợp lệ của '{real_table}' bao gồm: {', '.join(sorted(VALID_COLUMNS[real_table]))}."
                )
        elif prefix in VALID_TABLES:
            if col not in VALID_COLUMNS[prefix]:
                errors.append(
                    f"ẢO GIÁC CỘT (Column Hallucination): Cột '{col}' không tồn tại trong bảng '{prefix}'."
                )

    # 3. Kiểm tra các lỗi thường gặp trong MIMIC-IV (Domain-specific Checks)
    # Lỗi hay gặp 1: Nhầm cột tuổi 'age' thay vì 'anchor_age'
    if re.search(r"\bage\b", sql_lower) and not re.search(r"\banchor_age\b", sql_lower):
        if "patients" in tables_used or "p" in sql_lower:
            errors.append("LỖI CỘT TUỔI: Bảng patients trong MIMIC-IV sử dụng cột 'anchor_age', KHÔNG có cột 'age'.")

    # Lỗi hay gặp 2: JOIN diagnoses_icd và d_icd_diagnoses thiếu icd_version
    if "diagnoses_icd" in tables_used and "d_icd_diagnoses" in tables_used:
        if "icd_version" not in sql_lower:
            warnings.append(
                "CẢNH BÁO JOIN ICD: Khi JOIN diagnoses_icd với d_icd_diagnoses, cần khớp cả 'icd_code AND icd_version' "
                "để tránh trùng lặp mã giữa ICD-9 và ICD-10."
            )

    # Lỗi hay gặp 3: JOIN procedures_icd và d_icd_procedures thiếu icd_version
    if "procedures_icd" in tables_used and "d_icd_procedures" in tables_used:
        if "icd_version" not in sql_lower:
            warnings.append(
                "CẢNH BÁO JOIN THỦ THUẬT: Khi JOIN procedures_icd với d_icd_procedures, cần khớp cả 'icd_code AND icd_version'."
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }


def get_validator_prompt_hint(validation_result: Dict) -> str:
    """
    Tạo thông báo lỗi chi tiết để gửi cho LLM tự sửa lỗi (Self-Correction) nếu SQL bị invalid schema.
    """
    if validation_result["valid"]:
        return ""
    
    msg = "SQL vừa tạo mắc lỗi nghiêm trọng về cấu trúc Schema:\n"
    for err in validation_result["errors"]:
        msg += f"- {err}\n"
    if validation_result["warnings"]:
        for w in validation_result["warnings"]:
            msg += f"- {w}\n"
    msg += "\nHãy viết lại câu SQL chỉnh sửa các lỗi trên. CHỈ sử dụng đúng các bảng và cột có trong Schema đã cung cấp."
    return msg


if __name__ == "__main__":
    # Test nhanh validator
    test_sqls = [
        "SELECT * FROM patients WHERE age > 60;", # Lỗi age
        "SELECT * FROM vital_signs WHERE heart_rate > 100;", # Lỗi bảng vital_signs
        "SELECT p.subject_id, p.anchor_age, d.icd_code FROM patients p JOIN diagnoses_icd d ON p.subject_id = d.subject_id WHERE d.icd_code = 'J189';" # Valid
    ]
    for sql in test_sqls:
        res = validate_sql_schema(sql)
        print(f"\nSQL: {sql}")
        print(f"Valid: {res['valid']} | Errors: {res['errors']}")
