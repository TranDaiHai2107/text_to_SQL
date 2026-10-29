"""Shared EHRSQL semantics and conservative, non-mutating SQL diagnostics.

Evidence below was checked against train/dev labels and the actual SQLite
schema only.  No evaluation split is read when this module is imported.
Hard diagnostics concern introduced identifiers or complete enumerations;
semantic/shape conventions remain advisory because equivalent SQL is valid.
"""
from collections.abc import Mapping
import re

from sqlglot import exp, parse_one


BENCHMARK_CONVENTIONS = """EHRSQL benchmark conventions, shared by generation and checking:
Use the fixed present time 2100-12-31 23:59:00. 'This year/month' is relative to that clock. 'Last/previous year' denotes the previous calendar year; 'since 1 year ago' is a rolling lower bound. In 'this month/07' or 'last month/14', the suffix is the DAY of the relative month, not month 07/14. Preserve full explicit date and year constraints.
'This/current hospital visit' uses admissions with dischtime IS NULL. First/last historical hospital-visit templates use completed admissions (dischtime IS NOT NULL), ordered by admittime; distinguish this from the first/last measurement WITHIN a visit. ICU visits use icustays/stay_id and intime, not hospital admission ordering. General hospital careunit history is in transfers; ICU first/last_careunit alone is not a substitute for all transfers.
Return precisely the requested result fields. Daily/monthly/yearly aggregate templates can return only the aggregate, grouped by the period: do not add a date/year/count column merely for presentation. Top-frequency templates in this benchmark often use DENSE_RANK and retain ties; follow a matching knowledge example rather than automatically replacing this with LIMIT. Do not add a count or rank output column unless requested. Percentile templates use PERCENT_RANK over the requested measurement/cohort; do not silently substitute another percentile definition.
Elapsed days may be fractional: retain the Julian-day difference unless integer rounding is explicitly requested. Keep diagnosis/event time, admission time, and current-visit scope distinct. 'Within N months after' is an interval; 'in the same month' is a calendar-month relationship, not automatically a 30-day interval.
Use exact catalog values, event table, itemid/ICD code, and units. A partial retrieved catalog is not proof that a value is absent. Multiple similar measurement labels/units require disambiguation, not a fabricated conversion. For cost, match cost.event_type to the real event-table enum from metadata and cost.event_id to that event's row_id; hadm_id alone can multiply costs. Simple cost templates return DISTINCT recorded costs, whereas an explicit request for an average/total requires that aggregation. Do not invent event-type aliases such as 'lab'.
These are benchmark conventions grounded in knowledge examples, not additional patient facts. Preserve the original question. Never replace a normative treatment recommendation, missing document/consent field, or unsupported concept with an available historical-data query. If required information is genuinely missing, return null. A successful query, an empty query result, or an incomplete catalog alone does not establish semantic correctness or unanswerability.
"""

# Stable documentation anchors.  They are not injected as answer examples and
# contain no patient result rows. Each rule has train and dev corroboration.
RULE_EVIDENCE = {
    "relative_month_day": [
        {"split": "train", "id": "4d29021ef5a4f0368bdfa1a1"},
        {"split": "dev", "id": "068a6fbca2eb611746f77955"},
    ],
    "previous_calendar_year": [
        {"split": "train", "id": "366e4fe872705e8dbb87ae20"},
        {"split": "dev", "id": "d9dc77e2a9eef59e0164883e"},
    ],
    "rolling_since_year": [
        {"split": "train", "id": "05d218c03d4f3db81a54165a"},
        {"split": "dev", "id": "aef8b935473950853a7d8448"},
    ],
    "current_visit": [
        {"split": "train", "id": "b53daa3c6e0af875928b6bd7"},
        {"split": "dev", "id": "ffc47b7e01463f229eb09bce"},
    ],
    "completed_first_last_visit": [
        {"split": "train", "id": "f0ed8bc2f755ef37eb17af6e"},
        {"split": "dev", "id": "1039ad255c53fd49a3e45f2f"},
    ],
    "fractional_elapsed_days": [
        {"split": "train", "id": "b53daa3c6e0af875928b6bd7"},
        {"split": "dev", "id": "e76832974c5806793c6d4c8a"},
    ],
    "ranking_ties": [
        {"split": "train", "id": "003865fdb611e9f27fe18281"},
        {"split": "dev", "id": "a35a9346ab483d0db0f202ca"},
    ],
    "grouped_output_shape": [
        {"split": "train", "id": "eec94693605289856658f678"},
        {"split": "dev", "id": "2b36b98f68fb7d33d7e8e7f3"},
    ],
    "cost_event_join": [
        {"split": "train", "id": "ae87fc8fc5ccf8578f0ec36c"},
        {"split": "dev", "id": "a8225cc86d80b3c2bcb42899"},
    ],
    "careunit_history": [
        {"split": "train", "id": "05d218c03d4f3db81a54165a"},
        {"split": "dev", "id": "8ba1b2de9452cc1d23057b9f"},
    ],
    "percentile_definition": [
        {"split": "train", "id": "3f720ea93f94700efe7fe7ee"},
        {"split": "dev", "id": "1039ad255c53fd49a3e45f2f"},
    ],
}


