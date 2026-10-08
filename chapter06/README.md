# Chapter 06. 데이터를 보며 질문을 만드는 EDA

주 제출물: [실행 결과가 저장된 Notebook](chapter06.ipynb)

2025-07-02~2026-08-28 양 끝 포함, 유효한 주문일이 2026-10-08 이하인 completed 거래를 분석했다. 정제 후 남은 상세 421행, 금액이 있는 주문 175건의 `quantity × unit_price` 합은 **134,523,000원**이다. 카테고리·월·도시·고객·결제수단·월×카테고리 합계가 같다. 금액 1위는 패션 32,940,000원(24.49%)이다.

입력은 [Chapter 05 clean CSV 4개](../data/processed/)다. 일부 상세가 제외된 주문 18건이 기본 분석에 남아 있으므로 주문금액은 원래 청구총액이 아닌 남은 유효 상세 합계다. 해당 주문을 전부 제외한 민감도 결과도 Notebook과 [보고서](../reports/ch06_eda_summary.md)에 기록했다. 조건은 충족하지만 상세가 없는 주문 1건은 평균의 분모에서 제외했다.

공식 Notebook의 순서를 유지하여 질문·분포·병합·집계·총합 검증·관찰/가설/추가 검증과 추가 실습 6문항을 작성했다. 핵심 실행 Evidence는 Notebook 출력 E01~E06이다. [LLM 실제 프롬프트와 응답](llm_review.md)을 기록하고 제안의 사용·수정·보류 이유를 구분했다. 작성·실행·검토에는 Codex의 도움을 받았다.

저장소 루트에서 필요한 패키지를 설치한 Python 환경으로 다음을 실행한다.

```text
python scripts/preprocess_data.py
python scripts/run_eda.py
```

기존 수업 프로젝트 가상환경(Python 3.14.3)을 재사용했으며, Notebook 전체 34개 코드 셀을 실행했다. 스크립트 산출물 23개(CSV 22개·Markdown 1개)의 해시와 주요 CSV 재읽기를 대조했다. GitHub 게시·표시 확인과 eTL 접수 상태는 Notebook 상단에 별도 기록한다.
