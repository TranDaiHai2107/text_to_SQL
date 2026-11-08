"""Bounded question-contract and physical-metadata SQL repairs, developed on dev.

No labels, IDs, API calls or test files are read. All untouched V5 candidates
retain their predictions; changed proposals are re-executed read-only and keep
the original candidate for audit. Parent runner owns policy selection.
"""
from __future__ import annotations

from copy import deepcopy
import importlib.util
from pathlib import Path
import re
import sys

from sqlglot import exp, parse_one

_WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_WORKSPACE))
sys.path.append(str(_WORKSPACE / "baselines/probgate_ehrsql_2024"))
RUNTIME = Path(__file__).resolve().parent / "runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(1, str(RUNTIME))
import namespace as V5_MODULE
V4_MODULE = V5_MODULE.V4_MODULE


def _unaliased(node):
    return node.this if isinstance(node, exp.Alias) else node


def _sql_key(node):
    return _unaliased(node).sql(dialect="sqlite", normalize=True)


def _period_expression(node):
    text = _sql_key(node).casefold()
    return text.startswith("strftime(") and any(pattern in text for pattern in ("%y", "%m", "%d", "%w"))


def _aggregate_kind(question):
    q = question.casefold()
    if not re.search(r"\b(daily|weekly|monthly|yearly|annual)\b", q):
        return None
    # Explicitly requested date keys must remain output, even when grouped.
    if re.search(r"\b(date|dates|timestamp|timestamps|when)\b|\b(?:month|day|year|week)\s+(?:and|with)\b|\b(?:include|including|show|return|list)\s+(?:the\s+)?(?:month|day|year|week)\b|\b(?:by|per)\s+(?:the\s+)?(?:month|day|year|week)\b|\b(?:for\s+)?each\s+(?:month|day|year|week)\b", q):
        return None
    kinds = [(r"\b(average|mean|avg)\b", exp.Avg), (r"\b(maximum|max|highest)\b", exp.Max),
             (r"\b(minimum|min|lowest)\b", exp.Min), (r"\b(sum|total)\b", exp.Sum)]
    matched = [kind for pattern, kind in kinds if re.search(pattern, q)]
    return matched[0] if len(matched) == 1 else None


def _projection_repair(question, tree):
    kind = _aggregate_kind(question)
    if kind is None or not isinstance(tree, exp.Select) or tree.args.get("group") is None:
        return None
    projections = list(tree.expressions)
    if len(projections) < 2 or tree.args.get("distinct") or tree.args.get("with_"):
        return None
    # ORDER BY 1 binds to the projection position, not the source expression.
    # Dropping a period key can change the selected row under LIMIT. Skip any
    # numeric order expression conservatively rather than rewriting ordinals.
    order = tree.args.get("order")
    if order is not None and any(not node.is_string for node in order.find_all(exp.Literal)):
        return None
    aggregates = [node for node in projections if isinstance(_unaliased(node), kind)]
    if len(aggregates) != 1:
        return None
    other = [node for node in projections if node is not aggregates[0]]
    grouped = {_sql_key(node) for node in tree.args["group"].expressions}
    if not other or any(not _period_expression(node) or _sql_key(node) not in grouped for node in other):
        return None
    # Removing an alias referenced by ORDER/HAVING would need another rewrite.
    removed_aliases = {node.alias.casefold() for node in other if node.alias}
    for clause in (tree.args.get("order"), tree.args.get("having")):
        if clause is not None and any(not col.table and col.name.casefold() in removed_aliases for col in clause.find_all(exp.Column)):
            return None
    tree.set("expressions", [aggregates[0]])
    return {"kind": "period_aggregate_output_contract", "removed_projection_expressions": [_sql_key(n) for n in other],
            "retained_aggregate": _sql_key(aggregates[0]), "grouping_and_filters_unchanged": True,
            "evidence": "Question requests period aggregate, not period labels; removed expressions are exactly GROUP BY period keys"}


def _organism_repair(question, tree):
    q = question.casefold()
    if not (re.search(r"\borganism\b", q) and re.search(r"\b(first|last|earliest|latest)\b", q)):
        return None
    if re.search(r"\b(not|missing|absent|unknown|null|negative)\b|\bno organism\b", q):
        return None
    if not isinstance(tree, exp.Select) or len(tree.expressions) != 1 or tree.args.get("order") is None:
        return None
    value = _unaliased(tree.expressions[0])
    limit = tree.args.get("limit")
    if not isinstance(value, exp.Column) or value.name.casefold() != "org_name" or limit is None or str(limit.expression) != "1":
        return None
    tables = V4_MODULE._local_tables(tree)
    if value.table:
        if tables.get(value.table.casefold()) != "microbiologyevents":
            return None
    elif list(tables.values()) != ["microbiologyevents"]:
        return None
    where = tree.args.get("where")
    if where is not None:
        for node in where.find_all(exp.Is):
            if (isinstance(node.this, exp.Column) and node.this.name.casefold() == "org_name"
                    and isinstance(node.expression, exp.Null) and V4_MODULE._nearest_select(node) is tree):
                return None  # Respect both existing IS NULL and IS NOT NULL.
    predicate = exp.Not(this=exp.Is(this=value.copy(), expression=exp.Null()))
    tree.where(predicate, append=True, copy=False)
    return {"kind": "observed_first_last_organism", "added_condition": predicate.sql(dialect="sqlite"),
            "evidence": "EHRSQL train convention: 84/84 first/last organism labels filter missing org_name before chronological selection; this is benchmark-specific, not metadata proof or universal clinical semantics"}


