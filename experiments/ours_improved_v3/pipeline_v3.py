"""Independent candidate generation with evidence-based guards, no gold access."""
import copy
from decimal import Decimal
import hashlib
import json
from sqlglot import exp,parse_one
from infrastructure import V2_SYSTEM,clean_sql,execute,outcome
from semantics_v3 import BENCHMARK_CONVENTIONS,contract_issues

ROUTES=['direct','structural','plan']
ROUTE_RULES={
 'direct':'Translate the question directly, using the relevant demonstrations as benchmark conventions. Preserve EXACT requested output; do not add explanatory columns.',
 'structural':'Solve by matching the logical SQL structure in demonstrations, then binding entities and all time constraints from the actual question. Check aggregation, admission scope, grouping and ties. Do not copy patient IDs or filter values from another example.',
 'plan':'Independently determine requested output, patient/population, clinical entity, visit scope, temporal reference, grouping and aggregation before constructing SQL. Resolve these internally. Return only the final SQL or null, never the plan. Do not substitute historical records for treatment advice, explanations, consent, notes or other absent information.'}
GROUNDING_RULES="""
The dictionary is a candidate list, not an exhaustive database. Missing from this list alone is NOT proof the question is unanswerable.
Link clinical names to the correct table AND column. Event names in cost.event_type must match actual categorical metadata, not a guessed synonym.
Output only the requested attribute/aggregate. A time unit used for GROUP BY does not require adding that time key to SELECT unless the question explicitly asks to return it. Preserve fractions unless asked to round.
For medical recommendations (what should be prescribed/done), causal explanations, clinical notes, doctor identities, consent forms, or other fields absent from the schema, return null. Existing prescriptions only answer historical prescribing questions.
Never use invented catalog values or patient filters. Do not add LIMIT merely because a requested set has a singular noun. Preserve all tied top results when the benchmark examples use rank-based selection.
No conversation history is available; keep the original English question without adding inferred conditions.
"""


def messages_for(question,ctx,schemas,route):
    fields=('source','column','code','label','abbreviation','linksto')
    catalog=[{k:r[k] for k in fields if k in r} for r in ctx.get('medical',[])]
    context='\nDatabase schema:\n'+'\n'.join(schemas[t] for t in ctx['tables'])
    context+='\nCandidate value/catalog metadata:\n'+json.dumps(catalog,ensure_ascii=False)
    system=V2_SYSTEM+'\n'+BENCHMARK_CONVENTIONS+'\n'+GROUNDING_RULES+'\n'+ROUTE_RULES[route]+context
    messages=[{'role':'system','content':system}]
    seen=set()
    for row in ctx.get('examples',[])+ctx.get('null_neighbors',[]):
        if row['id'] not in seen:
            seen.add(row['id'])
            messages += [{'role':'user','content':row['question']},{'role':'assistant','content':row['sql']}]
    return messages+[{'role':'user','content':question}]


def fingerprint_rows(rows):
    if not rows:
        return None,{'rows':0,'columns':0,'trivial_scalar':False}
    def value(v):
        if v is None:
            return ['null',None]
        if isinstance(v,(int,float)):
            return ['number',str(Decimal(str(v)).normalize())]
        if isinstance(v,bytes):
            return ['bytes',v.hex()]
        return ['text',str(v)]
    # Full multiset: preserve duplicate rows, number/type of columns and NULLs.
    # Neither official round3 normalization nor 100-row cap is used for voting.
    canonical=sorted(json.dumps([value(v) for v in row],ensure_ascii=False,separators=(',',':')) for row in rows)
    digest=hashlib.sha256(json.dumps(canonical,separators=(',',':')).encode()).hexdigest()
    trivial=len(rows)==1 and len(rows[0])==1 and rows[0][0] in (None,0,0.0)
    return digest,{'rows':len(rows),'columns':len(rows[0]),'trivial_scalar':trivial}


def structural_signature(sql):
    if not sql or sql=='null':
        return None
    try:
        tree=parse_one(sql,read='sqlite')
        # Identifier-preserving, literal-masked AST. Logical conditions,
        # temporal functions and projections remain part of the signature.
        def mask(node):
            if isinstance(node,exp.Literal):
                return exp.Literal.string('?') if node.is_string else exp.Literal.number('0')
            return node
        return tree.transform(mask).sql(dialect='sqlite',normalize=True)
    except Exception:
        return None


def completion(response,question,known_values):
    if response['finish_reason']!='stop':
        return {'sql':'','execution':{'valid':False,'abstained':False,'empty':None,'error':'generation_incomplete:'+str(response['finish_reason'])},
                'contract':{'hard_issues':[],'soft_issues':['incomplete_generation']},'result_fingerprint':None,'result_summary':{}}
    sql=clean_sql(response['content'])
    contract=contract_issues(question,sql,known_values) if sql!='null' else {'hard_issues':[],'soft_issues':[]}
    if sql=='null':
        return {'sql':'null','execution':outcome('null'),'contract':contract,'result_fingerprint':None,'result_summary':{}}
    try:
        rows=execute(sql)
        fp,summary=fingerprint_rows(rows)
        execution={'valid':True,'abstained':False,'empty':not rows,'error':None}
    except Exception as error:
        fp,summary=None,{}
        execution={'valid':False,'abstained':False,'empty':None,'error':str(error)[:500]}
    return {'sql':sql,'execution':execution,'contract':contract,'result_fingerprint':fp,'result_summary':summary}


def guarded(record):
    result=copy.deepcopy(record)
    check=result['execution']
    if result['sql']!='null' and (not check['valid'] or check['empty'] or result['contract']['hard_issues']):
        result.update(pre_guard_sql=result['sql'],pre_guard_execution=check,sql='null',execution=outcome('null'),
                      guard_rejected=True,result_fingerprint=None)
    else:
        result['guard_rejected']=False
    return result


def run_question(item,rag,clients,on_candidate=None):
    candidates=[]
    for route in ROUTES:
        ctx=rag.retrieve(item['question'],route=route)
        messages=messages_for(item['question'],ctx,rag.schema,route)
        client=clients['reasoning'] if route=='plan' else clients['normal']
        response=client.call(messages,'v3_'+route,item['id'],max_tokens=4096 if route=='plan' else 2048)
        record=completion(response,item['question'],rag.known_values)
        record.update(route=route,call_hashes=[response['request_hash']],attempts=1,retrieval=ctx,
                      thinking=response.get('thinking'),finish_reason=response['finish_reason'],history=[])
        # Only concrete parse/execution failures permit automatic repair.
        if record['sql']!='null' and not record['execution']['valid'] and response['finish_reason']=='stop':
            messages += [{'role':'assistant','content':record['sql']},
                         {'role':'user','content':'SQLite execution failed: '+str(record['execution']['error'])+
                          '\nRepair only the schema/syntax error, preserving the original question exactly: '+item['question']+'\nReturn SQL or null only.'}]
            response2=client.call(messages,'v3_execution_repair_'+route,item['id'],max_tokens=4096 if route=='plan' else 2048)
            fixed=completion(response2,item['question'],rag.known_values)
            record.update(fixed,attempts=2,call_hashes=record['call_hashes']+[response2['request_hash']],
                          history=[{'sql':record['sql'],'error':record['execution']['error']}],finish_reason=response2['finish_reason'])
        record['static_issues']=record['contract']['hard_issues']
        record['structural_signature']=structural_signature(record['sql'])
        candidate=guarded(record)
        candidates.append(candidate)
        if on_candidate:
            on_candidate(route,candidate)
    return {'id':item['id'],'question':item['question'],'candidates':candidates}
