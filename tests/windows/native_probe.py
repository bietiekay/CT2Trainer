"""Run the independent implementation's controlled Windows fixture gate."""
import argparse
import json
from pathlib import Path
from ct2trainer.native.fixture_probe import run_probe

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = run_probe(json.loads(args.plan.read_text(encoding="utf-8")), args.target, args.report)
    print(result["status"])
