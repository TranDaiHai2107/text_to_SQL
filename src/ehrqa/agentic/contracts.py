"""Validate stage interfaces. Format/evidence validation is NOT semantic proof."""
import json
import re
from sqlglot import Dialect
from sqlglot.tokens import TokenType
from .evidence import resolve_ids


class StageError(ValueError): pass


def sql_evidence(sql,fragment,dialect='sqlite'):
    """Resolve a quoted span without treating whitespace/keyword case as errors.

    String literals and quoted identifiers retain exact text. Returns an actual
    substring, never a fabricated or merely semantically similar fragment.
    """
    if not isinstance(fragment,str) or not fragment.strip():return None
    if fragment in sql:return fragment
    try:
        tokenizer=Dialect.get_or_raise(dialect)
        hay=tokenizer.tokenize(sql);needle=tokenizer.tokenize(fragment)
        if not needle:return None
        def key(t):return (t.token_type,t.text if t.token_type in {TokenType.STRING,TokenType.IDENTIFIER} else t.text.casefold())
        wanted=[key(t) for t in needle]
        for start in range(len(hay)-len(needle)+1):
            if [key(t) for t in hay[start:start+len(needle)]]==wanted:
                return sql[hay[start].start:hay[start+len(needle)-1].end+1]
    except Exception:return None
    return None


def json_object(text):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d: raise StageError('Duplicate JSON key: '+k)
            d[k]=v
        return d
    try: obj=json.loads(text,object_pairs_hook=pairs)
    except (ValueError,TypeError) as e: raise StageError('Invalid stage JSON') from e
    if not isinstance(obj,dict):raise StageError('Expected a JSON object')
    return obj


KINDS={'output','population','entity','visit_scope','event_scope','time','relation','aggregation','multiplicity','negation'}


def quoted_literals(question):
    # A possessive apostrophe in "patient 1's" is not an opening quote.
    return [m.group(0) for m in re.finditer(r'''(?<!\w)(["'])(.+?)\1(?!\w)''',question)]


# CLINSQL patient-similarity template: "For an 87-year-old woman: among female
# patients aged 82-92, ...". The reference patient frames the cohort whose bounds
# are stated explicitly after the colon.
_REFERENCE_PATIENT=re.compile(r'^\s*(For (?:an?|my|the|this|our)\b[^:,]{0,160}?)\s*[:,]')
# Other reference-patient openings ("I have a 63-year-old man ...", "Patient: female, 55.",
# "My 56-year-old male inpatient:"): the clause before the first sentence break or 'among'.
_LEADING_CLAUSE=re.compile(r'^\s*([^.;]{3,200}?)(?=[.;:]\s|\s+[Aa]mong\b|,\s+(?:what|how|which|among)\b)')
_FIRST_SENTENCE=re.compile(r'^\s*([^.;]{3,200}?)(?=[.;]\s|\s+[Aa]mong\b)')


