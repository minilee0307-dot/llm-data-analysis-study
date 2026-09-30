# 데이터 출처

Chapter 03에서 보존한 수업용 가상 쇼핑몰 CSV 4개를 2026-09-30에 바이트 변경 없이 복사했다. 고객 이름은 Faker 생성값이며 실제 고객 정보가 아니다. Notebook과 결과 CSV에는 고객 이름을 출력하지 않는다.

- [원본 생성 코드](https://github.com/GilbertMoon/llm-data-analysis-course/blob/c72cab8def2a3ff99822d3d77da01998e28cb564/scripts/generate_sample_data.py)
- [Chapter 03 데이터 출처](../../chapter03/data/README.md)

실행일에 따라 날짜가 달라질 수 있어 데이터를 재생성하지 않았다. Notebook에서 아래 해시를 검사한다.

| 파일 | SHA-256 |
| --- | --- |
| customers.csv | cd53b7f52f960a13a67f509230f5a5ab6c68b3cdce2158ff57e6fce8a32917d8 |
| order_items.csv | a7a5c3942b0886c66cb38cc6a10fdfa68dbcde90e8642585dee49c4bd104063a |
| orders.csv | 67cc403001e68134ff2fca73266a8f3b706aca05741c593d30513d4143d1fb7e |
| products.csv | 46ff06753ade3e71011ee08dd366148dcd9c36521f111840cead0a9d1047e405 |
