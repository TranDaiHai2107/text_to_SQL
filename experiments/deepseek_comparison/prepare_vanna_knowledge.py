"""Reuse validated train vectors, then embed only additional dev documents."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
VANNA=ROOT.parent/'vanna_ehrsql'
sys.path.insert(0,str(VANNA))
from benchmark import corpus,schema,signature,dump
from vanna_adapter import make_vanna,training_documents,prepare_index


def main():
    import chromadb
    old_path=VANNA/'indexes/chroma'
    new_path=VANNA/'indexes/chroma_train_dev'
    old_manifest=json.loads((old_path/'manifest.json').read_text())
    if old_manifest['source'] != signature(('train',)):
        raise ValueError('Old train index does not match the current pinned sources/embedding')
    vn=make_vanna(new_path)
    original=chromadb.PersistentClient(path=str(old_path))
    expected=training_documents(corpus(('train','dev')),schema())
    reused={}
    for kind,documents in expected.items():
        source=original.get_collection(kind,embedding_function=vn.embedding_function).get(include=['documents','embeddings'])
        target=getattr(vn,kind+'_collection')
        present=set(target.get(include=[])['ids'])
        positions=[]
        for i,key in enumerate(source['ids']):
            if key not in documents or documents[key] != source['documents'][i]:
                raise ValueError('Cannot reuse a vector whose document/ID differs')
            if key not in present:
                positions.append(i)
        for start in range(0,len(positions),128):
            batch=positions[start:start+128]
            target.add(ids=[source['ids'][i] for i in batch],documents=[source['documents'][i] for i in batch],
                       embeddings=[source['embeddings'][i] for i in batch])
        reused[kind]=len(positions)
        print(f'Reused {len(positions)} existing train vectors for {kind}',flush=True)
    dump(new_path/'VECTOR_REUSE.json',{'source':old_manifest['source'],'new_vectors_copied':reused,
                                     'document_ids_and_content_verified':True,'model_api_calls':0})
    print(json.dumps(prepare_index(vn,new_path,('train','dev')),indent=2))


if __name__=='__main__':
    main()