def normalize_linking(question,obj,schema,catalog):
    """Deterministic, meaning-preserving repairs of a linker output (CLINSQL profile).

    Returns (obj, warnings). Only formatting is repaired; no clinical mapping is
    guessed:
    1. Literals inside the reference-patient preamble that no requirement covers
       get one verbatim 'population' requirement for that preamble.
    2. Fully qualified link tables (`project.dataset.table`) are reduced to the
       table name the schema uses.
    3. Links with an empty table/column are dropped (a requirement may stay unlinked).
    4. A catalog_id that does not support the linked column is cleared (the link
       keeps its schema column, the catalog evidence is not claimed).
    """
    warnings=[]
    requirements=obj.get('requirements')
    if isinstance(requirements,list):
        options=[m.group(1).strip() for m in (_REFERENCE_PATIENT.match(question),_LEADING_CLAUSE.match(question),
                 _FIRST_SENTENCE.match(question)) if m]
        # Prefer the first opening clause that actually carries a number.
        preamble=next((o for o in options if re.search(r'\d',o)),None)
        if preamble:
            spans=' '.join(r.get('span','') for r in requirements if isinstance(r,dict) and isinstance(r.get('span'),str))
            missing=[x for x in re.findall(r'\b\d+(?:\.\d+)?\b',preamble) if x not in spans]
            if missing and preamble in question and len(requirements)<32:
                used={r.get('id') for r in requirements if isinstance(r,dict)}
                rid=next(f'r{i}' for i in range(1,64) if f'r{i}' not in used)
                requirements.append({'id':rid,'kind':'population','span':preamble,
                    'description':'Reference patient that frames the similarity cohort; apply the explicit '
                                  'cohort bounds stated after it, not the reference value alone.'})
                warnings.append(f'added reference-patient requirement {rid} covering {missing}')
    links=obj.get('links')
    if isinstance(links,list):
        kept=[]
        known={c['id']:c for c in catalog}
        for link in links:
            if not isinstance(link,dict):
                kept.append(link);continue
            table=link.get('table')
            if isinstance(table,str) and '.' in table.strip('`'):
                short=table.replace('`','').split('.')[-1]
                if schema.has_ref(f"{short}.{link.get('column')}"):
                    warnings.append(f'qualified table {table} reduced to {short}')
                    link['table']=short
            if not str(link.get('table') or '').strip() or not str(link.get('column') or '').strip():
                warnings.append(f"dropped link without table/column for {link.get('requirement_id')}")
                continue
            cid=link.get('catalog_id')
            if cid is not None:
                record=known.get(cid)
                if record is None or record['table']!=link['table'] or link['column'] not in {record['column'],record.get('code_column')}:
                    warnings.append(f'cleared unsupported catalog_id {cid}')
                    link['catalog_id']=None
            kept.append(link)
        obj['links']=kept
    joins=obj.get('joins')
    if isinstance(joins,list):
        kept=[]
        for join in joins:
            if isinstance(join,dict):
                for side in ('left','right'):
                    ref=join.get(side)
                    if isinstance(ref,str) and ref.replace('`','').count('.')>1:
                        short='.'.join(ref.replace('`','').split('.')[-2:])
                        warnings.append(f'qualified join reference {ref} reduced to {short}')
                        join[side]=short
                # 5. A join outside the pinned relationship metadata is a hint the
                # generator does not need; drop it rather than reject the linker.
                if not schema.edge_path(join.get('left'),join.get('right')):
                    warnings.append(f"dropped join outside relationship metadata: {join.get('left')} = {join.get('right')}")
                    continue
            kept.append(join)
        obj['joins']=kept
    return obj,warnings


def linking(question,obj,schema,catalog):
    requirements=obj.get('requirements')
    if not isinstance(requirements,list) or not 1<=len(requirements)<=32:raise StageError('Requirements missing/too many')
    ids=set()
    for r in requirements:
        if not isinstance(r,dict) or not isinstance(r.get('id'),str) or not re.fullmatch(r'r\d+',r['id']) or r['id'] in ids:raise StageError('Invalid/duplicate requirement ID')
        if r.get('kind') not in KINDS or not isinstance(r.get('span'),str) or not r['span'].strip() or r['span'] not in question:raise StageError('Requirement needs a verbatim original span')
        if not isinstance(r.get('description'),str) or not r['description'].strip():raise StageError('Missing obligation description')
        ids.add(r['id'])
    spans=' '.join(r['span'] for r in requirements)
    # Evidence coverage checks, without interpreting clinical meaning.
    for literal in re.findall(r'\b\d+(?:\.\d+)?\b',question)+quoted_literals(question):
        if literal not in spans:raise StageError('Uncovered question literal: '+literal)
    if not any(r['kind']=='output' for r in requirements):raise StageError('Missing output obligation')
    known={c['id']:c for c in catalog}
    if not isinstance(obj.get('links'),list) or not isinstance(obj.get('joins'),list):raise StageError('Missing links/joins')
    for link in obj['links']:
        if link.get('requirement_id') not in ids or not isinstance(link.get('span'),str) or not link['span'].strip() or link['span'] not in question:raise StageError('Ungrounded schema link')
        ref=str(link.get('table'))+'.'+str(link.get('column'))
        if not schema.has_ref(ref):raise StageError('Unknown schema reference: '+ref)
        if not isinstance(link.get('role'),str) or not link['role'].strip():raise StageError('Missing column role')
        cid=link.get('catalog_id')
        if cid is not None:
            record=known.get(cid)
            if record is None or record['table']!=link['table'] or link['column'] not in {record['column'],record.get('code_column')}:
                raise StageError('Catalog record does not support linked source/column')
    for join in obj['joins']:
        path=schema.edge_path(join.get('left'),join.get('right'))
        if not path:raise StageError('Join not supported by relationship metadata: '+str(join))
        join['supported_key_path']=path
    for a,b in [('diagnoses_icd','d_icd_diagnoses'),('procedures_icd','d_icd_procedures')]:
        code={a+'.icd_code',b+'.icd_code'}
        version={a+'.icd_version',b+'.icd_version'}
        if schema.has_ref(a+'.icd_version') and schema.has_ref(b+'.icd_version'):
            if any({j['left'],j['right']}==code for j in obj['joins']) and not any({j['left'],j['right']}==version for j in obj['joins']):
                raise StageError('Linking omitted required icd_version composite relationship')
    if not isinstance(obj.get('ambiguities'),list):raise StageError('Missing ambiguity list')
    return obj


