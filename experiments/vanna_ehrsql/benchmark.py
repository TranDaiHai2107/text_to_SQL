"""Paths and input-only material for the independent Vanna benchmark."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
BASELINE = WORKSPACE/'baselines/probgate_ehrsql_2024'
OUR_SYSTEM = ROOT.parent/'apply_my_work_to_baseline'
DB = BASELINE/'upstream/src/data/mimic_iv/mimic_iv.sqlite'
VERSION = '2.0.2'
EMBEDDING = 'paraphrase-multilingual-MiniLM-L12-v2'
sys.path.insert(0, str(BASELINE))

# Benchmark semantics shared with the supplied task, not an error-driven prompt
# written from held-out SQL. This is context for Vanna, not the user's pipeline.
DOCUMENTATION = """EHRSQL uses a specialized MIMIC-IV SQLite database, not the full MIMIC-IV release.
The present time is fixed at 2100-12-31 23:59:00. Preserve IDs, dates, quantities and time constraints.
Use SQLite datetime/strftime/julianday, not PostgreSQL functions.
If the requested information is absent from the schema, return exactly null. Never invent columns or clinical facts.
A query that might return no rows is not by itself unanswerable.
Age is admissions.age. patients has dob/dod. ICD tables do not have icd_version.
For first/last hospital admission order by admittime; for ICU visits use icustays.intime.
For costs join cost.event_type and cost.event_id to the event row_id, not hadm_id alone.
Use d_items for ICU/chartevents/inputevents/outputevents and d_labitems for laboratory events.
Normal ranges: temperature 35.5..38.1, sao2 95..100, heart rate 60..100, respiration 12..18,
systolic bp 90..120, diastolic bp 60..90, mean bp 60..110. Abnormal means outside the range.
Return one SQLite SELECT/WITH query or exactly null, without explanations.
"""


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temporary.replace(path)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda:handle.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def run_path(name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', name):
        raise ValueError('Invalid run name')
    return ROOT/'runs'/name


def questions(split):
    if split not in {'train', 'dev', 'test'}:
        raise ValueError('Unknown split')
    return load(BASELINE/'data/inputs'/(split+'.json'))['data']


def schema():
    with closing(sqlite3.connect(DB.resolve().as_uri()+'?mode=ro', uri=True)) as con:
        return dict(con.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name"))


def corpus(knowledge_splits=('train',)):
    """Read selected knowledge labels only; the final test is always excluded."""
    if tuple(knowledge_splits) not in {('train',), ('train','dev')}:
        raise ValueError('Only train or train+dev may be used as knowledge')
    rows, ids = [], set()
    for source in knowledge_splits:
        source_rows = questions(source)
        labels = load(BASELINE/'data/gold'/source/'label.json')
        source_ids = {r['id'] for r in source_rows}
        if len(source_ids) != len(source_rows) or source_ids != set(labels) or ids & source_ids:
            raise ValueError('Knowledge IDs/labels do not align or overlap')
        ids.update(source_ids)
        rows.extend({'id':r['id'], 'question':r['question'], 'sql':labels[r['id']], 'split':source} for r in source_rows)
    for split in ({'dev','test'}-set(knowledge_splits)):
        if ids & {r['id'] for r in questions(split)}:
            raise ValueError('Knowledge/evaluation IDs overlap')
    return rows


def signature(knowledge_splits=('train',)):
    if tuple(knowledge_splits) not in {('train',), ('train','dev')}:
        raise ValueError('Invalid knowledge splits')
    result = {
        'vanna_version':VERSION, 'embedding_model':EMBEDDING,
        'database_sha256':sha(DB),
        'train_questions_sha256':sha(BASELINE/'data/inputs/train.json'),
        'train_labels_sha256':sha(BASELINE/'data/gold/train/label.json'),
        'documentation_sha256':hashlib.sha256(DOCUMENTATION.encode()).hexdigest(),
    }
    if tuple(knowledge_splits) != ('train',):
        result.update(knowledge_splits=list(knowledge_splits),
                      dev_questions_sha256=sha(BASELINE/'data/inputs/dev.json'),
                      dev_labels_sha256=sha(BASELINE/'data/gold/dev/label.json'))
    return result