def _nearest_select(node):
    while node is not None:
        if isinstance(node, exp.Select):
            return node
        node = node.parent
    return None


def _local_tables(select):
    """Resolve aliases inside one SELECT without flattening nested scopes."""
    if select is None:
        return {}
    return {table.alias_or_name.casefold(): table.name.casefold()
            for table in select.find_all(exp.Table)
            if _nearest_select(table.parent) is select}


def _catalog_entry(value):
    # Plain sets/lists mean an exhaustive DISTINCT metadata enumeration. Callers
    # passing retrieval-only candidates MUST mark complete=False.
    if isinstance(value, Mapping):
        return {str(x) for x in value.get("values", [])}, value.get("complete") is True
    return {str(x) for x in value}, True


def _known_catalog(known_values):
    result = {}
    for key, value in (known_values or {}).items():
        if isinstance(key, tuple) and len(key) == 2:
            result[(str(key[0]).casefold(), str(key[1]).casefold())] = _catalog_entry(value)
    return result


def _comparison_literals(tree):
    """Direct EQ/IN literals only: do not guess semantics of LOWER/COLLATE/CTEs."""
    for predicate in tree.find_all(exp.EQ):
        left, right = predicate.this, predicate.expression
        if isinstance(left, exp.Literal) and isinstance(right, exp.Column):
            left, right = right, left
        if isinstance(left, exp.Column) and isinstance(right, exp.Literal):
            yield left, right, predicate
    for predicate in tree.find_all(exp.In):
        if isinstance(predicate.this, exp.Column):
            for literal in predicate.expressions:
                if isinstance(literal, exp.Literal):
                    yield predicate.this, literal, predicate


