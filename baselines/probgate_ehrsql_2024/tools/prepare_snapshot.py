"""Materialize pinned public sources and matching data; never execute models/SQL.

The resulting experiment folder is independent of the application's modules.
This preparation reads the already-downloaded repositories only.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
SOURCES = WORKSPACE / "research/sources"
AUTHOR_REV = "2dcc2230ea049e7fb87160df922933b4ae2645b9"
DATA_REF = "5ddaaa7"


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != data:
        raise RuntimeError(f"Refusing to replace changed file: {path}")
    path.write_bytes(data)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main():
    author = SOURCES / "probgate-ehrsql"
    ehr = SOURCES / "ehrsql-2024"
    assert git(author, "rev-parse", "HEAD").decode().strip() == AUTHOR_REV
    data_rev = git(ehr, "rev-parse", DATA_REF).decode().strip()
    tracked = git(author, "ls-tree", "-r", "--name-only", AUTHOR_REV).decode().splitlines()
    manifest = {"author_url": "https://github.com/venzino-han/probgate_ehrsql",
        "author_commit": AUTHOR_REV, "ehrsql_url": "https://github.com/glee4810/ehrsql-2024",
        "annotation_commit": data_rev, "files": {}, "splits": {},
        "model_execution_performed": False, "sql_evaluation_performed": False}
    for relative in tracked:
        name = PurePosixPath(relative)
        if name.is_absolute() or ".." in name.parts:
            raise ValueError(relative)
        content = git(author, "show", AUTHOR_REV + ":" + relative)
        target = ROOT / "upstream" / Path(*name.parts)
        write_bytes(target, content)
        manifest["files"]["upstream/" + relative] = sha(content)

    # Preserve the author's question files, schema and database without rewriting.
    original = ROOT / "upstream/src/data/mimic_iv"
    manifest["database_path"] = "upstream/src/data/mimic_iv/mimic_iv.sqlite"
    manifest["cached_test_predictions"] = "upstream/src/log_probability_final_test.json"
    for split, public_name in (("train", "train"), ("valid", "dev"), ("test", "test")):
        questions = (original / split / "data.json").read_bytes()
        q = json.loads(questions)
        reference = json.loads(git(ehr, "show", f"{data_rev}:data/mimic_iv/{split}/data.json"))
        assert {r["id"]: r["question"] for r in q["data"]} == {r["id"]: r["question"] for r in reference["data"]}
        write_bytes(ROOT / "data/inputs" / (public_name + ".json"), questions)
        labels = git(ehr, "show", f"{data_rev}:data/mimic_iv/{split}/label.json")
        answers = git(ehr, "show", f"{data_rev}:data/mimic_iv/{split}/answer.json")
        write_bytes(ROOT / "data/gold" / public_name / "label.json", labels)
        write_bytes(ROOT / "data/gold" / public_name / "answer.json", answers)
        ids = {r["id"] for r in q["data"]}
        assert ids == set(json.loads(labels)) == set(json.loads(answers))
        source_labels = original / split / "label.json"
        if source_labels.is_file():
            assert json.loads(labels) == json.loads(source_labels.read_bytes())
        manifest["splits"][public_name] = {"version": q["version"], "count": len(ids),
            "unanswerable": sum(v == "null" for v in json.loads(labels).values())}

    # AST reads configuration only; notebook cells and pickle are never executed.
    notebook = json.loads((ROOT / "upstream/src/filter_log_probability.ipynb").read_bytes())
    reserved = None
    for cell in notebook["cells"]:
        if cell["cell_type"] != "code":
            continue
        try:
            tree = ast.parse("".join(cell["source"]))
        except SyntaxError:
            continue
        for statement in tree.body:
            if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "reserved" for t in statement.targets):
                reserved = ast.literal_eval(statement.value)
    assert isinstance(reserved, list) and "SELECT" in reserved
    write_bytes(ROOT / "configs/reserved_words.json", json_bytes(reserved))
    for path in sorted((ROOT / "data").rglob("*")):
        if path.is_file():
            manifest["files"][path.relative_to(ROOT).as_posix()] = sha(path.read_bytes())
    manifest["files"]["configs/reserved_words.json"] = sha((ROOT / "configs/reserved_words.json").read_bytes())
    write_bytes(ROOT / "source_manifest.json", json_bytes(manifest))
    print(json.dumps({"prepared": True, "author_files": len(tracked), "splits": manifest["splits"],
        "model_execution_performed": False, "sql_evaluation_performed": False}, indent=2))


if __name__ == "__main__":
    main()
