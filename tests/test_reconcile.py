from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
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
