# Chapter 04. pandas로 데이터에 질문하기

주 제출물: [실행 완료 Notebook](chapter04.ipynb)

2025-09-09~2026-09-09의 completed 주문에서 수량×주문 단가 합계가 가장 큰 카테고리를 확인했다. 스포츠가 31,743,000원(21.31%)으로 1위다. 원본 completed 금액과 카테고리·상품·월·고객별 합계는 모두 148,990,000원으로 일치한다.

- data/: Chapter 03와 동일한 가상 데이터, 출처와 해시 포함
- reports/: 카테고리·상품·월·고객 요약 CSV 4개
- images/: Notebook 실행 출력에서 캡처한 핵심 Evidence 6장
- requirements.txt: 실행에 사용한 패키지 버전

Python 3.14.3 가상환경에 requirements.txt를 설치하고 Notebook 전체를 실행한다. 원본 CSV는 수정하지 않으며, 결과 CSV는 다시 계산해 저장한다. 이름 대신 고객 ID 라벨을 출력한다. 본문에는 관찰·판단·한계, LLM 코드 검증, 공식 예제의 추가 실습 6문항이 포함되어 있다.

공식 [실습 가이드](https://github.com/GilbertMoon/llm-data-analysis-course/blob/main/practice/chapter04/chapter04.md)와 [제출 양식](https://github.com/GilbertMoon/llm-data-analysis-course/blob/main/practice/chapter04/templates/chapter04_assignment.md)을 따른다. 작성과 검증에는 Codex의 도움을 받았다.
