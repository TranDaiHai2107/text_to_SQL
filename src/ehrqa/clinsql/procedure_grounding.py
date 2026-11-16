"""Local, version-aware evidence for procedure concepts in the Ours pipeline."""
import re

from sqlglot import exp, parse_one
from sqlglot.optimizer.scope import traverse_scope


PROCEDURE_TABLE = 'd_icd_procedures'
TOP_K_PER_VERSION = 12
REVIEW = 'CODESET_AMBIGUOUS_REQUIRES_INDEPENDENT_REVIEW'
AMBIGUOUS = 'CODESET_AMBIGUOUS'
NOT_FOUND = 'CODESET_NOT_FOUND'
CODE_SYSTEMS = {9: 'ICD-9-CM-PROCEDURE', 10: 'ICD-10-PCS'}
CMS_DEVICE = 'https://www.cms.gov/files/document/2015-measure-information-form-aco-37-heart-failure-admissions.pdf'
CMS_ICD9 = 'https://www.cms.gov/medicare/coding-billing/icd-10-codes/icd-9-cm-diagnosis-procedure-codes-abbreviated-and-full-code-titles'
CMS_GEMS = 'https://www.cms.gov/files/document/general-equivalence-mappings-documentation-technical-users-revised-fy-2017.pdf'
CMS_PCS = 'https://www.cms.gov/files/document/icd-10-pcs-2020-tables-and-index-pdf.pdf'
CMS_ECMO = 'https://www.cms.gov/icd10m/version372-fullcode-cms/fullcode_cms/P0039.html'

# Exact public identities expand retrieval vocabulary. A hit establishes neither
# clinical membership nor completeness of a procedure set.
_MCS_ALIASES = ('mechanical circulatory support', 'mcs')
_PUBLIC_CONCEPT_ALIASES = {
    **{(9, code): (CMS_DEVICE, _MCS_ALIASES) for code in ('3760', '3762', '3765', '3766', '3768')},
    (9, '3761'): (CMS_ICD9, (*_MCS_ALIASES, 'iabp', 'intra aortic balloon pump')),
    (9, '3965'): (CMS_GEMS, (*_MCS_ALIASES, 'ecmo', 'extracorporeal membrane oxygenation')),
    **{(10, code): (CMS_DEVICE, _MCS_ALIASES)
       for code in ('02HA0QZ', '5A02216', '5A02116', '5A0221D', '5A0211D')},
    (10, '5A02210'): (CMS_PCS, (*_MCS_ALIASES, 'iabp', 'intra aortic balloon pump')),
    (10, '5A15223'): (CMS_GEMS, (*_MCS_ALIASES, 'ecmo', 'extracorporeal membrane oxygenation')),
    (10, '5A1522G'): (CMS_ECMO, (*_MCS_ALIASES, 'va ecmo', 'veno arterial ecmo')),
}
_LEGACY_ECMO = {(9, '3965'), (10, '5A15223')}
_ROUTES = (
    ('LAB', r'\b(?:lab(?:oratory)? tests?|assays?|laboratory results?)\b'),
    ('MEDICATION', r'\b(?:medications?|drugs?|prescriptions?|refills?)\b'),
    ('PROCEDURE', r'\b(?:procedures?|surger(?:y|ies)|implantation|interventions?)\b'),
    ('DIAGNOSIS', r'\b(?:diagnos(?:is|es|ed)|diseases?|disorders?)\b'),
)
_TABLE_ROUTES = {'d_icd_procedures': 'PROCEDURE', 'procedures_icd': 'PROCEDURE',
                 'd_icd_diagnoses': 'DIAGNOSIS', 'diagnoses_icd': 'DIAGNOSIS',
                 'd_labitems': 'LAB', 'labevents': 'LAB',
                 'prescriptions': 'MEDICATION', 'pharmacy': 'MEDICATION'}


class CodeSetBlocked(ValueError):
    def __init__(self, status, candidates=()):
        super().__init__(status)
        self.candidates = candidates


def concept_type(span, linked_tables=()):
    for kind, pattern in _ROUTES:
        if re.search(pattern, span, re.IGNORECASE):
            return kind
    types = {_TABLE_ROUTES[table] for table in linked_tables if table in _TABLE_ROUTES}
    return types.pop() if len(types) == 1 else 'OTHER'


