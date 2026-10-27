# Chapter 08 작은 데이터 분석 프로젝트 보고서

작성·실행일: 2026-10-27. 분석 기준일은 2026-10-08로 고정했다. 코드 작성·실행·검증에 Codex의 도움을 받았다.

## 분석 목적과 범위

- 카테고리별 completed 주문 기준 금액은 어떻게 다른가?
- 월별 completed 주문 금액과 고유 주문 수는 어떻게 변하는가?
- completed 주문 금액 상위 익명 고객의 구매 횟수와 평균 주문금액은 어떤가?

금액은 completed이고 유효 주문일이 고정 기준일 이하인, 정제 후 남은 유효 상세의 quantity×unit_price 합계다. 회계상 순매출이나 이익은 아니다. 원본은 변경하지 않고 기존 Chapter05 전처리를 임시 폴더에서 원본부터 다시 실행했다.

## 원본 4파일

| dataset     |   rows |   columns |   missing_values |   duplicated_rows |
|:------------|-------:|----------:|-----------------:|------------------:|
| customers   |    152 |         6 |                6 |                 2 |
| products    |    102 |         4 |                0 |                 2 |
| orders      |    302 |         5 |                0 |                 2 |
| order_items |    765 |         5 |                0 |                 2 |

## 전처리 전후 변화

| dataset     |   rows_before |   columns_before |   missing_cells_before |   full_row_duplicates_before |   key_missing_before |   key_duplicates_before |   rows_after |   columns_after |   missing_cells_after |   full_row_duplicates_after |   key_missing_after |   key_duplicates_after |
|:------------|--------------:|-----------------:|-----------------------:|-----------------------------:|---------------------:|------------------------:|-------------:|----------------:|----------------------:|----------------------------:|--------------------:|-----------------------:|
| customers   |           152 |                6 |                      6 |                            2 |                    0 |                       2 |          150 |              11 |                     2 |                           0 |                   0 |                      0 |
| products    |           102 |                4 |                      0 |                            2 |                    0 |                       2 |           96 |               5 |                     0 |                           0 |                   0 |                      0 |
| orders      |           302 |                5 |                      0 |                            2 |                    0 |                       2 |          298 |              10 |                     9 |                           0 |                   0 |                      0 |
| order_items |           765 |                5 |                      0 |                            2 |                    0 |                       2 |          724 |               7 |                     0 |                           0 |                   0 |                      0 |

## 제외 규칙과 행 수

| dataset     | stage        | reasons                                                         |   excluded_rows |
|:------------|:-------------|:----------------------------------------------------------------|----------------:|
| customers   | duplicate    | full_row_duplicate                                              |               2 |
| order_items | duplicate    | full_row_duplicate                                              |               2 |
| order_items | foreign_key  | order_fk_absent_in_raw_master                                   |               2 |
| order_items | foreign_key  | order_fk_removed_by_cleaning                                    |               3 |
| order_items | foreign_key  | order_fk_removed_by_cleaning \| product_fk_absent_in_raw_master |               1 |
| order_items | foreign_key  | product_fk_absent_in_raw_master                                 |               1 |
| order_items | foreign_key  | product_fk_removed_by_cleaning                                  |              24 |
| order_items | numeric_rule | nonpositive_quantity_candidate                                  |               3 |
| order_items | numeric_rule | nonpositive_unit_price_candidate                                |               1 |
| order_items | numeric_rule | quantity_conversion_failed                                      |               2 |
| order_items | numeric_rule | unit_price_conversion_failed                                    |               2 |
| orders      | duplicate    | full_row_duplicate                                              |               2 |
| orders      | foreign_key  | customer_fk_absent_in_raw_master                                |               2 |
| products    | duplicate    | full_row_duplicate                                              |               2 |
| products    | numeric_rule | nonpositive_price_candidate                                     |               2 |
| products    | numeric_rule | price_conversion_failed                                         |               2 |

## PK

| dataset     | key           |   missing_count |   duplicate_count | status   |
|:------------|:--------------|----------------:|------------------:|:---------|
| customers   | customer_id   |               0 |                 0 | PASS     |
| products    | product_id    |               0 |                 0 | PASS     |
| orders      | order_id      |               0 |                 0 | PASS     |
| order_items | order_item_id |               0 |                 0 | PASS     |

## FK

| relationship                                 |   invalid_count | status   |
|:---------------------------------------------|----------------:|:---------|
| orders.customer_id → customers.customer_id   |               0 | PASS     |
| order_items.order_id → orders.order_id       |               0 | PASS     |
| order_items.product_id → products.product_id |               0 | PASS     |

## 안전한 병합

