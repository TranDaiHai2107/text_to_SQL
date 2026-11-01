"""Validate packaged artifacts and tests offline; never evaluate a model on gold."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

try:
    from .common_io import HERE, WORKSPACE, dump, jsonl, load, sha, verify_frozen
    from .english_metrics import score_records
    from .reference_renderer import render_answer
except ImportError:
    from common_io import HERE, WORKSPACE, dump, jsonl, load, sha, verify_frozen
    from english_metrics import score_records
    from reference_renderer import render_answer


def main():
    manifest = load(HERE / "data/MANIFEST.json")
    audit = load(HERE / "REFERENCE_AUDIT.json")
    source_audit = load(HERE / "SOURCE_AUDIT.json")
    if audit["status"] != "passed" or audit["error_count"] or source_audit["status"] != "passed":
        raise ValueError("Corpus/source audits must pass first")
    if audit["reference_manifest_sha256"] != sha(HERE / "data/MANIFEST.json"):
        raise ValueError("References were changed after independent audit")
    for filename, expected in manifest["implementation_sha256"].items():
        if sha(HERE / filename) != expected:
            raise ValueError("Builder changed after reference generation")
    for split, record in manifest["splits"].items():
        for folder, ext, key in (("references", "jsonl", "reference_sha256"), ("references", "csv", "csv_sha256"),
                                 ("inputs", "jsonl", "input_sha256"), ("sql_to_text_inputs", "jsonl", "sql_to_text_input_sha256")):
            if sha(HERE / "data" / folder / f"{split}.{ext}") != record[key]:
                raise ValueError("Dataset file changed after annotation: " + split + "/" + folder)
    temporary_parent = HERE / ".test_tmp"
    temporary_parent.mkdir(exist_ok=True)
    temporary = temporary_parent / str(uuid.uuid4())
    # Pytest may clean its basetemp. A new UUID strictly under this workspace is
    # deliberately used so no pre-existing data is ever targeted for cleanup.
    if not temporary.resolve().is_relative_to(HERE.resolve()) or temporary.exists():
        raise ValueError("Unsafe test temporary path")
    junit = HERE / "results/TEST_RESULTS.xml"
    completed = subprocess.run([sys.executable, "-m", "pytest", str(HERE / "tests"), "-q",
                                "--basetemp", str(temporary), "--junitxml", str(junit)],
                               cwd=WORKSPACE, text=True, capture_output=True)
    print(completed.stdout)
    if completed.returncode:
        print(completed.stderr)
        raise RuntimeError("New evaluator tests failed")
    suites = list(ET.parse(junit).getroot().iter("testsuite"))
    tests = {key: sum(int(s.attrib.get(key, 0)) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
    if tests["failures"] or tests["errors"]:
        raise ValueError("Test failure in JUnit report")
    checks = {"kind": "scorer_integration_self_check_NOT_model_performance", "splits": {}}
    for split in manifest["splits"]:
        refs = jsonl(HERE / "data/references" / f"{split}.jsonl")
        # Oracle inputs are deliberately named as a SELF-CHECK. These numbers
        # must never be presented as a model's generation performance.
        oracle = score_records(refs, {r["id"]: r["output_text"] for r in refs})
        if oracle["n"] != len(refs) or oracle["controlled"]["fact_EM"] != 100 or oracle["lexical"]["WER"] != 0:
            raise ValueError("Full-corpus scorer integration failure: " + split)
        checks["splits"][split] = {k: oracle[k] for k in ("n", "lexical", "controlled")}
    example = jsonl(HERE / "data/references/test.jsonl")[0]
    mutated = score_records([example], {example["id"]: render_answer([["deliberately incorrect organism"]])})
    if mutated["controlled"]["fact_EM"] != 0 or mutated["lexical"]["WER"] <= 0:
        raise ValueError("Known incorrect entity was accepted")
    checks["known_incorrect_entity_rejected"] = True
    dump(HERE / "results/SCORER_SELF_CHECK.json", checks)
    report = {"date": "2026-11-01", "status": "passed", "new_model_API_calls": 0,
              "new_SQL_to_text_model_performance_claimed": False,
              "original_frozen_files_verified": verify_frozen(),
              "questions_annotated": sum(r["n"] for r in manifest["splits"].values()),
              "source_audit": source_audit["status"], "independent_reference_audit": audit["status"],
              "unit_tests": tests,
              "artifact_sha256": {str(p.relative_to(HERE)): sha(p) for p in [
                  HERE / "data/MANIFEST.json", HERE / "SOURCE_AUDIT.json", HERE / "REFERENCE_AUDIT.json",
                  HERE / "english_metrics.py", HERE / "reference_renderer.py", HERE / "answer_from_sql.py",
                  HERE / "results/TEXT_TO_SQL_COMPARISON.json", HERE / "results/SCORER_SELF_CHECK.json", junit]},
              "annotation_status": "automatically_generated_and_mechanically_audited_not_human_validated"}
    dump(HERE / "results/DELIVERY_VALIDATION.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    main()