def contract_issues(question, sql, known_values):
    """Return {hard_issues: [...], soft_issues: [...]}; never change SQL.

    `known_values` maps (table, column) to a complete set of actual DB values,
    or to {"values": [...], "complete": bool}. Partial catalogs only produce
    soft diagnostics. Shape/time/ranking/units diagnostics are ALWAYS soft;
    callers must not count them as schema errors or automatically reject them.
    """
    hard, soft = [], []
    if not sql or sql.strip().casefold() == "null":
        return {"hard_issues": hard, "soft_issues": soft}
    try:
        tree = parse_one(sql, read="sqlite")
    except Exception:
        return {"hard_issues": hard, "soft_issues": ["sql_parse: use execution/schema validation for this SQL"]}
    q = question.casefold()
    text = re.sub(r"\s+", " ", sql.casefold())
    known = _known_catalog(known_values)
    question_numbers = {str(int(x)) for x in re.findall(r"\b\d+\b", question)}
    for column, literal, predicate in _comparison_literals(tree):
        name, value = column.name.casefold(), str(literal.this)
        if name == "subject_id" and re.fullmatch(r"\d+", value):
            if str(int(value)) not in question_numbers:
                hard.append("introduced_patient_id: subject_id=" + value + " is absent from the question")
        if not literal.is_string:
            continue
        tables = _local_tables(_nearest_select(predicate))
        qualifier = column.table.casefold()
        resolved = tables.get(qualifier) if qualifier else None
        candidates = [key for key in known if key[1] == name and
                      (key[0] == resolved if qualifier else key[0] in tables.values())]
        if len(candidates) != 1:
            continue  # Ambiguous/correlated/CTE-derived values need a richer resolver.
        key = candidates[0]
        values, complete = known[key]
        if value in values:
            continue
        message = "unknown_enum: " + ".".join(key) + "=" + repr(value)
        # A user can legitimately ask about a literal whose data are absent.
        # Internal structural enums are different: 'lab' is never a valid
        # cost.event_type just because the question says 'lab test'.
        structural = key == ("cost", "event_type") or key == ("d_items", "linksto")
        explicit_user_literal = bool(value.strip()) and value.casefold() in q
        if complete and (structural or not explicit_user_literal):
            hard.append(message + " is absent from the complete DB enumeration")
        else:
            soft.append(message + "; partial catalog or literal supplied by user, check grounding without inferring unanswerability")

    outer = tree if isinstance(tree, exp.Select) else None
    if outer is not None:
        projections = outer.expressions
        period_request = bool(re.search(r"\b(daily|monthly|yearly|per day|per month|per year)\b", q))
        if len(projections) > 1 and outer.args.get("group") and period_request:
            soft.append("output_shape: grouped-period request has multiple output columns; confirm dates/counts were requested rather than presentation-only additions")
        frequency_request = bool(re.search(r"\b(most common|most frequent\w*|top \w+)\b", q))
        if frequency_request and len(projections) > 1:
            soft.append("output_shape: frequency/ranking request has multiple output columns; confirm count/rank columns belong to the requested answer")
        if frequency_request and outer.args.get("limit") and not tree.find(exp.DenseRank):
            soft.append("ranking_ties: matching EHRSQL examples may retain ties with DENSE_RANK; confirm tie policy, do not blindly replace an equivalent query")

    month_day = re.search(r"\b(?:this|last|previous) month/(\d{1,2})\b", q)
    if month_day and "%d" not in text:
        day = int(month_day.group(1))
        date_literals = [str(x.this) for x in tree.find_all(exp.Literal) if x.is_string]
        if not any(re.search(r"\d{4}-\d{2}-" + f"{day:02d}" + r"(?:\D|$)", x) for x in date_literals):
            soft.append("relative_month_day: slash suffix is day of the relative month; confirm an equivalent day constraint exists")
    if re.search(r"\b(?:last|previous) year\b", q) and not re.search(r"\bsince\s+(?:the\s+)?(?:last|previous) year\b", q):
        if "start of year" not in text and "2099" not in text:
            soft.append("calendar_year: previous/last year uses the previous calendar year; confirm an equivalent calendar-year range rather than a rolling lookback")
    if re.search(r"\b(?:this|current) hospital (?:visit|encounter|admission)\b|\bcurrent (?:visit|admission)\b", q):
        if not re.search(r"\bdischtime\s+is\s+null\b", text):
            soft.append("current_visit: confirm the hospital admission is current (dischtime IS NULL or equivalent), not merely latest")
    if re.search(r"\b(?:first|last) hospital (?:visit|encounter|admission|stay)\b", q):
        if not re.search(r"\bdischtime\s+is\s+not\s+null\b", text):
            soft.append("historical_visit: matching first/last hospital templates use completed admissions; confirm scope without changing first/last measurement semantics")
    if "days" in q and ("julianday" in text or "%j" in text):
        for cast in tree.find_all(exp.Cast):
            target = cast.args.get("to")
            if target is not None and target.sql().upper() in {"INT", "INTEGER", "BIGINT", "SMALLINT"} and ("julianday" in cast.this.sql().casefold() or "%j" in cast.this.sql().casefold()):
                soft.append("fractional_days: integer CAST can truncate an elapsed-day result; retain fractional days unless rounding was requested")
    tables = {table.name.casefold() for table in tree.find_all(exp.Table)}
    if "cost" in tables:
        if not any(c.name.casefold() == "event_type" for c in tree.find_all(exp.Column)):
            soft.append("cost_join: confirm cost.event_type matches the event table as well as the event row_id")
        if not any(c.name.casefold() == "event_id" for c in tree.find_all(exp.Column)):
            soft.append("cost_join: confirm cost.event_id joins the event row_id; hadm_id alone may duplicate costs")
        if not re.search(r"\b(average|mean|total|sum)\b", q) and re.search(r"\b(avg|sum)\s*\(", text):
            soft.append("cost_output: simple cost knowledge templates return DISTINCT recorded costs; confirm whether aggregation was explicitly requested")
    if ("care unit" in q or "careunit" in q) and "icustays" in tables and "transfers" not in tables:
        soft.append("careunit_scope: ICU first/last_careunit does not represent all hospital transfers; confirm the requested scope")
    if re.search(r"\bheight\b", q) and any("height" in str(x.this).casefold() for x in tree.find_all(exp.Literal) if x.is_string):
        soft.append("measurement_units: multiple height labels/units may exist; use actual item metadata and stated units, without inventing a conversion")
    return {"hard_issues": list(dict.fromkeys(hard)), "soft_issues": list(dict.fromkeys(soft))}
