# Exit Drill

Exit Drill checks whether a case handover preserves the records and relationships that staff need to continue their work. This first reproducible case migrates 100 synthetic housing applications through CSV into SQLite.

## Run

From this folder, run `python demo.py`. The demo uses the Python standard library. It creates the CSV export and destination databases in a temporary folder. It runs offline with synthetic records.

The legacy importer misreads case identifiers as integers. It still inserts all 100 application rows, but application `001247` becomes `1247`. Its document and decision still point to `001247`, so the migration audit reports both orphaned records. The corrected importer preserves the original identifier as text. The audit checks the full rows and confirms that downstream references resolve.

The command exits successfully when both importers report 100 rows, the audit detects the four expected legacy findings, and the corrected import produces no findings.