def procedure_candidates(catalog, span, *, top_k=TOP_K_PER_VERSION):
    if not 1 <= top_k <= TOP_K_PER_VERSION:
        raise ValueError('Procedure retrieval exceeds the per-version candidate limit')
    aliases = {f'{PROCEDURE_TABLE}:{version}:{code}': names
               for (version, code), (_, names) in _PUBLIC_CONCEPT_ALIASES.items()}
    candidates = []
    for version, system in CODE_SYSTEMS.items():
        for record in catalog.search(span, {'tables': [PROCEDURE_TABLE]}, table=PROCEDURE_TABLE,
                                     icd_version=version, limit=top_k, supplemental_aliases=aliases):
            key = version, record['code']
            terminology = _PUBLIC_CONCEPT_ALIASES.get(key)
            candidates.append({
                'icd_code': record['code'], 'icd_version': version, 'code_system': system,
                'label': record['label'], 'dictionary_source': catalog.source,
                'official_sources': [terminology[0]] if terminology else [],
                'status': 'AMBIGUOUS_LEGACY_CODE' if key in _LEGACY_ECMO else 'RETRIEVED',
            })
    return candidates


def procedure_evidence(catalog, linked):
    """Stop before generation when a required procedure set has no verified membership."""
    for requirement in linked['requirements']:
        if requirement['kind'] not in {'entity', 'population', 'event_scope'}:
            continue
        tables = [link['table'] for link in linked['links'] if link['requirement_id'] == requirement['id']]
        if concept_type(requirement['span'], tables) != 'PROCEDURE':
            continue
        candidates = procedure_candidates(catalog, requirement['span'])
        if any(item['status'] == 'AMBIGUOUS_LEGACY_CODE' for item in candidates):
            raise CodeSetBlocked(REVIEW, candidates)
        if candidates:
            raise CodeSetBlocked(AMBIGUOUS, candidates)
        raise CodeSetBlocked(NOT_FOUND)


def adjudication_format(candidates):
    """One Structured Outputs response classifies only supplied identities."""
    properties = {
        'icd_code': {'type': 'string', 'enum': sorted({r['icd_code'] for r in candidates})},
        'icd_version': {'type': 'integer', 'enum': sorted({r['icd_version'] for r in candidates})},
        'candidate_label': {'type': 'string'},
        'decision': {'type': 'string', 'enum': ['INCLUDE', 'EXCLUDE', 'AMBIGUOUS']},
        'reason': {'type': 'string'},
        'evidence_source_ids': {'type': 'array', 'items': {'type': 'string'}},
    }
    entries = {'type': 'array', 'items': {'type': 'object', 'properties': properties,
                                         'required': list(properties), 'additionalProperties': False}}
    return {'type': 'json_schema', 'name': 'procedure_code_adjudication', 'strict': True,
            'schema': {'type': 'object', 'properties': {'decisions': entries},
                       'required': ['decisions'], 'additionalProperties': False}}


def validated_decisions(catalog, candidates, decisions):
    """Bind exact structured decisions to reviewed source records and dictionary versions."""
    expected = {(r['icd_version'], r['icd_code']): r for r in candidates}
    bound = {}
    for decision in decisions:
        key = decision['icd_version'], decision['icd_code']
        record = expected.get(key)
        if not record:
            continue
        if (key in bound or type(key[0]) is not int or
                f'{PROCEDURE_TABLE}:{key[0]}:{key[1]}' not in catalog.records or
                decision['candidate_label'] != record['label'] or
                decision['decision'] not in {'INCLUDE', 'EXCLUDE', 'AMBIGUOUS'} or
                not decision['reason'].strip() or not decision['evidence_source_ids'] or
                not set(decision['evidence_source_ids']) <= set(record['official_sources']) or
                (record['status'] == 'AMBIGUOUS_LEGACY_CODE' and decision['decision'] != 'AMBIGUOUS')):
            raise CodeSetBlocked(REVIEW, candidates)
        bound[key] = {**record, 'decision': decision['decision'], 'reason': decision['reason'],
                      'evidence_source_ids': decision['evidence_source_ids']}
    if bound.keys() != expected.keys() or any(r['decision'] == 'AMBIGUOUS' for r in bound.values()):
        raise CodeSetBlocked(REVIEW, candidates)
    includes = [r for r in bound.values() if r['decision'] == 'INCLUDE']
    if not includes:
        raise CodeSetBlocked(NOT_FOUND)
    return includes


