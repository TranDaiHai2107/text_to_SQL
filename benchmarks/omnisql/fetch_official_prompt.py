"""Extract only OmniSQL's preprocessed BIRD prompt from its 22 GB ZIP.

The upstream dataset is one large ZIP; HTTP range requests avoid downloading it all.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

import requests

DATASET_REVISION = "e1db8bb10ef11f92eacd8d87801d716ba0e9e9be"
URL = f"https://huggingface.co/datasets/seeklhy/OmniSQL-datasets/resolve/{DATASET_REVISION}/data.zip"
ROOT = Path(__file__).resolve().parents[2]
BLOCK = 2 * 1024 * 1024


class RangeFile(io.RawIOBase):
    def __init__(self) -> None:
        self.session = requests.Session()
        response = self.session.get(URL, headers={"Range": "bytes=0-0"}, timeout=60)
        response.raise_for_status()
        if response.status_code != 206:
            raise RuntimeError("Dataset server does not support HTTP ranges")
        self.url = response.url
        self.size = int(response.headers["Content-Range"].split("/")[-1])
        self.position = 0
        self.cached_start = -1
        self.cached = b""

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = 0) -> int:
        self.position = (self.size + offset if whence == 2 else self.position + offset if whence == 1 else offset)
        if self.position < 0:
            raise ValueError("Negative position")
        return self.position

    def read(self, count: int = -1) -> bytes:
        if count < 0:
            count = self.size - self.position
        count = min(count, self.size - self.position)
        chunks = []
        while count:
            start = self.position // BLOCK * BLOCK
            if self.cached_start != start:
                end = min(start + BLOCK, self.size) - 1
                response = self.session.get(self.url, headers={"Range": f"bytes={start}-{end}"}, timeout=90)
                response.raise_for_status()
                if response.status_code != 206 or len(response.content) != end - start + 1:
                    raise RuntimeError(f"Unexpected range response at {start}: {response.status_code}")
                self.cached_start, self.cached = start, response.content
            within = self.position - start
            part = self.cached[within:within + count]
            if not part:
                raise EOFError("Empty HTTP range")
            chunks.append(part)
            self.position += len(part)
            count -= len(part)
        return b"".join(chunks)

    def close(self) -> None:
        self.session.close()
        super().close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    with RangeFile() as remote, zipfile.ZipFile(remote) as archive:
        matches = [info for info in archive.infolist() if re.search(r"(^|/)dev_bird\.json$", info.filename)]
        if args.list:
            print(json.dumps({"zip_bytes": remote.size, "matches": [{"path": x.filename, "bytes": x.file_size} for x in matches]}, indent=2))
            return
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one dev_bird.json; found {len(matches)}")
        target = ROOT / "data" / "benchmarks" / "bird" / "omnisql_dev_bird.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        with archive.open(matches[0]) as source, target.open("wb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
        count = len(json.loads(target.read_text(encoding="utf-8")))
        if count != 1534:
            raise ValueError(f"Expected 1534 processed prompts; found {count}")
        manifest = {"source_url": URL, "zip_bytes": remote.size, "member": matches[0].filename,
                    "bytes": target.stat().st_size, "sha256": digest.hexdigest(), "questions": count}
        (target.parent / "omnisql_prompt_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
