# Chapter 09. 회귀 분석으로 숫자 예측하기

주 제출물은 [실행 결과가 저장된 Notebook](chapter09.ipynb)이다. 공식 회귀 Notebook·실습 가이드·eTL 요구사항을 기준으로 작성했다. 별도의 χ-separation 뇌지도 프로젝트와 구분되는 수업 실습이다.

공식 공통 Raw4개(150/100/300/764행)를 커밋 `6105f42bd8294cb364dde6dcc2fee71c32e14794`의 URL·SHA-256으로 검증했다. 기존 Chapter05~08 오류 탐지용 입력과 섞지 않고 `data/ch09/raw`, `data/ch09/processed`에 준비한다. 학습 전에 전체 데이터의 median 등 통계를 학습하지 않는다.

대상은 취소·환불을 포함한 전체300주문의 상세 금액 합이다. 원본 Decimal 계산과300개 개별 Target이 일치하며 총합255,610,000원이다. 허용 Feature6개, 금지 Feature11개를 감사했고 PK/FK·Target·one_to_one/many_to_one 관계를 확인했다.

Train244건(2025-07-09~2026-04-13), Final Test56건(2026-04-14~2026-07-08)을 엄격한 날짜순으로 나눴다. CV도 고유 날짜 TimeSeriesSplit5Fold로 경계를 나누며 전처리는 각 Fold의 Train Pipeline에서만 fit한다. 비Baseline 후보 중 CV MAE가 낮은 Random Forest를 manifest로 고정한 뒤 Baseline과 함께 Final Test에서 평가했다.

RF의 CV MAE431,319.99원은 Linear455,325.13원보다 낮지만 Baseline421,924.14원보다 높았다. Final Test에서 RF MAE458,819.92원·RMSE548,190.45원·R²−0.1033, Baseline MAE443,449.65원 대비 개선율−3.47%다. 최종 판단은 **현재 데이터로는 사용 보류**이며 Test를 보고 새 설정을 선택하지 않았다.

Notebook30셀·코드14개 실행 오류0, 최종 Validation15개·Target검증18개·전처리15개·지표8개·그래프4개가 통과했다. 공개 그림2개, 오차 사례3개, [실제 LLM 검토와 반영 기록](llm_review.md)을 포함했다. 작성·실행·검토에는 Codex의 도움을 받았다.

재현 환경은 Python3.14.3, pandas3.0.5, NumPy2.5.3, sklearn1.9.0, SciPy1.18.1, joblib1.6.0이며 `requirements.txt`에 기록했다. 저장소 루트에서 다음을 실행한다.

```text
python scripts/prepare_ch09_data.py
python scripts/run_regression_analysis.py
```

원본 캐시와 Internal CSV2개는 생성하되 Git에서 제외한다. 공개 결과에는 순위 라벨만 남겼다. 두 스크립트 재실행의 전체25개 산출물(Internal2개 포함) 해시가 일치하고 기존 raw/clean8개는 변경하지 않았다. 프로필의 과거 시점과 예정 결제수단 가용성은 가정이며 실제 운영 전에 확인해야 한다. 신규 고객에 대한 일반화도 입증하지 않았다.

[공개 보고서](../reports/ch09_regression_report.md), [Validation](../reports/ch09_regression_validation.csv), [Train CV](../reports/ch09_regression_cv_summary.csv), [최종 평가](../reports/ch09_regression_model_comparison.csv)를 확인할 수 있다. 온라인 게시와 eTL 접수 상태는 Notebook 상단에 별도로 기록한다.
