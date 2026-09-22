# 데이터 출처와 재현 방법

공식 수업 저장소: https://github.com/GilbertMoon/llm-data-analysis-course/tree/c72cab8def2a3ff99822d3d77da01998e28cb564

수업 실습에서 이미 생성한 가상 쇼핑몰 CSV 4개를 2026-09-22에 바이트 변경 없이 복사했다. 고객 이름은 Faker 생성값이다. 원본 생성 코드는 가입일과 주문일을 별도로 생성하며, 실행 날짜에 따라 결과 날짜가 바뀔 수 있어 이번에는 재생성하지 않았다.

원본 생성 코드: https://github.com/GilbertMoon/llm-data-analysis-course/blob/c72cab8def2a3ff99822d3d77da01998e28cb564/scripts/generate_sample_data.py

검증에 사용한 Python: 3.14.3. 정확한 패키지 버전은 ../requirements.txt에 기록했다.

| 파일 | SHA-256 |
| --- | --- |
| customers.csv | cd53b7f52f960a13a67f509230f5a5ab6c68b3cdce2158ff57e6fce8a32917d8 |
| order_items.csv | a7a5c3942b0886c66cb38cc6a10fdfa68dbcde90e8642585dee49c4bd104063a |
| orders.csv | 67cc403001e68134ff2fca73266a8f3b706aca05741c593d30513d4143d1fb7e |
| products.csv | 46ff06753ade3e71011ee08dd366148dcd9c36521f111840cead0a9d1047e405 |
