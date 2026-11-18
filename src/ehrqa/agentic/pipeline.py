"""Full agentic flow; no gold answers, historical predictions or cross-model votes."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import threading
import time

from . import contracts,prompts
from .trace import Trace,digest,safe
from .evidence import build_catalog,public_catalog
from sqlglot import errors as sql_errors, parse
from ehrqa.clinsql.execution_errors import IncompleteResultError, SecurityRejected, classify_execution_failure


STATIC_PAYLOAD_KEYS=('schema','relationships','examples','full_schema_available')


class PipelineError(RuntimeError): pass
class StageInterfaceError(PipelineError): pass


@dataclass(frozen=True)
class Config:
    profile: str='clinsql'
    max_repairs: int=2
    semantic_repairs: int=1
    max_model_calls: int=24
    log_dir: object=None
    base_prompt_only: bool=False
    schema_rag: bool=True
    multi_layer_rag: bool=True
    sql_validation: bool=True
    self_correction: bool=True
    requirement_verification: bool=True
    # v6 (CLINSQL): local result-fingerprint voting, LLM selection only on
    # disagreement, verification only on an empty/all-NULL signal.
    fingerprint_selection: bool=False
    # v6: run the two independent branches (c1, c3) concurrently.
    parallel_branches: bool=False
    # v8 "lite" (CLINSQL): no decomposer, one full-schema candidate; a second,
    # independent candidate only when the first does not execute or returns no
    # values; no LLM selector.
    adaptive_single: bool=False
    run_version: str | None=None

    def __post_init__(self):
        if self.profile!='clinsql':raise ValueError('Unsupported profile')
        if not 0<=self.max_repairs<=3 or not 0<=self.semantic_repairs<=1:raise ValueError('Invalid repair bounds')
        if self.max_model_calls<1:raise ValueError('Invalid call budget')


class FullAgentic:
    def __init__(self,database,retriever,model,config=None,*,procedure_grounding=None):
        self.db,self.rag,self.model=database,retriever,model
        self.config=config or Config()
        self.procedure_grounding = procedure_grounding

    def run(self,question,*,query_id=None,history_context=(),saved_linking=None):
        trace=Trace(self.config.log_dir,query_id=query_id)
        self.trace=trace
        calls=0
        ctx={};candidates=[];interface_failures=[]
        fallbacks=[]
        procedure_sets = {}
        # v5 CLINSQL: one verifier attempt, evidence defects downgrade checks
        # instead of rejecting the audit; see contracts.verification(lenient=True).
        lenient=self.config.profile=='clinsql'
        schema=self.db.schema
        history=[{k:str(r[k])[:(1000 if k=='sql' else 500)] for k in ['role','content','sql','result_summary'] if k in r}
                 for r in list(history_context)[-8:]]
        retrieval_question=question
        grounding_question=(question if isinstance(question,str) else '')+' '+json.dumps(history,ensure_ascii=False)

        call_lock=threading.Lock()

        def ask(stage,data,validate=None,*,tokens=4096,attempts=2):
            nonlocal calls
            feedback=None
            previous=None
            for attempt in range(attempts if validate else 1):
                with call_lock:
                    if calls>=self.config.max_model_calls:raise PipelineError('Per-question model-call budget exhausted')
                    calls+=1
                    call_number=calls
                # Prompt-cache friendly order: large static context first,
                # per-question content last. Same keys and values as before.
                payload={k:data[k] for k in STATIC_PAYLOAD_KEYS if k in data}
                payload.update({k:v for k,v in data.items() if k not in payload})
                payload['original_question']=question
                if history:
                    payload.update(conversation_context=history,contextualized_question_advisory=retrieval_question)
                if feedback:
                    payload['interface_validation_error']=feedback
                    payload['previous_invalid_output']=previous
                messages=[{'role':'system','content':prompts.system(self.config.profile,stage)},
                          {'role':'user','content':json.dumps(payload,ensure_ascii=False,default=str)}]
                trace.emit('model.request',operation=stage,attempt=attempt+1,call=call_number,
                           input=payload,input_hash=digest(messages),max_output_tokens=tokens)
                result=self.model.complete(stage,messages,tokens)
                trace.emit('model.response',operation=stage,call=call_number,
                           **{k:v for k,v in result.items() if k!='content'},output=result['content'])
                try:
                    if stage == 'link' and result.get('link_anchor_error'):
                        raise contracts.StageError(result['link_anchor_error'])
                    obj=contracts.json_object(result['content'])
                    if stage == 'link' and self.config.profile == 'clinsql':
                        from ehrqa.clinsql.linking_format import validate_link_format
                        validate_link_format(obj)
                    return validate(obj) if validate else obj
                except (contracts.StageError,TypeError,KeyError,AttributeError) as error:
                    feedback=str(error)[:1200]
                    previous=result['content'][:24000]
                    trace.emit('stage.interface_error',operation=stage,error=feedback)
            raise StageInterfaceError(stage+' could not produce a valid interface')

        def sql_object(obj):
            if 'sql' not in obj:raise contracts.StageError('Missing sql field is not a refusal')
            sql=obj.get('sql')
            if sql is None:sql='null'
            if not isinstance(sql,str) or not sql.strip():raise contracts.StageError('SQL string missing; empty is not a refusal')
            return {'sql':sql.strip(),'unresolved':obj.get('unresolved',[])}

        def execute_proposal(cid,proposal,base_context):
            history=[]
            max_repairs=self.config.max_repairs if self.config.self_correction else 0
            for attempt in range(max_repairs+1):
                sql=proposal['sql']
                if sql.casefold()=='null':
                    return {'id':cid,'sql':'null','status':'model_refusal','history':history,'unresolved':proposal['unresolved']}
                if self.config.sql_validation:
                    inspection=schema.inspect(sql,grounding_question)
                else:
                    inspection={'valid':True,'ast_sql':sql,'used_refs':[],'errors':[]}
                if inspection['valid'] and procedure_sets:
                    from ehrqa.clinsql.procedure_grounding import verify_procedure_cte
                    try:
                        for cte, includes in procedure_sets.items():
                            verify_procedure_cte(sql,cte,includes)
                    except ValueError as error:
                        inspection.update(valid=False,errors=[str(error)])
                if inspection['valid'] and hasattr(self.db,'prepare_sql'):
                    # Persist the exact fixed-clock SQL verified and executed;
                    # exported predictions must not depend on the wall clock.
                    sql=self.db.prepare_sql(sql)
                    inspection=schema.inspect(sql,grounding_question)
                error=None;result=None;category=None
                if inspection['valid']:
                    try:
                        result=self.db.execute(sql,grounding_question)
                        if not result.complete:raise PipelineError('Execution result truncated; do not add LIMIT to conceal missing rows')
                    except PipelineError:raise
                    except (TimeoutError,ConnectionError,IncompleteResultError):raise
                    except SecurityRejected:
                        error='SQL rejected by the read-only guard';category='schema'
                    except PermissionError:raise
                    except ValueError as e:
                        if self.config.profile!='clinsql':
                            error=str(e)[:500]
                        else:
                            # Same disclosure rule as the CLINSQL CoT baseline: only a
                            # whitelisted error class, never raw database text.
                            from ehrqa.clinsql.execution_errors import redacted_sql_error_class
                            error='BigQuery rejected the SQL: '+redacted_sql_error_class(str(e))
                        category='execution_sql'
                    except Exception as e:
                        if self.config.profile=='clinsql':raise
                        error=str(e)[:500]
                        category='execution_sql'
                        if any(s in error.lower() for s in ('locked','interrupted','timeout','connection','permission denied')):
                            raise PipelineError('Database operational failure') from None
                else:
                    error='; '.join(inspection['errors'])
                    category='schema'
                    if self.config.profile=='clinsql':
                        try:
                            parse(sql,read='bigquery')
                        except sql_errors.SqlglotError:
                            category='syntax'
                history.append({'attempt':attempt+1,'sql':sql,'error':error,'error_category':category,'inspection':inspection})
                trace.emit('candidate.execution',candidate_id=cid,attempt=attempt+1,sql=sql,inspection=inspection,
                           error=error,error_category=category,result=result.summary() if result else None)
                if error is None:
                    forward={l['table']+'.'+l['column'] for l in links['links']}
                    trace.emit('schema.backward_linking',candidate_id=cid,forward=sorted(forward),
                               backward=inspection['used_refs'],union=sorted(forward|set(inspection['used_refs'])),
                               newly_used_refs=sorted(set(inspection['used_refs'])-forward))
                    catalog=build_catalog(sql,cid,schema.dialect)
                    trace.emit('candidate.evidence',candidate_id=cid,catalog=catalog)
                    return {'id':cid,'sql':sql,'status':'executed','inspection':inspection,'result':result,'history':history,'evidence_catalog':catalog}
                if attempt<max_repairs:
                    trace.emit('candidate.correction',candidate_id=cid,category=category,reason=error)
                    proposal=ask('repair',{**base_context,'candidate_sql':sql,'technical_errors':[error]},sql_object)
            return {'id':cid,'sql':sql,'status':'technical_failure','history':history,'error':error}

        def verify(candidate):
            findings=(self.db.requirement_findings(candidate['sql'],question,clinical['records'])
                      if hasattr(self.db,'requirement_findings') else [])
            check=ask('verify',{'requirements':links['requirements'],'schema':schema.payload(),
                'catalog':clinical['records'],'examples':ctx['examples'],'linking_ambiguities':links['ambiguities'],'candidate_sql':candidate['sql'],
                'grounding_findings':findings,
                'static_inspection':candidate['inspection'],'execution_metadata':{
                    'rows':len(candidate['result'].rows),'columns':candidate['result'].columns,
                    'complete':candidate['result'].complete,'column_types':candidate['result'].column_types},
                'sql_evidence_catalog':public_catalog(candidate['evidence_catalog'])},
                lambda obj:contracts.verification(obj,links['requirements'],candidate['sql'],candidate['inspection'],question,schema,candidate['evidence_catalog'],lenient=lenient),
                tokens=8192,attempts=1 if lenient else 2)
            if check.get('evidence_warnings'):
                trace.emit('semantic.verification_warnings',candidate_id=candidate['id'],warnings=check['evidence_warnings'])
            if findings:
                check.update(verdict='contradicted',grounding_findings=findings)
            return check

        def select(eligible,*,require_supported=True):
            # Same evidence as verification; no gold, result voting, or pairwise
            # tournament. Non-unique best is different from unanswerability.
            data={'requirements':links['requirements'],'schema':schema.payload(),
                  'catalog':clinical['records'],'examples':ctx['examples'],
                  'linking_ambiguities':links['ambiguities'],
                  'candidates':[{'id':c['id'],'sql':c['sql'],'verification':c.get('verification'),
                                 'static_inspection':c['inspection'],
                                 'sql_evidence_catalog':public_catalog(c['evidence_catalog'])}
                                for c in eligible]}
            if not require_supported:
                data['instruction']=('These executed candidates returned different results. Choose the one that '
                    'best answers the original question even if none is fully supported; return null only if '
                    'every candidate clearly answers a different question.')
            return ask('select',data,
                lambda obj:contracts.selection(obj,links['requirements'],eligible,question,schema,lenient=lenient,
                                               require_supported=require_supported),tokens=8192)

        def has_values(candidate):
            rows=candidate['result'].rows
            return bool(rows) and any(value is not None for row in rows for value in row)

        def branch(index,strategy,common,linked,backward,payload=None):
            context={**common,'strategy':strategy,'schema':payload or schema.payload()}
            if index==1:
                scope=schema.join_closure(set(linked)|{r.split('.')[0] for r in backward})
                if self.config.schema_rag and scope:context['schema']=schema.payload(scope)
                forward={l['table']+'.'+l['column'] for l in links['links']}
                context['schema_link_evidence']={'forward':sorted(forward),'backward':sorted(backward),
                    'union':sorted(forward|backward),'backward_semantic_correctness_assumed':False}
                trace.emit('schema.bidirectional_context',tables=scope,evidence=context['schema_link_evidence'])
            if index==2:
                context={k:v for k,v in context.items() if k not in {'decomposition','links','requirements'}}
                context['instruction']='Independently interpret the original question; do not inherit another candidate or plan.'
            cid='c'+str(index+1)
            try:
                proposal=ask('generate',context,sql_object)
                trace.emit('candidate.proposal',candidate_id=cid,strategy=strategy,proposal=proposal)
                return execute_proposal(cid,proposal,{**common,'schema':payload or schema.payload()})
            except StageInterfaceError as error:
                failure={'candidate_id':cid,'operation':str(error).split()[0],'error':str(error)}
                interface_failures.append(failure)
                trace.emit('candidate.interface_error',**failure)
                return None

        def lite_flow(common,scope):
            """v8: one pruned-schema candidate; escalate once to an independent full-schema one."""
            pruned=schema.payload(scope) if scope else None
            c1=branch(0,'direct_full_schema' if pruned is None else 'direct_pruned_schema',
                      {**common,'full_schema_available':pruned is None},set(),set(),payload=pruned)
            candidates[:]=[c for c in (c1,) if c]
            if c1 and c1['status']=='executed' and has_values(c1):
                trace.emit('selection.choice',candidate_id=c1['id'],method='single_pass')
                return finish('answered',c1['sql'],'v8 selection: single_pass',c1)
            fallbacks.append('escalated_second_candidate')
            trace.emit('pipeline.escalation',reason='first candidate '+('not executed' if not c1 or c1['status']!='executed' else 'returned no values'))
            c3=branch(2,'independent_full_schema',common,set(),set())
            candidates[:]=[c for c in (c1,c3) if c]
            executed=[c for c in candidates if c['status']=='executed']
            if executed:
                # Local rule, no LLM: prefer a result with values, then the full-schema retry.
                chosen=next((c for c in reversed(executed) if has_values(c)),executed[-1])
                how='escalated_'+chosen['id']+('' if has_values(chosen) else '_without_values')
                trace.emit('selection.choice',candidate_id=chosen['id'],method=how)
                return finish('answered',chosen['sql'],'v8 selection: '+how,chosen)
            attempted=[c for c in candidates if c.get('sql') and c['sql']!='null']
            if attempted:
                fallbacks.append('unexecuted_sql')
                return finish('unresolved',attempted[-1]['sql'],'Fallback: no executable candidate; last generated SQL returned')
            if interface_failures:return finish('error','','No candidate; branch interface failures')
            return finish('abstained','null','All branches declined to generate SQL')

        def fingerprint_flow(common,linked,link_fallback,verify_enabled):
            """v6: c1 || c3, then c2; local fingerprint vote; LLM only on disagreement or empty."""
            jobs=[(0,'direct_full_schema'),(2,'independent_full_schema')]
            if self.config.parallel_branches:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures=[pool.submit(branch,i,s,common,linked,set()) for i,s in jobs]
                    c1,c3=[f.result() for f in futures]
            else:
                c1,c3=[branch(i,s,common,linked,set()) for i,s in jobs]
            c2=None
            if not link_fallback:
                backward=set(c1['inspection']['used_refs']) if c1 and c1.get('inspection',{}).get('valid') else set()
                c2=branch(1,'decomposed_linked_schema',common,linked,backward)
            candidates[:]=[c for c in (c1,c2,c3) if c]
            executed=[c for c in candidates if c['status']=='executed']
            if not executed:
                attempted=[c for c in candidates if c.get('sql') and c['sql']!='null']
                if attempted:
                    fallbacks.append('unexecuted_sql')
                    trace.emit('pipeline.fallback',kind='unexecuted_sql',candidate_id=attempted[-1]['id'])
                    return finish('unresolved',attempted[-1]['sql'],'Fallback: no executable candidate; last generated SQL returned')
                if interface_failures:return finish('error','','No candidate; branch interface failures')
                return finish('abstained','null','All branches declined to generate SQL')
            groups={}
            for c in executed:groups.setdefault(c['result'].fingerprint(),[]).append(c)
            trace.emit('selection.fingerprints',groups=[[c['id'] for c in g] for g in groups.values()],
                       has_values={c['id']:has_values(c) for c in executed})
            majority=max(groups.values(),key=len)
            if len(majority)>=2 and has_values(majority[0]):
                chosen,how=majority[0],f'fingerprint_majority_{len(majority)}_of_{len(executed)}'
            elif len(groups)==1:
                chosen,how=majority[0],('single_executed' if len(executed)==1 else 'agreement_without_values')
            else:
                representatives=[g[0] for g in groups.values()]
                chosen,how=None,'llm_selection'
                try:
                    decision=select(representatives,require_supported=False)
                    trace.emit('selection.resolution',decision=decision)
                    chosen=next((c for c in representatives if c['id']==decision.get('selected_id')),None)
                except StageInterfaceError as error:
                    trace.emit('pipeline.fallback',kind='selection_fallback',error=str(error))
                if chosen is None:
                    fallbacks.append('selection_fallback')
                    chosen=next((c for c in representatives if has_values(c)),representatives[0])
                    how='selection_fallback'
            trace.emit('selection.choice',candidate_id=chosen['id'],method=how)
            # B1: verification only on a suspicious signal (no values returned).
            if verify_enabled and not has_values(chosen):
                how+='+gated_verification'
                try:
                    check=verify(chosen)
                except StageInterfaceError:
                    check=None
                if check:
                    chosen['verification']=check
                    trace.emit('semantic.verification',candidate_id=chosen['id'],verification=check,gated=True)
                if (check and check['verdict']=='contradicted' and self.config.self_correction
                        and self.config.semantic_repairs):
                    try:
                        corrected=ask('repair',{**common,'schema':schema.payload(),'candidate_sql':chosen['sql'],
                            'question_coverage_audit':check['question_coverage'],
                            'grounding_findings':check.get('grounding_findings',[]),
                            'contradicted_requirements':[c for c in check['checks'] if c['status']=='contradicted']},sql_object)
                        repaired=execute_proposal(chosen['id']+'r',corrected,{**common,'schema':schema.payload()})
                        candidates.append(repaired)
                        if repaired['status']=='executed' and has_values(repaired):
                            chosen,how=repaired,how+'+semantic_repair'
                    except StageInterfaceError as error:
                        trace.emit('pipeline.fallback',kind='gated_repair_interface',error=str(error))
            return finish('answered',chosen['sql'],'v6 selection: '+how,chosen)

        def finish(status,sql,reason,selected=None):
            reason=safe(reason)
            trace.emit('pipeline.final',status=status,sql=sql,reason=reason,model_calls=calls,
                       selected_candidate=selected['id'] if selected else None)
            return {'status':status,'sql':sql,'reason':reason,'ctx':ctx,'candidates':candidates,
                    'selected':selected,'model_calls':calls,'trace':trace.events,'trace_path':str(trace.path) if trace.path else None,
                    'branch_interface_failures':interface_failures,'fallbacks':fallbacks,
                    'prompt_version':self.config.run_version or prompts.VERSION,
                    'mode':'full_agentic','rewritten_question':retrieval_question}

        try:
            if not isinstance(question,str) or not question.strip():raise PipelineError('Question is empty')
            cfg=getattr(self.model,'settings',None)
            trace.emit('pipeline.start',question=question,profile=self.config.profile,
                       prompt_version=self.config.run_version or prompts.VERSION,
                       model=getattr(cfg,'model','injected_test_model'),provider=getattr(cfg,'provider','injected'),
                       schema_hash=digest(schema.payload()),historical_prediction_input=False)
            if self.config.base_prompt_only:
                links={'links':[]}
                proposal=ask('generate',{'schema':schema.payload()},sql_object)
                candidate=execute_proposal('c1',proposal,{'schema':schema.payload()})
                candidates.append(candidate)
                if candidate['status']=='executed':
                    return finish('answered',candidate['sql'],'Base generation executed',candidate)
                if candidate['status']=='model_refusal':
                    return finish('abstained','null','Model declined to generate SQL')
                return finish('error','','Base generation failed to execute')
            if history:
                def validate_rewrite(obj):
                    import re
                    text=obj.get('question')
                    if not isinstance(text,str) or not text.strip():raise contracts.StageError('Missing rewritten question')
                    nums=lambda s:set(re.findall(r'\b\d+(?:\.\d+)?\b',s))
                    if not nums(question)<=nums(text) or not nums(text)<=nums(grounding_question):raise contracts.StageError('Rewrite changed/invented original numeric constraints')
                    for literal in contracts.quoted_literals(question):
                        if literal not in text:raise contracts.StageError('Rewrite changed quoted entity')
                    used=obj.get('used_history_indices')
                    if not isinstance(used,list) or any(type(i) is not int or not 0<=i<len(history) for i in used):raise contracts.StageError('Unknown rewrite history reference')
                    return obj
                rewrite=ask('rewrite',{'recent_history':history},validate_rewrite)
                retrieval_question=rewrite['question']
                trace.emit('question.rewrite',original=question,rewritten=retrieval_question,used_history_indices=rewrite['used_history_indices'])
            ctx['schema']=self.rag.schema(retrieval_question) if self.config.schema_rag else {
                'tables':sorted(schema.tables),'relationships':schema.edges}
            trace.emit('rag.schema',context=ctx['schema'])
            clinical=self.rag.clinical(retrieval_question,ctx['schema']) if self.config.multi_layer_rag else {
                'records':[], 'found':False}
            ctx['clinical']=clinical;ctx['icd']=clinical.get('legacy_icd',{})
            trace.emit('rag.clinical',context=clinical)
            link_fallback=False
            if saved_linking is None:
                try:
                    def validate_link(obj):
                        if self.config.profile=='clinsql':
                            obj,repairs=contracts.normalize_linking(question,obj,schema,clinical['records'])
                            if repairs:trace.emit('schema.linking_normalized',repairs=repairs)
                        return contracts.linking(question,obj,schema,clinical['records'])
                    links=ask('link',{'schema':schema.payload(),'schema_candidates':ctx['schema'],
                                      'catalog':clinical['records']},validate_link,tokens=8192)
                except StageInterfaceError as error:
                    if self.config.profile!='clinsql':raise
                    # Fail open: an invalid linker interface must not prevent an
                    # answer. Full-schema branches still run; the case is flagged.
                    link_fallback=True
                    fallbacks.append('link_fallback')
                    links={'requirements':[],'links':[],'joins':[],'ambiguities':[]}
                    trace.emit('pipeline.fallback',kind='link_fallback',error=str(error))
            else:
                if self.config.profile != 'clinsql' or history:
                    raise ValueError('Saved linker is restricted to single-turn CLINSQL')
                links=contracts.linking(question,saved_linking,schema,clinical['records'])
                trace.emit('schema.linking_replayed')
            ctx['linking']=links;trace.emit('schema.forward_linking',links=links)
            if self.procedure_grounding is not None:
                from ehrqa.clinsql.procedure_grounding import CodeSetBlocked
                try:
                    procedure_sets = self.procedure_grounding(links) or {}
                except CodeSetBlocked as error:
                    trace.emit('clinical.procedure_grounding',status=str(error),
                               candidate_count=len(error.candidates))
                    return finish('abstained','null',str(error))
            skip_decomposed=link_fallback
            lite=self.config.adaptive_single and self.config.profile=='clinsql'
            if link_fallback or lite:
                plan={'steps':[],'output_step':None}
            else:
                try:
                    plan=ask('decompose',{'requirements':links['requirements'],'links':links['links'],
                             'relationships':schema.edges,'ambiguities':links['ambiguities']},
                             lambda obj:contracts.decomposition(obj,links['requirements'],schema),tokens=8192)
                except StageInterfaceError as error:
                    if self.config.profile!='clinsql':raise
                    # Fail open like the linker: an invalid plan only removes the
                    # decomposed branch; full-schema branches still answer.
                    skip_decomposed=True
                    fallbacks.append('decompose_fallback')
                    plan={'steps':[],'output_step':None}
                    trace.emit('pipeline.fallback',kind='decompose_fallback',error=str(error))
            ctx['decomposition']=plan;trace.emit('query.decomposition',plan=plan)
            verify_enabled=self.config.requirement_verification and not link_fallback
            if not self.config.multi_layer_rag:
                ctx['examples']={'items':[]}
            elif self.config.profile=='clinsql':
                ctx['examples']=self.rag.examples(retrieval_question,query_id=query_id)
            else:
                ctx['examples']=self.rag.examples(retrieval_question)
            if len(ctx['examples'].get('items',[]))>3:raise PipelineError('Few-shot budget changed unexpectedly')
            trace.emit('rag.examples',context=ctx['examples'],few_shot_limit=3)
            linked=schema.join_closure({l['table'] for l in links['links']}|{t for s in plan['steps'] for t in s['tables']})
            common={'requirements':links['requirements'],'catalog':clinical['records'],'links':links,
                    'decomposition':plan,'examples':ctx['examples'],'full_schema_available':True}
            if procedure_sets:
                common['verified_procedure_sets'] = procedure_sets
                common['procedure_set_instruction'] = ('Use exactly the verified code/version pairs '
                    'in each named selector CTE. Do not insert extra codes or an empty fallback.')
            if lite:
                # Full schema for every candidate: on validation the RAG-pruned scope held all
                # gold tables for only 15% of questions (85% even with linked + core tables),
                # while input tokens are a small share of cost. Savings come from fewer calls.
                return lite_flow(common,None)
            if self.config.fingerprint_selection and self.config.profile=='clinsql':
                return fingerprint_flow(common,linked,skip_decomposed,verify_enabled)
            for index,strategy in enumerate(['direct_full_schema','decomposed_linked_schema','independent_full_schema']):
                if skip_decomposed and index==1:continue
                backward={r for c in candidates if c.get('inspection',{}).get('valid') for r in c['inspection']['used_refs']}
                if index==1:
                    linked=schema.join_closure(set(linked)|{r.split('.')[0] for r in backward})
                context={**common,'strategy':strategy,'schema':schema.payload(linked)
                         if self.config.schema_rag and index==1 and linked else schema.payload()}
                if index==1:
                    forward={l['table']+'.'+l['column'] for l in links['links']}
                    context['schema_link_evidence']={'forward':sorted(forward),'backward':sorted(backward),
                        'union':sorted(forward|backward),'backward_semantic_correctness_assumed':False}
                    trace.emit('schema.bidirectional_context',tables=linked,evidence=context['schema_link_evidence'])
                if index==2:
                    context={k:v for k,v in context.items() if k not in {'decomposition','links','requirements'}}
                    context['instruction']='Independently interpret the original question; do not inherit another candidate or plan.'
                cid='c'+str(index+1)
                try:
                    proposal=ask('generate',context,sql_object)
                    trace.emit('candidate.proposal',candidate_id=cid,strategy=strategy,proposal=proposal)
                    candidate=execute_proposal(cid,proposal,{**common,'schema':schema.payload()})
                    candidates.append(candidate)
                    if candidate['status']!='executed':continue
                    if not verify_enabled:
                        if self.config.profile=='clinsql':
                            # C: nothing can rank later branches, so stop at the first executable SQL.
                            trace.emit('pipeline.early_stop',candidate_id=candidate['id'],reason='verification_disabled')
                            break
                        continue
                    try:
                        check=verify(candidate)
                    except StageInterfaceError:
                        if self.config.profile!='clinsql':raise
                        # C: the verifier gave no usable audit; keep this executable SQL.
                        fallbacks.append('unverified_selection')
                        trace.emit('pipeline.early_stop',candidate_id=candidate['id'],reason='verifier_interface_failure')
                        return finish('answered',candidate['sql'],'Fallback: verifier interface failed; first executable candidate kept',candidate)
                    candidate['verification']=check
                    trace.emit('semantic.verification',candidate_id=candidate['id'],verification=check)
                    for repair in range(self.config.semantic_repairs if self.config.self_correction else 0):
                        if check['verdict']!='contradicted':break
                        trace.emit('candidate.correction',candidate_id=candidate['id'],category='semantic',
                                   reason=check)
                        corrected=ask('repair',{**common,'schema':schema.payload(),'candidate_sql':candidate['sql'],
                            'question_coverage_audit':check['question_coverage'],
                            'grounding_findings':check.get('grounding_findings',[]),
                            'contradicted_requirements':[c for c in check['checks'] if c['status']=='contradicted']},sql_object)
                        candidate=execute_proposal(candidate['id']+'r',corrected,{**common,'schema':schema.payload()})
                        candidates.append(candidate)
                        if candidate['status']!='executed':break
                        check=verify(candidate);candidate['verification']=check
                        trace.emit('semantic.verification',candidate_id=candidate['id'],verification=check,after_semantic_repair=True)
                except StageInterfaceError as error:
                    failure={'candidate_id':cid,'operation':str(error).split()[0],'error':str(error)}
                    interface_failures.append(failure)
                    trace.emit('candidate.interface_error',**failure)
                    # A malformed branch cannot invalidate another fully
                    # checked candidate. Provider/budget/DB failures still abort.
                    continue
            if not verify_enabled:
                executed=next((c for c in candidates if c['status']=='executed'),None)
                if executed:return finish('answered',executed['sql'],'First executable candidate',executed)
            eligible=[c for c in candidates if c.get('verification',{}).get('verdict')=='supported']
            # AST-identical duplicates can share a choice. Matching execution
            # results alone never merge semantically different queries.
            unique={}
            for c in eligible:unique.setdefault(c['inspection']['ast_sql'],c)
            eligible=list(unique.values())
            trace.emit('selection.eligibility',eligible_ids=[c['id'] for c in eligible],
                       result_groups={c['id']:c['result'].fingerprint() for c in eligible},agreement_is_semantic_proof=False)
            if not eligible and self.config.profile=='clinsql':
                # Fail open with flags: a benchmark answer is always produced when
                # any candidate executed (unknown verdict preferred over contradicted),
                # otherwise the last generated SQL is returned unexecuted.
                rank={'unknown':0,'contradicted':1}
                executed=[c for c in candidates if c['status']=='executed']
                if executed:
                    best=min(executed,key=lambda c:rank.get(c.get('verification',{}).get('verdict'),2))
                    verdict=best.get('verification',{}).get('verdict')
                    fallbacks.append('unverified_selection')
                    trace.emit('pipeline.fallback',kind='unverified_selection',candidate_id=best['id'],verdict=verdict)
                    return finish('answered',best['sql'],f'Fallback: no supported candidate; selected {best["id"]} with verdict {verdict}',best)
                attempted=[c for c in candidates if c.get('sql') and c['sql']!='null']
                if attempted:
                    fallbacks.append('unexecuted_sql')
                    trace.emit('pipeline.fallback',kind='unexecuted_sql',candidate_id=attempted[-1]['id'])
                    return finish('unresolved',attempted[-1]['sql'],'Fallback: no executable candidate; last generated SQL returned')
            if not eligible:
                if interface_failures:return finish('error','','No supported candidate; unresolved branch interface failures')
                if any(c['status']=='technical_failure' for c in candidates) and not any(c['status']=='executed' for c in candidates):
                    return finish('error','','No executable candidate; technical failure is not a correct refusal')
                return finish('abstained','null','No candidate has evidence satisfying all original obligations')
            if len(eligible)==1:return finish('answered',eligible[0]['sql'],'One evidence-supported SQL',eligible[0])
            try:
                decision=select(eligible)
            except StageInterfaceError as error:
                if self.config.profile!='clinsql':raise
                fallbacks.append('selection_fallback')
                trace.emit('pipeline.fallback',kind='selection_fallback',error=str(error))
                return finish('answered',eligible[0]['sql'],'Fallback: selector interface failed; first supported candidate',eligible[0])
            trace.emit('selection.resolution',decision=decision)
            if decision['selected_id'] is None:
                if self.config.profile=='clinsql':
                    fallbacks.append('selection_fallback')
                    trace.emit('pipeline.fallback',kind='selection_fallback',reason=decision['reason'])
                    return finish('answered',eligible[0]['sql'],'Fallback: selector refused; first supported candidate',eligible[0])
                return finish('abstained','null',decision['reason'])
            winner=next(c for c in eligible if c['id']==decision['selected_id'])
            return finish('answered',winner['sql'],decision['reason'],winner)
        except Exception as error:
            if self.config.profile=='clinsql':
                from ehrqa.clinsql.openai_provider import (
                    AmbiguousModelRequest, ModelGenerationFailure, ModelUsageUnknown)
                from ehrqa.clinsql.benchmark_model import ModelMismatch
                from ehrqa.clinsql.evidence_router import RestrictedEvidenceEgress
                if isinstance(error, RestrictedEvidenceEgress):
                    trace.emit('model.egress_block', operation=error.stage, category=error.category)
                    return finish('error', '', 'RESTRICTED_EVIDENCE_EGRESS')
                model_failure={AmbiguousModelRequest:'MODEL_REQUEST_OUTCOME_UNKNOWN',
                               ModelGenerationFailure:'MODEL_GENERATION_FAILURE',
                               ModelMismatch:'MODEL_MISMATCH',
                               ModelUsageUnknown:'MODEL_USAGE_UNKNOWN'}.get(type(error))
                if model_failure:
                    # Keep the transport cause (e.g. APITimeoutError, HTTP 5xx) for
                    # infrastructure-censoring decisions; no request content is logged.
                    trace.emit('pipeline.error',error_type=type(error).__name__,error_category=model_failure,
                               cause_type=getattr(error,'cause_type',None),http_status=getattr(error,'http_status',None))
                    return finish('error','',model_failure)
            infrastructure=self.config.profile=='clinsql' and isinstance(
                error,(PermissionError,TimeoutError,ConnectionError,IncompleteResultError))
            failure=('SECURITY_REJECTED' if infrastructure and str(error)=='SECURITY_REJECTED' else
                     classify_execution_failure(error,stage='execute') if infrastructure else type(error).__name__)
            detail=failure if infrastructure else str(error)[:400]
            trace.emit('pipeline.error',error_type=type(error).__name__,error_category=failure,error=detail)
            return finish('error','',detail if infrastructure else failure+': '+detail)

    def answer(self,question,output,*,include_values=False,preview_rows=20):
        """Grounded answer stage; privacy setting and preview limitations explicit."""
        if self.config.profile == 'clinsql':
            raise PermissionError('CLINSQL benchmark disables result-to-LLM answer generation')
        if output['status']!='answered':
            output['answer_status']='unavailable_'+output['status']
            self.trace.emit('answer.unavailable',status=output['status'])
            return 'Insufficient evidence to answer.' if self.config.profile=='clinsql' else 'Chưa đủ bằng chứng để trả lời.'
        result=output['selected']['result']
        english=self.config.profile=='clinsql'
        if not result.rows:
            output['answer_status']='empty_result'
            self.trace.emit('answer.empty_result',row_count=0)
            return 'No matching records were found.' if english else 'Không tìm thấy dữ liệu phù hợp.'
        facts={k:v for k,v in result.summary().items() if k!='fingerprint'}
        if include_values:
            facts.update(values=result.rows[:preview_rows],preview_complete=len(result.rows)<=preview_rows)
        elif len(result.rows)==1 and len(result.rows[0])==1 and any(f in output['sql'].upper() for f in ('COUNT(', 'COUNT (','SUM(', 'AVG(')):
            facts.update(aggregate_value=result.rows[0][0],preview_complete=True)
        else:facts.update(values_withheld=True,preview_complete=False)
        fallback=(f"The query returned {len(result.rows)} rows; detailed values were not verbalized." if english else
                  f"Truy vấn trả về {len(result.rows)} dòng; chưa diễn giải các giá trị chi tiết.")
        if facts.get('values_withheld'):
            output['answer_status']='metadata_only_values_withheld'
            self.trace.emit('answer.metadata_only',answer=fallback,values_withheld=True)
            return fallback
        try:
            if output['model_calls']>=self.config.max_model_calls:raise PipelineError('Model-call budget exhausted before answer')
            payload={'original_question':question,'language':'English' if english else 'Vietnamese',
                     'sql':output['sql'],'execution_facts':facts}
            messages=[{'role':'system','content':prompts.system(self.config.profile,'answer')},
                      {'role':'user','content':json.dumps(payload,ensure_ascii=False,default=str)}]
            self.trace.emit('answer.request',input=payload,input_hash=digest(messages),include_values=include_values)
            output['model_calls']+=1
            response=self.model.complete('answer',messages,4096)
            obj=contracts.json_object(response['content'])
            text=obj.get('answer')
            if not isinstance(text,str) or not text.strip():raise PipelineError('Missing answer text')
            import re
            from decimal import Decimal
            def nums(t):return {str(Decimal(n).normalize()) for n in re.findall(r'(?<!\w)\d+(?:\.\d+)?',t)}
            if not nums(text)<=nums(json.dumps(facts,default=str)+' '+question):
                raise PipelineError('Answer introduced an unsupported numerical value')
            self.trace.emit('answer.response',answer=text,limitations=obj.get('limitations',[]),usage=response.get('usage',{}),
                            factual_validation='numerical_support_only_NOT_clinical_or_full_semantic_proof')
            output['answer_status']='generated_from_provided_facts'
            return text.strip()
        except Exception as error:
            self.trace.emit('answer.fallback',error_type=type(error).__name__,error=str(error)[:400])
            output['answer_status']='fallback'
            return fallback
