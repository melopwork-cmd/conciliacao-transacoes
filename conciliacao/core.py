from collections import Counter, defaultdict
import csv
from dataclasses import asdict, dataclass
from decimal import Decimal
import hashlib
import io
import re


FIELDS = ["referencia", "valor", "moeda"]
REF = re.compile(r"[A-Za-z0-9._-]{1,100}")
MONEY = re.compile(r"[0-9]{1,12}(?:[,.][0-9]{1,2})?")
CURRENCY = re.compile(r"[A-Z]{3}")


@dataclass(frozen=True)
class Transaction:
    reference: str
    cents: int
    currency: str
    line: int


def read_csv(payload: bytes, source: str) -> list[Transaction]:
    try:
        text = payload.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=";", strict=True)
        header = reader.fieldnames or []
        if len(header) != len(FIELDS) or set(header) != set(FIELDS):
            raise ValueError(f"{source}: expected the columns referencia, valor and moeda")
        transactions = []
        for row in reader:
            label = f"{source}, line {reader.line_num}"
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{label}: unexpected number of fields")
            ref, amount, currency = (row[key].strip() for key in FIELDS)
            if not REF.fullmatch(ref) or not CURRENCY.fullmatch(currency) or not MONEY.fullmatch(amount):
                raise ValueError(f"{label}: invalid reference, amount or currency")
            cents = int(Decimal(amount.replace(",", ".")) * 100)
            if cents <= 0:
                raise ValueError(f"{label}: amount must be positive")
            transactions.append(Transaction(ref, cents, currency, reader.line_num))
        return transactions
    except (UnicodeDecodeError, csv.Error) as error:
        raise ValueError(f"{source}: invalid UTF-8 or malformed CSV") from error


def batch_id(ledger_bytes: bytes, settlement_bytes: bytes) -> str:
    left = hashlib.sha256(ledger_bytes).digest()
    right = hashlib.sha256(settlement_bytes).digest()
    return hashlib.sha256(left + right).hexdigest()


def compare(ledger: list[Transaction], settlements: list[Transaction]) -> list[dict]:
    ledgers = defaultdict(list)
    partners = defaultdict(list)
    for row in ledger:
        ledgers[row.reference].append(row)
    for row in settlements:
        partners[row.reference].append(row)

    findings = []
    for ref in sorted(set(ledgers) | set(partners)):
        left, right = ledgers.get(ref, []), partners.get(ref, [])
        if len(left) > 1 or len(right) > 1:
            status = "duplicate_reference"
        elif not left:
            status = "unexpected_settlement"
        elif not right:
            status = "missing_settlement"
        elif left[0].currency != right[0].currency:
            status = "currency_mismatch"
        elif left[0].cents != right[0].cents:
            status = "amount_mismatch"
        else:
            status = "matched"
        findings.append({
            "reference": ref,
            "status": status,
            "ledger": [asdict(row) for row in left],
            "settlements": [asdict(row) for row in right],
        })
    return findings


def reconcile(ledger: bytes, settlements: bytes) -> dict:
    findings = compare(read_csv(ledger, "ledger"), read_csv(settlements, "settlements"))
    return {
        "batch_id": batch_id(ledger, settlements),
        "by_status": dict(sorted(Counter(item["status"] for item in findings).items())),
        "findings": findings,
    }
