"""
Schema-Aware SQL Validator cho MIMIC-IV RAG Engine.
Xác thực SQL trước khi thực thi để phát hiện và ngăn chặn Hallucination (Ảo giác tên bảng/cột)
và các lỗi logic phổ biến trong câu lệnh PostgreSQL.

Sử dụng kết hợp:
  - sqlparse: parse câu SQL thành token tree để trích xuất tên bảng chính xác
  - regex fallback: xử lý các trường hợp sqlparse không cover được
  - domain-specific rules: kiểm tra logic JOIN đặc thù MIMIC-IV
"""

import re
import sys
from typing import Dict, List, Tuple, Set

try:
    import sqlparse
    from sqlparse.sql import IdentifierList, Identifier, Where, Parenthesis
    from sqlparse.tokens import Keyword, DML, DDL
    HAS_SQLPARSE = True
except ImportError:
    HAS_SQLPARSE = False

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
    Sử dụng sqlparse để parse token tree; fallback về regex nếu cần.
    """
    tables = set()
    sql_keywords = {"select", "where", "group", "order", "limit", "having",
                    "as", "on", "using", "left", "right", "inner", "outer",
                    "cross", "natural", "full", "lateral", "case", "when",
                    "then", "else", "end", "and", "or", "not", "in", "exists",
                    "between", "like", "ilike", "is", "null", "true", "false",
                    "distinct", "all", "any", "some", "union", "intersect", "except"}

    if HAS_SQLPARSE:
        # Phương pháp 1: Dùng sqlparse token tree
        parsed = sqlparse.parse(sql)
        for statement in parsed:
            _extract_tables_from_parsed(statement, tables, sql_keywords)

    # Phương pháp 2 (fallback/bổ sung): Regex bắt FROM/JOIN + tên bảng
    cleaned_sql = re.sub(r"'[^']*'", "''", sql)
    cleaned_sql = re.sub(r"--.*?\n", "\n", cleaned_sql)
    cleaned_sql = re.sub(r"/\*.*?\*/", "", cleaned_sql, flags=re.DOTALL)
    matches = re.findall(
        r"\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        cleaned_sql, flags=re.IGNORECASE
    )
    for m in matches:
        tbl = m.lower()
        if tbl not in sql_keywords:
            tables.add(tbl)

    return tables


def _extract_tables_from_parsed(token_list, tables: set, sql_keywords: set):
    """Helper: đệ quy duyệt sqlparse token tree để tìm tên bảng."""
    from_seen = False
    join_seen = False

    for token in token_list.tokens:
        if token.ttype is Keyword:
            upper_val = token.value.upper()
            if upper_val in ('FROM',):
                from_seen = True
                join_seen = False
            elif 'JOIN' in upper_val:
                join_seen = True
                from_seen = False
            else:
                from_seen = False
                join_seen = False

        elif from_seen or join_seen:
            if isinstance(token, IdentifierList):
                for identifier in token.get_identifiers():
                    _add_table_name(identifier, tables, sql_keywords)
                from_seen = False
                join_seen = False
            elif isinstance(token, Identifier):
                _add_table_name(token, tables, sql_keywords)
                from_seen = False
                join_seen = False
            elif isinstance(token, Parenthesis):
                # Subquery: đệ quy vào trong
                _extract_tables_from_parsed(token, tables, sql_keywords)
                from_seen = False
                join_seen = False

        # Đệ quy vào subquery và WHERE
        if isinstance(token, (Where, Parenthesis)):
            _extract_tables_from_parsed(token, tables, sql_keywords)


def _add_table_name(identifier, tables: set, sql_keywords: set):
    """Trích xuất tên bảng từ một Identifier token."""
    real_name = identifier.get_real_name()
    if real_name:
        name_lower = real_name.lower()
        if name_lower not in sql_keywords:
            tables.add(name_lower)


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
    Kiểm tra tính hợp lệ của câu lệnh SQL đối với Schema MIMIC-IV 31 bảng.
    
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

    # 0. Kiểm tra Dangerous SQL (DML/DDL không cho phép)
    dangerous_keywords = {"insert", "update", "delete", "drop", "alter", "truncate", "create", "grant", "revoke"}
    if HAS_SQLPARSE:
        parsed = sqlparse.parse(sql)
        for statement in parsed:
            token_types = [token.ttype for token in statement.tokens if token.ttype in (DML, DDL)]
            if any(token_types):
                errors.append("LỖI BẢO MẬT: Câu lệnh chứa hành động thay đổi dữ liệu (INSERT/UPDATE/DELETE/DROP). Chỉ cho phép SELECT.")
                break
    
    # Fallback/Additional check bằng regex cho an toàn
    for keyword in dangerous_keywords:
        if re.search(rf"\b{keyword}\b", sql_lower):
            errors.append(f"LỖI BẢO MẬT: Phát hiện từ khóa '{keyword.upper()}'. Chỉ cho phép câu lệnh SELECT.")
            break

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
            # Phỏng đoán alias phổ biến (hosp module)
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
            elif tbl == "pharmacy": alias_to_table["ph"] = tbl
            elif tbl == "poe": alias_to_table["po"] = tbl
            elif tbl == "poe_detail": alias_to_table["pd"] = tbl
            elif tbl == "emar": alias_to_table["e"] = tbl
            elif tbl == "emar_detail": alias_to_table["ed"] = tbl
            elif tbl == "drgcodes": alias_to_table["drg"] = tbl
            elif tbl == "hcpcsevents": alias_to_table["h"] = tbl
            elif tbl == "d_hcpcs": alias_to_table["dh"] = tbl
            elif tbl == "omr": alias_to_table["o"] = tbl
            # Alias phổ biến cho ICU module
            elif tbl == "icustays": alias_to_table["icu"] = tbl
            elif tbl == "chartevents": alias_to_table["ce"] = tbl
            elif tbl == "d_items": alias_to_table["di"] = tbl  # chú ý: trùng với d_icd_diagnoses nếu cả 2 cùng query
            elif tbl == "inputevents": alias_to_table["ie"] = tbl
            elif tbl == "outputevents": alias_to_table["oe"] = tbl
            elif tbl == "procedureevents": alias_to_table["pe"] = tbl
            elif tbl == "datetimeevents": alias_to_table["de"] = tbl
            elif tbl == "ingredientevents": alias_to_table["ig"] = tbl

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

    # Lỗi hay gặp 4: JOIN emar + emar_detail thiếu emar_seq
    if "emar" in tables_used and "emar_detail" in tables_used:
        if "emar_seq" not in sql_lower:
            warnings.append(
                "CẢNH BÁO JOIN eMAR: Khi JOIN emar với emar_detail, cần khớp cả 'emar_id AND emar_seq' để tránh trùng bản ghi."
            )

    # Lỗi hay gặp 5: JOIN chartevents/inputevents/outputevents với d_items phải qua itemid
    icu_event_tables = {"chartevents", "inputevents", "outputevents", "datetimeevents",
                        "procedureevents", "ingredientevents"}
    if "d_items" in tables_used and icu_event_tables & tables_used:
        if "itemid" not in sql_lower:
            warnings.append(
                "CẢNH BÁO JOIN ICU: Khi JOIN bảng events ICU với d_items, phải dùng 'ON events.itemid = d_items.itemid'."
            )

    # Lỗi hay gặp 6: Dùng 'los' không đúng bảng (chỉ icustays mới có cột los)
    if re.search(r'\blos\b', sql_lower) and "icustays" not in tables_used:
        if not re.search(r'\bextract\b', sql_lower):  # nếu tính LOS bằng EXTRACT thì OK
            warnings.append(
                "CẢNH BÁO CỘT LOS: Cột 'los' chỉ tồn tại trong bảng 'icustays'. "
                "Bảng 'admissions' không có cột los, cần tính bằng EXTRACT(EPOCH FROM (dischtime - admittime))/86400."
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
