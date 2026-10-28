"""Vanna's shipped legacy SQL/RAG pipeline with transport/embedding adapters."""
from importlib.metadata import version
import json
import os
from pathlib import Path
import sys
from benchmark import ROOT, VERSION, EMBEDDING, DOCUMENTATION, corpus, schema, signature, dump


def runtime():
    vendor = ROOT/'.vendor'
    if not (vendor/'vanna').is_dir():
        raise RuntimeError('Install requirements-vendor.txt into .vendor first; no automatic downloads')
    sys.path.insert(0, str(vendor))
    if version('vanna') != VERSION:
        raise RuntimeError('Wrong Vanna distribution version')
    from vanna.legacy.chromadb import ChromaDB_VectorStore
    from vanna.legacy.utils import deterministic_uuid
    return ChromaDB_VectorStore, deterministic_uuid


def make_vanna(index_path, client=None, examples=4, embedding_function=None, vector_client=None):
    vector_class, _ = runtime()
    if embedding_function is None:
        # This model is already cached by the main application; no hosted
        # embedding API and no silent model download.
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['ANONYMIZED_TELEMETRY'] = 'False'
        import torch
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        embedding_function = SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING, device='cpu', normalize_embeddings=True)

    class VannaBenchmark(vector_class):
        def __init__(self):
            super().__init__(config={
                'path':str(index_path), 'embedding_function':embedding_function,
                'client':vector_client if vector_client is not None else 'persistent',
                'dialect':'SQLite', 'language':'English',
                'n_results_sql':examples, 'n_results_ddl':17, 'n_results_documentation':1,
            })
            self.transport = client
            self.question_id = None
            self.responses = []

        def system_message(self, message):
            return {'role':'system', 'content':message}

        def user_message(self, message):
            return {'role':'user', 'content':message}

        def assistant_message(self, message):
            return {'role':'assistant', 'content':message}

        def submit_prompt(self, prompt, **kwargs):
            if self.transport is None:
                raise RuntimeError('No LLM transport configured; preparation cannot call an API')
            response = self.transport.call(prompt, 'vanna_generate_sql', self.question_id,
                                           max_tokens=self.transport.sql_tokens)
            self.responses.append(response)
            return response['content']

        def get_sql_prompt(self, *args, **kwargs):
            messages = super().get_sql_prompt(*args, **kwargs)
            # Native guideline 3 asks for prose on unanswerable questions. Use
            # the benchmark's explicit abstention format, not a prose classifier.
            messages[0]['content'] += (
                '\n===EHRSQL output contract (takes precedence over response guideline 3)\n'
                'If the schema cannot answer the question, output exactly null instead of a prose explanation. '
                'Output one SQLite query or null. No intermediate database introspection is available.\n')
            return messages

        def log(self, message, title='Info'):
            # Native Vanna logs entire prompts. Keep benchmark console compact;
            # the transport retains responses, hashes and token accounting.
            pass

    return VannaBenchmark()


def training_documents(rows, schemas):
    """Identical serialization/IDs to native add_question_sql/add_ddl/add_documentation."""
    _, uuid = runtime()
    sql_docs = {}
    for row in rows:
        document = json.dumps({'question':row['question'], 'sql':row['sql']}, ensure_ascii=False)
        sql_docs[uuid(document)+'-sql'] = document
    return {
        'sql':sql_docs,
        'ddl':{uuid(ddl)+'-ddl':ddl for ddl in schemas.values()},
        'documentation':{uuid(DOCUMENTATION)+'-doc':DOCUMENTATION},
    }


def prepare_index(vn, index_path, knowledge_splits=('train',)):
    index_path = Path(index_path)
    expected = signature(knowledge_splits)
    manifest_path = index_path/'manifest.json'
    if manifest_path.exists() and json.loads(manifest_path.read_text())['source'] != expected:
        raise ValueError('Index sources changed; use a new index directory')
    rows = corpus(knowledge_splits)
    documents = training_documents(rows, schema())
    counts = {}
    for kind, records in documents.items():
        collection = getattr(vn, kind+'_collection')
        existing = collection.get(include=['documents'])
        present = dict(zip(existing['ids'], existing['documents']))
        if any(key not in records or records[key] != text for key,text in present.items()):
            raise ValueError('Index contains unknown or modified material')
        missing = [key for key in records if key not in present]
        # Batch only the native storage operation. Retrieval, prompt assembly,
        # SQL extraction and LLM invocation remain Vanna's own implementations.
        for start in range(0, len(missing), 128):
            ids = missing[start:start+128]
            texts = [records[key] for key in ids]
            vectors = vn.embedding_function(texts)
            collection.add(ids=ids, documents=texts, embeddings=vectors)
            print(f'Vanna index {kind}: {collection.count()}/{len(records)}', flush=True)
        counts[kind] = collection.count()
        if counts[kind] != len(records):
            raise ValueError('Incomplete Vanna index')
    manifest = {'source':expected, 'counts':counts, 'train_questions':sum(r['split']=='train' for r in rows),
                'knowledge_questions':len(rows), 'knowledge_splits':list(knowledge_splits),
                'training_is_fine_tuning':False, 'held_out_labels_read':False,
                'native_document_format':True, 'bulk_loading':True}
    dump(manifest_path, manifest)
    return manifest


def assert_index(vn, index_path, knowledge_splits=('train',)):
    manifest = json.loads((Path(index_path)/'manifest.json').read_text())
    if manifest['source'] != signature(knowledge_splits):
        raise ValueError('Index provenance mismatch; prepare it again in a new directory')
    for kind, count in manifest['counts'].items():
        if getattr(vn, kind+'_collection').count() != count:
            raise ValueError('Index changed since preparation')
    return manifest


def generate(vn, item):
    from bridge import shared
    sql_runtime = shared('sql_runtime')
    vn.question_id = item['id']
    vn.responses = []
    raw_sql = vn.generate_sql(question=item['question'], allow_llm_to_see_data=False)
    if len(vn.responses) != 1:
        raise RuntimeError('Expected exactly one Vanna model call; no intermediate data introspection')
    response = vn.responses[0]
    if response['finish_reason'] != 'stop':
        sql = ''
        execution = {'valid':False, 'abstained':False, 'empty':None,
                     'error':'model_generation_incomplete:'+str(response['finish_reason'])}
    else:
        sql = sql_runtime.clean_sql(raw_sql)
        execution = sql_runtime.outcome(sql)
    return {'id':item['id'], 'question':item['question'], 'variants':{'vanna':{
        'sql':sql, 'raw_vanna_output':raw_sql, 'execution':execution,
        'attempts':1, 'call_hashes':[response['request_hash']],
        'allow_llm_to_see_data':False, 'self_correction':False, 'gef_filtered':False,
    }}}
