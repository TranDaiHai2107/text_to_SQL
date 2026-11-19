"""Download the dated BIRD dev release used by OmniSQL, with byte-range resume."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import requests

URL = "https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip"
ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "data" / "benchmarks" / "bird" / "dev.zip"
CHUNK = 8 * 1024 * 1024


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args()
    DEST.parent.mkdir(parents=True, exist_ok=True)
    with requests.Session() as session:
        head = session.head(URL, timeout=30)
        head.raise_for_status()
        total = int(head.headers["Content-Length"])
        current = DEST.stat().st_size if DEST.exists() else 0
        if current > total:
            raise ValueError(f"Existing archive larger than source: {current} > {total}")
        with DEST.open("ab") as output:
            while current < total:
                end = min(current + CHUNK, total) - 1
                for attempt in range(5):
                    try:
                        response = session.get(URL, headers={"Range": f"bytes={current}-{end}"}, timeout=60)
                        response.raise_for_status()
                        if response.status_code != 206 or len(response.content) != end - current + 1:
                            raise ValueError(f"Unexpected range response: {response.status_code}, {len(response.content)}")
                        output.write(response.content)
                        output.flush()
                        current = end + 1
                        print(f"{current}/{total}", flush=True)
                        break
                    except (requests.RequestException, ValueError):
                        if attempt == 4:
                            raise
                        time.sleep(2 ** attempt)
        with DEST.open("rb") as downloaded:
            digest = hashlib.file_digest(downloaded, "sha256").hexdigest()
        manifest = {"source_url": URL, "bytes": total, "sha256": digest, "release": "dev_20240627"}
        (DEST.parent / "download_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(manifest, indent=2))
    if not args.download_only:
        import zipfile
        with zipfile.ZipFile(DEST) as archive:
            names = archive.namelist()
            target = DEST.parent.resolve()
            if not all((target / name).resolve().is_relative_to(target) for name in names):
                raise ValueError("Unsafe ZIP path")
            archive.extractall(target)
        nested = target / "dev_20240627" / "dev_databases.zip"
        with zipfile.ZipFile(nested) as databases:
            database_names = databases.namelist()
            if not all((nested.parent / name).resolve().is_relative_to(nested.parent) for name in database_names):
                raise ValueError("Unsafe database ZIP path")
            databases.extractall(nested.parent)
        print(f"Extracted {len(names)} outer and {len(database_names)} database entries")


if __name__ == "__main__":
    main()