def decomposition(obj,requirements,schema):
    steps=obj.get('steps')
    if not isinstance(steps,list) or not 1<=len(steps)<=24:raise StageError('Missing/oversized decomposition')
    wanted={r['id'] for r in requirements}
    seen={}
    for step in steps:
        sid=step.get('id')
        if not isinstance(sid,str) or sid in seen:raise StageError('Invalid/duplicate plan step')
        if step.get('operation') not in {'filter','join','select_event','aggregate','rank','project'}:raise StageError('Invalid relational operation')
        if not isinstance(step.get('depends_on'),list) or not set(step['depends_on'])<=set(seen):raise StageError('Cyclic/forward/missing dependency')
        if not isinstance(step.get('requirement_ids'),list) or not set(step['requirement_ids'])<=wanted:raise StageError('Unknown requirement in plan')
        if not isinstance(step.get('tables'),list) or not set(step['tables'])<=set(schema.tables):raise StageError('Unknown plan table')
        if not isinstance(step.get('description'),str) or not step['description'].strip():raise StageError('Missing step description')
        seen[sid]=step
    output=obj.get('output_step')
    if output not in seen:raise StageError('Missing output step')
    reachable=set()
    def visit(sid):
        if sid in reachable:return
        reachable.add(sid)
        for parent in seen[sid]['depends_on']:visit(parent)
    visit(output)
    if reachable!=set(seen):raise StageError('Detached plan step')
    covered={i for sid in reachable for i in seen[sid]['requirement_ids']}
    if covered!=wanted:raise StageError('Plan dropped a question obligation')
    return obj


def verification(obj,requirements,sql,inspection,question,schema=None,evidence_catalog=None,*,lenient=False):
    """Validate a verifier audit.

    lenient=True (CLINSQL v5): evidence-citation defects no longer reject the
    whole audit. A check with defective evidence cannot count as satisfied and
    is downgraded to unknown; the verdict is recomputed from the checks. The
    defects are kept in obj['evidence_warnings']. Structural defects (missing
    obligations, invalid status, missing coverage audit) still raise.
    """
    if lenient:
        warnings=[]
        checks=obj.get('checks')
        wanted={r['id'] for r in requirements}
        if not isinstance(checks,list) or len(checks)!=len(wanted):raise StageError('Verifier omitted obligations')
        seen=set()
        for check in checks:
            if not isinstance(check,dict):raise StageError('Invalid verification check')
            rid=check.get('requirement_id')
            if rid not in wanted or rid in seen:raise StageError('Unknown/duplicate verification obligation')
            seen.add(rid)
            if check.get('status') not in {'satisfied','contradicted','unknown'}:raise StageError('Invalid verification status')
            if not isinstance(check.get('evidence'),str) or not check['evidence'].strip():check['evidence']='(no evidence text)'
            try:
                single=dict(obj,checks=[check],question_coverage={'status':'unknown','uncovered_spans':[],'extra_constraints':[]},verdict=None)
                _verify_checks(single,{rid},sql,inspection,schema,evidence_catalog)
            except StageError as error:
                warnings.append(f'{rid}: {error}'[:300])
                check.setdefault('sql_fragments',[])
                if check['status']=='satisfied':check['status']='unknown'
        coverage=obj.get('question_coverage')
        if not isinstance(coverage,dict) or coverage.get('status') not in {'complete','incomplete','unknown'}:
            raise StageError('Missing original-question coverage audit')
        spans=[s for s in coverage.get('uncovered_spans') or [] if isinstance(s,str) and s.strip() and s in question]
        if coverage['status']=='complete' and spans:coverage['status']='incomplete'
        if coverage['status']=='incomplete' and not spans:coverage['status']='unknown'
        coverage['uncovered_spans']=spans
        extras=[]
        for extra in coverage.get('extra_constraints') or []:
            try:
                if not isinstance(extra,dict):raise StageError('Invalid unsupported-constraint evidence')
                if evidence_catalog is not None:
                    extra['sql_fragments']=resolve_ids(evidence_catalog,extra.get('sql_evidence_ids'))
                    extra['sql_fragment']=extra['sql_fragments'][0]
                aligned=sql_evidence(sql,extra.get('sql_fragment'),schema.dialect if schema else 'sqlite')
                if aligned is None:raise StageError('Invented unsupported-constraint SQL evidence')
                extra['sql_fragment']=aligned
                extras.append(extra)
            except (StageError,ValueError,TypeError,KeyError,IndexError) as error:
                warnings.append(f'extra_constraint dropped: {error}'[:300])
        coverage['extra_constraints']=extras
        statuses={c['status'] for c in checks}
        verdict=('contradicted' if 'contradicted' in statuses or extras else
                 'unknown' if 'unknown' in statuses or coverage['status']!='complete' else 'supported')
        if obj.get('verdict')!=verdict:warnings.append(f'verdict recomputed: {obj.get("verdict")} -> {verdict}')
        obj['verdict']=verdict
        obj['evidence_warnings']=warnings
        return obj
    return _strict_verification(obj,requirements,sql,inspection,question,schema,evidence_catalog)


