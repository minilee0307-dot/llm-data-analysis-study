"""Run Chapter 10 after `python scripts/prepare_ch10_data.py`."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.classification import run_classification_analysis


def main():
    result = run_classification_analysis()
    for name in ("target_distribution", "split_summary", "validation_model_comparison", "threshold_metrics", "test_metrics", "confusion_matrix", "validation"):
        print(f"\n{name}")
        print(result[name].to_string(index=name == "confusion_matrix"))
    print(f"\nValidation 선택 고정 SHA-256: {result['selection_sha256']}")
    print(f"공개 예측 컬럼: {', '.join(result['prediction_result'].columns)}")


if __name__ == "__main__":
    main()
