"""실행: 프로젝트 루트에서 python scripts/preprocess_data.py."""
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.preprocessing import run_preprocessing


def main():
    result = run_preprocessing(PROJECT_ROOT)
    print("Chapter 05 전처리 완료")
    print(result["comparison"].to_string(index=False))
    print("\n[변환 실패: 원래 결측과 구분]")
    print(result["conversions"].to_string(index=False))
    print("\n[PK/FK]")
    print(result["relationship_after"].to_string(index=False))
    print("\n[clean CSV 4개]")
    for path in result["saved_paths"]:
        print(path.relative_to(PROJECT_ROOT), "exists=", path.exists(), "bytes=", path.stat().st_size)
    print("원본 보존:", result["manifest"]["raw_preserved"])
    print("보고서: reports/ch05_preprocessing_summary.md")


if __name__ == "__main__":
    main()
