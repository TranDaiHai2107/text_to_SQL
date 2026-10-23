"""English/SQLite adaptations of build_prompt, three RAG layers and agentic repair.

No evaluation gold is available to this module. Native multi-turn rewrite with
empty history is intentionally identity, exactly like the user's original code.
"""
import copy
import re
from sql_runtime import clean_sql, outcome

MODES = ["base", "icd", "schema", "examples", "three_rag", "three_rag_agentic",
         "three_rag_native_rewrite_agentic", "three_rag_standalone_rewrite_agentic",
         "three_rag_agentic_gef", "three_rag_standalone_rewrite_agentic_gef"]
DEFAULT_MODES = ["base", "three_rag", "three_rag_agentic", "three_rag_native_rewrite_agentic",
                 "three_rag_standalone_rewrite_agentic", "three_rag_agentic_gef",
                 "three_rag_standalone_rewrite_agentic_gef"]

SYSTEM = """You translate an English medical question into ONE executable SQLite SELECT query on the provided EHR database.
Return ONLY SQL, or exactly null if the question cannot be answered from this schema. No markdown or explanations.
Use ONLY listed tables and columns. Never invent medical facts, fields, patient attributes or joins.
This is the EHRSQL benchmark, not standard MIMIC-IV: age is admissions.age; patients has dob/dod; ICD codes have no icd_version.
All timestamps are stored as text-compatible SQLite timestamps. Use SQLite datetime/strftime/julianday, not PostgreSQL syntax.
The fixed present time is '2100-12-31 23:59:00'. Today is 2100-12-31. Keep all patient IDs, dates, quantities and requested time scopes.
For first/last hospital admission use admittime ordering. For first/last ICU visit use icustays.intime ordering.
For costs, match cost.event_type and cost.event_id to the event row_id; hadm_id alone can multiply costs.
Clinical measurements use d_items for ICU/chartevents/inputevents/outputevents and d_labitems for labevents.
Normal ranges: temperature 35.5..38.1, sao2 95..100, heart rate 60..100, respiration 12..18,
systolic bp 90..120, diastolic bp 60..90, mean bp 60..110. Abnormal means outside the relevant range.
Retrieved medical dictionary entries are candidates, not facts about the patient. Use only relevant entries.
Retrieved training examples teach SQL structure; replace their IDs, names and time constraints with the user's request.
If required information is absent (e.g. clinical notes, cancer stage, doctor identity or unavailable measurements), return null.
Do not return null merely because a query might have no rows: SQL should determine data availability.
An unanswerable example's null is evidence of missing schema information, not a template to copy blindly.
"""

REWRITE = """Rewrite this single English medical question as a clear standalone English question, preserving its EXACT meaning.
It is already independent: do not add history, clinical assumptions, diagnoses, constraints, patient facts or missing dates.
Keep every patient ID, number, quoted drug/test name, first/last/before/after relation and time interval.
If already clear, return it unchanged. Return only the question, without quotation marks or explanation."""


def preserve_rewrite(original, proposed):
    text = proposed.strip().strip('"').strip()
    if not text or len(text) > max(1000, 3*len(original)):
        return original, "invalid_length"
    numbers = re.findall(r"\b\d+(?:\.\d+)?\b", original)
    if any(n not in re.findall(r"\b\d+(?:\.\d+)?\b", text) for n in numbers):
        return original, "numeric_constraint_changed"
    for phrase in re.findall(r"['\"]([^'\"]+)['\"]", original):
        if phrase.casefold() not in text.casefold():
            return original, "quoted_entity_changed"
    for word in ["first", "last", "before", "after", "since", "until", "within"]:
        if re.search(r"\b"+word+r"\b", original, re.I) and not re.search(r"\b"+word+r"\b", text, re.I):
            return original, "temporal_relation_changed"
    return text, "accepted" if text != original else "identity"


def build_prompt(question, ctx, schemas):
    sections = ["Database schema:\n"+"\n".join(schemas[t] for t in ctx["tables"])]
    if ctx["medical"]:
        sections.append("Candidate clinical dictionary matches:\n"+"\n".join(
            f"{r['source']}: {r['label']} -> {r['code']}" for r in ctx["medical"]))
    if ctx["examples"]:
        sections.append("Training examples (train split only):\n"+"\n\n".join(
            "Question: "+r["question"]+"\nSQL: "+r["sql"] for r in ctx["examples"]))
    sections.append("Question: "+question+"\nSQL:")
    return [{"role":"system", "content":SYSTEM}, {"role":"user", "content":"\n\n".join(sections)}]


