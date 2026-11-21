"""Replay a synthetic housing-case migration and verify the imported records."""

import csv
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory


CASE_ID = "001247"
TABLES = {
    "applications": ("case_id", "status"),
    "documents": ("document_id", "case_id", "body"),
    "decisions": ("decision_id", "case_id", "outcome"),
}


def create_schema(db):
    db.executescript("""
        CREATE TABLE applications (case_id TEXT PRIMARY KEY, status TEXT NOT NULL);
        CREATE TABLE documents (
            document_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, body TEXT NOT NULL
        );
        CREATE TABLE decisions (
            decision_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, outcome TEXT NOT NULL
        );
    """)


def export_bundle(directory):
    with closing(sqlite3.connect(":memory:")) as source:
        create_schema(source)
        case_ids = [str(number) for number in range(2000, 2099)] + [CASE_ID]
        source.executemany(
            "INSERT INTO applications VALUES (?, 'submitted')",
            [(case_id,) for case_id in case_ids],
        )
        source.execute(
            "INSERT INTO documents VALUES ('doc-1', ?, 'Synthetic income statement')",
            (CASE_ID,),
        )
        source.execute(
            "INSERT INTO decisions VALUES ('decision-1', ?, 'Eligibility review queued')",
            (CASE_ID,),
        )
        for table, columns in TABLES.items():
            with (directory / f"{table}.csv").open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(columns)
                writer.writerows(source.execute(f"SELECT * FROM {table}"))


def read_bundle(directory):
    bundle = {}
    for table in TABLES:
        with (directory / f"{table}.csv").open(newline="", encoding="utf-8") as stream:
            reader = csv.reader(stream)
            if tuple(next(reader)) != TABLES[table]:
                raise ValueError(f"Unexpected columns in {table}.csv")
            bundle[table] = [tuple(row) for row in reader]
    return bundle


def import_bundle(db, bundle, *, preserve_ids):
    create_schema(db)
    applications = bundle["applications"]
    if not preserve_ids:
        applications = [(str(int(case_id)), status) for case_id, status in applications]
    db.executemany("INSERT INTO applications VALUES (?, ?)", applications)
    db.executemany("INSERT INTO documents VALUES (?, ?, ?)", bundle["documents"])
    db.executemany("INSERT INTO decisions VALUES (?, ?, ?)", bundle["decisions"])
    db.commit()


def audit(db, bundle):
    findings = []
    for table in TABLES:
        expected = set(bundle[table])
        actual = set(db.execute(f"SELECT * FROM {table}"))
        for record in sorted(expected - actual):
            findings.append(f"missing or changed {table} row {record[0]}")
        for record in sorted(actual - expected):
            findings.append(f"unexpected {table} row {record[0]}")
    for table, id_column in (("documents", "document_id"), ("decisions", "decision_id")):
        orphaned = db.execute(f"""
            SELECT child.{id_column}, child.case_id
            FROM {table} AS child
            LEFT JOIN applications AS app ON app.case_id = child.case_id
            WHERE app.case_id IS NULL
            ORDER BY child.{id_column}
        """)
        for record_id, case_id in orphaned:
            findings.append(f"orphaned {table} row {record_id} points to {case_id}")
    return findings


def main():
    with TemporaryDirectory(prefix="exit-drill-") as temp:
        directory = Path(temp)
        export_bundle(directory)
        bundle = read_bundle(directory)
        results = {}
        for label, preserve_ids in (("legacy", False), ("fixed", True)):
            with closing(sqlite3.connect(directory / f"{label}.sqlite")) as target:
                import_bundle(target, bundle, preserve_ids=preserve_ids)
                (count,) = target.execute("SELECT COUNT(*) FROM applications").fetchone()
                findings = audit(target, bundle)
            results[label] = (count, findings)
            print(f"{label}: {count}/{len(bundle['applications'])} applications imported")
            print(f"  audit: {'FAIL' if findings else 'PASS'}")
            for finding in findings:
                print(f"  - {finding}")

    expected_legacy_findings = [
        "missing or changed applications row 001247",
        "unexpected applications row 1247",
        "orphaned documents row doc-1 points to 001247",
        "orphaned decisions row decision-1 points to 001247",
    ]
    expected = {"legacy": (100, expected_legacy_findings), "fixed": (100, [])}
    return 0 if results == expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
