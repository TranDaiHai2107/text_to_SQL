"""Read-only candidate normalization and a small dev-calibrated policy family.

No API calls and no evaluation labels are read here. ICD metadata comes from
the full dictionaries, never only observed patient facts. Voting follows the
official numeric normalization while retaining ALL rows, duplicates and shape.
"""
from collections import defaultdict
from collections.abc import Mapping
from contextlib import closing
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import sys

from sqlglot import exp, parse_one


V3 = Path(__file__).resolve().parents[1] / "ours_improved_v3"
if str(V3) not in sys.path:
    sys.path.insert(1, str(V3))
# A private module name avoids confusing a new runner's ROOT with the v3 ROOT.
_SPEC = importlib.util.spec_from_file_location("_postprocess_v4_v3_infrastructure", V3 / "infrastructure.py")
_INFRA = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_INFRA)
DB, execute = _INFRA.DB, _INFRA.execute
from baseline_core import process_item
from risk_v3 import select_record


BASELINE_POLICY = "strict3_raw"
POLICIES = (
    BASELINE_POLICY,
    "strict3_round3",
    "strict3_round3_no_trivial",
    "strict3_round3_exact_binding",
    "strict3_round3_both",
)
FINGERPRINT_METHOD = "official_process_item_round3_full_multiset_no_row_cap"
FACT_DICTIONARIES = {
    "diagnoses_icd": "d_icd_diagnoses",
    "procedures_icd": "d_icd_procedures",
    "d_icd_diagnoses": "d_icd_diagnoses",
    "d_icd_procedures": "d_icd_procedures",
}


def _surface_key(text):
    return re.sub(r"\W+", " ", str(text).casefold()).strip()


def metadata_from_rows(dictionary_rows):
    """Build JSON-compatible complete indexes from {dictionary: [(code,title)]}.

    Public for tests and metadata transport; production uses load_metadata(DB).
    Complete universes include codes absent from the sampled patient facts.
    """
    tables = {}
    for table in ("d_icd_diagnoses", "d_icd_procedures"):
        code_to_titles = defaultdict(list)
        title_to_codes = defaultdict(list)
        normalized_to_titles = defaultdict(list)
        for code, title in dictionary_rows.get(table, []):
            if code is None or title is None:
                continue
            code, title = str(code), str(title)
            if title not in code_to_titles[code]:
                code_to_titles[code].append(title)
            if code not in title_to_codes[title]:
                title_to_codes[title].append(code)
            key = _surface_key(title)
            if title not in normalized_to_titles[key]:
                normalized_to_titles[key].append(title)
        tables[table] = {
            "code_to_titles": dict(code_to_titles),
            "title_to_codes": dict(title_to_codes),
            "normalized_to_titles": dict(normalized_to_titles),
        }
    return {
        "complete_dictionary_universes": True,
        "source": "full_ICD_dictionary_tables_not_observed_patient_fact_codes",
        "fact_dictionary_mapping": dict(FACT_DICTIONARIES),
        "tables": tables,
        "counts": {table: {"codes": len(value["code_to_titles"]),
                            "titles": len(value["title_to_codes"])}
                   for table, value in tables.items()},
    }


def load_metadata(db=None):
    """Read full code/title dictionaries from a SQLite database in mode=ro."""
    database = Path(db) if db is not None else DB
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as con:
        con.execute("PRAGMA query_only=ON")
        rows = {table: con.execute(f"SELECT icd_code,long_title FROM {table}").fetchall()
                for table in ("d_icd_diagnoses", "d_icd_procedures")}
    return metadata_from_rows(rows)


def fingerprint_round3(rows):
    """Official process_item per cell, complete row multiset without a 100 cap."""
    if not isinstance(rows, (list, tuple)) or any(not isinstance(row, (list, tuple)) for row in rows):
        raise ValueError("Executed rows must be a row sequence")
    if not rows:
        return None, {"rows": 0, "columns": 0, "trivial_scalar": False}
    values = sorted([[process_item(value) for value in row] for row in rows])
    widths = sorted(len(row) for row in rows)
    payload = {"row_count": len(rows), "row_widths": widths, "rows": values}
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode()).hexdigest()
    scalar = len(rows) == 1 and len(rows[0]) == 1
    normalized_scalar = values[0][0] if scalar else None
    trivial = scalar and normalized_scalar in {"None", "0.0", "-0.0"}
    return digest, {
        "rows": len(rows), "columns": len(rows[0]) if len(set(widths)) == 1 else None,
        "trivial_scalar": trivial, "trivial_scalar_after_official_normalization": trivial,
        "fingerprint_method": FINGERPRINT_METHOD,
    }


