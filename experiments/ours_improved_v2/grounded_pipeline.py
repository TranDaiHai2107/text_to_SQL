"""Grounding, semantic review and calibrated abstention; no gold labels here."""
import copy
import json
import math
import re
from sqlglot import exp, parse_one
from common import BASELINE, load, bottom_logprob
from pipeline import SYSTEM, completion_sql
from sql_runtime import outcome

MODES=['v2_grounded','v2_verified','v2_calibrated']
PRIMARY='v2_calibrated'
RESERVED=set(load(BASELINE/'configs/reserved_words.json'))
RULES="""
Match EVERY requested concept, aggregation, entity and temporal constraint. If a required concept has no corresponding field, return null; never substitute a different available concept.
Use exact catalog values rather than guessing a label. d_items.linksto identifies the event table; an abbreviation or unit-bearing label helps distinguish measurements. Microbiology specimen/test/organism names belong to microbiologyevents, not the laboratory item dictionary.
For a requested set return the whole set; add LIMIT only when the question asks for a first/last/top/extreme item or a specific number of results. Do not add demographic filters, patient IDs, or limits from demonstrations.
Honor first vs last admission and the requested before/after relation, including the reference event. A successful SQLite execution alone does not prove that the query answers the question.
No conversation history is supplied. The question is already standalone; preserve its meaning without adding constraints.
"""
REVIEW="""Check whether a candidate SQLite query faithfully answers the ORIGINAL English question using ONLY the supplied database schema and catalog. You are a critical reviewer, not a paraphraser.
Return exactly a JSON object with boolean fields answerable and sql_matches_question and an issues array of short strings. No SQL or markdown.
answerable is false only if required information is absent from this database schema; rarity or a possibly empty answer is not sufficient.
Check the requested output, clinical concept, exact dictionary value/event table, all patient IDs, missing or extra filters, temporal order/reference admission, aggregation, grouping, and unrequested LIMIT. Do not approve an unrelated query merely because it executes.
Use the fixed present time 2100-12-31 23:59:00. No patient result rows or evaluation answer are provided. The catalog is a candidate list, not an exhaustive list or patient evidence.
"""


def context_text(ctx,schemas):
    catalog=[{k:r[k] for k in ('source','column','code','label','abbreviation','linksto') if k in r} for r in ctx['medical']]
    return 'Database schema:\n'+'\n'.join(schemas[t] for t in ctx['tables'])+'\n\nCandidate catalog entries:\n'+json.dumps(catalog,ensure_ascii=False)


def build_messages(question,ctx,schemas):
    messages=[{'role':'system','content':SYSTEM+RULES+'\n'+context_text(ctx,schemas)}]
    used=set()
    for row in ctx['examples']+ctx['null_neighbors']:
        if row['id'] in used:
            continue
        used.add(row['id'])
        messages += [{'role':'user','content':row['question']},{'role':'assistant','content':row['sql']}]
    return messages+[{'role':'user','content':question}]


def static_issues(question,sql,known_values):
    if not sql or sql=='null':
        return []
    try:
        tree=parse_one(sql,read='sqlite')
    except Exception:
        return []  # Execution validation supplies the parse error.
    issues=[]
    requested_ids=set(re.findall(r'\b\d{8}\b',question))
    supplied_ids=set(re.findall(r'(?<!\d)\d{8}(?!\d)',sql))
    if supplied_ids-requested_ids:
        issues.append('Patient identifier(s) not present in the question: '+','.join(sorted(supplied_ids-requested_ids)))
    if tree.args.get('limit') and not re.search(r'\b(first|last|earliest|latest|top|most|least|highest|lowest|maximum|minimum|largest|smallest|recent|best|worst)\b',question,re.I):
        # A stated result count can also license LIMIT. Counts of occurrences
        # (e.g. prescribed two times) do not license cutting the output set.
        if not re.search(r'\b(show|list|return|give)\s+(?:me\s+)?\d+\b',question,re.I):
            issues.append('Top-level LIMIT is not requested; return the complete requested set')
    aliases={t.alias_or_name:t.name for t in tree.find_all(exp.Table)}
    sources=set(aliases.values())
    for equality in tree.find_all(exp.EQ):
        left,right=equality.this,equality.expression
        if isinstance(right,exp.Column) and isinstance(left,exp.Literal):
            left,right=right,left
        if not isinstance(left,exp.Column) or not isinstance(right,exp.Literal) or not right.is_string:
            continue
        table=aliases.get(left.table,left.table) if left.table else None
        candidates=[(t,c) for t,c in known_values if c==left.name and (t==table if table else t in sources)]
        if len(candidates)==1 and right.this not in known_values[candidates[0]]:
            issues.append(f'Exact catalog value does not exist for {candidates[0][0]}.{left.name}: {right.this}')
    return issues


