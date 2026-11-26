from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import csv
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from conciliacao.core import read_csv, reconcile
from conciliacao.store import read_report, save_report

ROOT = Path(__file__).resolve().parents[1]
HEADER = b"referencia;valor;moeda\n"
LEDGER = (ROOT / "examples/ledger.csv").read_bytes()
SETTLEMENTS = (ROOT / "examples/settlements.csv").read_bytes()


class ReconciliationTests(unittest.TestCase):
    def test_exact_cents_with_comma_and_period(self):
        result = read_csv(HEADER + b"PED-1;105,09;BRL\nPED-2;0.10;BRL\n", "ledger")
        self.assertEqual([t.cents for t in result], [10509, 10])

    def test_malformed_columns_and_fraction_precision(self):
        for payload in [b"ref;valor;moeda\nPED-1;1;BRL\n", HEADER + b"PED-1;1,001;BRL\n",
                        HEADER + b"PED-1;1;BRL;extra\n"]:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    read_csv(payload, "ledger")

    def test_fixture_exercises_each_status(self):
        report = reconcile(LEDGER, SETTLEMENTS)
        self.assertEqual(report["by_status"], {
            "amount_mismatch": 1, "currency_mismatch": 1, "duplicate_reference": 1,
            "matched": 1, "missing_settlement": 1, "unexpected_settlement": 1,
        })
        duplicate = next(row for row in report["findings"] if row["status"] == "duplicate_reference")
        self.assertEqual([row["line"] for row in duplicate["settlements"]], [5, 6])

    def test_direction_matters_for_batch_identity(self):
        forward = reconcile(LEDGER, SETTLEMENTS)
        self.assertNotEqual(forward["batch_id"], reconcile(SETTLEMENTS, LEDGER)["batch_id"])
        self.assertEqual(forward, reconcile(LEDGER, SETTLEMENTS))

    def test_concurrent_reimport_stores_one_report(self):
        report = reconcile(LEDGER, SETTLEMENTS)
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "history.db"
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda _: save_report(db, report), range(8)))
            self.assertEqual(read_report(db, report["batch_id"]), report)
            with closing(sqlite3.connect(db)) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM batches").fetchone()[0], 1)

    def test_csv_export_reports_discrepancies_and_keeps_ambiguous_amounts_blank(self):
        report = reconcile(LEDGER, SETTLEMENTS)
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "discrepancies.db"
            save_report(db, report)
            output = subprocess.check_output([
                sys.executable, "-m", "conciliacao", "--db", str(db),
                "report", report["batch_id"], "--format", "csv",
            ], cwd=ROOT, text=True)
            rows = {row["referencia"]: row for row in csv.DictReader(output.splitlines(), delimiter=";")}
            self.assertNotIn("PED-1001", rows)
            self.assertEqual(len(rows), 5)
            self.assertEqual(rows["PED-1002"]["centavos_ledger"], "3500")
            self.assertEqual(rows["PED-1002"]["centavos_liquidacao"], "3000")
            self.assertEqual(rows["PED-1005"]["registros_liquidacao"], "2")
            self.assertEqual(rows["PED-1005"]["centavos_liquidacao"], "")

    def test_cli_can_fail_on_discrepancies_and_save_the_report(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "demo.db"
            run = [sys.executable, "-m", "conciliacao", "--db", str(db), "reconcile"]
            result = subprocess.run([*run, "examples/ledger.csv", "examples/settlements.csv",
                                     "--fail-on-discrepancies"], cwd=ROOT, capture_output=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(read_report(db, json.loads(result.stdout)["batch_id"]), json.loads(result.stdout))

    def test_lists_recent_batches_without_creating_an_empty_database(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "demo.db"
            cmd = [sys.executable, "-m", "conciliacao", "--db", str(db), "batches"]
            self.assertEqual(json.loads(subprocess.check_output(cmd, cwd=ROOT)), [])
            self.assertFalse(db.exists())
            save_report(db, reconcile(LEDGER, SETTLEMENTS))
            latest = reconcile(SETTLEMENTS, LEDGER)
            save_report(db, latest)
            rows = json.loads(subprocess.check_output([*cmd, "--limit", "1"], cwd=ROOT))
            self.assertEqual([row["batch_id"] for row in rows], [latest["batch_id"]])
            self.assertIn("created_at", rows[0])

    def test_summary_reports_counts_without_transaction_rows(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "demo.db"
            report = reconcile(LEDGER, SETTLEMENTS)
            save_report(db, report)
            result = json.loads(subprocess.check_output([
                sys.executable, "-m", "conciliacao", "--db", str(db),
                "report", report["batch_id"], "--format", "summary",
            ], cwd=ROOT))
            self.assertEqual(result, {"batch_id": report["batch_id"], "by_status": report["by_status"],
                                      "total_references": 6, "discrepancies": 5})

    def test_validate_counts_input_rows_and_rejects_a_malformed_file(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "demo.db"
            bad = Path(tmp) / "bad.csv"
            bad.write_bytes(b"wrong,headers\n")
            command = [sys.executable, "-m", "conciliacao", "--db", str(db),
                       "validate", "examples/ledger.csv"]
            result = subprocess.check_output([*command, "examples/settlements.csv"], cwd=ROOT)
            self.assertEqual(json.loads(result), {
                "ledger_rows": len(read_csv(LEDGER, "ledger")),
                "settlement_rows": len(read_csv(SETTLEMENTS, "settlements")),
            })
            error = subprocess.run([*command, str(bad)], cwd=ROOT, capture_output=True)
            self.assertEqual(error.returncode, 2, error.stderr)
            self.assertFalse(db.exists())

    def test_dry_run_reports_discrepancies_without_writing_a_database(self):
        with TemporaryDirectory() as tmp:
            db = Path(tmp) / "demo.db"
            result = subprocess.run([
                sys.executable, "-m", "conciliacao", "--db", str(db), "reconcile",
                "examples/ledger.csv", "examples/settlements.csv", "--dry-run", "--fail-on-discrepancies",
            ], cwd=ROOT, capture_output=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(json.loads(result.stdout), reconcile(LEDGER, SETTLEMENTS))
            self.assertFalse(db.exists())

    def test_cli_round_trip(self):
        with TemporaryDirectory() as tmp:
            db = str(Path(tmp) / "demo.db")
            base = [sys.executable, "-m", "conciliacao", "--db", db]
            report = json.loads(subprocess.check_output(
                [*base, "reconcile", "examples/ledger.csv", "examples/settlements.csv"], cwd=ROOT
            ))
            recovered = json.loads(subprocess.check_output(
                [*base, "report", report["batch_id"]], cwd=ROOT
            ))
            self.assertEqual(recovered, report)


if __name__ == "__main__":
    unittest.main()