| merge                           | validate    |   before_rows |   after_rows | row_count_preserved   |   unmatched_count | status   |
|:--------------------------------|:------------|--------------:|-------------:|:----------------------|------------------:|:---------|
| order_items → orders            | many_to_one |           724 |          724 | True                  |                 0 | PASS     |
| completed details → products    | many_to_one |           421 |          421 | True                  |                 0 | PASS     |
| customer aggregates → customers | one_to_one  |            96 |           96 | True                  |                 0 | PASS     |

## line_total

| check                              | source             |   row_count |   mismatch_count | status   |
|:-----------------------------------|:-------------------|------------:|-----------------:|:---------|
| line_total = quantity × unit_price | existing rechecked |         724 |                0 | PASS     |

## 해결 전 FAIL 기록

| check                                  |     value |   expected |   affected_amount | status   |
|:---------------------------------------|----------:|-----------:|------------------:|:---------|
| completed_rows_with_invalid_order_date |         6 |          0 |           1903000 | FAIL     |
| monthly_total_before_scope_resolution  | 135432000 |  137335000 |           1903000 | FAIL     |
| completed_rows_after_fixed_as_of       |         3 |          0 |            909000 | FAIL     |

## 날짜 범위의 명시적 해결

| stage   | rule                                         |   detail_rows |   orders |    amount | action                                                            | status   |
|:--------|:---------------------------------------------|--------------:|---------:|----------:|:------------------------------------------------------------------|:---------|
| before  | completed invalid dates                      |             6 |        2 |   1903000 | 날짜를 추정하지 않고 세 금액 집계의 공통 범위에서 명시적으로 제외 | FAIL     |
| before  | completed date after 2026-10-08              |             3 |        1 |    909000 | 고정 기준일을 넘으므로 모든 금액 집계에서 공통 제외               | FAIL     |
| after   | completed + valid date + date <= fixed_as_of |           421 |      175 | 134523000 | 원래 NaT/후보 플래그는 보존하고 분석 대상만 한정                  | PASS     |

원래 NaT와 미래 후보는 남겼다. 모든 금액 집계의 공통 대상만 한정했고 날짜를 추정하거나 보완하여 PASS로 만든 것은 아니다.

## 분모와 분석 범위

| parameter                          | value      |
|:-----------------------------------|:-----------|
| analysis_as_of                     | 2026-10-08 |
| written_date                       | 2026-10-27 |
| date_start                         | 2025-07-02 |
| date_end                           | 2026-08-28 |
| eligible_orders_before_detail_join | 176        |
| orders_with_retained_details       | 175        |
| eligible_orders_without_details    | 1          |
| selected_detail_rows               | 421        |
| purchasing_customers               | 96         |
| selected_partially_retained_orders | 18         |
| selected_partial_detail_rows       | 44         |
| selected_partial_amount            | 13551000   |
| calendar_months                    | 14         |
| unobserved_months                  | 0          |
| observed_zero_amount_months        | 0          |

## 전체 상세·completed·날짜 제외

| scope                                |    amount |   detail_rows |   order_count |
|:-------------------------------------|----------:|--------------:|--------------:|
| all_order_items_not_revenue          | 244374000 |           724 |           297 |
| completed_before_date_scope          | 137335000 |           430 |           178 |
| excluded_invalid_date_completed      |   1903000 |             6 |             2 |
| excluded_after_fixed_as_of_completed |    909000 |             3 |             1 |
| final_completed_valid_date_as_of     | 134523000 |           421 |           175 |

## 독립 원본 CSV 재계산

| check                                     |    actual |   expected | status   |
|:------------------------------------------|----------:|-----------:|:---------|
| raw csv Decimal completed total           | 134523000 |  134523000 | PASS     |
| raw csv independent category amounts      |         7 |          7 | PASS     |
| raw csv independent monthly amounts       |        14 |         14 | PASS     |
| raw csv independent customer amounts      |        96 |         96 | PASS     |
| raw csv independent monthly unique orders |       175 |        175 | PASS     |
| raw csv independent selected detail rows  |       421 |        421 | PASS     |

독립 검산은 전처리의 격리 행 번호를 적용한 원본 CSV를 csv.DictReader로 다시 읽고, 원본 orders의 상태·날짜로 주문을 선택해 원본 order_items의 quantity×unit_price를 Decimal로 별도 계산했다. 같은 병합 DataFrame끼리의 총합 비교에만 의존하지 않았다.

## 같은 의미의 총합

| source           |    amount |   difference_from_completed | matches_completed   | status   |
|:-----------------|----------:|----------------------------:|:--------------------|:---------|
| completed_source | 134523000 |                           0 | True                | PASS     |
| category         | 134523000 |                           0 | True                | PASS     |
| monthly          | 134523000 |                           0 | True                | PASS     |
| customer         | 134523000 |                           0 | True                | PASS     |