def _verify_checks(obj,wanted,sql,inspection,schema,evidence_catalog):
    for check in obj['checks']:
        rid=check.get('requirement_id')
        if evidence_catalog is not None:
            try:check['sql_fragments']=resolve_ids(evidence_catalog,check.get('sql_evidence_ids'))
            except ValueError as error:raise StageError(str(error)) from error
        fragments=check.get('sql_fragments')
        refs=check.get('schema_refs')
        if not isinstance(fragments,list) or not isinstance(refs,list):raise StageError('Missing structured evidence')
        aligned=[sql_evidence(sql,f,schema.dialect if schema else 'sqlite') for f in fragments]
        if any(f is None for f in aligned):raise StageError('Invented SQL evidence')
        check['sql_fragments']=aligned
        invalid=set(refs)-(set(inspection['used_refs'])|set(inspection['tables']))
        if invalid:raise StageError('Positive evidence cites unused refs '+str(sorted(invalid)))
        missing=check.get('missing_schema_refs',[])
        if not isinstance(missing,list) or any(not schema or not schema.has_ref(r) or r in inspection['used_refs'] for r in missing):
            raise StageError('Missing schema evidence must name known columns absent from the query')
        if check['status']=='satisfied' and missing:raise StageError('Satisfied check cannot claim a required column is missing')
        if check['status']=='satisfied' and (not fragments or not refs):raise StageError('Satisfied '+rid+' requires SQL/schema evidence')


