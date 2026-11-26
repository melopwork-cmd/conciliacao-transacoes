from argparse import ArgumentParser
import json
from pathlib import Path
import sqlite3
import sys

from .core import discrepancies_csv, reconcile
from .store import list_batches, read_report, save_report


def main() -> int:
    parser = ArgumentParser(description="Compare ledger transactions with settlements.")
    parser.add_argument("--db", type=Path, default=Path("conciliacao.db"))
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser("reconcile", help="compare two CSV files")
    run.add_argument("ledger", type=Path)
    run.add_argument("settlements", type=Path)
    run.add_argument("--fail-on-discrepancies", action="store_true",
                     help="exit with status 1 if the report contains discrepancies")
    report_cmd = commands.add_parser("report", help="read a previously saved result")
    report_cmd.add_argument("batch_id")
    report_cmd.add_argument("--format", choices=("json", "csv", "summary"), default="json",
                            help="CSV lists discrepancies, summary provides counts only")
    batches_cmd = commands.add_parser("batches", help="list recently saved batches")
    batches_cmd.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    if args.action == "batches" and not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100")
    try:
        if args.action == "batches":
            print(json.dumps(list_batches(args.db, args.limit), indent=2))
            return 0
        if args.action == "reconcile":
            result = reconcile(args.ledger.read_bytes(), args.settlements.read_bytes())
            save_report(args.db, result)
        else:
            result = read_report(args.db, args.batch_id)
            if result is None:
                parser.error("batch not found")
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.error(str(error))
    if args.action == "report" and args.format == "csv":
        sys.stdout.write(discrepancies_csv(result))
    else:
        if args.action == "report" and args.format == "summary":
            by_status = result["by_status"]
            total = sum(by_status.values())
            result = {"batch_id": result["batch_id"], "by_status": by_status,
                      "total_references": total, "discrepancies": total - by_status.get("matched", 0)}
        print(json.dumps(result, ensure_ascii=True, indent=2))
    return int(args.action == "reconcile" and args.fail_on_discrepancies
               and any(finding["status"] != "matched" for finding in result["findings"]))


if __name__ == "__main__":
    raise SystemExit(main())
