# Chapter 09 회귀 분석 보고서

작성·실행일: 2026-11-02. 코드 작성·실행·검토에는 Codex의 도움을 받았다.

## 문제와 데이터
주문 접수 초기, 예정 결제수단과 고객 프로필은 알지만 장바구니 상세 확정 전이라는 교육용 시점을 가정했다. 주문 1건의 order_total을 예측한다. 현재 프로필의 age·gender·city가 과거 주문 시점에도 알려져 있었다는 가정이며, 실제 as-of 이력은 없어 운영 적용 전에 검증해야 한다. 주문 취소·환불 상태와 관계없이 공통 합성 주문 300건을 사용하며 order_status는 Feature에서 제외했다. target은 기록된 상세 합계이고 회계상 순매출이 아니다.

## Target·Feature
line_total = quantity × unit_price; order_total = order_id별 line_total 합계. 상세 개수·수량·단가·금액·사후 상태·식별자를 Feature에 넣지 않았다. 원본 Decimal 재계산과 관계 검증은 ch09_regression_target_checks.csv에 저장했다.

| column          | selected   | available_at_prediction   | target_ingredient   | post_outcome_or_id   | role            | reason                                                    |
|:----------------|:-----------|:--------------------------|:--------------------|:---------------------|:----------------|:----------------------------------------------------------|
| order_month     | True       | True                      | False               | False                | allowed_feature | 주문 접수 시 달력에서 계산하는 월(1~12)                   |
| order_dayofweek | True       | True                      | False               | False                | allowed_feature | 주문 접수 시 달력에서 계산하는 요일(월=0~일=6)            |
| age             | True       | True                      | False               | False                | allowed_feature | 접수 시 사용 가능한 고객 나이로 가정; 과거 시점 이력 없음 |
| payment_method  | True       | True                      | False               | False                | allowed_feature | 접수 초기 고객이 고른 예정 결제수단으로 가정              |
| gender          | True       | True                      | False               | False                | allowed_feature | 접수 시 고객 프로필에 이미 등록된 값으로 가정             |
| city            | True       | True                      | False               | False                | allowed_feature | 접수 시 고객 프로필 도시로 가정; 과거 변경 이력 없음      |
| avg_unit_price  | False      | False                     | True                | False                | forbidden       | 주문 상세에서 만든 목표 대리 변수                         |
| customer_id     | False      | False                     | False               | True                 | forbidden       | 고객 식별자                                               |
| item_count      | False      | False                     | True                | False                | forbidden       | 주문 상세가 확인된 뒤 계산되는 사후 집계                  |
| line_total      | False      | False                     | True                | False                | forbidden       | 목표값을 구성하는 주문 상세 금액                          |
| order_id        | False      | False                     | False               | True                 | forbidden       | 주문 식별자                                               |
| order_status    | False      | False                     | False               | True                 | forbidden       | 예측 시점 이후에 확정될 수 있는 사후 정보                 |
| order_total     | False      | False                     | True                | False                | forbidden       | 예측 대상 자체                                            |
| product_id      | False      | False                     | False               | True                 | forbidden       | 주문 상세가 확인되어야 알 수 있는 식별자                  |
| quantity        | False      | False                     | True                | False                | forbidden       | 목표값 계산 재료                                          |
| total_quantity  | False      | False                     | True                | False                | forbidden       | 주문 상세에서 만든 목표 대리 변수                         |
| unit_price      | False      | False                     | True                | False                | forbidden       | 목표값 계산 재료                                          |

## 날짜순 분리
최종 분할은 고유 날짜의 마지막 약20%다. 표의 실제 주문 수 비율은 정확히80/20일 필요가 없다. CV도 고유 날짜에 TimeSeriesSplit 5fold를 적용해 같은 날짜가 Train/Validation 경계를 넘지 않도록 공식 행 단위 CV를 강화했다.

| split   |   rows |   ratio_pct | start_date          | end_date            |
|:--------|-------:|------------:|:--------------------|:--------------------|
| train   |    244 |      81.330 | 2025-07-09 00:00:00 | 2026-04-13 00:00:00 |
| test    |     56 |      18.670 | 2026-04-14 00:00:00 | 2026-07-08 00:00:00 |

## Train CV
전처리는 매fold Train에서만 median/scaler/most-frequent/one-hot을 fit했다. 고정 후보는 Mean Dummy, Linear Regression, Random Forest(300trees, min_samples_leaf5, seed42)다. 나머지 설정을 Test 결과로 조정하지 않았다.

| model             |   n_splits |   cv_MAE_mean |   cv_MAE_std |   cv_R2_mean |
|:------------------|-----------:|--------------:|-------------:|-------------:|
| Baseline Mean     |          5 |   421,924.136 |   47,631.460 |       -0.025 |
| Random Forest     |          5 |   431,319.994 |   24,810.544 |       -0.095 |
| Linear Regression |          5 |   455,325.127 |   57,645.538 |       -0.294 |

선택 모델: **Random Forest**. 비Baseline 후보 중 Train CV MAE 평균이 가장 낮은 모델을 선택하고 manifest를 Final Test 평가 전에 파일로 고정했다. Baseline이 후보보다 좋더라도 교육용 비교를 위해 비Baseline 후보를 고정 평가한다.

