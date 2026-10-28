"""Prepare/index Vanna locally; never initialize an LLM client."""
import argparse
import json
from benchmark import ROOT, VERSION, EMBEDDING, DOCUMENTATION, corpus, schema, signature, dump


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-index', action='store_true')
    args = parser.parse_args()
    rows, schemas = corpus(), schema()
    dump(ROOT/'prepared/train_pairs.json', rows)
    dump(ROOT/'prepared/schema.json', schemas)
    (ROOT/'prepared/documentation.txt').write_text(DOCUMENTATION, encoding='utf-8')
    report = {'vanna_version':VERSION, 'pipeline':'vanna.legacy.generate_sql + ChromaDB',
              'source':signature(), 'train_pairs':len(rows), 'schema_tables':len(schemas),
              'train_null_examples':sum(r['sql']=='null' for r in rows),
              'embedding_model':EMBEDDING, 'api_calls':0, 'fine_tuning':False,
              'index_built':False}
    if args.build_index:
        from vanna_adapter import make_vanna, prepare_index
        vn = make_vanna(ROOT/'indexes/chroma')
        report['index'] = prepare_index(vn, ROOT/'indexes/chroma')
        report['index_built'] = True
    dump(ROOT/'PREPARATION_STATUS.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
