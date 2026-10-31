"""Seal NEW reviewed inputs separately from gold. Reject exposed/near-duplicate inputs."""
import argparse
from collections import Counter, defaultdict
from pathlib import Path
import re
import sqlite3
from validation_common import ROOT, DB, BASELINE, load, dump, freeze, sha, known_inputs, normalized, checked_name, verify_protocol


def validate_inputs(rows, old_rows, *, threshold=.85, minimum_clusters=30):
    if not isinstance(rows, list) or not rows:
        raise ValueError('Nonempty list of input records required')
    ids, clusters = set(), set()
    old_ids = {r['id'] for r in old_rows}
    old_texts = {normalized(r['question']) for r in old_rows}
    def masked(text):
        return normalized(re.sub(r'\b\d+(?:\.\d+)?\b', ' numeric_literal ', text))
    old_masked = {masked(r['question']) for r in old_rows}
    old_tokens = [set(normalized(r['question']).split()) for r in old_rows]
    postings = defaultdict(set)
    for i, tokens in enumerate(old_tokens):
        for word in tokens:
            postings[word].add(i)
    clean, new_texts = [], set()
    for row in rows:
        if any(not isinstance(row.get(k), str) or not row[k].strip() for k in ('id', 'question', 'cluster_id')):
            raise ValueError('Each input needs nonempty id, English question and reviewed cluster_id')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', row['id']):
            raise ValueError('Question ID must be a safe filename identifier')
        if row['id'] in ids or row['id'] in old_ids:
            raise ValueError('Duplicate/exposed question ID')
        question = normalized(row['question'])
        if not question or question in old_texts or question in new_texts:
            raise ValueError('Duplicate/exposed normalized question')
        if masked(row['question']) in old_masked:
            raise ValueError('Near-duplicate with numeric literals substituted; confirmation refused')
        terms = set(question.split())
        candidates = set().union(*(postings.get(t, set()) for t in terms))
        for i in candidates:
            other = old_tokens[i]
            if min(len(terms), len(other)) / max(len(terms), len(other)) < threshold:
                continue
            if len(terms & other) / len(terms | other) >= threshold:
                raise ValueError('Near-duplicate of previously exposed input; confirmation refused')
        ids.add(row['id'])
        new_texts.add(question)
        clusters.add(row['cluster_id'])
        # Gold, answerability flags and other annotation fields cannot enter inference.
        clean.append({k: row[k] for k in ('id', 'question', 'cluster_id')})
    if len(clusters) < minimum_clusters:
        raise ValueError(f'At least {minimum_clusters} reviewed clusters required; not a power guarantee')
    return clean


def validate_provenance(provenance):
    for key in ('source', 'version', 'independence_statement', 'annotation_evidence', 'cluster_evidence'):
        if not isinstance(provenance.get(key), str) or not provenance[key].strip():
            raise ValueError(f'Dataset provenance needs {key}')
    if provenance.get('not_used_for_method_design') is not True:
        raise ValueError('Independent-from-method-design attestation is required')
    if provenance.get('English_questions') is not True:
        raise ValueError('English input contract required')
    if provenance.get('annotation_validation') not in {'official_release', 'documented_human_review'}:
        raise ValueError('Gold SQL AND unanswerable labels need official provenance or documented review')
    if provenance.get('cluster_ids_reviewed') is not True:
        raise ValueError('Template/family clusters must be reviewed; unique IDs are not clusters')


def register(name, inputs_path, gold_path, provenance_path, db_path=DB):
    protocol = verify_protocol()
    if sha(db_path) != sha(DB):
        raise ValueError('Frozen V5 supports only its pinned MIMIC-IV schema/database; cross-database adapter is not registered')
    provenance = load(provenance_path)
    validate_provenance(provenance)
    rules = protocol['dataset_eligibility']
    inputs = validate_inputs(load(inputs_path), known_inputs(), threshold=rules['near_duplicate_threshold'],
                             minimum_clusters=rules['minimum_clusters'])
    labels = load(gold_path)
    if not isinstance(labels, dict) or set(labels) != {r['id'] for r in inputs}:
        raise ValueError('Gold SQL must cover every input exactly')
    if any(not isinstance(sql, str) or not sql.strip() for sql in labels.values()):
        raise ValueError('Every gold label must be an explicit SQL string or exactly null')
    answerable = sum(sql != 'null' for sql in labels.values())
    if not 0 < answerable < len(inputs):
        raise ValueError('Reliability confirmation requires both answerable and unanswerable questions')
    import sys
    sys.path.insert(1, str(BASELINE))
    from baseline_core import execute_readonly
    # Gold is executed only in intake/scoring, never provided to generation.
    answers = {key: 'null' if sql == 'null' else execute_readonly(sql, DB, 30) for key, sql in labels.items()}
    target = ROOT / 'datasets' / checked_name(name)
    target.mkdir(parents=True, exist_ok=True)
    freeze(target / 'inputs.json', inputs)
    freeze(target / 'gold_sql.json', labels)
    freeze(target / 'gold_answers.json', answers)
    freeze(target / 'provenance.json', provenance)
    manifest = {'name': name, 'state': 'eligible_for_locked_protocol_not_proof_of_independence',
                'protocol_sha256': sha(ROOT / 'protocol.json'), 'database_sha256': sha(DB),
                'questions': len(inputs), 'answerable': answerable, 'unanswerable': len(inputs)-answerable,
                'clusters': len({r['cluster_id'] for r in inputs}),
                'empty_gold_results': sum(v == [] for v in answers.values()),
                'files': {n: sha(target / n) for n in ('inputs.json', 'gold_sql.json', 'gold_answers.json', 'provenance.json')},
                'source_sha256': {'inputs': sha(inputs_path), 'gold': sha(gold_path), 'provenance': sha(provenance_path)},
                'independence_limits': 'Hashes and overlap checks cannot certify provenance, paraphrase independence or model pretraining exposure.'}
    freeze(target / 'manifest.json', manifest)
    print(f'Registered {len(inputs)} inputs, {manifest["clusters"]} clusters; no API calls')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--name', required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--gold', type=Path, required=True)
    parser.add_argument('--provenance', type=Path, required=True)
    parser.add_argument('--database', type=Path, default=DB)
    args = parser.parse_args()
    register(args.name, args.inputs, args.gold, args.provenance, args.database)