## 카테고리

| category   |   total_quantity |   total_sales |   order_count |   sales_ratio |   quantity_weighted_unit_price |
|:-----------|-----------------:|--------------:|--------------:|--------------:|-------------------------------:|
| 패션       |              290 |      32940000 |            68 |         24.49 |                     113,586.21 |
| 식품       |              220 |      24731000 |            61 |         18.38 |                     112,413.64 |
| 전자기기   |              172 |      20445000 |            53 |         15.20 |                     118,866.28 |
| 뷰티       |              176 |      17166000 |            53 |         12.76 |                      97,534.09 |
| 도서       |              168 |      16895000 |            47 |         12.56 |                     100,565.48 |
| 스포츠     |              165 |      13237000 |            47 |          9.84 |                      80,224.24 |
| 생활용품   |              125 |       9109000 |            42 |          6.77 |                      72,872.00 |

## 월별

| order_month   |   total_sales |   order_count | observed_in_selected_data   | zero_amount_observed   | month_start         |   avg_order_value |
|:--------------|--------------:|--------------:|:----------------------------|:-----------------------|:--------------------|------------------:|
| 2025-07       |       9479000 |            11 | True                        | False                  | 2025-07-01 00:00:00 |        861,727.27 |
| 2025-08       |       8892000 |            17 | True                        | False                  | 2025-08-01 00:00:00 |        523,058.82 |
| 2025-09       |       4519000 |             4 | True                        | False                  | 2025-09-01 00:00:00 |      1,129,750.00 |
| 2025-10       |      12547000 |            17 | True                        | False                  | 2025-10-01 00:00:00 |        738,058.82 |
| 2025-11       |       9163000 |            16 | True                        | False                  | 2025-11-01 00:00:00 |        572,687.50 |
| 2025-12       |       8113000 |            12 | True                        | False                  | 2025-12-01 00:00:00 |        676,083.33 |
| 2026-01       |       7759000 |             8 | True                        | False                  | 2026-01-01 00:00:00 |        969,875.00 |
| 2026-02       |       7689000 |            12 | True                        | False                  | 2026-02-01 00:00:00 |        640,750.00 |
| 2026-03       |       7493000 |            13 | True                        | False                  | 2026-03-01 00:00:00 |        576,384.62 |
| 2026-04       |      11459000 |            14 | True                        | False                  | 2026-04-01 00:00:00 |        818,500.00 |
| 2026-05       |      11850000 |            12 | True                        | False                  | 2026-05-01 00:00:00 |        987,500.00 |
| 2026-06       |       9926000 |            16 | True                        | False                  | 2026-06-01 00:00:00 |        620,375.00 |
| 2026-07       |       8966000 |             8 | True                        | False                  | 2026-07-01 00:00:00 |      1,120,750.00 |
| 2026-08       |      16668000 |            15 | True                        | False                  | 2026-08-01 00:00:00 |      1,111,200.00 |

## 익명 고객 Top10

| customer_label   | city   |   order_count |   total_sales |   avg_order_value |
|:-----------------|:-------|--------------:|--------------:|------------------:|
| Customer 01      | 서울   |             3 |       6702000 |      2,234,000.00 |
| Customer 02      | 대구   |             4 |       5122000 |      1,280,500.00 |
| Customer 03      | 수원   |             3 |       4311000 |      1,437,000.00 |
| Customer 04      | 광주   |             6 |       3977000 |        662,833.33 |
| Customer 05      | 서울   |             2 |       3966000 |      1,983,000.00 |
| Customer 06      | 울산   |             4 |       3845000 |        961,250.00 |
| Customer 07      | 성남   |             4 |       3808000 |        952,000.00 |
| Customer 08      | 성남   |             4 |       3656000 |        914,000.00 |
| Customer 09      | 인천   |             4 |       3201000 |        800,250.00 |
| Customer 10      | 부산   |             4 |       2832000 |        708,000.00 |

## 전체 clean 주문 상태

| order_status   |   order_count |   order_ratio |
|:---------------|--------------:|--------------:|
| completed      |           179 |         60.07 |
| cancelled      |            62 |         20.81 |
| refunded       |            57 |         19.13 |

## 일부 상세가 남은 주문의 민감도

| scope                                           |   detail_rows |   order_count |    amount |
|:------------------------------------------------|--------------:|--------------:|----------:|
| retained_valid_details_including_partial_orders |           421 |           175 | 134523000 |
| exclude_entire_partially_retained_orders        |           377 |           157 | 120972000 |

