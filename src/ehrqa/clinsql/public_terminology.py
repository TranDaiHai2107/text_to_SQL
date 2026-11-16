"""Independent CMS terminology using the frozen CLINSQL retrieval implementation."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from .clinical_catalog import ClinicalCatalog
from .evidence_router import RestrictedEvidenceEgress, guard_ours_payload
from ehrqa.agentic.contracts import StageError
from .linking_format import anchored_link_format, question_anchors, resolve_link_anchors
from .openai_provider import OpenAIModelProvider
from .proposed_runner import ProposedModelProvider


PROFILE = 'PUBLIC_CLINICAL_TERMINOLOGY_SOURCE_ADAPTATION'
SOURCE = 'CMS public ICD-10-CM FY2022 and ICD-9-CM v32'
ARCHIVES = {
    'icd10cm_fy2022.zip': '423206a194dd6db8384c3b39699ad3c1efa19718677fa81690557732a31bf560',
    'icd9cm_v32.zip': '45a7d05ddcadf124af88375b64cdf068bb1e3f999ce7fdacb91f65f4e6d55f08',
}
MEMBERS = (
    ('icd10cm_fy2022.zip', 'Code Descriptions/icd10cm_codes_2022.txt', 'd_icd_diagnoses', 10, 'ascii'),
    ('icd9cm_v32.zip', 'CMS32_DESC_LONG_DX.txt', 'd_icd_diagnoses', 9, 'cp1252'),
    ('icd9cm_v32.zip', 'CMS32_DESC_LONG_SG.txt', 'd_icd_procedures', 9, 'ascii'),
)


class PublicClinicalCatalog(ClinicalCatalog):
    def __init__(self, directory):
        directory = Path(directory)
        for filename, sha256 in ARCHIVES.items():
            if hashlib.sha256((directory / filename).read_bytes()).hexdigest() != sha256:
                raise ValueError('Public CMS archive differs from SHA-256 pin')
        rows = []
        for filename, member, table, version, encoding in MEMBERS:
            with ZipFile(directory / filename) as archive:
                lines = archive.read(member).decode(encoding).splitlines()
            for line in filter(str.strip, lines):
                code, label = line.split(maxsplit=1)
                rows.append({'table': table, 'icd_version': version, 'icd_code': code,
                             'long_title': label.strip()})
        serialized = json.dumps({'source': SOURCE, 'archives': ARCHIVES, 'rows': rows},
                                ensure_ascii=False, separators=(',', ':'), sort_keys=True)
        super().__init__(rows, source=SOURCE, sha256=hashlib.sha256(serialized.encode()).hexdigest())
        # Independently snapshot exact public wire records for the egress check.
        self._wire_records = {key: self._wire(value) for key, value in self.records.items()}

    @staticmethod
    def _wire(value):
        return json.loads(json.dumps(value, ensure_ascii=False))

    def verify_payload(self, stage, catalog):
        if not isinstance(catalog, list):
            raise RestrictedEvidenceEgress(stage, 'invalid public terminology payload')
        for item in catalog:
            if not isinstance(item, dict):
                raise RestrictedEvidenceEgress(stage, 'invalid public terminology record')
            entry = {key: value for key, value in item.items()
                     if key not in ('candidate_list_complete', 'match')}
            key = item.get('id')
            if (not isinstance(key, str) or entry != self._wire_records.get(key)
                    or item.get('candidate_list_complete') is not False
                    or item.get('match') not in ('exact_surface', 'lexical_candidate')):
                raise RestrictedEvidenceEgress(stage, 'clinical record differs from pinned public CMS source')


class PublicTerminologyModelProvider(ProposedModelProvider):
    def __init__(self, ledger, *, public_catalog, **kwargs):
        if type(public_catalog) is not PublicClinicalCatalog:
            raise TypeError('Expected the pinned public CMS corpus')
        super().__init__(ledger, **kwargs)
        self.public_catalog = public_catalog

    def complete(self, stage, messages, tokens):
        payload = json.loads(messages[-1]['content'])
        if 'catalog' in payload:
            self.public_catalog.verify_payload(stage, payload.pop('catalog'))
        guard_input = [*messages[:-1], {**messages[-1], 'content': json.dumps(payload)}]
        guard_ours_payload(stage, guard_input)
        if stage != 'link':
            return OpenAIModelProvider.complete(self, stage, json.dumps(messages, ensure_ascii=False))
        wire_payload = json.loads(messages[-1]['content'])
        question = wire_payload['original_question']
        anchors = question_anchors(question)
        wire_payload['question_tokens'] = {i: question[start:end] for i, (start, end) in enumerate(anchors)}
        instructions = (
            '\nQuote each span verbatim from original_question. In this interface span must be '
            '{"first": <zero-based token index>, "last": <zero-based token index, inclusive>}. '
            'Select the smallest contiguous range in question_tokens supporting each requirement '
            'or link. The runner copies the exact original substring, including punctuation and spaces. '
            'Put paraphrases only in description or role. '
            'Use the required output_requirement for what the question asks to return, even when '
            'it asks for a count. Its ID is r0. Use an exact supporting range. '
            'Put other obligations, including aggregation semantics, in requirements, numbered '
            'r1 onward without repetition. Refer to r0 in links for the output requirement. '
            'On retry correct the indicated fields.'
        )
        wire = [{**messages[0], 'content': messages[0]['content'] + instructions},
                {**messages[-1], 'content': json.dumps(wire_payload, ensure_ascii=False)}]
        result = OpenAIModelProvider.complete(self, stage, json.dumps(wire, ensure_ascii=False),
                                             text_format=anchored_link_format())
        try:
            resolved = resolve_link_anchors(json.loads(result['content']), question, anchors)
        except (StageError, ValueError, TypeError, KeyError) as exc:
            return {**result, 'link_anchor_error': str(exc) if isinstance(exc, StageError)
                    else 'Link spans must be paired integer token indexes'}
        return {**result, 'content': json.dumps(resolved, ensure_ascii=False)}


def compare_local_records(catalog, restricted_records):
    counts = {'total': len(restricted_records), 'exact_label_match': 0,
              'wording_difference': 0, 'absent_from_public_corpus': 0}
    for record in restricted_records:
        match = catalog.records.get(record['id'])
        if not match:
            counts['absent_from_public_corpus'] += 1
        elif match['label'] == record['label']:
            counts['exact_label_match'] += 1
        else:
            counts['wording_difference'] += 1
    return counts
