# LLM을 활용한 빅데이터 분석 실습

공식 수업의 합성 쇼핑몰 데이터를 사용한 실습 저장소다. 코드 실행과 검증, 답안 정리에 Codex의 도움을 받았고, 제안과 실제 실행 결과를 구분해 기록했다.

| 실습 | 주 제출물 | 내용 |
| --- | --- | --- |
| Chapter 01 | [답안](chapter01/chapter01.md) | 분석 질문 구체화 |
| Chapter 02 | [답안](chapter02/chapter02.md) | 환경 설정과 실행 검증 |
| Chapter 03 | [Notebook](chapter03/chapter03.ipynb) | 데이터 구조와 품질 확인 |
| Chapter 04 | [Notebook](chapter04/chapter04.ipynb) | pandas 선택·병합·집계 |
| Chapter 05 | [Notebook](chapter05/chapter05.ipynb) | 원본 보존, 전처리와 재검증 |
| Chapter 06 | [Notebook](chapter06/chapter06.ipynb) | 동일 분석 범위에서 EDA 질문과 검증 |
| Chapter 07 | [Notebook](chapter07/chapter07.ipynb) | 질문에 맞는 시각화, 집계값 교차 검증과 해석 |
| Chapter 08 | [Notebook](chapter08/chapter08.ipynb) | 원본부터 전처리·분석·검증·보고서까지 재현하는 종합 실습 |

Chapter 05·06·07은 `data/raw` → `data/processed` → 집계·검증 → 시각화 순서로 연결된다. Chapter 05의 전처리 연습용 dirty CSV를 사용하므로 Chapter 03·04의 원본과 결과가 같을 필요는 없다. 출처와 원본 해시는 `data/raw/README.md`에 기록한다. 이전 챕터의 데이터는 각각의 폴더에 보존한다.

Python 3.14.3 가상환경에서 루트의 `requirements.txt`를 설치한 뒤 다음 순서로 재실행한다.

```bash
python scripts/preprocess_data.py
python scripts/run_eda.py
python scripts/run_visualization.py
python scripts/run_midterm_project.py
```

Chapter 08은 같은 raw 4개를 임시 작업 폴더에서 다시 전처리하고 `ch08_*` 결과를 생성한다. 기존 Chapter 05~07의 clean과 보고서는 덮지 않는다. 날짜 처리 전 FAIL 기록과 최종 공통 분석 범위의 PASS를 함께 남겼다.

각 Notebook도 해당 챕터 폴더에서 처음부터 끝까지 실행할 수 있다. 실제 실행 출력, 처리·제외 이유, LLM 제안의 채택 판단, 재실행 결과는 Notebook과 보고서에 담았다. GitHub 게시와 eTL 접수 상태는 별도로 확인하며, Notebook의 상태 기록을 따른다.

자유 주제인 **데이터분석 프로젝트 1차 과제 — 프로젝트 기획**은 이 챕터 실습들과 별개의 제출물이다. [프로젝트 기획안](data-analysis-project/01_proposal/01_proposal.md)은 공개 χ-separation 뇌지도의 영역별 특성과 ROI 경계 민감도를 분석하는 계획이다. 실제 파일 확보와 구조 검사 근거는 [프로젝트 폴더](data-analysis-project/README.md)에 정리했다.
