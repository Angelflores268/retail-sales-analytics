"""Build a portable, compressed SQLite snapshot for the Streamlit dashboard.

The pipeline mirrors the cleanup rules in src/transform.py. It is independent
of MySQL and only needs internet access when using the public UCI source.

Usage:
    python src/build_snapshot.py --output data/retail_sales.sqlite.gz
    python src/build_snapshot.py --source 'data/raw/Online Retail.xlsx'
"""

from __future__ import annotations

import argparse
import gzip
import io
import os
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "retail_sales.sqlite.gz"
SOURCE_URL = "https://archive.ics.uci.edu/static/public/352/online+retail.zip"
EXPECTED_COLUMNS = {
    "InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate",
    "UnitPrice", "CustomerID", "Country",
}


def _read_xlsx_from_zip(raw_zip: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        files = [name for name in zf.namelist() if name.lower().endswith(".xlsx")]
        if len(files) != 1:
            raise ValueError(f"Expected one XLSX in UCI archive; found {len(files)}")
        with zf.open(files[0]) as xlsx_file:
            return pd.read_excel(io.BytesIO(xlsx_file.read()), engine="openpyxl")


def read_source(source: Path | None = None) -> pd.DataFrame:
    """Read a local Excel/ZIP/CSV file or the original public UCI archive."""
    if source is not None:
        path = Path(source).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Dataset file not found: {path}")
        suffix = path.suffix.lower()
        if suffix == ".xlsx":
            return pd.read_excel(path, engine="openpyxl")
        if suffix == ".zip":
            return _read_xlsx_from_zip(path.read_bytes())
        if suffix == ".csv":
            return pd.read_csv(path)
        raise ValueError("Source must be .xlsx, .zip, or .csv")

    print("Downloading the original Online Retail dataset from UCI...")
    response = requests.get(SOURCE_URL, timeout=(20, 180))
    response.raise_for_status()
    # The official archive is about 22.6 MB. Refuse unexpected huge responses.
    if len(response.content) > 100 * 1024 * 1024:
        raise ValueError("Unexpectedly large UCI download")
    return _read_xlsx_from_zip(response.content)


def clean_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """Replicate the existing project's cleaning logic in a typed form."""
    missing = EXPECTED_COLUMNS.difference(df.columns)
    if missing:
        raise ValueError("Missing source columns: " + ", ".join(sorted(missing)))

    cleaned = df[list(EXPECTED_COLUMNS)].copy()
    cleaned = cleaned.dropna(subset=["Description", "CustomerID"])
    cleaned = cleaned.drop_duplicates()
    cleaned["InvoiceNo"] = (
        cleaned["InvoiceNo"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    )
    cleaned = cleaned[~cleaned["InvoiceNo"].str.upper().str.startswith("C")]
    cleaned["Quantity"] = pd.to_numeric(cleaned["Quantity"], errors="coerce")
    cleaned["UnitPrice"] = pd.to_numeric(cleaned["UnitPrice"], errors="coerce")
    cleaned["InvoiceDate"] = pd.to_datetime(cleaned["InvoiceDate"], errors="coerce")
    cleaned["CustomerID"] = pd.to_numeric(cleaned["CustomerID"], errors="coerce")
    cleaned = cleaned.dropna(subset=["InvoiceDate", "CustomerID"])
    cleaned = cleaned[(cleaned["Quantity"] > 0) & (cleaned["UnitPrice"] > 0)].copy()
    cleaned["CustomerID"] = cleaned["CustomerID"].astype("int64")
    cleaned["Quantity"] = cleaned["Quantity"].astype("int64")
    cleaned["InvoiceDate"] = cleaned["InvoiceDate"].dt.strftime("%Y-%m-%d %H:%M:%S")
    cleaned["TotalPrice"] = cleaned["Quantity"] * cleaned["UnitPrice"]
    cleaned["StockCode"] = cleaned["StockCode"].astype(str)
    cleaned["Country"] = cleaned["Country"].astype(str)

    return cleaned[
        ["InvoiceNo", "StockCode", "Description", "Quantity", "InvoiceDate",
         "UnitPrice", "CustomerID", "Country", "TotalPrice"]
    ]


def write_sqlite(df: pd.DataFrame, database_path: Path) -> None:
    """Write SQLite atomically; never leave a partially built working DB."""
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="retail_build_", suffix=".sqlite", dir=database_path.parent)
    os.close(fd)
    temporary = Path(temp_name)
    try:
        with sqlite3.connect(temporary) as conn:
            conn.execute("""
                CREATE TABLE retail_sales (
                    InvoiceNo TEXT,
                    StockCode TEXT,
                    Description TEXT,
                    Quantity INTEGER,
                    InvoiceDate TEXT,
                    UnitPrice REAL,
                    CustomerID INTEGER,
                    Country TEXT,
                    TotalPrice REAL
                )
            """)
            df.to_sql("retail_sales", conn, if_exists="append", index=False, chunksize=5000)
            conn.execute("CREATE INDEX idx_sales_country ON retail_sales (Country)")
            conn.execute("CREATE INDEX idx_sales_invoice ON retail_sales (InvoiceNo)")
            conn.execute("CREATE INDEX idx_sales_date ON retail_sales (InvoiceDate)")
            conn.execute("CREATE INDEX idx_sales_customer ON retail_sales (CustomerID)")
            count = conn.execute("SELECT COUNT(*) FROM retail_sales").fetchone()[0]
            if count != len(df):
                raise RuntimeError(f"Database row count mismatch ({count} != {len(df)})")
        os.replace(temporary, database_path)
    finally:
        temporary.unlink(missing_ok=True)


def build_snapshot(output: Path = DEFAULT_OUTPUT, source: Path | None = None) -> tuple[int, Path]:
    """Build .sqlite or .sqlite.gz from source; return (transaction_rows, path)."""
    output = Path(output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    print("Reading retail transactions...")
    raw = read_source(source)
    print(f"Source rows: {len(raw):,}")
    cleaned = clean_transactions(raw)
    print(f"Valid cleaned rows: {len(cleaned):,}")
    if cleaned.empty:
        raise ValueError("No valid transactions after cleaning")
    del raw

    if not output.name.endswith(".gz"):
        write_sqlite(cleaned, output)
        print(f"Saved SQLite snapshot: {output}")
        return len(cleaned), output

    # Create the db beside the target, compress it, and publish the .gz atomically.
    fd, db_temp_name = tempfile.mkstemp(suffix=".sqlite", dir=output.parent)
    os.close(fd)
    db_temp = Path(db_temp_name)
    gz_temp = output.with_name(output.name + ".tmp")
    try:
        write_sqlite(cleaned, db_temp)
        with db_temp.open("rb") as input_file, gzip.open(gz_temp, "wb", compresslevel=9) as out:
            shutil.copyfileobj(input_file, out)
        os.replace(gz_temp, output)
    finally:
        db_temp.unlink(missing_ok=True)
        gz_temp.unlink(missing_ok=True)

    print(f"Saved compressed SQLite snapshot: {output} ({output.stat().st_size:,} bytes)")
    return len(cleaned), output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Optional local XLSX, ZIP, or CSV input")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build_snapshot(args.output, args.source)
