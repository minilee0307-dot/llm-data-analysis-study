# Chapter 05 — 데이터 전처리

최종 답안은 [실행 완료 Notebook](chapter05.ipynb)이다.

- 최종 URL: https://github.com/minilee0307-dot/llm-data-analysis-study/blob/main/chapter05/chapter05.ipynb
- 분석 기준일: 2026-10-08
- Notebook 코드 21셀을 모두 실행했고 오류 출력은 없다.
- 공식 Notebook·추가 실습6문제와 템플릿0–7을 반영했다.
- 핵심 Evidence1–6은 Notebook의 실제 출력으로 제공한다.
- GitHub 본문·출력 표시 확인: PASS. eTL Chapter05(381907) 접수: COMPLETE — 2026-10-08 오후 4:17, 제출된 Notebook URL 확인.

## 입력과 산출물

- [원본4종 출처·SHA-256](../data/raw/README.md)
- [처리 코드](../src/preprocessing.py)
- [재실행 스크립트](../scripts/preprocess_data.py)
- [요약 보고서](../reports/ch05_preprocessing_summary.md)
- [변환 실패 검사](../reports/ch05_conversion_checks.csv)
- [행별 격리 사유](../reports/ch05_row_exclusions.csv)
- [변경 기록](../reports/ch05_processing_audit.csv)
- [원본 보존·clean4 해시](../reports/ch05_manifest.json)
- [재실행·재읽기 검증](../reports/ch05_reproduction_checks.json)
- `../data/processed/`: clean CSV4종, Chapter06에서도 같은 파일 사용.
- `../data/quarantine/`: 원래 행·행 번호·격리 사유4종.

## 재현

저장소 루트에서 환경을 준비한 뒤 실행한다.

```bash
python -m pip install -r requirements.txt
python scripts/preprocess_data.py
```

Notebook도 같은 함수를 호출한다. 이번 저장된 출력의 실제 Python은 기존 수업 프로젝트의 가상환경이며, `assignment/.venv`를 사용했다고 기록하지 않았다.

## 결과와 해석 범위

고객152→150, 상품102→96, 주문302→298, 상세765→724행. 각 파일에서 원본행=clean행+격리행을 확인했다.
원본4 해시 보존, 최종 PK/FK, 금액 계산식, 재실행 해시와 네 CSV 재읽기가 모두 PASS이다.

날짜 실패와 미래 날짜, 큰 양수 후보는 숨기지 않고 플래그로 보존했다.
`line_total`은 상세 금액이며 전체 합을 매출·순매출로 부르지 않는다.
일부 상세가 분리된 주문의 잔여금액은 원래 청구액이 아니며, 다음 EDA에서 분석 범위와 영향을 따로 확인한다.

작성·실행에는 Codex 지원을 받았고, 실제 LLM 제안과 실행 검증의 차이를 Notebook에 기록했다.