def _strict_verification(obj,requirements,sql,inspection,question,schema=None,evidence_catalog=None):
    checks=obj.get('checks')
    wanted={r['id'] for r in requirements}
    if not isinstance(checks,list) or len(checks)!=len(wanted):raise StageError('Verifier omitted obligations')
    seen=set()
    for check in checks:
        rid=check.get('requirement_id')
        if rid not in wanted or rid in seen:raise StageError('Unknown/duplicate verification obligation')
        seen.add(rid)
        if check.get('status') not in {'satisfied','contradicted','unknown'}:raise StageError('Invalid verification status')
        if not isinstance(check.get('evidence'),str) or not check['evidence'].strip():raise StageError('Missing verification evidence')
        if evidence_catalog is not None:
            try:check['sql_fragments']=resolve_ids(evidence_catalog,check.get('sql_evidence_ids'))
            except ValueError as error:raise StageError(str(error)) from error
        fragments=check.get('sql_fragments')
        refs=check.get('schema_refs')
        if not isinstance(fragments,list) or not isinstance(refs,list):raise StageError('Missing structured evidence')
        aligned=[sql_evidence(sql,f,schema.dialect if schema else 'sqlite') for f in fragments]
        if any(f is None for f in aligned):raise StageError('Invented SQL evidence')
        check['sql_fragments']=aligned
        invalid=set(refs)-(set(inspection['used_refs'])|set(inspection['tables']))
        if invalid:raise StageError('Positive evidence cites unused refs '+str(sorted(invalid))+'. Put absent-but-required columns in missing_schema_refs; positive refs must be in '+str(inspection['used_refs']))
        missing=check.get('missing_schema_refs',[])
        if not isinstance(missing,list) or any(not schema or not schema.has_ref(r) or r in inspection['used_refs'] for r in missing):
            raise StageError('Missing schema evidence must name known columns absent from the query')
        if check['status']=='satisfied' and missing:raise StageError('Satisfied check cannot claim a required column is missing')
        if check['status']=='satisfied' and (not fragments or not refs):raise StageError('Satisfied '+rid+' requires SQL/schema evidence, including outer projections backed by an actual source table')
    coverage=obj.get('question_coverage')
    if not isinstance(coverage,dict) or coverage.get('status') not in {'complete','incomplete','unknown'}:
        raise StageError('Missing original-question coverage audit')
    spans=coverage.get('uncovered_spans')
    extras=coverage.get('extra_constraints')
    if not isinstance(spans,list) or not isinstance(extras,list):raise StageError('Missing coverage evidence')
    if any(not isinstance(s,str) or not s.strip() or s not in question for s in spans):raise StageError('Invented uncovered question span')
    if coverage['status']=='complete' and spans:raise StageError('Complete coverage contradicts uncovered spans')
    if coverage['status']=='incomplete' and not spans:raise StageError('Incomplete coverage needs an original question span')
    for extra in extras:
        if not isinstance(extra,dict):raise StageError('Invalid unsupported-constraint evidence')
        if evidence_catalog is not None:
            try:extra['sql_fragments']=resolve_ids(evidence_catalog,extra.get('sql_evidence_ids'))
            except ValueError as error:raise StageError(str(error)) from error
            extra['sql_fragment']=extra['sql_fragments'][0]
        aligned=sql_evidence(sql,extra.get('sql_fragment'),schema.dialect if schema else 'sqlite')
        if aligned is None:
            raise StageError('Invented unsupported-constraint SQL evidence')
        extra['sql_fragment']=aligned
        if not isinstance(extra.get('evidence'),str) or not extra['evidence'].strip():raise StageError('Missing unsupported-constraint explanation')
    statuses={c['status'] for c in checks}
    verdict=('contradicted' if 'contradicted' in statuses or extras else
             'unknown' if 'unknown' in statuses or coverage['status']!='complete' else 'supported')
    if obj.get('verdict')!=verdict:raise StageError('Verifier verdict inconsistent with checks')
    return obj


def selection(obj,requirements,candidates,question,schema,*,lenient=False,require_supported=True):
    """Judge candidate suitability, not a tournament requiring a unique winner.

    All assessments must be grounded independently. Matching results alone do
    not establish correctness. A chosen query must pass its final assessment.
    """
    known={c['id']:c for c in candidates}
    assessments=obj.get('assessments')
    if not isinstance(assessments,list) or len(assessments)!=len(known):
        raise StageError('Assess every eligible candidate exactly once')
    checked={}
    for item in assessments:
        if not isinstance(item,dict):raise StageError('Invalid candidate assessment')
        cid=item.get('candidate_id')
        if cid not in known or cid in checked:raise StageError('Unknown/duplicate candidate assessment')
        candidate=known[cid]
        try:
            checked[cid]=verification(item,requirements,candidate['sql'],candidate['inspection'],question,schema,candidate['evidence_catalog'],lenient=lenient)
        except StageError as error:
            if require_supported:raise
            # v6/v7 disagreement resolution uses only selected_id and reason; a
            # malformed per-candidate audit is kept as a warning, not a failure.
            checked[cid]=None
            obj.setdefault('assessment_warnings',[]).append({'candidate_id':cid,'error':str(error)})
    if 'selected_id' not in obj:raise StageError('Missing selected_id is not a refusal')
    selected=obj['selected_id']
    if not require_supported:
        # v6 disagreement resolution: pick the most suitable executed candidate,
        # even when none is fully supported; refusal is handled by the caller.
        if selected is not None and selected not in known:
            raise StageError('Selected candidate must be one of the supplied candidates')
        if not isinstance(obj.get('reason'),str) or not obj['reason'].strip():raise StageError('Missing selection reason')
        return obj
    supported={cid for cid,assessment in checked.items() if assessment['verdict']=='supported'}
    if selected is None and supported:
        raise StageError('Select one supported candidate; lack of a unique best is not unanswerability')
    if selected is not None and (not isinstance(selected,str) or selected not in supported):
        raise StageError('Selected candidate must have a supported grounded assessment')
    if not isinstance(obj.get('reason'),str) or not obj['reason'].strip():raise StageError('Missing selection reason')
    return obj
