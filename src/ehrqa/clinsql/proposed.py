"""BigQuery/English configuration for the existing full-agentic pipeline."""
from __future__ import annotations

from ehrqa.agentic.pipeline import Config, FullAgentic
from ehrqa.agentic.retrieval import SequentialRAG
from ehrqa.agentic.schema import Schema
from ehrqa.agentic.database import QueryResult


class PipelineDatabase:
    def __init__(self, adapter):
        self.adapter = adapter
        self.schema = Schema.from_records(adapter.schema_metadata(), dialect='bigquery')

    def execute(self, sql, question=''):
        inspection = self.schema.inspect(sql, question)
        if not inspection['valid']:
            raise ValueError('; '.join(inspection['errors']))
        result = self.adapter.execute(sql)
        return QueryResult(list(result.columns), list(result.rows), result.complete)

    def catalog_search(self, question, tables, limit=24):
        return []  # No patient data or clinical values sent to the LLM before policy approval.


def build_pipeline(adapter, model, *, log_dir=None):
    db = PipelineDatabase(adapter)
    def examples(_question):
        return {'items': [], 'found': False, 'few_shot_count': 3, 'source': 'no_test_knowledge'}
    return FullAgentic(db, SequentialRAG(db, examples), model, Config(profile='clinsql', log_dir=log_dir))
