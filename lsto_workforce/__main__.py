"""
CLI for the LsTo Agent Workforce system.

Commands:
    demo            Run an end-to-end demo decision and write brief + ledger
    verify-ledger   Verify hash-chain integrity of a workforce ledger
    scorecard       Compute the workforce scorecard from persisted records
    show-charter    Print the active charter (and its hash)
"""

import argparse
import json
import sys
from pathlib import Path

from lsto_workforce.brief import render_brief
from lsto_workforce.charter import default_charter, load_charter
from lsto_workforce.demo import run_demo
from lsto_workforce.ledger import HashChainLedger
from lsto_workforce.metrics import compute_scorecard, render_scorecard
from lsto_workforce.orchestrator import Workforce


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="lsto_workforce",
        description="LsTo Agent Workforce — governed, auditable decision support",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_demo = sub.add_parser("demo", help="Run an end-to-end demo decision")
    p_demo.add_argument("--out", default="./out/workforce", help="Output directory")
    p_demo.add_argument("--charter", default=None, help="Optional charter YAML")

    p_verify = sub.add_parser("verify-ledger", help="Verify ledger hash chain")
    p_verify.add_argument("path", help="Path to workforce_ledger.jsonl")

    p_score = sub.add_parser("scorecard", help="Compute workforce scorecard")
    p_score.add_argument("--records", default="./out/workforce/decisions",
                         help="Directory of decision record JSON files")
    p_score.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")

    p_charter = sub.add_parser("show-charter", help="Print the active charter")
    p_charter.add_argument("--charter", default=None, help="Optional charter YAML")

    args = parser.parse_args(argv)

    if args.command == "demo":
        charter = load_charter(args.charter) if args.charter else default_charter()
        paths = run_demo(out_dir=args.out, charter=charter)
        print("Demo decision complete. Outputs:")
        for label, path in paths.items():
            print(f"  {label}: {path}")
        return 0

    if args.command == "verify-ledger":
        ledger = HashChainLedger(args.path)
        result = ledger.verify()
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.valid else 1

    if args.command == "scorecard":
        records_dir = Path(args.records)
        workforce = Workforce(
            ledger_path=str(records_dir.parent / "workforce_ledger.jsonl"),
            records_dir=str(records_dir),
        )
        records = workforce.load_all_records()
        card = compute_scorecard(records)
        if args.json:
            print(json.dumps(card.to_dict(), indent=2))
        else:
            print(render_scorecard(card))
        return 0

    if args.command == "show-charter":
        charter = load_charter(args.charter) if args.charter else default_charter()
        payload = charter.to_dict()
        payload["charter_hash"] = charter.charter_hash()
        print(json.dumps(payload, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
