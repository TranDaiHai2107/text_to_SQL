"""Restore ignored historical CLIN-SQL/SDE-SQL checkouts at locked commits."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
LOCK = Path(__file__).with_name("PAPER_SOURCE_LOCK.json")


def main() -> None:
    specs = json.loads(LOCK.read_text(encoding="utf-8"))
    for name, spec in specs.items():
        target = (ROOT / spec["path"]).resolve()
        if not target.is_relative_to(ROOT) or not target.is_relative_to(LOCK.parent):
            raise ValueError(f"Unsafe restore path for {name}: {target}")
        if not target.exists():
            subprocess.run(["git", "clone", spec["origin"], str(target)], check=True)
            subprocess.run(["git", "-C", str(target), "checkout", "--detach", spec["commit"]], check=True)
        head = subprocess.check_output(["git", "-C", str(target), "rev-parse", "HEAD"], text=True).strip()
        if head != spec["commit"]:
            raise ValueError(f"{name}: restored commit mismatch: {head}")
        print(f"{name}: {head}")


if __name__ == "__main__":
    main()
