"""Download the authors' released OmniSQL predictions for evaluator audit."""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import zipfile

import requests

FILE_ID = "1Mj6uNQxg-eghNK3-u7Zr0Z7iVuQKSgmz"
DEST = Path(__file__).resolve().parents[2] / "data" / "benchmarks" / "bird" / "OmniSQL_eval_results.zip"


class FormInputs(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "input":
            item = dict(attrs)
            if item.get("name") and item.get("value"):
                self.fields[item["name"]] = item["value"]


def main() -> None:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    with requests.Session() as session:
        warning = session.get("https://drive.google.com/uc", params={"export": "download", "id": FILE_ID}, timeout=30)
        warning.raise_for_status()
        form = FormInputs()
        form.feed(warning.text)
        if form.fields.get("id") != FILE_ID or form.fields.get("confirm") != "t":
            raise ValueError("Unexpected Google Drive confirmation form")
        with session.get("https://drive.usercontent.google.com/download", params=form.fields,
                         timeout=120, stream=True) as response:
            response.raise_for_status()
            if "html" in response.headers.get("Content-Type", ""):
                raise ValueError("Google Drive returned HTML, not predictions ZIP")
            with DEST.open("wb") as target:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        target.write(chunk)
    with DEST.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    with zipfile.ZipFile(DEST) as archive:
        names = archive.namelist()
        bad = archive.testzip()
    if bad:
        raise ValueError(f"Corrupt ZIP member: {bad}")
    summary = {"source": f"https://drive.google.com/file/d/{FILE_ID}/view",
               "bytes": DEST.stat().st_size, "sha256": digest, "entries": len(names),
               "bird_entries": [name for name in names if "bird" in name.lower()][:30]}
    DEST.with_name("omnisql_predictions_manifest.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
