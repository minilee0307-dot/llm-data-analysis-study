"""프로젝트 루트에서 python scripts/run_eda.py로 실행한다."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from src.eda import load_processed_sales_data,run_basic_eda,save_eda_outputs,build_eda_report

def main():
    results=run_basic_eda(load_processed_sales_data(ROOT/'data'/'processed'))
    paths=save_eda_outputs(results,ROOT/'reports')
    report=ROOT/'reports'/'ch06_eda_summary.md'
    report.write_text(build_eda_report(results),encoding='utf-8')
    print('Chapter06 EDA 완료 — completed, 유효 주문일, 2026-10-08 기준')
    print(results['parameters'].to_string(index=False))
    print(results['scope'].to_string(index=False))
    print(results['category_sales'].to_string(index=False))
    print('검증 통과:',int(results['validation']['통과'].sum()),'/',len(results['validation']))
    print('CSV 저장:',len(paths),'개; 요약:',report.relative_to(ROOT))

if __name__=='__main__': main()
