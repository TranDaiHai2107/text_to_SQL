"""Project commands. Run `python run.py --help` from any working directory."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
MODULES = {
    "clinsql-inspect": "ehrqa.cli.clinsql",
    "bigquery-preflight": "ehrqa.cli.bigquery_preflight",
    "bigquery-sql-smoke": "ehrqa.cli.bigquery_sql_smoke",
    "bigquery-approved-smoke": "ehrqa.cli.bigquery_approved_smoke",
    "phase-a-retention": "ehrqa.cli.phase_a_retention",
    "phase-c1-pilot": "ehrqa.cli.phase_c1_pilot",
    "four-method-pilot": "ehrqa.cli.four_method_pilot",
    "openai-access-probe": "ehrqa.cli.openai_access_probe",
    "clinsql-rubric": "ehrqa.cli.clinsql_rubric",
}

RESEARCH_ENV_KEYS = frozenset({
    'OPENAI_API_KEY', 'OPENAI_MODEL', 'OPENAI_REASONING_EFFORT',
    'BQ_PROJECT_ID', 'BQ_HOSP_DATASET', 'BQ_ICU_DATASET',
    'BQ_LOCATION', 'BQ_BILLING_PROJECT', 'SEND_RESULTS_TO_LLM',
})


def load_research_env(path: Path, env: dict[str, str]) -> None:
    """Load only research settings; process environment retains precedence."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name, value = line.split('=', 1)
        name = name.strip()
        if name in RESEARCH_ENV_KEYS and name not in env:
            env[name] = value.strip().strip('"').strip("'")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["test", *MODULES])
    args = parser.parse_args(sys.argv[1:2])
    extra = sys.argv[2:]
    env = os.environ.copy()
    if args.command != 'test':
        load_research_env(ROOT / '.env', env)
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), str(ROOT), env.get("PYTHONPATH", "")])
    if args.command == "test":
        command = ["-m", "pytest", "tests"]
    else:
        command = ["-m", MODULES[args.command]]
    return subprocess.call([sys.executable, *command, *extra], cwd=ROOT, env=env)


if __name__ == "__main__":
    sys.exit(main())
