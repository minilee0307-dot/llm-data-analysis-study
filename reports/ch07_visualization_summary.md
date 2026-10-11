# Chapter 07 시각화 요약

작성·실행일: 2026-10-11. 분석 기준일은 Chapter06과 같은 2026-10-08로 고정했다.

## 분석 범위

2025-07-02~2026-08-28 양 끝 포함. completed, 유효 주문일, 기준일 이하. 정제 후 남은 상세 421행·금액 있는 주문 175건·134,523,000원. 금액은 quantity×unit_price이며 원래 전체 청구금액이나 회계상 순매출이 아니다.

## 질문과 그래프
```text
         질문      그래프                      범위                오해 방지         이미지
 카테고리 금액 비교       막대        completed+유효과거날짜       0축·금액내림차순·원 단위 graph01.png
   월별 금액 변화        선        동일 completed 모집단    월순서·14개월달력·누락은NaN graph02.png
상품 목록 가격 분포    히스토그램          전체 clean 상품96개    전체96+확대95·범위밖1 공개 graph03.png
목록 가격과 판매수량      산점도       동일 completed 판매상품     한점=상품·전체/확대범위 명시 graph04.png
  구매금액 상위고객     가로막대 동일 completed 구매고객 Top10     익명순위·반복/객단가와함께판단 graph05.png
  주문 상태별 건수       막대         전체 clean 주문298건        완료금액모집단과구분·0축 graph06.png
bins별 모양 변화 히스토그램 비교           동일 전체96/확대95개 bins10/20/30·표본별합계검증 graph07.png
```

## 범위와 제외 영향
```text
                 범위  상세행수  주문수      금액합계                             주석
전체 clean 상세 (매출 아님)   724  297 244374000
       completed 전체   430  178 137335000
 completed 날짜 결측 제외     6    2   1903000                    금액분석의 공통 제외
 completed 미래 후보 제외     3    1    909000                  기준일 이후를 공통 제외
          최종 분석 모집단   421  175 134523000 금액 상세가 없는 조건충족 주문 1건; 평균 분모 제외
```

## 일부 상세가 제외된 주문의 민감도
```text
            분석 범위  상세행수  주문수      금액합계   남은상세 주문금액평균
 남은 유효 상세 포함 (기본)   421  175 134523000 768702.857143
일부 상세 제외 주문 전부 제외   377  157 120972000 770522.292994
```

## 집계 검증
```text
              check    actual  expected  passed
     FK customer_id         0         0    True
        FK order_id         0         0    True
      FK product_id         0         0    True
     orders 병합 행 증가         0         0    True
   products 병합 행 증가         0         0    True
  customers 병합 행 증가         0         0    True
집계 전 clean 독립 계산 합계 134523000 134523000    True
           병합 상세 합계 134523000 134523000    True
            카테고리 합계 134523000 134523000    True
               월 합계 134523000 134523000    True
              도시 합계 134523000 134523000    True
            결제수단 합계 134523000 134523000    True
              고객 합계 134523000 134523000    True
          월×카테고리 합계 134523000 134523000    True
          도시 고객수 합계       150       150    True
           결제수단 주문수       175       175    True
           상품 금액 합계 134523000 134523000    True
       달력 재색인 금액 합계 134523000 134523000    True
           전체 상태 건수       298       298    True
        히스토그램 전체 표본        96        96    True
```

## artist와 원본 집계의 교차 검증
```text
          graph                               그래프 검증         실제값         기대값   통과
 category_sales                          bar heights 134523000.0 134523000.0 True
 category_sales                                범주 순서         7.0         7.0 True
 category_sales                               값 축 시작         0.0         0.0 True
  monthly_sales                               line y 134523000.0 134523000.0 True
  monthly_sales                            line x 달력        14.0        14.0 True
  monthly_sales                                시간 정렬         1.0         1.0 True
  monthly_sales                     누락 월을 0으로 채우지 않음         0.0         0.0 True
  product_price                       전체 hist counts        96.0        96.0 True
  product_price                       확대 hist counts        95.0        95.0 True
  product_price                              전체=확대+밖        96.0        96.0 True
 price_quantity                        전체 scatter xy        95.0        95.0 True
 price_quantity             0~200,000원 확대 scatter xy        94.0        94.0 True
  top_customers                          barh widths  41420000.0  41420000.0 True
  top_customers                              익명 라벨 수        10.0        10.0 True
  top_customers                               값 축 시작         0.0         0.0 True
   order_status                   status bar heights       298.0       298.0 True
   order_status                               값 축 시작         0.0         0.0 True
bins_comparison           전체 96개 bins=10 hist counts        96.0        96.0 True
bins_comparison           전체 96개 bins=20 hist counts        96.0        96.0 True
bins_comparison           전체 96개 bins=30 hist counts        96.0        96.0 True
bins_comparison 확대 95개 · 범위 밖 1개 bins=10 hist counts        95.0        95.0 True
bins_comparison 확대 95개 · 범위 밖 1개 bins=20 hist counts        95.0        95.0 True
bins_comparison 확대 95개 · 범위 밖 1개 bins=30 hist counts        95.0        95.0 True
```

## 해석 원칙과 한계

카테고리 금액이 크다고 선호도나 이익이 높다고 단정하지 않았다. 월별선은 시간 정렬을 확인하고 누락 월을 임의의 0으로 바꾸지 않았다. 실제 추출 시작·종료일이 없어 경계 월 수집 완전성은 확인할 수 없다. 가격9,999,999원 후보는 전체분포에 보존하고 확대95개와 범위밖1개를 함께 표시했다. 목록 가격은 주문 당시 unit_price와 다르다. 산점도는 인과를, Top10 고객은 충성도를 증명하지 않는다. 상태분포만으로 취소·환불의 원인도 알 수 없다. 그래프별 원본값·관찰·판단·업무의미·한계는 chapter07/chapter07.ipynb에 기록했다.
