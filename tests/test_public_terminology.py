import json
from pathlib import Path

import pytest

from ehrqa.clinsql.evidence_router import RestrictedEvidenceEgress
from ehrqa.clinsql.linking_format import anchored_link_format, validate_link_format
from ehrqa.clinsql.openai_provider import OpenAIModelProvider
from ehrqa.clinsql.public_terminology import PublicClinicalCatalog, PublicTerminologyModelProvider


def test_public_cms_transport_matches_pinned_records_and_preserves_wire_prompt(monkeypatch):
    catalog = PublicClinicalCatalog(Path(__file__).resolve().parents[1] / 'data/clinsql/public_terminology')
    assert len(catalog.records) == 91_199
    entries = catalog.search('cholera', {'tables': ['d_icd_diagnoses']})
    assert entries
    request = []

    def complete(self, stage, prompt, *, text_format):
        request.append((stage, json.loads(prompt), text_format))
        return {'content': json.dumps({
            'requirements': [{'id': 'r1', 'kind': 'aggregation', 'span': anchor, 'description': 'Count'}],
            'output_requirement': {'id': 'r0', 'kind': 'output', 'span': {'first': 0, 'last': 2},
                                   'description': 'Return count'},
            'links': [], 'joins': [], 'ambiguities': [],
        })}

    monkeypatch.setattr(OpenAIModelProvider, 'complete', complete)
    model = PublicTerminologyModelProvider(None, public_catalog=catalog, client=object())
    messages = [{'role': 'system', 'content': 'Link the question.'},
                {'role': 'user', 'content': json.dumps({
                    'original_question': 'Count  cholera cases.', 'catalog': entries})}]
    anchor = {'first': 0, 'last': 1}
    output = json.loads(model.complete('link', messages, 8192)['content'])
    validate_link_format(output)
    assert output['requirements'][0]['span'] == 'Count  cholera'
    assert output['requirements'][1]['span'] == 'Count  cholera cases.'
    stage, wire, format_ = request[0]
    assert stage == 'link' and format_ == anchored_link_format()
    schema_fields = format_['schema']['properties']
    assert schema_fields['links']['items']['properties']['table'] == {'type': 'string'}
    assert schema_fields['links']['items']['properties']['column'] == {'type': 'string'}
    assert schema_fields['output_requirement']['properties']['id']['enum'] == ['r0']
    assert 'verbatim' in wire[0]['content']
    assert json.loads(wire[1]['content'])['question_tokens']['2'] == 'cases.'

    for changed in ({'label': 'different label'}, {'source': 'MIMIC-IV'}, {'subject_id': 123}):
        tampered = [{**entries[0], **changed}]
        with pytest.raises(RestrictedEvidenceEgress):
            model.complete('link', [{'role': 'user', 'content': json.dumps({'catalog': tampered})}], 8192)
    with pytest.raises(RestrictedEvidenceEgress):
        model.complete('answer', messages, 8192)
    assert len(request) == 1
    anchor = {'first': 2, 'last': 3}
    error = model.complete('link', messages, 8192)['link_anchor_error']
    assert error == 'requirements[0].span requires 0 <= first <= last < 3'