def parse_review(response):
    if response['finish_reason']!='stop':
        return {'answerable':False,'sql_matches_question':False,'issues':['Incomplete semantic review'],'review_error':True}
    text=response['content'].strip()
    if text.startswith('```'):
        text='\n'.join(text.splitlines()[1:-1])
    try:
        obj=json.loads(text)
        if type(obj.get('answerable')) is not bool or type(obj.get('sql_matches_question')) is not bool or not isinstance(obj.get('issues'),list) or not all(isinstance(x,str) for x in obj['issues']):
            raise ValueError('Invalid review schema')
        return {k:obj[k] for k in ('answerable','sql_matches_question','issues')}
    except (ValueError,TypeError,AttributeError):
        return {'answerable':False,'sql_matches_question':False,'issues':['Malformed semantic review'],'review_error':True}


def confidence(response,review_response=None):
    try:
        sql_score=bottom_logprob(response['logprobs'] or [],RESERVED,bottom_n=10)
    except (TypeError,KeyError,ValueError):
        return {'score':None,'sql_bottom10':None,'review_true_min':None,'sql_call_hash':response['request_hash'],'missing_logprobs':True}
    review_score=None
    if review_response is not None:
        values=[r['logprob'] for r in review_response.get('logprobs') or [] if r['token'].strip()=='true']
        if len(values)>=2 and all(math.isfinite(v) for v in values):
            review_score=min(values)
    # This is a calibrated heuristic score, not a probability of correctness.
    return {'score':min(sql_score,review_score) if review_score is not None else sql_score,
            'sql_bottom10':sql_score,'review_true_min':review_score,'sql_call_hash':response['request_hash'],
            'review_call_hash':review_response['request_hash'] if review_response else None,'missing_logprobs':False}


def reject(record,reason):
    result=copy.deepcopy(record)
    result['pre_filter_sql']=result['sql']
    result['sql']='null'
    result['execution']=outcome('null')
    result['rejection_reason']=reason
    return result


def apply_threshold(record,threshold):
    if record['sql']=='null' or threshold is None:
        return copy.deepcopy(record)
    value=record['confidence']['score']
    if value is None or value<=threshold:
        return reject(record,'calibrated_confidence_gate')
    return copy.deepcopy(record)


def run_question(item,rag,client,threshold=None,exclude_self=False):
    question=item['question']
    ctx=rag.retrieve(question,exclude_id=item['id'] if exclude_self else None)
    messages=build_messages(question,ctx,rag.schema)
    hashes=[]
    history=[]
    attempts=0
    def generate(stage,feedback=None):
        nonlocal attempts
        if feedback:
            messages.extend([{'role':'assistant','content':sql or '[invalid completion]'},
                             {'role':'user','content':'Re-check the original question: '+question+'\nProblems: '+feedback+'\nCorrect the SQL using the supplied schema, or return null if required information is absent. Output only SQL or null.'}])
        response=client.call(messages,stage,item['id'],max_tokens=2048)
        hashes.append(response['request_hash'])
        attempts+=1
        return response,*completion_sql(response)
    response,sql,execution=generate('v2_grounded_sql')
    issues=static_issues(question,sql,rag.known_values)
    if sql!='null' and (not execution['valid'] or issues):
        history.append({'sql':sql,'issues':issues,'execution_error':execution['error']})
        response,sql,execution=generate('v2_static_repair','; '.join(issues+[execution['error'] or '']))
        issues=static_issues(question,sql,rag.known_values)
    record={'sql':sql,'execution':execution,'attempts':attempts,'history':history,'call_hashes':list(hashes),
            'retrieval':ctx,'input_question':question,'static_issues':issues,'confidence':confidence(response)}
    # Preserve the generation variant; execution failures remain visible here.
    grounded=copy.deepcopy(record)
    if sql!='null' and (not execution['valid'] or execution['empty'] or issues):
        record=reject(record,'execution_empty_invalid_or_static_guard')
    elif sql!='null':
        def review(current_sql):
            result=client.call([{'role':'system','content':REVIEW},
                {'role':'user','content':context_text(ctx,rag.schema)+'\nOriginal question: '+question+'\nCandidate SQL: '+current_sql}],
                'v2_semantic_review',item['id'],max_tokens=512)
            hashes.append(result['request_hash'])
            return result,parse_review(result)
        review_response,verdict=review(sql)
        if verdict['answerable'] and not verdict['sql_matches_question']:
            history.append({'sql':sql,'semantic_issues':verdict['issues']})
            response,sql,execution=generate('v2_semantic_repair','; '.join(verdict['issues']) or 'SQL does not faithfully answer the question')
            issues=static_issues(question,sql,rag.known_values)
            record.update(sql=sql,execution=execution,attempts=attempts,static_issues=issues)
            if sql!='null' and execution['valid'] and not execution['empty'] and not issues:
                review_response,verdict=review(sql)
            else:
                verdict={'answerable':False,'sql_matches_question':False,'issues':['Repair abstained, failed a guard, or produced empty output']}
                review_response=None
        record.update(review=verdict,confidence=confidence(response,review_response))
        if not (verdict['answerable'] and verdict['sql_matches_question']):
            record=reject(record,'semantic_review_rejected')
    record.update(call_hashes=list(hashes),attempts=attempts,history=history)
    return {'id':item['id'],'question':question,'variants':{'v2_grounded':grounded,'v2_verified':record,
             'v2_calibrated':apply_threshold(record,threshold)}}
