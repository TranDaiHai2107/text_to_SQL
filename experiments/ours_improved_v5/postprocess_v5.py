"""Deterministic, metadata-proven ICD namespace and exact-surface proposals.

No model calls or evaluation labels. Rewrites are limited to resolved ICD
literal positions. All source candidates remain immutable and auditable.
"""
from collections import defaultdict
from copy import deepcopy
import importlib.util
from pathlib import Path
import re
import sys

from sqlglot import exp, parse_one


V4 = Path(__file__).resolve().parents[1] / "ours_improved_v4"
if str(V4) not in sys.path:
    sys.path.insert(1, str(V4))
_SPEC = importlib.util.spec_from_file_location("_postprocess_v5_v4", V4 / "postprocess_v4.py")
V4_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(V4_MODULE)
from risk_v3 import select_record


POLICIES = (
    "strict3_raw",
    "strict3_canonical",
    "strict3_canonical_no_trivial",
    "strict3_canonical_exact_binding",
    "strict3_canonical_both",
)
_V4_POLICIES = {
    "strict3_canonical": "strict3_round3",
    "strict3_canonical_no_trivial": "strict3_round3_no_trivial",
    "strict3_canonical_exact_binding": "strict3_round3_exact_binding",
    "strict3_canonical_both": "strict3_round3_both",
}


def _add_suffix_indexes(metadata):
    if metadata.get("complete_dictionary_universes") is not True:
        raise ValueError("The compiler requires full dictionary universes")
    for info in metadata["tables"].values():
        suffixes = defaultdict(list)
        for code in info["code_to_titles"]:
            if re.match(r"^icd(?:9|10)\|", code):
                suffix = code.split("|", 1)[1]
                suffixes[suffix].append(code)
        info["suffix_to_codes"] = {suffix: sorted(set(codes)) for suffix, codes in suffixes.items()}
    metadata["namespace_suffix_index"] = "exact_suffix_same_complete_dictionary"
    return metadata


def load_metadata(db=None):
    return _add_suffix_indexes(V4_MODULE.load_metadata(db))


def metadata_from_rows(rows):
    """Synthetic fixture helper; production uses load_metadata on the DB."""
    return _add_suffix_indexes(V4_MODULE.metadata_from_rows(rows))


def _contains_exact_surface(question, title):
    return re.search(r"(?<!\w)" + re.escape(title.casefold()) + r"(?!\w)", question.casefold()) is not None


def compile_namespace(question, sql, metadata, *, enable_exact_surface=True):
    """Build a deterministic proposal; never guess an entity or namespace.

    Existing full/bare dictionary values, unknown full codes, unmatched suffixes,
    ambiguous suffixes and ambiguous question surfaces remain unchanged.
    """
    if metadata.get("namespace_suffix_index") != "exact_suffix_same_complete_dictionary":
        raise ValueError("Complete metadata with a same-dictionary suffix index is required")
    result = {"source_sql": sql, "sql": sql, "changed": False, "changes": [], "unresolved": [],
              "enable_exact_surface": bool(enable_exact_surface),
              "SQL_serialization": "unchanged unless a metadata-proven literal replacement is made"}
    if not sql or sql == "null":
        return result
    try:
        tree = parse_one(sql, read="sqlite")
    except Exception:
        result["unresolved"].append({"reason": "SQL_not_parseable_no_compiler_rewrite"})
        return result
    # Materialize positions before replacement; no global textual substitution.
    for column, literal, predicate in list(V4_MODULE._direct_literals(tree)):
        name = column.name.casefold()
        if name not in {"icd_code", "long_title"}:
            continue
        dictionary = V4_MODULE._resolve_dictionary(column, predicate, metadata)
        if dictionary is None:
            continue
        info = metadata["tables"][dictionary]
        value = str(literal.this)
        replacement = None
        evidence = None
        if name == "icd_code":
            if value in info["code_to_titles"] or re.match(r"^icd(?:9|10)\|", value, re.I):
                continue
            options = info["suffix_to_codes"].get(value, [])
            if len(options) == 1:
                replacement = options[0]
                evidence = {"kind": "unique_ICD_namespace_suffix", "dictionary": dictionary,
                            "suffix": value, "matching_full_codes": list(options)}
            else:
                result["unresolved"].append({"kind": "ICD_namespace_suffix", "dictionary": dictionary,
                                             "literal": value, "matching_full_codes": list(options),
                                             "reason": "ambiguous_suffix" if options else "no_exact_suffix_match"})
        elif enable_exact_surface and literal.is_string:
            selected_codes = set(info["title_to_codes"].get(value, []))
            if not selected_codes:
                continue
            group = info["normalized_to_titles"].get(V4_MODULE._surface_key(value), [])
            exact = [title for title in group if _contains_exact_surface(question, title)]
            if len(exact) != 1:
                if len(exact) > 1:
                    result["unresolved"].append({"kind": "exact_dictionary_surface", "dictionary": dictionary,
                                                 "literal": value, "question_surfaces": exact,
                                                 "reason": "multiple_exact_question_labels"})
                continue
            target = exact[0]
            target_codes = set(info["title_to_codes"][target])
            if value.casefold() != target.casefold() and target_codes and selected_codes.isdisjoint(target_codes):
                replacement = target
                evidence = {"kind": "unique_exact_question_surface", "dictionary": dictionary,
                            "question_surface": target, "source_codes": sorted(selected_codes),
                            "target_codes": sorted(target_codes),
                            "collision_key": V4_MODULE._surface_key(value)}
        if replacement is not None and replacement != value:
            literal.replace(exp.Literal.string(replacement))
            result["changes"].append({"column": name, "original_literal": value,
                                      "replacement_literal": replacement, "evidence": evidence})
    if result["changes"]:
        result["sql"] = tree.sql(dialect="sqlite")
        result["changed"] = True
        result["SQL_serialization"] = "SQLGlot SQLite rendering after targeted literal replacements only"
    return result