일부 상세가 격리된 18주문을 기본 범위에 포함하므로 원래 청구총액과 다를 수 있다. 18주문을 모두 제외한 민감도도 비교했다. 총액 차이만으로 카테고리 순위나 월별 모양이 같다고 주장하지 않는다.

## 실제 그래프 값과의 대조

| 그래프 검증                 |         실제값 |         기대값 | 통과   | graph          |
|:----------------------------|---------------:|---------------:|:-------|:---------------|
| bar heights                 | 134,523,000.00 | 134,523,000.00 | True   | category_sales |
| 범주 순서                   |           7.00 |           7.00 | True   | category_sales |
| 값 축 시작                  |           0.00 |           0.00 | True   | category_sales |
| line y                      | 134,523,000.00 | 134,523,000.00 | True   | monthly_sales  |
| line x 달력                 |          14.00 |          14.00 | True   | monthly_sales  |
| 시간 정렬                   |           1.00 |           1.00 | True   | monthly_sales  |
| 누락 월을 0으로 채우지 않음 |           0.00 |           0.00 | True   | monthly_sales  |
| barh widths                 |  41,420,000.00 |  41,420,000.00 | True   | top_customers  |
| 익명 라벨 수                |          10.00 |          10.00 | True   | top_customers  |
| 값 축 시작                  |           0.00 |           0.00 | True   | top_customers  |

## 공개 고객 결과의 익명화

공개 CSV는 customer_label, city, order_count, total_sales, avg_order_value만 포함한다. 라벨은 금액 순위로 새로 붙였고 원본 customer_id·name·email·phone·address는 저장하지 않는다. 저장 CSV도 다시 읽어 컬럼과 값을 확인했다.

## 최종 Validation

| check                                  | value                | expected             | status   |
|:---------------------------------------|:---------------------|:---------------------|:---------|
| pk_integrity                           | all PASS             | all PASS             | PASS     |
| fk_integrity                           | 0                    | 0                    | PASS     |
| merge_checks_pass                      | all PASS             | all PASS             | PASS     |
| line_total_consistency                 | 0                    | 0                    | PASS     |
| completed_total_consistency            | all match            | all match            | PASS     |
| category_sales_ratio_pct_sum           | 100.0                | 100                  | PASS     |
| completed_rows_with_invalid_order_date | 0                    | 0                    | PASS     |
| completed_rows_after_fixed_as_of       | 0                    | 0                    | PASS     |
| public_customer_columns_safe           | no forbidden columns | no forbidden columns | PASS     |
| completed_scope_consistent             | True                 | True                 | PASS     |
| raw_csv_Decimal_recalculation          | all match            | all match            | PASS     |
| graph_artist_values_match              | 10                   | 10                   | PASS     |
| raw_to_clean_reproduction              | 4                    | 4                    | PASS     |
| existing_raw_clean_inputs_preserved    | 8                    | 8                    | PASS     |

## 관찰·판단·한계

| analysis   | observation                                         | interpretation                                    | caution                                                    | next_question                                                   |
|:-----------|:----------------------------------------------------|:--------------------------------------------------|:-----------------------------------------------------------|:----------------------------------------------------------------|
| category   | 패션 32,940,000원·24.49%로 최대                     | 현재 범위의 완료 상세 금액 기여가 가장 크다       | 수량·단가·원가 없이 선호나 이익의 원인으로 단정하지 않는다 | 카테고리별 수량과 수량가중 거래 단가를 나누어 비교한다          |
| monthly    | 최대 2026-08 16,668,000원; 최소 2025-09 4,519,000원 | 월별 금액과 주문 수·평균 주문금액을 함께 확인한다 | 경계 월 수집 완전성과 광고·재고·계절성은 확인하지 못했다   | 금액 차이가 큰 월의 주문 수와 카테고리 구성을 비교한다          |
| customers  | 구매고객 96명; 상위10명 41,420,000원; 주문 수 2~6회 | 상위10명은 기간 내 반복 구매 고객이다             | 상위10명은 전체 고객 분포가 아니며 미래 충성도는 모른다    | 기간·금액 기준을 바꿔 반복 구매와 고액 1회 고객을 따로 비교한다 |

## 재현성

Notebook과 python scripts/run_midterm_project.py는 같은 함수를 호출한다. 기존 raw/clean 8파일의 해시 보존과 재생성 clean 4파일의 일치를 확인했다.

## 남은 한계

광고·원가·할인·재고·추출기간의 완전성은 모른다. 월별 변동을 인과로 설명하지 않고 고객 미래가치나 충성도를 단정하지 않는다. 자동 PASS는 정해 둔 구조·수치 조건의 통과이며 데이터의 진실성이나 해석의 원인을 증명하지 않는다. 자세한 질문·관찰·판단·LLM 기록은 chapter08/chapter08.ipynb에 있다.
