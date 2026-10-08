# 데이터 확보와 구조 검사 기록

검사일: 2026-10-08 KST. Codex의 도움으로 파일 다운로드와 코드를 실제 실행했다. 이 기록은 1차 기획의 확보 가능성 검사이며, 본 분석·수동 단면 검토·작성자의 코드 이해도 평가를 대신하지 않는다.

## 출처와 파일 범위

[SNU-LIST 공식 저장소](https://github.com/SNU-LIST/chi-separation-atlas)의 커밋 `8c9b19d6e463a50919d9df60a512e1e8d6b00125`에서 CSV 3개, NIfTI 4개, README, LICENSE를 받았다. 원본 9개는 로컬 `data/raw/`에 보존하며 Git에서 제외한다. [LICENSE](https://github.com/SNU-LIST/chi-separation-atlas/blob/8c9b19d6e463a50919d9df60a512e1e8d6b00125/LICENSE.pdf)의 학술·연구 목적 및 재배포 제한을 확인했다. 공식 코드나 원자료를 이 저장소에 복사해 게시하지 않는다.

## 실행값

- 두 통계표는 각각 26행, `ROI_name`, `Mean`, `SD` 3열이다. 라벨표는 24행, `Index`, `ROI_name` 2열이다.
- 세 CSV의 결측 셀·전체 행 중복·기준 키 중복은 모두 0이다. 통계표의 숫자 변환 실패·비유한 숫자·음수 SD도 모두 0이다.
- 원본 라벨 이름의 작은따옴표·앞뒤 공백을 정규화한 연결 키로 비교하면 각 통계표와 24개 라벨이 모두 대응한다. 통계표 전용 2개는 `Whole thalamus`, `Whole white matter`이다.
- 영상 크기는 모두 `(193, 229, 193)`, 세 지도의 affine은 라벨과 일치한다. 지도 헤더의 복셀 크기는 `(1, 1, 1)`, 공간 단위는 mm이다. 이는 좌표 단위이며 **영상 신호 단위 ppm은 공식 README로 확인**했다.
- 라벨은 `uint16`, 값은 정수이며 배경 0과 ID 1–24이다. 세 지도는 `float64`이고 NaN·무한값은 모두 0개이다.
- χdia 통계표 Mean 26개는 모두 음수이다. χdia·χpara 지도는 ROI 내부 음수 복셀이 모두 0개이다. 공식 설명은 χdia 지도가 절댓값임을 명시한다.

기계가 읽을 수 있는 전체 실행 기록, 원본 해시와 URL은 [data-check.json](data-check.json)에 있다. 숫자·부호가 이상해 보인다는 이유로 원본을 덮어쓰지 않았다. README의 모집단 인원 설명과 성별 인원 합계가 일치하지 않는 부분은 이 분석에 개인별 인구통계 자료를 사용할 수 있다는 근거로 삼지 않는다.

## 재실행

Python 3.12 환경에서 프로젝트의 `requirements.txt`를 설치하고 저장소 루트에서 실행한다.

```bash
python -m pip install -r data-analysis-project/requirements.txt
python data-analysis-project/scripts/check_atlas.py
```

직접 작성한 검사 스크립트는 고정 커밋의 파일이 로컬에 없을 때 내려받으며, 기존 로컬 원본은 덮어쓰지 않는다. 출력 JSON의 실행 시각과 환경 버전은 재실행 시 갱신된다. 원본 무결성은 최초 검사 JSON의 SHA-256과 재실행 후 값을 비교한다. 네트워크 접근이 필요하고 실제 MRI 자료를 사용하는 실행이므로, 합성 테스트 배열을 확보 근거로 대신하지 않는다.

## 아직 수행하지 않은 작업

본 분석용 ROI 집계표 생성, QSM이 가까운 영역 쌍 비교, 침식 후 민감도 실험, MRI 단면 마스크 검토, 공개 통계 SD의 정확한 산출 방식 문헌 확인은 후속 단계에서 수행한다. 확보·구조 검사는 완료했으나 이 작업들의 결과를 이미 얻은 것처럼 보고하지 않는다.
