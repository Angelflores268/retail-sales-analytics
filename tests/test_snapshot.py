"""Offline fixture tests for the SQLite dashboard snapshot generator.

Usage: python -m unittest discover -s tests -v
"""

import gzip
import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.build_snapshot import build_snapshot, clean_transactions


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.raw = pd.DataFrame([
            ("1001", "A", "Hat", 2, "2010-12-01 10:00", 5.0, 51, "United Kingdom"),
            ("1001", "A", "Hat", 2, "2010-12-01 10:00", 5.0, 51, "United Kingdom"), # duplicate
            ("1002", "B", "Bag", 3, "2010-12-02 10:00", 10.0, 52, "France"),
            ("C1003", "C", "Return", -2, "2010-12-03 10:00", 2.0, 53, "France"), # cancel
            ("1004", "D", "Free", 1, "2010-12-03 10:00", 0.0, 53, "France"), # zero price
            ("1005", "E", "Other", 1, "2010-12-03 10:00", 10.0, None, "France"), # missing customer
            ("1006", "F", None, 1, "2010-12-03 10:00", 10.0, 54, "France"), # missing description
        ], columns=["InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate",
                    "UnitPrice", "CustomerID", "Country"])

    def test_cleaning_rules(self):
        cleaned = clean_transactions(self.raw)
        self.assertEqual(len(cleaned), 2)
        self.assertEqual(set(cleaned["Country"]), {"France", "United Kingdom"})
        self.assertAlmostEqual(cleaned["TotalPrice"].sum(), 40.0)

    def test_compressed_database_and_queries(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / "test.xlsx"
            output = folder / "retail_sales.sqlite.gz"
            self.raw.to_excel(source, index=False)
            count, result = build_snapshot(output, source)
            self.assertEqual(count, 2)
            self.assertTrue(result.is_file())
            db = folder / "retail_sales.sqlite"
            with gzip.open(output, "rb") as packed, db.open("wb") as extracted:
                extracted.write(packed.read())
            with sqlite3.connect(db) as conn:
                rows, revenue, orders, customers = conn.execute("""
                    SELECT COUNT(*), SUM(TotalPrice), COUNT(DISTINCT InvoiceNo),
                    COUNT(DISTINCT CustomerID) FROM retail_sales
                """).fetchone()
                self.assertEqual((rows, orders, customers), (2, 2, 2))
                self.assertEqual(revenue, 40)
                country = conn.execute("SELECT SUM(TotalPrice) FROM retail_sales WHERE Country=?", ("France",)).fetchone()[0]
                self.assertEqual(country, 30)
                monthly = conn.execute("SELECT substr(InvoiceDate,1,7) FROM retail_sales LIMIT 1").fetchone()[0]
                self.assertEqual(monthly, "2010-12")
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")


if __name__ == "__main__":
    unittest.main()