def _nearest_select(node):
    while node is not None:
        if isinstance(node, exp.Select):
            return node
        node = node.parent
    return None


def _local_tables(select):
    if select is None:
        return {}
    return {table.alias_or_name.casefold(): table.name.casefold()
            for table in select.find_all(exp.Table)
            if _nearest_select(table.parent) is select}


def _resolve_dictionary(column, predicate, metadata):
    mapping = metadata["fact_dictionary_mapping"]
    local = _local_tables(_nearest_select(predicate))
    qualifier = column.table.casefold()
    if qualifier:
        table = local.get(qualifier)
        # A qualified correlated column can refer to an outer SELECT. Resolve
        # only explicit aliases, stopping at the nearest matching scope.
        node = _nearest_select(predicate)
        while table is None and node is not None:
            node = _nearest_select(node.parent)
            if node is not None:
                table = _local_tables(node).get(qualifier)
        return mapping.get(table)
    possibilities = {mapping[table] for table in local.values() if table in mapping}
    return next(iter(possibilities)) if len(possibilities) == 1 else None


def _direct_literals(tree):
    for predicate in tree.find_all(exp.EQ):
        column, literal = predicate.this, predicate.expression
        if isinstance(literal, exp.Column) and isinstance(column, exp.Literal):
            column, literal = literal, column
        if isinstance(column, exp.Column) and isinstance(literal, exp.Literal):
            yield column, literal, predicate
    for predicate in tree.find_all(exp.In):
        if isinstance(predicate.this, exp.Column):
            for literal in predicate.expressions:
                if isinstance(literal, exp.Literal):
                    yield predicate.this, literal, predicate


def dictionary_issues(question, sql, metadata):
    """Detect physical bare-code errors and punctuation/version ambiguity.

    Unknown prefixed codes are not auto-rejected here. Only a bare literal
    absent from its COMPLETE corresponding dictionary triggers the code guard.
    Surface ambiguity is advisory and is never itself a hard SQL rejection.
    """
    if metadata.get("complete_dictionary_universes") is not True:
        raise ValueError("Full dictionary metadata is required; observed fact codes are insufficient")
    if not sql or sql == "null":
        return {"hard_issues": [], "soft_issues": [], "details": []}
    try:
        tree = parse_one(sql, read="sqlite")
    except Exception:
        return {"hard_issues": [], "soft_issues": [], "details": []}
    hard, soft, details = [], [], []
    q = question.casefold()
    for column, literal, predicate in _direct_literals(tree):
        if column.name.casefold() not in {"icd_code", "long_title"}:
            continue
        dictionary = _resolve_dictionary(column, predicate, metadata)
        if dictionary is None:
            continue
        info = metadata["tables"][dictionary]
        value = str(literal.this)
        if column.name.casefold() == "icd_code":
            if value not in info["code_to_titles"] and not re.match(r"^icd(?:9|10)\|", value, re.I):
                issue = f"physical_icd_code: {dictionary}.icd_code={value!r} lacks a stored version prefix and is absent from the full dictionary"
                hard.append(issue)
                details.append({"kind": "physical_icd_code", "dictionary": dictionary, "literal": value})
            continue
        if not literal.is_string:
            continue
        # Compare only real labels in this dictionary. If a literal is absent,
        # existing enum diagnostics handle it; this detector never fabricates a
        # replacement or treats a partial retrieved catalog as exhaustive.
        selected_codes = set(info["title_to_codes"].get(value, []))
        if not selected_codes:
            continue
        for title in info["normalized_to_titles"].get(_surface_key(value), []):
            if title.casefold() == value.casefold() or title.casefold() not in q:
                continue
            exact_codes = set(info["title_to_codes"][title])
            if exact_codes and selected_codes.isdisjoint(exact_codes):
                issue = (f"dictionary_surface_ambiguity: question contains exact {dictionary}.long_title={title!r} "
                         f"but SQL selects punctuation-colliding label {value!r} with distinct codes")
                soft.append(issue)
                details.append({"kind": "dictionary_surface_ambiguity", "dictionary": dictionary,
                                "question_surface": title, "SQL_literal": value,
                                "question_surface_codes": sorted(exact_codes), "SQL_literal_codes": sorted(selected_codes)})
    return {"hard_issues": list(dict.fromkeys(hard)), "soft_issues": list(dict.fromkeys(soft)),
            "details": details}