def generate(question_id, question, rag_mode, rag, client):
    ctx = rag.retrieve(question, rag_mode)
    messages = build_prompt(question, ctx, rag.schema)
    response = client.call(messages, "sql_"+rag_mode, question_id, max_tokens=getattr(client, "sql_tokens", 4096))
    sql = clean_sql(response["content"])
    execution = outcome(sql)
    if response["finish_reason"] == "length":
        execution = {"valid":False, "abstained":False, "empty":None, "error":"model_generation_truncated"}
    return {"sql":sql, "execution":execution, "attempts":1, "messages":messages,
            "retrieval":ctx, "call_hashes":[response["request_hash"]], "history":[]}


def repair(question_id, record, client):
    result = copy.deepcopy(record)
    # Valid null is a model abstention. Do not fabricate a SQL repair for it.
    for attempt in range(2):
        if result["execution"]["valid"] or result["execution"]["abstained"]:
            break
        error = result["execution"]["error"]
        result["history"].append({"sql":result["sql"], "error":error})
        result["messages"].extend([
            {"role":"assistant", "content":result["sql"]},
            {"role":"user", "content":"This SQL failed SQLite schema validation/execution: "+str(error)+
             "\nCorrect it using only the supplied schema and the original question. If the requested information is absent, return null. Output SQL or null only."}])
        response = client.call(result["messages"], "self_correction", question_id, max_tokens=getattr(client, "sql_tokens", 4096))
        result["call_hashes"].append(response["request_hash"])
        result["attempts"] += 1
        result["sql"] = clean_sql(response["content"])
        result["execution"] = outcome(result["sql"])
        if response["finish_reason"] == "length":
            result["execution"] = {"valid":False, "abstained":False, "empty":None, "error":"model_generation_truncated"}
    return result


def gef(record):
    result = copy.deepcopy(record)
    if not result["execution"]["valid"] or result["execution"]["empty"]:
        result["sql"] = "null"
        result["gef_filtered"] = not result["execution"]["abstained"]
    else:
        result["gef_filtered"] = False
    return result


def public_record(record):
    # No raw patient result rows are ever persisted or sent to the LLM.
    return {key:value for key,value in record.items() if key != "messages"}


def run_question(item, modes, rag, client, on_stage=None):
    question_id, question = item["id"], item["question"]
    records = {}
    def save(mode, record):
        records[mode] = record
        if on_stage:
            on_stage(mode, public_record(record))
    for mode in ["base", "icd", "schema", "examples"]:
        if mode in modes:
            save(mode, generate(question_id, question, mode, rag, client))
    full_modes = [m for m in modes if m.startswith("three_rag")]
    if full_modes:
        full = generate(question_id, question, "full", rag, client)
        if "three_rag" in modes:
            save("three_rag", full)
        enhanced = repair(question_id, full, client) if any(m != "three_rag" for m in full_modes) else full
        if "three_rag_agentic" in modes:
            save("three_rag_agentic", enhanced)
        if "three_rag_native_rewrite_agentic" in modes:
            save("three_rag_native_rewrite_agentic", {**enhanced,
                "rewrite":{"kind":"native_multiturn", "history_messages":0, "changed":False,
                           "question":question, "reason":"original rewrite_question returns identity without history"}})
        if "three_rag_agentic_gef" in modes:
            save("three_rag_agentic_gef", gef(enhanced))
        if any("standalone_rewrite" in m for m in modes):
            response = client.call([{"role":"system", "content":REWRITE}, {"role":"user", "content":question}],
                                   "standalone_rewrite", question_id, max_tokens=getattr(client, "rewrite_tokens", 1024))
            rewritten, guard = preserve_rewrite(question, response["content"])
            if response["finish_reason"] == "length":
                rewritten, guard = question, "truncated_rewrite_rejected"
            rewritten_result = enhanced if rewritten == question else repair(question_id,
                generate(question_id, rewritten, "full", rag, client), client)
            rewritten_result = copy.deepcopy(rewritten_result)
            rewritten_result["rewrite"] = {"kind":"standalone_extension", "question":rewritten,
                                           "changed":rewritten != question, "guard":guard}
            rewritten_result["call_hashes"].append(response["request_hash"])
            if "three_rag_standalone_rewrite_agentic" in modes:
                save("three_rag_standalone_rewrite_agentic", rewritten_result)
            if "three_rag_standalone_rewrite_agentic_gef" in modes:
                save("three_rag_standalone_rewrite_agentic_gef", gef(rewritten_result))
    return {"id":question_id, "question":question, "variants":{k:public_record(v) for k,v in records.items()}}