def _casefold_code_repairs(tree, metadata):
    changes = []
    for column, literal, predicate in list(V4_MODULE._direct_literals(tree)):
        if column.name.casefold() != "icd_code" or not literal.is_string:
            continue
        dictionary = V4_MODULE._resolve_dictionary(column, predicate, metadata)
        if dictionary is None:
            continue
        info = metadata["tables"][dictionary]
        value = str(literal.this)
        if value in info["code_to_titles"]:
            continue
        if re.match(r"^icd(?:9|10)\|", value, re.I):
            options = [code for code in info["code_to_titles"] if code.casefold() == value.casefold()]
        else:
            options = [code for code in info["code_to_titles"] if "|" in code and code.split("|", 1)[1].casefold() == value.casefold()]
        if len(options) == 1:
            literal.replace(exp.Literal.string(options[0]))
            changes.append({"kind": "unique_casefold_physical_ICD_code", "dictionary": dictionary,
                            "original_literal": value, "replacement_literal": options[0],
                            "matching_full_codes": options})
    return changes


def compile_v6(question, sql, metadata, *, enable_projection=True, enable_organism=True, enable_casefold=True):
    result = {"source_sql": sql, "sql": sql, "changed": False, "changes": [], "no_gold_access": True}
    if not sql or sql == "null":
        return result
    try:
        tree = parse_one(sql, read="sqlite")
    except Exception:
        return result
    if enable_casefold:
        result["changes"].extend(_casefold_code_repairs(tree, metadata))
    if enable_projection:
        change = _projection_repair(question, tree)
        if change:
            result["changes"].append(change)
    if enable_organism:
        change = _organism_repair(question, tree)
        if change:
            result["changes"].append(change)
    if result["changes"]:
        result.update(sql=tree.sql(dialect="sqlite"), changed=True)
    return result


def enhance_candidate(question, candidate, metadata, **flags):
    original = deepcopy(candidate)
    output = deepcopy(candidate)
    source_sql = candidate["sql"]
    revival = False
    if source_sql == "null":
        repair = candidate.get("namespace_repair", {})
        # Inherit the existing strict V5 valid-but-empty revival requirements.
        if repair.get("revival_eligible") is not True:
            output["v6_repair"] = {"changed": False, "reason": "model_null_or_nonrevivable_guard"}
            return output
        source_sql = repair.get("source_sql", "null")
        revival = True
    elif candidate.get("finish_reason", "stop") != "stop" or candidate.get("execution", {}).get("valid") is not True:
        output["v6_repair"] = {"changed": False, "reason": "generation_incomplete_or_invalid"}
        return output
    if candidate.get("static_issues") or candidate.get("contract", {}).get("hard_issues"):
        output["v6_repair"] = {"changed": False, "reason": "existing_hard_issue"}
        return output
    proposal = compile_v6(question, source_sql, metadata, **flags)
    output["v6_repair"] = proposal
    if not proposal["changed"]:
        return output
    if revival and not any(c["kind"] == "unique_casefold_physical_ICD_code" for c in proposal["changes"]):
        output["v6_repair"]["reason"] = "empty_revive_requires_proven_physical_code_repair"
        return output
    active = deepcopy(candidate)
    active.pop("v4_original_record", None)
    active["sql"] = proposal["sql"]
    active["execution"] = {"valid": True, "abstained": False, "empty": False, "error": None}
    active["guard_rejected"] = False
    if any(c["kind"] == "period_aggregate_output_contract" for c in proposal["changes"]):
        active["contract"]["soft_issues"] = [s for s in active["contract"].get("soft_issues", []) if not s.startswith("output_shape:")]
    normalized = V4_MODULE.normalize_candidate(question, active, metadata)
    if normalized["execution"].get("valid") is not True or normalized["execution"].get("empty") is not False:
        output["v6_repair"].update(proposal_accepted=False, reason="proposal_not_valid_nonempty_keep_V5")
        return output
    normalized.update(v6_original_record=original, v6_repair={**proposal, "proposal_accepted": True,
                      "revived_gef_empty": revival, "readonly_reexecuted": True})
    return normalized


def enhance_v6(question, candidates, metadata, **flags):
    return [enhance_candidate(question, candidate, metadata, **flags) for candidate in candidates]
