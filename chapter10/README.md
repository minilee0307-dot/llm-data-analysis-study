# Chapter 10. 분류 분석으로 주문 취소 여부 예측하기

[실행 결과가 저장된 Notebook](chapter10.ipynb)이 제출물이다. 공식 공통 원본 4개를 고정한 SHA-256과 대조하고 별도 `data/ch10/` 폴더에 준비한다.

`completed=0`, `cancelled=1`로 248개 주문을 분류했고 `refunded` 52건을 제외했다. 가입일이 주문일보다 늦은 이진 분류 대상 45건을 확인해 `days_since_signup` 입력을 제외했다. 분석 대상과 원본 날짜는 유지했다.

주문 단위 층화 분할은 Train 148건, Validation 50건, Final Test 50건이다. Train에서만 전처리를 학습하고 Validation으로 Logistic Regression과 Threshold 0.45를 고정했다. Final Test Accuracy는 0.6000, Precision은 0.3158, Recall은 0.4615, F1은 0.3750이다. 취소 13건 중 6건을 탐지했고 정상 주문 13건도 표시해 현재 사용을 보류했다.

저장소 루트에서 실행한다.

```bash
python -m pip install -r requirements.txt
python scripts/prepare_ch10_data.py
python scripts/run_classification_analysis.py
```

원본 캐시와 내부 예측 자료는 Git에서 제외한다. 공개 결과와 지표 검증은 [Validation 보고서](../reports/ch10_classification_validation.csv), 별도 검토와 반영은 [LLM 검토 기록](llm_review.md)에 남겼다. 작성, 실행, 검토에 Codex의 도움을 받았다.

**PARTIAL**. [최종 Notebook 파일 URL](https://github.com/minilee0307-dot/llm-data-analysis-study/blob/main/chapter10/chapter10.ipynb)의 eTL 접수 확인 대기.
