"""Classify evidence immediately before pinned OpenAI inference."""

from .benchmark_model import ModelMismatch
from .clinical_catalog import DICTIONARIES

_DICTIONARY_FIELDS = {
    'id', 'table', 'column', 'code_column', 'code', 'label', 'aliases', 'source',
    'icd_version', 'match', 'candidate_list_complete', 'fluid', 'category',
    'linksto', 'abbreviation', 'unitname',
}
_PATIENT_OBSERVATION_FIELDS = {
    'subject_id', 'hadm_id', 'stay_id', 'charttime', 'storetime', 'valuenum', 'value',
}


class RestrictedEvidenceEgress(PermissionError):
    def __init__(self, stage, category):
        self.stage = stage
        self.category = category
        super().__init__(f'RESTRICTED_EVIDENCE_EGRESS: {stage}: {category}')


def classify_ours_catalog(catalog):
    if not isinstance(catalog, list):
        return 'unverified clinical dictionary payload'
    if any(isinstance(item, dict) and _PATIENT_OBSERVATION_FIELDS & item.keys()
           for item in catalog):
        return 'patient-specific observations'
    if all(isinstance(item, dict) and item.get('table') in DICTIONARIES
           and item.keys() <= _DICTIONARY_FIELDS for item in catalog):
        return 'MIMIC-IV static clinical dictionary records'
    return 'unverified clinical dictionary payload'


def guard_ours_payload(stage, messages):
    import json

    payload = json.loads(messages[-1]['content'])
    if payload.get('catalog'):
        raise RestrictedEvidenceEgress(stage, classify_ours_catalog(payload['catalog']))
    if payload.get('verified_procedure_sets'):
        raise RestrictedEvidenceEgress(stage, 'locally grounded procedure dictionary records')
    if stage == 'answer' or payload.get('conversation_context'):
        raise RestrictedEvidenceEgress(stage, 'unverified conversation or result content')


def guard_mac_payload(stage, prompt):
    if ' Value examples: ' in prompt:
        raise RestrictedEvidenceEgress(stage, 'MIMIC-IV column-value samples')


class EvidenceRouter:
    """Retired inference path. Existing debug artifacts remain readable."""
    def __init__(self, *args, **kwargs):
        raise ModelMismatch()
