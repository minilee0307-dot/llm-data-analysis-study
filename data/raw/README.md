# Chapter 05 원본 데이터 출처와 보존

강사 공개 저장소의 **Chapter 05 전용 전처리 전 데이터** 4종을 그대로 복사했다.
공통 `data/raw`의 정상 샘플과 다른, 문자열·타입·중복·이상 후보·관계 문제를 의도적으로 넣은 수업용 합성 데이터다.
이름처럼 보이는 필드도 합성 자료이며 실제 고객 자료를 추가하지 않았다.

- 출처: [GilbertMoon/llm-data-analysis-course](https://github.com/GilbertMoon/llm-data-analysis-course/tree/b1597e10c87f5c461bdb7e3f8f9b8454ba8cbedc/practice/chapter05/data/raw)
- 원본 경로: `practice/chapter05/data/raw/`
- 확인 커밋: `b1597e10c87f5c461bdb7e3f8f9b8454ba8cbedc`
- 복사 확인일·실습 고정 기준일: 2026-10-08
- 생성 스크립트로 정상 샘플을 다시 만들지 않았다. 이번 과제에 지정된 전용 원본 4개를 사용했다.
- 강의 Notebook/가이드에는 공통 `data/raw` 경로가 남아 있지만, 공식 `scripts/preprocess_data.py`의 Chapter 05 전용 입력 안내를 기준으로 선택했다.

| 파일 | 크기(bytes) | SHA-256 |
| --- | ---: | --- |
| `customers.csv` | 5846 | `ef4e554eaae1bb0cb7605aa9e4503aad1e68bbf1eae9093def5c2d04bd26b8cc` |
| `products.csv` | 3906 | `cad0a825a29078d9451aa74fdfa9e61d474f442d2e377839eca24e9595debbf0` |
| `orders.csv` | 11345 | `bb32cb334b9e4920f68e6ef55df17d414bdc51f7c28a58fa3bf1bfb6b2aa5fa1` |
| `order_items.csv` | 14559 | `e59b236328b6b094fdcbc0142af35b7ccb54e4246e1a57180c39997582303e5f` |

전처리는 이 파일을 덮어쓰지 않는다. 결과는 `../processed/*_clean.csv`, 분석에서 분리한 원래 행과 이유는 `../quarantine/*_quarantine.csv`에 저장한다.
각 격리 행의 `raw_row_number`는 CSV 헤더를 포함한 원본 행 번호다. 완전중복 제거도 사유를 남긴다.

`../../reports/ch05_manifest.json`에 처리 전후 원본 해시와 clean 파일 해시를 기록했다.
Notebook과 `python scripts/preprocess_data.py`는 같은 전처리 함수를 호출한다.
