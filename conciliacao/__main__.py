from argparse import ArgumentParser
import json
from pathlib import Path
import sqlite3

from .core import reconcile
from .store import read_report, save_report


def main() -> int:
    parser = ArgumentParser(description="Compare ledger transactions with settlements.")
    parser.add_argument("--db", type=Path, default=Path("conciliacao.db"))
    commands = parser.add_subparsers(dest="action", required=True)
    run = commands.add_parser("reconcile", help="compare two CSV files")
    run.add_argument("ledger", type=Path)
    run.add_argument("settlements", type=Path)
    report_cmd = commands.add_parser("report", help="read a previously saved result")
    report_cmd.add_argument("batch_id")
    args = parser.parse_args()
    try:
        if args.action == "reconcile":
            result = reconcile(args.ledger.read_bytes(), args.settlements.read_bytes())
            save_report(args.db, result)
        else:
            result = read_report(args.db, args.batch_id)
            if result is None:
                parser.error("batch not found")
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
