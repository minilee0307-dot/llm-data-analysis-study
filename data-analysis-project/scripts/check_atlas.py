"""Download pinned official atlas files locally and check proposal feasibility.

Raw data are ignored by Git; only metadata and validation counts are published.
Run from any directory: python data-analysis-project/scripts/check_atlas.py
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen, Request
from zoneinfo import ZoneInfo
import json
import platform

import nibabel as nib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
COMMIT = "8c9b19d6e463a50919d9df60a512e1e8d6b00125"
BASE = f"https://raw.githubusercontent.com/SNU-LIST/chi-separation-atlas/{COMMIT}"
FILES = ["README.md", "LICENSE.pdf", "chi_para_ROI_stats.csv",
         "chi_dia_ROI_stats.csv", "label_names.csv",
         "NIfTI/labels.nii.gz", "NIfTI/chi.nii.gz",
         "NIfTI/chi_para.nii.gz", "NIfTI/chi_dia.nii.gz"]


def acquire(name):
    path = RAW / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        request = Request(f"{BASE}/{name}", headers={"User-Agent": "CourseAtlasFeasibility/1.0"})
        with urlopen(request, timeout=90) as response:
            content = response.read()
        temporary = path.with_name(path.name + ".part")
        temporary.write_bytes(content)
        temporary.replace(path)
    return {"file": name, "url": f"{BASE}/{name}",
            "bytes": path.stat().st_size,
            "sha256": sha256(path.read_bytes()).hexdigest()}


def table_check(frame, key):
    return {"rows": len(frame), "columns": list(frame.columns),
            "dtypes": {k: str(v) for k, v in frame.dtypes.items()},
            "missing_cells": int(frame.isna().sum().sum()),
            "duplicate_rows": int(frame.duplicated().sum()),
            "duplicate_keys": int(frame.duplicated(key).sum())}


def normalized_name(values):
    # Labels in the official CSV have literal single quotes; preserve raw files.
    return values.str.strip().str.strip("'").str.strip()


def main():
    with ThreadPoolExecutor(max_workers=4) as pool:
        manifest = list(pool.map(acquire, FILES))
    tables = {name: pd.read_csv(RAW / f"{name}.csv")
              for name in ["chi_para_ROI_stats", "chi_dia_ROI_stats", "label_names"]}
    stats = {}
    for name, frame in tables.items():
        stats[name] = table_check(frame, "Index" if name == "label_names" else "ROI_name")
        if name != "label_names":
            numbers = frame[["Mean", "SD"]].apply(pd.to_numeric, errors="coerce")
            stats[name].update({
                "numeric_conversion_failures": int(numbers.isna().sum().sum()),
                "nonfinite_numeric_values": int((~np.isfinite(numbers)).sum().sum()),
                "negative_sd_count": int((numbers.SD < 0).sum()),
                "negative_mean_count": int((numbers.Mean < 0).sum()),
            })
    label_table = tables["label_names"].copy()
    label_table["roi_key"] = normalized_name(label_table.ROI_name)
    labels = nib.load(RAW / "NIfTI/labels.nii.gz")
    label_values = labels.get_fdata()
    unique = np.unique(label_values)
    label_ids = sorted(int(i) for i in unique if i != 0)
    voxel_counts = {str(i): int((label_values == i).sum()) for i in label_ids}
    image_checks = {}
    for name in ["chi", "chi_para", "chi_dia"]:
        img = nib.load(RAW / f"NIfTI/{name}.nii.gz")
        values = img.get_fdata()
        in_roi = values[label_values > 0]
        image_checks[name] = {
            "shape": list(img.shape), "dtype": str(img.get_data_dtype()),
            "voxel_size_header": list(map(float, img.header.get_zooms())),
            "header_space_time_units": list(img.header.get_xyzt_units()),
            "same_shape_as_labels": img.shape == labels.shape,
            "same_affine_as_labels": bool(np.allclose(img.affine, labels.affine)),
            "nonfinite_voxels": int((~np.isfinite(values)).sum()),
            "negative_voxels_within_labels": int((in_roi < 0).sum()),
        }
    source_names = set(label_table.roi_key)
    join_checks = {}
    for name in ["chi_para_ROI_stats", "chi_dia_ROI_stats"]:
        keys = set(normalized_name(tables[name].ROI_name))
        join_checks[name] = {
            "matched_mask_regions": len(keys & source_names),
            "stats_only_regions": sorted(keys - source_names),
            "labels_only_regions": sorted(source_names - keys),
        }
    report = {
        "checked_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
        "scope": "Codex-assisted automated feasibility checks; no completed main analysis",
        "source_commit": COMMIT,
        "environment": {"python": platform.python_version(), "numpy": np.__version__,
                        "pandas": pd.__version__, "nibabel": nib.__version__},
        "manifest": manifest, "tables": stats, "joins_after_quote_normalization": join_checks,
        "labels": {"shape": list(labels.shape), "dtype": str(labels.get_data_dtype()),
                   "integer_values_only": bool(np.equal(unique, np.round(unique)).all()),
                   "background_value": 0, "nonzero_ids": label_ids,
                   "mask_ids_equal_csv_ids": label_ids == sorted(label_table.Index.tolist()),
                   "voxel_counts": voxel_counts},
        "images": image_checks,
    }
    output = ROOT / "docs" / "data-check.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "manifest"}, ensure_ascii=False, indent=2))
    assert all(v["missing_cells"] == v["duplicate_rows"] == v["duplicate_keys"] == 0
               for v in stats.values())
    assert all(v["numeric_conversion_failures"] == v["nonfinite_numeric_values"] == v["negative_sd_count"] == 0
               for k, v in stats.items() if k != "label_names")
    assert report["labels"]["mask_ids_equal_csv_ids"]
    assert all(v["same_shape_as_labels"] and v["same_affine_as_labels"]
               and v["nonfinite_voxels"] == 0 for v in image_checks.values())


if __name__ == "__main__":
    main()
