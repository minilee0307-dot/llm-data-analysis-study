"""python scripts/run_visualization.py. 원본/clean을 수정하지 않는 Chapter07 재실행."""
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from src.visualization import (setup_korean_font,prepare_visualization_data,
    create_all_figures,create_visualization_summary,save_visualization_outputs,
    build_visualization_report)

def main():
    font=setup_korean_font();data=prepare_visualization_data(ROOT/'data'/'processed')
    paths,checks=create_all_figures(data,ROOT/'chapter07'/'images',show=False)
    summary=create_visualization_summary(data)
    csvs=save_visualization_outputs(data,ROOT/'reports',checks)
    report=ROOT/'reports'/'ch07_visualization_summary.md'
    report.write_text(build_visualization_report(summary,data,checks),encoding='utf-8')
    print('Chapter07 시각화 완료; 분석 기준일 2026-10-08; 작성일 2026-10-11')
    print('한글 폰트:',font['font_family']);print('기간:',data['date_range'])
    print('completed 상세:',len(data['completed_order_sales']),' / 주문:',data['completed_order_sales'].order_id.nunique(),' / 금액:',int(data['completed_order_sales'].line_total.sum()))
    print('집계 검증:',int(data['visualization_validation'].passed.sum()),'/',len(data['visualization_validation']))
    print('artist 검증:',int(checks['통과'].sum()),'/',len(checks))
    print('PNG:',len(paths),'CSV:',len(csvs),'Markdown:',report.relative_to(ROOT))

if __name__=='__main__':main()
