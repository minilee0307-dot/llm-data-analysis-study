# Chapter 05 전처리 요약

기준일: 2026-10-08. 강사 저장소 b1597e1의 Chapter 05 전용 오류 포함 샘플을 사용했다.
실제 고객 자료가 아닌 수업용 합성 데이터다. Notebook과 스크립트는 같은 함수를 호출한다.

## 전처리 전후 실제 결과

| dataset     |   rows_before |   columns_before |   missing_cells_before |   full_row_duplicates_before |   key_missing_before |   key_duplicates_before |   rows_after |   columns_after |   missing_cells_after |   full_row_duplicates_after |   key_missing_after |   key_duplicates_after |
|:------------|--------------:|-----------------:|-----------------------:|-----------------------------:|---------------------:|------------------------:|-------------:|----------------:|----------------------:|----------------------------:|--------------------:|-----------------------:|
| customers   |           152 |                6 |                      6 |                            2 |                    0 |                       2 |          150 |              11 |                     2 |                           0 |                   0 |                      0 |
| products    |           102 |                4 |                      0 |                            2 |                    0 |                       2 |           96 |               5 |                     0 |                           0 |                   0 |                      0 |
| orders      |           302 |                5 |                      0 |                            2 |                    0 |                       2 |          298 |              10 |                     9 |                           0 |                   0 |                      0 |
| order_items |           765 |                5 |                      0 |                            2 |                    0 |                       2 |          724 |               7 |                     0 |                           0 |                   0 |                      0 |

위 결측 셀 수는 파생 컬럼까지 포함한다. orders의 처리 후 결측 9셀은 원래 주문일 3셀과
그 날짜에서 만들어진 월 3셀·요일 3셀이다. 날짜 오류가 9건이라는 뜻은 아니다.
원래 컬럼만 비교하면 customers 6→2셀, products 0→0셀, orders 0→3셀, order_items 0→0셀이다.

## 숫자·날짜 변환

| dataset     | column      | kind    |   input_rows |   original_missing |   parse_failures_before_formatting |   comma_removed |   recovered_unit_suffix |   new_parse_failures |   missing_after_conversion |
|:------------|:------------|:--------|-------------:|-------------------:|-----------------------------------:|----------------:|------------------------:|---------------------:|---------------------------:|
| customers   | age         | numeric |          150 |                  4 |                                  2 |               0 |                       0 |                    2 |                          6 |
| products    | price       | numeric |          100 |                  0 |                                  6 |               4 |                       0 |                    2 |                          2 |
| order_items | quantity    | numeric |          763 |                  0 |                                  5 |               0 |                       3 |                    2 |                          2 |
| order_items | unit_price  | numeric |          763 |                  0 |                                  7 |               5 |                       0 |                    2 |                          2 |
| customers   | signup_date | date    |          150 |                  0 |                                  2 |               0 |                       0 |                    2 |                          2 |
| orders      | order_date  | date    |          300 |                  0 |                                  3 |               0 |                       0 |                    3 |                          3 |

`original_missing`과 `new_parse_failures`를 따로 셌다. 이 표는 완전중복 제거 후 변환 시점이다.
`parse_failures_before_formatting`은 쉼표/단위 정리 전, `new_parse_failures`는 정리 후 남은 실패다.
쉼표 제거 횟수도 별도로 기록했다. 수량에서 숫자+`개`로 정확히 해석되는 표기만 복구했다.
`three`, `unknown`은 임의 해석하지 않았다.

## 처리 기준과 실제 변경

