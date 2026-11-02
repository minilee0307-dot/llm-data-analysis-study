"""Prepare the pinned, non-dirty common sample without changing earlier chapters.

The local cache is excluded from Git. A fresh clone downloads the four public
course CSV files from an immutable commit and verifies their SHA-256 values.
No feature imputation is performed here; learned transforms belong in Train.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from urllib.request import urlopen

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = "6105f42bd8294cb364dde6dcc2fee71c32e14794"
RAW_DIR = PROJECT_ROOT / "data/ch09/raw"
PROCESSED_DIR = PROJECT_ROOT / "data/ch09/processed"
EXPECTED_SHA256 = {
    "customers.csv": "3b31aaefa66505f0a1820ccd89f0eac3b5e12830b71ecb45f2b65928bcdfb143",
    "products.csv": "46ff06753ade3e71011ee08dd366148dcd9c36521f111840cead0a9d1047e405",
    "orders.csv": "8f6e7ee39aa5ee6e229199532caa84bd9d4d30ef2abc2b9412cf45b0b2fdbfae",
    "order_items.csv": "a7a5c3942b0886c66cb38cc6a10fdfa68dbcde90e8642585dee49c4bd104063a",
}
KEYS = {"customers": "customer_id", "products": "product_id", "orders": "order_id", "order_items": "order_item_id"}


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare_ch09_data(raw_dir=RAW_DIR, processed_dir=PROCESSED_DIR, report_dir=None):
    raw_dir, processed_dir = Path(raw_dir), Path(processed_dir)
    report_dir = Path(report_dir) if report_dir is not None else PROJECT_ROOT / "reports"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    old_paths = sorted((PROJECT_ROOT / "data/raw").glob("*.csv")) + sorted((PROJECT_ROOT / "data/processed").glob("*.csv"))
    old_hashes = {str(p): _hash(p) for p in old_paths}
    source_rows, raw = [], {}
    for filename, expected in EXPECTED_SHA256.items():
        path = raw_dir / filename
        url = f"https://raw.githubusercontent.com/GilbertMoon/llm-data-analysis-course/{SOURCE_COMMIT}/data/raw/{filename}"
        if not path.exists():
            with urlopen(url, timeout=30) as response:
                payload = response.read()
            if hashlib.sha256(payload).hexdigest() != expected:
                raise ValueError(f"Source hash mismatch: {filename}")
            path.write_bytes(payload)
        if _hash(path) != expected:
            raise ValueError(f"Cached source differs from pinned public course file: {filename}")
        name = path.stem
        raw[name] = pd.read_csv(path)
        source_rows.append({"dataset": name, "source_url": url, "sha256": expected,
                            "rows": len(raw[name]), "columns": len(raw[name].columns), "status": "PASS"})
    processed = {name: df.copy(deep=True) for name, df in raw.items()}
    checks = []

    def record(name, value, expected):
        ok = value == expected
        checks.append({"check": name, "value": value, "expected": expected, "status": "PASS" if ok else "FAIL"})
        if not ok:
            raise ValueError(f"Preparation gate failed: {name}: {value} != {expected}")

    for name, df in processed.items():
        key = KEYS[name]
        record(f"{name}.pk_missing", int(df[key].isna().sum()), 0)
        record(f"{name}.pk_duplicate", int(df[key].duplicated().sum()), 0)
        record(f"{name}.whole_row_duplicate", int(df.duplicated().sum()), 0)
        for column in df.select_dtypes(include=["object", "string"]).columns:
            df[column] = df[column].str.strip().replace("", pd.NA)
    # Pure parsing only: no fit/median/global most-frequent calculation here.
    for name, columns in {"customers": ["age"], "products": ["price"], "order_items": ["quantity", "unit_price"]}.items():
        for column in columns:
            values = pd.to_numeric(processed[name][column], errors="raise")
            processed[name][column] = values
    for name, column in [("customers", "signup_date"), ("orders", "order_date")]:
        processed[name][column] = pd.to_datetime(processed[name][column], errors="raise")
        record(f"{name}.{column}_missing", int(processed[name][column].isna().sum()), 0)
    relations = []
    for child, fk, parent, pk in [("orders", "customer_id", "customers", "customer_id"),
                                  ("order_items", "order_id", "orders", "order_id"),
                                  ("order_items", "product_id", "products", "product_id")]:
        bad = int((processed[child][fk].isna() | ~processed[child][fk].isin(processed[parent][pk])).sum())
        relations.append({"relationship": f"{child}.{fk} -> {parent}.{pk}", "invalid_count": bad,
                          "status": "PASS" if bad == 0 else "FAIL"})
        record(f"FK {child}.{fk}", bad, 0)
    items = processed["order_items"]
    record("nonpositive_quantity", int(items.quantity.le(0).sum()), 0)
    record("nonpositive_unit_price", int(items.unit_price.le(0).sum()), 0)
    items["line_total"] = items.quantity * items.unit_price
    saved = []
    for name, df in processed.items():
        record(f"{name}.row_loss", len(raw[name]) - len(df), 0)
        path = processed_dir / f"{name}_clean.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
        saved.append(path)
    record("existing_inputs_preserved", sum(_hash(Path(p)) == v for p, v in old_hashes.items()), len(old_hashes))
    summary = pd.DataFrame(source_rows)
    check_table = pd.DataFrame(checks)
    summary.to_csv(report_dir / "ch09_input_summary.csv", index=False, encoding="utf-8-sig")
    check_table.to_csv(report_dir / "ch09_input_checks.csv", index=False, encoding="utf-8-sig")
    manifest = {"source_commit": SOURCE_COMMIT, "source_sha256": EXPECTED_SHA256,
                "processed_sha256": {p.name: _hash(p) for p in saved},
                "feature_imputation_before_split": False,
                "source": "common course data/raw; not Chapter05 dirty-practice data"}
    (report_dir / "ch09_source_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"raw_data": raw, "processed_data": processed, "relationship_checks": pd.DataFrame(relations),
            "saved_paths": saved, "input_summary": summary, "checks": check_table, "manifest": manifest}


def main():
    result = prepare_ch09_data()
    print("Chapter09 공통 원본 준비 완료 (기존 Chapter05~08 입력 보존)")
    print(result["input_summary"][["dataset", "rows", "columns", "status"]].to_string(index=False))
    print(result["relationship_checks"].to_string(index=False))
    print("Feature imputation before split: False; all learned preprocessing is inside Train pipelines")


if __name__ == "__main__":
    main()
