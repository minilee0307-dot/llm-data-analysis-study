"""Run fixed Chapter09 training CV, freeze selection, and evaluate Final Test."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from src.regression import run_regression_analysis


def main():
    result=run_regression_analysis(processed_dir=ROOT/'data/ch09/processed',report_dir=ROOT/'reports',test_size=.2,random_state=42)
    print('Chapter09 regression complete: 2026-11-02')
    for name in ['split_summary','feature_audit','cv_summary']:
        print(name);print(result[name].to_string(index=False))
    print('Frozen before Final Test:',result['selected_model_name'])
    print(result['model_comparison'].to_string(index=False))
    print(result['validation'].to_string(index=False))
    print('Public errors (rank labels; no original IDs or individual dates)')
    print(result['public_predictions'].head(3).to_string(index=False))
    print('Public output files:',sum('internal' not in name for name in result['output_paths']))
    print('Internal diagnostics generated locally and excluded from Git: 2')


if __name__=='__main__':
    main()
