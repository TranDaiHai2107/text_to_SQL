"""Project commands. Run `python run.py --help` from any working directory."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
MODULES = {
    "build-db": "ehrqa.cli.build_mimic_mini",
    "build-vectors": "ehrqa.cli.build_vector_db",
    "evaluate": "ehrqa.cli.evaluate",
    "expand-queries": "ehrqa.cli.expand_test_dataset",
    "test-rewrite": "ehrqa.cli.test_rewrite",
    "clinsql-inspect": "ehrqa.cli.clinsql",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["app", "test", *MODULES])
    args = parser.parse_args(sys.argv[1:2])
    extra = sys.argv[2:]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), str(ROOT), env.get("PYTHONPATH", "")])
    if args.command == "app":
        command = ["-m", "streamlit", "run", str(ROOT / "src/ehrqa/app.py")]
    elif args.command == "test":
        command = ["-m", "pytest", "tests"]
    else:
        command = ["-m", MODULES[args.command]]
    return subprocess.call([sys.executable, *command, *extra], cwd=ROOT, env=env)


if __name__ == "__main__":
    sys.exit(main())
