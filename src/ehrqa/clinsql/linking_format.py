"""Structured Outputs contract for the Proposed linker."""
from copy import deepcopy
import re

from ehrqa.agentic.contracts import KINDS, StageError


def _object(**fields):
    return {'type': 'object', 'properties': fields, 'required': list(fields),
            'additionalProperties': False}


def _array(items):
    return {'type': 'array', 'items': items}


STRING = {'type': 'string'}
LINK_SCHEMA = _object(
    requirements=_array(_object(id=STRING, kind={'type': 'string', 'enum': sorted(KINDS)},
                                span=STRING, description=STRING)),
    links=_array(_object(requirement_id=STRING, span=STRING, table=STRING, column=STRING, role=STRING,
                         catalog_id={'type': ['string', 'null']})),
    joins=_array(_object(left=STRING, right=STRING)),
    ambiguities=_array(STRING),
)
LINK_FORMAT = {'type': 'json_schema', 'name': 'clinsql_linking', 'strict': True, 'schema': LINK_SCHEMA}


def question_anchors(question):
    return [(match.start(), match.end()) for match in re.finditer(r'\S+', question)]


def anchored_link_format():
    schema = deepcopy(LINK_SCHEMA)
    for group in ('requirements', 'links'):
        schema['properties'][group]['items']['properties']['span'] = _object(
            first={'type': 'integer'}, last={'type': 'integer'})
    output = deepcopy(schema['properties']['requirements']['items'])
    output['properties']['kind']['enum'] = ['output']
    output['properties']['id'] = {'type': 'string', 'enum': ['r0']}
    regular = schema['properties']['requirements']['items']['properties']
    regular['id'] = {'type': 'string', 'enum': [f'r{i}' for i in range(1, 32)]}
    regular['kind']['enum'].remove('output')
    schema['properties']['output_requirement'] = output
    schema['required'].append('output_requirement')
    return {**LINK_FORMAT, 'name': 'clinsql_anchored_linking', 'schema': schema}


def resolve_link_anchors(output, question, anchors):
    obligation = output.pop('output_requirement')
    if obligation['kind'] != 'output':
        raise StageError('output_requirement.kind must be output')
    output['requirements'].append(obligation)
    for group in ('requirements', 'links'):
        for index, item in enumerate(output[group]):
            span = item['span']
            first, last = span['first'], span['last']
            if not (type(first) is int and type(last) is int and 0 <= first <= last < len(anchors)):
                raise StageError(f'{group}[{index}].span requires 0 <= first <= last < {len(anchors)}')
            item['span'] = question[anchors[first][0]:anchors[last][1]]
    return output


def validate_link_format(output):
    def check(value, schema, field):
        kind = schema['type']
        if kind == 'object' and isinstance(value, dict) and set(value) == set(schema['properties']):
            for key, item in value.items():
                check(item, schema['properties'][key], f'{field}.{key}')
            return
        if kind == 'array' and isinstance(value, list):
            for number, item in enumerate(value):
                check(item, schema['items'], f'{field}[{number}]')
            return
        if isinstance(value, str) and (kind == 'string' or kind == ['string', 'null']):
            if 'enum' not in schema or value in schema['enum']:
                return
        if value is None and kind == ['string', 'null']:
            return
        raise StageError(f'Link JSON format violation at {field}')

    check(output, LINK_SCHEMA, '$')
