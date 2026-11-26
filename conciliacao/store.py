from contextlib import closing
import json
from pathlib import Path
import sqlite3


def save_report(database: Path, report: dict) -> None:
    with closing(sqlite3.connect(database, timeout=5)) as db, db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS batches ("
            "id TEXT PRIMARY KEY, report TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        db.execute(
            "INSERT INTO batches (id, report) VALUES (?, ?) ON CONFLICT(id) DO NOTHING",
            (report["batch_id"], json.dumps(report, ensure_ascii=False)),
        )


def read_report(database: Path, key: str) -> dict | None:
    if not database.is_file():
        return None
    file_uri = database.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(file_uri, uri=True, timeout=5)) as db:
        table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='batches'").fetchone()
        if not table:
            return None
        row = db.execute("SELECT report FROM batches WHERE id = ?", (key,)).fetchone()
    return json.loads(row[0]) if row else None

def list_batches(database: Path, limit: int) -> list[dict[str, str]]:
    if not database.is_file():
        return []
    file_uri = database.resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(file_uri, uri=True, timeout=5)) as db:
        table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='batches'").fetchone()
        if not table:
            return []
        rows = db.execute("SELECT id, created_at FROM batches ORDER BY rowid DESC LIMIT ?", (limit,))
        return [{"batch_id": batch_id, "created_at": created_at} for batch_id, created_at in rows]
