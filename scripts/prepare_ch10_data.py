"""Prepare Chapter 10 from the pinned common course sample in its own cache."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.prepare_ch09_data import prepare_ch09_data


def prepare_ch10_data(raw_dir=None, processed_dir=None, report_dir=None):
    """Reuse the common source checks without writing any Chapter 09 outputs."""
    raw_dir = Path(raw_dir) if raw_dir is not None else ROOT / "data/ch10/raw"
    processed_dir = Path(processed_dir) if processed_dir is not None else ROOT / "data/ch10/processed"
    report_dir = Path(report_dir) if report_dir is not None else ROOT / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    with TemporaryDirectory() as scratch:
        result = prepare_ch09_data(raw_dir=raw_dir, processed_dir=processed_dir, report_dir=scratch)
        for name in ("input_summary.csv", "input_checks.csv", "source_manifest.json"):
            evidence = (Path(scratch) / f"ch09_{name}").read_bytes()
            (report_dir / f"ch10_{name}").write_bytes(evidence)
    return result


def main():
    result = prepare_ch10_data()
    print(result["input_summary"][["dataset", "rows", "columns", "status"]].to_string(index=False))
    print(result["relationship_checks"].to_string(index=False))
    print("Chapter 10 inputs: data/ch10/raw -> data/ch10/processed")


if __name__ == "__main__":
    main()