def _source_record(record):
    current = record
    seen = set()
    while isinstance(current, dict):
        if id(current) in seen:
            raise ValueError("Cyclic original-record provenance")
        seen.add(id(current))
        nested = current.get("v5_original_record", current.get("v4_original_record"))
        if nested is None:
            break
        current = nested
    if not isinstance(current, dict) or not isinstance(current.get("sql"), str):
        raise ValueError("A source SQL candidate record is required")
    return deepcopy(current)


def _other_hard_issues(source):
    return list(source.get("static_issues", [])) + list(source.get("contract", {}).get("hard_issues", []))


def normalize_candidate(question, record, metadata, *, enable_exact_surface=True):
    """Normalize from the immutable v3 source, optionally revive a GEF empty.

    Revival requires a completed valid-but-empty original execution, no hard
    issue, a stopped generation and an actual deterministic literal rewrite.
    Genuine model nulls, truncations and syntax failures are not revived.
    """
    source = _source_record(record)
    original_sql = source["sql"]
    source_execution = source.get("execution", {})
    candidate_sql = original_sql
    revival_eligible = False
    skipped_reason = None
    if original_sql == "null":
        previous = source.get("pre_guard_execution", {})
        previous_sql = source.get("pre_guard_sql")
        revival_eligible = bool(
            source.get("guard_rejected") and previous.get("valid") is True
            and previous.get("empty") is True and previous.get("abstained") is False
            and isinstance(previous_sql, str) and previous_sql.strip() and previous_sql != "null"
            and not _other_hard_issues(source) and source.get("finish_reason", "stop") == "stop"
        )
        if revival_eligible:
            candidate_sql = previous_sql
        else:
            skipped_reason = "original_model_null_or_nonrevivable_guard"
    elif source.get("finish_reason", "stop") != "stop" or source_execution.get("valid") is not True:
        skipped_reason = "original_incomplete_or_invalid_generation_not_compiled"
    if skipped_reason is None:
        proposal = compile_namespace(question, candidate_sql, metadata, enable_exact_surface=enable_exact_surface)
    else:
        proposal = {"source_sql": candidate_sql, "sql": candidate_sql, "changed": False, "changes": [],
                    "unresolved": [], "enable_exact_surface": bool(enable_exact_surface),
                    "skipped_reason": skipped_reason}
    active = deepcopy(source)
    if proposal["changed"]:
        active["sql"] = proposal["sql"]
        active["result_fingerprint"] = None  # Old fingerprint belongs to old SQL.
        if revival_eligible:
            active["execution"] = deepcopy(source["pre_guard_execution"])
            active["execution"]["abstained"] = False
            active["guard_rejected"] = False
    # v4 executes the deterministic proposal read-only, applies complete-code
    # physical guards, and rebuilds a full official-round3 multiset fingerprint.
    normalized = V4_MODULE.normalize_candidate(question, active, metadata)
    normalized.update(
        v5_original_record=deepcopy(source), v5_original_record_sql=original_sql,
        v5_original_generation_sql=source.get("pre_guard_sql", original_sql),
        v5_original_execution=deepcopy(source_execution),
        v5_original_result_fingerprint=source.get("result_fingerprint"),
        namespace_repair={**proposal, "revival_eligible": revival_eligible,
                          "revived_gef_empty": revival_eligible and proposal["changed"],
                          "proposal_executed_successfully": bool(proposal["changed"] and normalized["execution"]["valid"]),
                          "original_source_immutable": True,
                          "not_an_LLM_generation_or_semantic_self_review": True},
    )
    return normalized


def select_v5(candidates, policy):
    if policy == "strict3_raw":
        selected = select_record([_source_record(row) for row in candidates], "strict_three_agree")
        selected["selection"].update(policy=policy, normalization="raw_v3_source_fingerprint",
                                      namespace_compiler_enabled=False)
        return selected
    if policy not in _V4_POLICIES:
        raise ValueError("Unknown fixed v5 policy: " + str(policy))
    if any("namespace_repair" not in row or "v5_original_record" not in row for row in candidates):
        raise ValueError("Normalize all candidates with the v5 compiler before selection")
    selected = V4_MODULE.select_v4(candidates, _V4_POLICIES[policy])
    index = selected["selected_candidate_index"]
    selected["selection"].update(
        policy=policy, namespace_compiler_enabled=True,
        deterministic_proposal_selected=bool(index is not None and candidates[index]["namespace_repair"]["changed"]),
        original_LLM_candidate_immutable=True,
    )
    return selected