def _guard(record, reason):
    result = deepcopy(record)
    result["v4_pre_guard_sql"] = result["sql"]
    result["v4_pre_guard_execution"] = deepcopy(result["execution"])
    # Preserve any historical v3 pre_guard_* fields instead of overwriting them.
    result.setdefault("pre_guard_sql", result["sql"])
    result.setdefault("pre_guard_execution", deepcopy(result["execution"]))
    result.update(sql="null", execution={"valid": False, "abstained": True, "empty": None, "error": None},
                  result_fingerprint=None, guard_rejected=True, v4_guard_rejected=True, v4_guard_reason=reason)
    return result


def normalize_candidate(question, record, metadata):
    """Deep-copy a source record, apply physical-code guard, execute read-only.

    Re-normalizing a normalized record starts from its immutable source snapshot
    to avoid nested snapshots or accidental accumulation of soft diagnostics.
    """
    original = deepcopy(record.get("v4_original_record", record))
    if not isinstance(original.get("sql"), str) or not isinstance(original.get("execution"), Mapping):
        raise ValueError("A completed source candidate record is required")
    if any(original.get(key) for key in ("api_error", "provider_error", "network_error", "quota_error")):
        raise ValueError("Provider failures must stop inference, not become normalized abstentions")
    result = deepcopy(original)
    result.update(v4_original_record=deepcopy(original), v4_original_sql=original["sql"],
                  v4_original_execution=deepcopy(original["execution"]),
                  raw_result_fingerprint=original.get("result_fingerprint"),
                  v4_normalization={"method": FINGERPRINT_METHOD, "executed_readonly": False,
                                    "full_dictionary_metadata": True, "row_cap": None})
    result["contract"] = deepcopy(original.get("contract", {"hard_issues": [], "soft_issues": []}))
    for key in ("hard_issues", "soft_issues"):
        result["contract"].setdefault(key, [])
    result["static_issues"] = list(original.get("static_issues", []))
    if original["sql"] == "null":
        if original["execution"].get("abstained") is not True:
            raise ValueError("Malformed source null record")
        return result
    issues = dictionary_issues(question, original["sql"], metadata)
    result["v4_dictionary_issues"] = issues
    for key in ("hard_issues", "soft_issues"):
        result["contract"][key] = list(dict.fromkeys(result["contract"][key] + issues[key]))
    result["static_issues"] = list(dict.fromkeys(result["static_issues"] + issues["hard_issues"]))
    if issues["hard_issues"]:
        return _guard(result, "invalid_physical_ICD_code_literal")
    if not original["sql"].strip() or original.get("finish_reason", "stop") != "stop":
        return _guard(result, "incomplete_generation_not_reexecuted_as_valid_SQL")
    try:
        rows = execute(original["sql"])
        fingerprint, summary = fingerprint_round3(rows)
        result.update(result_fingerprint=fingerprint, result_summary=summary,
                      execution={"valid": True, "abstained": False, "empty": not rows, "error": None})
        result["v4_normalization"]["executed_readonly"] = True
        if not rows:
            return _guard(result, "empty_readonly_execution")
    except Exception as error:
        result["execution"] = {"valid": False, "abstained": False, "empty": None, "error": str(error)[:500]}
        return _guard(result, "readonly_execution_failure")
    return result


def select_v4(candidates, policy):
    """Select via strict-three agreement after a fixed optional risk gate."""
    if policy == BASELINE_POLICY:
        sources = [deepcopy(row.get("v4_original_record", row)) for row in candidates]
        selected = select_record(sources, "strict_three_agree")
    elif policy in POLICIES:
        if any(row.get("v4_normalization", {}).get("method") != FINGERPRINT_METHOD for row in candidates):
            raise ValueError("Normalize all candidates before applying a round3 v4 policy")
        sources = deepcopy(candidates)
        for index, row in enumerate(sources):
            trivial = row.get("result_summary", {}).get("trivial_scalar") is True
            ambiguous = any(issue.startswith("dictionary_surface_ambiguity:")
                            for issue in row.get("contract", {}).get("soft_issues", []))
            reject_trivial = policy in {"strict3_round3_no_trivial", "strict3_round3_both"} and trivial
            reject_binding = policy in {"strict3_round3_exact_binding", "strict3_round3_both"} and ambiguous
            if row["sql"] != "null" and (reject_trivial or reject_binding):
                sources[index] = _guard(row, "trivial_scalar_risk_gate" if reject_trivial else "dictionary_surface_ambiguity_risk_gate")
        selected = select_record(sources, "strict_three_agree")
    else:
        raise ValueError("Unknown fixed v4 policy: " + str(policy))
    selected["selection"].update(base_policy="strict_three_agree", policy=policy,
                                  normalization=FINGERPRINT_METHOD if policy != BASELINE_POLICY else "raw_v3_fingerprint",
                                  no_gold_access=True)
    return selected
