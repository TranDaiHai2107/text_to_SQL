"""Fixed controls around unchanged V5. No evaluation labels or policy fitting."""
from copy import deepcopy
import time
from validation_common import VANNA, activate_methods

activate_methods()
from infrastructure import execute
from pipeline_v3 import run_question, ROUTE_RULES, guarded, fingerprint_rows
from risk_v3 import select_record
from postprocess_v4 import normalize_candidate as normalize_v4, select_v4, fingerprint_round3
from postprocess_v5 import normalize_candidate as normalize_v5, select_v5

ARM_NAMES = ('vanna_native_single', 'vanna_matched_three', 'dense_three_v5', 'ours_direct_gef',
             'ours_raw_three', 'ours_round3_no_compiler', 'v5_full')


class DenseExampleControl:
    """Replace only example selection, retaining schema/catalog/guards/prompts."""
    def __init__(self, structured):
        self.structured = structured
        self.schema = structured.schema
        self.known_values = structured.known_values

    def retrieve(self, question, route='direct'):
        context = deepcopy(self.structured.retrieve(question, route=route))
        rag = self.structured
        with rag.lock:
            base = rag.hybrid.base
            result = base.collections[base.examples_collection].query(
                query_embeddings=base.query_cache[question], n_results=len(rag.by_id), include=['distances'])
        keys = [key for key in result['ids'][0] if key in rag.by_id and key not in rag.excluded_ids]
        context['examples'] = [dict(rag.by_id[k]) for k in keys[:4]]
        context['null_neighbors'] = [dict(rag.by_id[k]) for k in keys if rag.by_id[k]['sql']=='null'][:2]
        context['retrieval_route'] = 'dense_examples_only_same_metadata'
        return context


def vanna_candidates(vn, item, clients):
    """Native retrieval/prompt/extraction; explicitly augmented route envelope."""
    from sql_runtime import clean_sql, outcome
    question = item['question']
    native_prompt = vn.get_sql_prompt(
        initial_prompt=vn.config.get('initial_prompt'), question=question,
        question_sql_list=vn.get_similar_question_sql(question),
        ddl_list=vn.get_related_ddl(question), doc_list=vn.get_related_documentation(question))
    candidates = []
    native_single = None
    for route in ('direct', 'structural', 'plan'):
        messages = deepcopy(native_prompt)
        if route != 'direct':
            messages[0]['content'] += '\n' + ROUTE_RULES[route]
        client = clients['reasoning' if route=='plan' else 'normal']
        cap = 4096 if route=='plan' else 2048

        def complete(response):
            if response['finish_reason'] != 'stop':
                sql = ''
                execution = {'valid':False, 'abstained':False, 'empty':None, 'error':'generation_incomplete'}
            else:
                # Native extraction and no intermediate database introspection.
                text = response['content']
                extracted = text if 'intermediate_sql' in text else vn.extract_sql(text)
                sql = clean_sql(extracted)
                execution = outcome(sql)
            fp, summary = None, {}
            if execution['valid']:
                fp, summary = fingerprint_rows(execute(sql))
            return {'sql':sql, 'execution':execution, 'result_fingerprint':fp, 'result_summary':summary,
                    'contract':{'hard_issues':[], 'soft_issues':[]}, 'static_issues':[],
                    'route':route, 'call_hashes':[response['request_hash']], 'attempts':1,
                    'finish_reason':response['finish_reason'], 'thinking':response.get('thinking'), 'history':[]}

        response = client.call(messages, 'control_vanna_'+route, item['id'], max_tokens=cap)
        record = complete(response)
        if route=='direct':
            native_single = deepcopy(record)
        if record['sql'] != 'null' and not record['execution']['valid'] and response['finish_reason']=='stop':
            messages += [{'role':'assistant', 'content':record['sql']},
                         {'role':'user', 'content':'SQLite execution failed: '+str(record['execution']['error'])+
                          '\nRepair only the schema/syntax error, preserving the original question exactly: '+question+
                          '\nReturn SQL or null only.'}]
            fixed = complete(client.call(messages, 'control_vanna_repair_'+route, item['id'], max_tokens=cap))
            fixed.update(attempts=2, call_hashes=record['call_hashes']+fixed['call_hashes'],
                         history=[{'sql':record['sql'], 'error':record['execution']['error']}])
            record = fixed
        candidate = guarded(record)
        if candidate['execution']['valid']:
            candidate['result_fingerprint'], candidate['result_summary'] = fingerprint_round3(execute(candidate['sql']))
        candidates.append(candidate)
    return {'id':item['id'], 'question':question, 'candidates':candidates, 'native_single':native_single}


def derive_arms(families, metadata):
    ours = families['ours_structured']['candidates']
    question = families['ours_structured']['question']
    canonical = [normalize_v5(question, c, metadata) for c in ours]
    round3 = [normalize_v4(question, c, metadata) for c in ours]
    dense = [normalize_v5(question, c, metadata) for c in families['control_dense']['candidates']]
    return {
        'vanna_native_single': families['control_vanna']['native_single'],
        'vanna_matched_three': select_record(families['control_vanna']['candidates'], 'strict_three_agree'),
        'dense_three_v5': select_v5(dense, 'strict3_canonical'),
        'ours_direct_gef': deepcopy(ours[0]),
        'ours_raw_three': select_record(ours, 'strict_three_agree'),
        'ours_round3_no_compiler': select_v4(round3, 'strict3_round3'),
        'v5_full': select_v5(canonical, 'strict3_canonical'),
    }