## Final Test: Baseline vs Frozen Model

| model         | selection_role       |   train_MAE |    test_MAE |   test_RMSE |   test_R2 |   MAE_improvement_vs_baseline_pct |
|:--------------|:---------------------|------------:|------------:|------------:|----------:|----------------------------------:|
| Baseline Mean | baseline             | 416,266.192 | 443,449.649 | 522,189.700 |    -0.001 |                             0.000 |
| Random Forest | selected_by_train_cv | 326,438.478 | 458,819.917 | 548,190.447 |    -0.103 |                            -3.470 |

MAE는 원 단위 평균 절대오차, RMSE는 큰 오차에 더 민감한 원 단위 지표다. 선택 모델의 Baseline 대비 MAE 개선율은 -3.47%이며 음수면 더 나빴다는 뜻이다. R²는 Test 실제값 평균을 쓰는 상수예측 대비 제곱오차로 계산된다. Dummy는 Train 평균을 예측하므로 R²=0 기준과 정확히 동일하지 않다. 음수 R²는 반드시 실행 오류라는 뜻이 아니다.

## 공개 오차 사례
순위 라벨을 새로 부여했고 원본 order_id/customer_id와 개별 주문 날짜는 공개하지 않았다.

| case_label    |   actual_order_total |   predicted_order_total |      residual |     abs_error | model         |
|:--------------|---------------------:|------------------------:|--------------:|--------------:|:--------------|
| Error rank 01 |              1877000 |             605,528.716 | 1,271,471.284 | 1,271,471.284 | Random Forest |
| Error rank 02 |              1767000 |             756,889.655 | 1,010,110.345 | 1,010,110.345 | Random Forest |
| Error rank 03 |              1863000 |             861,784.708 | 1,001,215.292 | 1,001,215.292 | Random Forest |

큰 양수 잔차는 과소예측, 음수 잔차는 과대예측이다. 거래 상세를 Feature에서 제외했으므로 실제 장바구니 차이를 구분하지 못했을 가능성이 있으나 원인으로 확정하지 않는다. 실제 운영에서는 예측 시점에 이미 알려진 상품군·프로모션·고객 과거 구매이력의 시점 유효성을 먼저 확인해야 한다.

## 자동 검증

| check                                     | value         | status   |
|:------------------------------------------|:--------------|:---------|
| forbidden_feature_overlap                 | 0             | PASS     |
| strict_train_before_test                  | True          | PASS     |
| selected_model_exists_in_train_cv         | True          | PASS     |
| final_test_contains_baseline              | True          | PASS     |
| final_test_contains_frozen_selected_model | True          | PASS     |
| test_rows_for_r2                          | 56            | PASS     |
| target_and_relationship_checks            | 18            | PASS     |
| strict_cv_date_groups                     | 5             | PASS     |
| train_only_preprocessing_audit            | 15            | PASS     |
| selected_is_minimum_train_cv_mae          | Random Forest | PASS     |
| selection_manifest_unchanged              | True          | PASS     |
| exactly_baseline_and_frozen_final_models  | 2             | PASS     |
| metrics_independently_recalculated        | 8             | PASS     |
| public_prediction_identifier_overlap      | 0             | PASS     |
| graph_artist_values_match                 | 4             | PASS     |

## 검증·해석 체크리스트

| check_item                                 | status   | evidence                      |
|:-------------------------------------------|:---------|:------------------------------|
| 예측 시점·프로필 정보 가정 명시            | PASS     | report                        |
| 목표값과 계산 재료를 Feature에서 제외      | PASS     | feature_audit                 |
| 사후 주문 상태와 식별자를 Feature에서 제외 | PASS     | feature_audit                 |
| 각 Train fold에서만 전처리 fit             | PASS     | preprocessing_audit           |
| Train/Final Test 날짜 엄격 분리            | PASS     | split_summary                 |
| CV Train/Validation 날짜 엄격 분리         | PASS     | cv_folds                      |
| Train CV 최저 MAE로 비Baseline 모델 고정   | PASS     | selection_manifest            |
| 선택 파일을 먼저 저장한 뒤 Final Test 평가 | PASS     | selection_order               |
| Final Test는 Baseline과 고정모델만 비교    | PASS     | model_comparison              |
| MAE·RMSE·R²와 낮은 성능도 보고             | PASS     | model_comparison              |
| 공개 결과에 원본 식별자와 개별 날짜 제외   | PASS     | public_predictions            |
| 실제 그래프 값과 계산 지표 대조            | PASS     | artist_checks / metric_checks |

## 최종 판단
**현재 데이터로는 사용 보류**. 작은 합성 데이터와 현재 프로필 가정으로 실제 주문 금액을 보장할 수 없다. 반복 날짜, CV 변동, Baseline 대비 성능, 큰 오차를 함께 보았다. Final Test를 보고 후보나 Feature를 바꾸지 않았다.

## 재현
python scripts/prepare_ch09_data.py → python scripts/run_regression_analysis.py. 원본은 고정 공식 commit과 SHA-256으로 확인하고 기존 Chapter05~08 입력은 변경하지 않는다. Internal CSV 2개는 생성되지만 Git에서 제외하며 공개 CSV와 Notebook은 순위 라벨만 사용한다.
