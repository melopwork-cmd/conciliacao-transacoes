from argparse import ArgumentParser
import json
from pathlib import Path
import sqlite3
import sys

from .core import discrepancies_csv, read_csv, reconcile
from .store import list_batches, read_report, save_report


def main() -> int:
    parser = ArgumentParser(description="Compare ledger transactions with settlements.")
    parser.add_argument("--db", type=Path, default=Path("conciliacao.db"))
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser("reconcile", help="compare two CSV files")
    run.add_argument("ledger", type=Path)
    run.add_argument("settlements", type=Path)
    run.add_argument("--dry-run", action="store_true", help="print the report without saving it")
    run.add_argument("--fail-on-discrepancies", action="store_true",
                     help="exit with status 1 if the report contains discrepancies")
    validate = commands.add_parser("validate", help="validate the two input CSV files")
    validate.add_argument("ledger", type=Path)
    validate.add_argument("settlements", type=Path)
    report_cmd = commands.add_parser("report", help="read a previously saved result")
    report_cmd.add_argument("batch_id")
    report_cmd.add_argument("--format", choices=("json", "csv", "summary"), default="json",
                            help="CSV lists discrepancies, summary provides counts only")
    batches_cmd = commands.add_parser("batches", help="list recently saved batches")
    batches_cmd.add_argument("--limit", type=int, default=20)
    batches_cmd.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()
    if args.action == "batches" and not 1 <= args.limit <= 100:
        parser.error("--limit must be between 1 and 100")
    if args.action == "batches" and not 0 <= args.offset <= 2**63 - 1:
        parser.error("--offset must be a nonnegative SQLite integer")
    try:
        if args.action == "validate":
            ledger = read_csv(args.ledger.read_bytes(), "ledger")
            settlements = read_csv(args.settlements.read_bytes(), "settlements")
            print(json.dumps({"ledger_rows": len(ledger), "settlement_rows": len(settlements)}, indent=2))
            return 0
        if args.action == "batches":
            print(json.dumps(list_batches(args.db, args.limit, args.offset), indent=2))
            return 0
        if args.action == "reconcile":
            result = reconcile(args.ledger.read_bytes(), args.settlements.read_bytes())
            if not args.dry_run:
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
