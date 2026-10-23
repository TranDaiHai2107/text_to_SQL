"""Port of the application's three Chroma retrieval layers to the pinned EHRSQL schema.

Only train Q/SQL labels enter the example index. Dictionary metadata comes from
the benchmark DB, without patient rows. No dev/test labels are read here.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from contextlib import closing

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
from settings import ROOT, BASELINE, DB, EMBEDDING_MODEL

DESCRIPTIONS = {
    "patients": "Patient demographics, sex, date of birth, date of death",
    "admissions": "Hospital admissions, admission discharge time, age, insurance, admission location",
    "diagnoses_icd": "Patient diagnoses, disease ICD code, diagnosis charttime",
    "procedures_icd": "Patient procedures, surgery ICD code, procedure charttime",
    "d_icd_diagnoses": "Dictionary of diagnosis ICD codes and disease names",
    "d_icd_procedures": "Dictionary of procedure ICD codes and surgery names",
    "d_labitems": "Dictionary of laboratory test names and item IDs",
    "d_items": "Dictionary of vital signs ICU input output item IDs and names",
    "labevents": "Laboratory blood tests, measurement values, units, time",
    "chartevents": "ICU vital signs, heart respiratory rate, blood pressure, temperature, weight",
    "inputevents": "ICU administered inputs, fluids and medications amount",
    "outputevents": "ICU output measurements, urine and drainage volumes",
    "microbiologyevents": "Microbiology cultures, specimens, organisms, test names and charttime",
    "prescriptions": "Prescribed drug names, dosage, units, route and start stop time",
    "icustays": "ICU visits, care unit, ICU admission discharge time and stay ID",
    "transfers": "Hospital care unit transfers and entry exit times",
    "cost": "Hospital costs for diagnosis procedure laboratory prescription events, charge time",
}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def signature():
    h = hashlib.sha256(EMBEDDING_MODEL.encode())
    for path in [DB, BASELINE / "data/inputs/train.json", BASELINE / "data/gold/train/label.json"]:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024*1024), b""):
                h.update(chunk)
    h.update(json.dumps(DESCRIPTIONS, sort_keys=True).encode())
    return h.hexdigest()


def schema_metadata(db=DB):
    with closing(sqlite3.connect(Path(db).resolve().as_uri()+"?mode=ro", uri=True)) as con:
        schema = {name: re.sub(r"\s+", " ", ddl).strip() for name, ddl in con.execute(
            "SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name")}
        neighbors = {name: set() for name in schema}
        for table in schema:
            for row in con.execute(f'PRAGMA foreign_key_list("{table}")'):
                neighbors[table].add(row[2])
                neighbors[row[2]].add(table)
    return schema, {k: sorted(v) for k, v in neighbors.items()}


def dictionary_records():
    records = []
    with closing(sqlite3.connect(DB.resolve().as_uri()+"?mode=ro", uri=True)) as con:
        for dictionary, facts, kind in [("d_icd_diagnoses", "diagnoses_icd", "diagnosis"),
                                         ("d_icd_procedures", "procedures_icd", "procedure")]:
            rows = con.execute(f"SELECT d.icd_code,d.long_title,COUNT(*) FROM {dictionary} d "
                               f"JOIN {facts} f ON f.icd_code=d.icd_code GROUP BY d.icd_code,d.long_title ORDER BY d.icd_code")
            for code, title, count in rows:
                records.append({"id": f"{dictionary}:{code}", "document": f"{kind}: {title}. ICD code {code}",
                                "source": dictionary, "code": code, "label": title, "frequency": count})
        for table in ("d_items", "d_labitems"):
            for code, label in con.execute(f"SELECT itemid,label FROM {table} WHERE label IS NOT NULL ORDER BY itemid"):
                records.append({"id": f"{table}:{code}", "document": f"{'ICU measurement' if table=='d_items' else 'laboratory test'}: {label}",
                                "source": table, "code": str(code), "label": label, "frequency": 0})
        for (drug,) in con.execute("SELECT DISTINCT drug FROM prescriptions ORDER BY drug"):
            records.append({"id": "drug:"+drug, "document": "Prescription drug: "+drug,
                            "source": "prescriptions", "code": drug, "label": drug, "frequency": 0})
    return records


class ThreeRAG:
    def __init__(self):
        import chromadb
        import torch
        from sentence_transformers import SentenceTransformer
        torch.set_num_threads(min(4, os.cpu_count() or 1))
        self.model = SentenceTransformer(EMBEDDING_MODEL, device="cpu", local_files_only=True)
        self.client = chromadb.PersistentClient(path=str(ROOT / "indexes/chroma"))
        self.schema, self.neighbors = schema_metadata()
        self.source_signature = signature()
        self.collections = {}
        self.query_cache = {}

    def build(self):
        questions = load(BASELINE / "data/inputs/train.json")["data"]
        labels = load(BASELINE / "data/gold/train/label.json")
        for split in ("dev", "test"):
            other = {row["id"] for row in load(BASELINE / "data/inputs" / (split+".json"))["data"]}
            if other & {row["id"] for row in questions}:
                raise ValueError("Train/evaluation IDs overlap")
        examples = [{"id": r["id"], "document": r["question"], "source": "EHRSQL_train",
                     "question": r["question"], "sql": labels[r["id"]]} for r in questions]
        schemas = [{"id": table, "document": DESCRIPTIONS.get(table, table)+"\n"+ddl,
                    "source": "sqlite_schema", "table": table} for table, ddl in self.schema.items()]
        collections = {"medical_dictionary": dictionary_records(), "schema_dictionary": schemas,
                       "sql_examples_train": examples}
        counts = {}
        for name, records in collections.items():
            collection = self.client.get_or_create_collection(name,
                metadata={"source_signature": self.source_signature, "embedding_model": EMBEDDING_MODEL,
                          "hnsw:space": "cosine", "expected_count": len(records)})
            if collection.metadata.get("source_signature") != self.source_signature:
                raise ValueError(f"Index {name} is stale; use a new index directory")
            present = set(collection.get(include=[])["ids"])
            if not present <= {r["id"] for r in records}:
                raise ValueError("Unexpected IDs in retrieval index")
            missing = [r for r in records if r["id"] not in present]
            for start in range(0, len(missing), 128):
                batch = missing[start:start+128]
                vectors = self.model.encode([r["document"] for r in batch], batch_size=32,
                                            normalize_embeddings=True, show_progress_bar=False).tolist()
                collection.add(ids=[r["id"] for r in batch], documents=[r["document"] for r in batch],
                               embeddings=vectors,
                               metadatas=[{k:v for k,v in r.items() if k not in {"id", "document"}} for r in batch])
                print(f"Index {name}: {collection.count()}/{len(records)}", flush=True)
            if collection.count() != len(records):
                raise ValueError("Incomplete retrieval collection")
            self.collections[name] = collection
            counts[name] = len(records)
        report = {"source_signature": self.source_signature, "embedding_model": EMBEDDING_MODEL,
                  "counts": counts, "examples_split": "train_only", "gold_test_read": False,
                  "dictionary_policy": "observed diagnosis/procedure codes, item dictionaries and drug names; no patient rows"}
        (ROOT / "indexes").mkdir(exist_ok=True)
        (ROOT / "indexes/manifest.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
        return report

    def retrieve(self, question, mode="full"):
        if mode not in {"base", "icd", "schema", "examples", "full"}:
            raise ValueError("Unknown retrieval mode")
        ctx = {"medical": [], "tables": sorted(self.schema), "examples": []}
        if mode == "base":
            return ctx
        if question not in self.query_cache:
            self.query_cache[question] = self.model.encode([question], normalize_embeddings=True, show_progress_bar=False).tolist()
        query = self.query_cache[question]
        def search(name, count, where=None):
            result = self.collections[name].query(query_embeddings=query, n_results=count,
                                                  include=["metadatas", "distances"], **({"where":where} if where else {}))
            return [{"id": key, **meta, "distance": distance} for key, meta, distance in zip(
                result["ids"][0], result["metadatas"][0], result["distances"][0])]
        if mode in {"icd", "full"}:
            ctx["medical"] = search("medical_dictionary", 5)
            # Preserve the application's explicit disease lookup behavior:
            # generic lab/item matches must not crowd out a diagnosis/procedure.
            for pattern, source in [(r"diagnos|disease|suffer", "d_icd_diagnoses"),
                                    (r"procedure|surg|operation", "d_icd_procedures")]:
                if re.search(pattern, question, re.I):
                    extra = search("medical_dictionary", 3, {"source":source})
                    seen = {r["id"] for r in ctx["medical"]}
                    ctx["medical"].extend(r for r in extra if r["id"] not in seen)
        if mode in {"schema", "full"}:
            found = {r["table"] for r in search("schema_dictionary", 4)}
            # Same core/one-hop expansion pattern as rag_engine.retrieve_schema.
            selected = found | {"patients", "admissions"}
            for table in found:
                selected.update(self.neighbors[table])
            ctx["tables"] = sorted(selected)
        if mode in {"examples", "full"}:
            ctx["examples"] = search("sql_examples_train", 4)
        return ctx