- pandas 3의 string dtype을 포함해 문자열 앞뒤 공백을 정리했고 빈 문자열은 결측으로 처리했다.
- 나이 결측/변환 실패 6건은 18–100 범위의 관측값 중앙값 41로 대체하고 `age_imputed`를 남겼다. 나이 150은 삭제하지 않고 후보 플래그로 보존했다.
- 도시 결측 2건은 Unknown으로 구분했다.
- 완전중복만 제거했다. 고유 ID의 충돌은 전부 격리하도록 했고 현재 충돌은 없다. 주문 상세의 주문 ID 반복은 유지했다.
- 상태는 completed/cancelled/refunded로 표준화했다. 카테고리 내부 공백은 명시한 세 가지 표기만 매핑했다.
- 숫자 변환 실패와 비양수 금액/수량은 정상 판매 분석에서 분리했다. 오류로 확정하거나 원본에서 삭제하지 않았으며 원래 행과 사유를 `data/quarantine/`에 남겼다.
- 부모 키가 없는 행과 부모 제외 때문에 연결이 끊긴 행을 별도 사유로 격리했다.
- 날짜 실패는 NaT와 플래그로 보존했다. 미래 날짜는 기준일보다 뒤인지를 표시했으며 날짜 기반 EDA에서 별도 범위를 정하도록 했다.
- 양수이지만 큰 가격/수량은 IQR 상한 후보로 표시하고 보존했다. 임계값: {'products.price_iqr_upper': 304000.0, 'order_items.quantity_iqr_upper': 7.0}.
- 주문 월/요일과 `line_total = quantity × unit_price`를 만들었다. 전체 상세금액 합계는 244,374,000원이다. 이 값에는 취소·환불도 포함하므로 매출·순매출로 부르지 않는다.

## 격리 행 수

| dataset     | stage        |   excluded_rows |
|:------------|:-------------|----------------:|
| customers   | duplicate    |               2 |
| order_items | duplicate    |               2 |
| order_items | foreign_key  |              31 |
| order_items | numeric_rule |               8 |
| orders      | duplicate    |               2 |
| orders      | foreign_key  |               2 |
| products    | duplicate    |               2 |
| products    | numeric_rule |               4 |

`raw 행 수 = clean 행 수 + quarantine 행 수`를 각 파일에서 확인했다.
자세한 행별 사유는 `ch05_row_exclusions.csv`, 값 변경은 `ch05_processing_audit.csv`에 있다.
한 행에 사유가 둘 이상일 수 있어 사유 건수의 합계와 실제 격리 행 수는 다를 수 있다.

## 전처리 후 PK/FK

| relationship                                 |   invalid_count |
|:---------------------------------------------|----------------:|
| orders.customer_id → customers.customer_id   |               0 |
| order_items.order_id → orders.order_id       |               0 |
| order_items.product_id → products.product_id |               0 |

고유 ID 결측·중복과 FK 미연결이 모두 0이다. 모든 금액 계산식을 다시 확인했다.

## 생성된 네 파일

- `data/processed/customers_clean.csv` — 10358 bytes
- `data/processed/products_clean.csv` — 4278 bytes
- `data/processed/orders_clean.csv` — 21439 bytes
- `data/processed/order_items_clean.csv` — 23047 bytes

원본 SHA-256은 처리 전후 동일하다. `python scripts/preprocess_data.py`를 재실행하면 같은 경로에 같은 정렬·값으로 저장한다.
재실행 해시 및 저장 후 네 CSV 재읽기 검증은 제출 Notebook에 출력했다.

## 한계와 다음 EDA

이 실습의 정상 판매 범위는 실제 회계 기준을 확정한 것이 아니다. 증정·반품 의미와 변환 불가능한 값은 원본 시스템 확인이 필요하다.
나이 대체값은 실제 나이가 아니고, 가격·수량 이상후보를 포함하면 집계가 민감해질 수 있다.
가입일 2건과 주문일 3건이 NaT로 남았다.
주문 미래날짜 후보 2건이 남았다. Chapter 06 금액 비교는 completed이면서 유효 주문일≤2026-10-08인 같은 범위를 사용한다.
상세 일부가 분리되고 나머지만 남은 clean 주문은 31건이며, Chapter 06 completed·유효 과거 범위에도 18건이 있다.
그 주문의 남은 상세 합을 원래 전체 청구액으로 해석할 수 없다. 그 범위에서 상세가 전부 빠진 주문도 1건 있다.
원자료가 합성 샘플이므로 실제 사업 또는 인과관계로 일반화하지 않는다.