def _unwrap(node):
    while isinstance(node, exp.Paren):
        node = node.this
    return node


def _predicates(node, operator):
    node = _unwrap(node)
    if isinstance(node, operator):
        return [*_predicates(node.this, operator), *_predicates(node.expression, operator)]
    return [node]


def _filter_pairs(condition):
    pairs = set()
    for branch in _predicates(condition, exp.Or):
        version = None
        codes = None
        for predicate in _predicates(branch, exp.And):
            lhs = predicate.this if isinstance(predicate, exp.Expression) else None
            if not isinstance(lhs, exp.Column):
                raise ValueError('Required procedure filter is not a grounded code/version predicate')
            if isinstance(predicate, exp.EQ) and lhs.name == 'icd_version' and isinstance(
                    predicate.expression, exp.Literal) and predicate.expression.is_int and version is None:
                version = int(predicate.expression.this)
            elif (lhs.name == 'icd_code' and codes is None and isinstance(predicate, (exp.In, exp.EQ))):
                values = predicate.expressions if isinstance(predicate, exp.In) else [predicate.expression]
                if not values or not all(isinstance(v, exp.Literal) and v.is_string for v in values):
                    raise ValueError('Required procedure code predicate needs known literal codes')
                codes = {v.this for v in values}
            else:
                raise ValueError('Unexpected condition in required procedure code selector')
        if version not in CODE_SYSTEMS or not codes:
            raise ValueError('Required procedure selector needs literal code/version pairs')
        pairs.update((version, code) for code in codes)
    return pairs


def verify_procedure_cte(sql, cte_name, includes):
    """Fail closed on an unverifiable or empty selector for an explicitly grounded concept."""
    expected = {(row['icd_version'], row['icd_code']) for row in includes
                if row['decision'] == 'INCLUDE' and row['evidence_source_ids']
                and CODE_SYSTEMS.get(row['icd_version']) == row['code_system']}
    if not expected or len(expected) != len(includes):
        raise ValueError('Required procedure selector has no complete verified code set')
    tree = parse_one(sql, read='bigquery')
    matches = [cte.this for cte in tree.find_all(exp.CTE) if cte.alias_or_name == cte_name]
    if len(matches) != 1 or not isinstance(matches[0], exp.Select):
        raise ValueError('Required procedure selector CTE is absent or ambiguous')
    selection = matches[0]
    source = selection.args.get('from_')
    if (not source or not isinstance(source.this, exp.Table) or source.this.name != PROCEDURE_TABLE
            or any(selection.args.get(key) is not None for key in (
                'joins', 'limit', 'offset', 'group', 'having', 'qualify', 'with_', 'sample'))
            or len(selection.selects) != 2
            or {item.name for item in selection.selects if isinstance(item, exp.Column)} != {'icd_code', 'icd_version'}):
        raise ValueError('Required procedure selector must project both dictionary keys directly')
    scopes = traverse_scope(tree)
    selector_scope = next(scope for scope in scopes if scope.expression is selection)
    origin = selector_scope.sources.get(source.this.alias_or_name)
    if not isinstance(origin, exp.Table) or origin.name != PROCEDURE_TABLE:
        raise ValueError('Required procedure selector must use the physical dictionary')
    # Unused WITH declarations are not dependencies of the root result.
    reachable = set()
    remaining = scopes[-1:]
    while remaining:
        scope = remaining.pop()
        if scope in reachable:
            continue
        reachable.add(scope)
        remaining.extend(child for _, child in scope.selected_sources.values() if child in scopes)
        remaining.extend([*scope.set_operation_scopes, *scope.subquery_scopes])
    if selector_scope not in reachable:
        raise ValueError('Required procedure selector is not used by the final query')
    where = selection.args.get('where')
    if where is None or _filter_pairs(where.this) != expected:
        raise ValueError('Required procedure selector differs from the verified code set')
    # Any additional literal procedure-code filter could change the verified set.
    for predicate in tree.find_all(exp.EQ, exp.In, exp.Like, exp.ILike):
        if predicate.find_ancestor(exp.Select) is selection:
            continue
        if any(isinstance(child, exp.Column) and child.name == 'icd_code' for child in predicate.iter_expressions()):
            if any(isinstance(child, exp.Literal) for child in predicate.iter_expressions()):
                raise ValueError('Additional literal ICD code predicate outside the verified selector')
