"""Chapter08 전체 재실행: python scripts/run_midterm_project.py."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.midterm_project import run_midterm_project


def main():
    result = run_midterm_project(ROOT)
    a = result["analysis_tables"]
    print("Chapter08 원본부터 전체 재실행 완료")
    print("작성·실행일: 2026-10-27; 고정 분석 기준일: 2026-10-08")
    print(f"completed 유효 상세: {len(a['completed_order_sales'])}; 상세 보유 주문: {a['completed_order_sales'].order_id.nunique()}")
    print(f"공통 금액: {int(a['completed_order_sales'].line_total.sum()):,}원; 구매고객: {len(a['customer_sales_public'])}명")
    print(result["project_validation"].to_string(index=False))
    print(f"CSV: {len(result['saved_tables'])}; 대표 PNG: {len(result['saved_figures'])}; 공식경로 동일 PNG: {len(result['official_figures'])}")
    print("보고서: reports/ch08_midterm_report.md")


if __name__ == "__main__":
    main()
