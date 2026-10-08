"""Chapter 05: 원본을 보존하고 변경·격리 사유를 남기는 전처리.

공식 b1597e1의 intentionally dirty Chapter 05 CSV를 사용한다.
강의 예제를 pandas 3 문자열 dtype, 실패 기록, PK/FK 검사에 맞게 보완했다.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

AS_OF_DATE = pd.Timestamp("2026-10-08")
DATASETS = ("customers", "products", "orders", "order_items")
KEYS = {"customers": "customer_id", "products": "product_id", "orders": "order_id", "order_items": "order_item_id"}
STATUS_MAP = {
    "complete": "completed", "completed": "completed", "완료": "completed",
    "cancel": "cancelled", "cancelled": "cancelled", "취소": "cancelled",
    "refund": "refunded", "refunded": "refunded", "환불": "refunded",
}
CATEGORY_MAP = {"생활 용품": "생활용품", "전자 기기": "전자기기", "뷰 티": "뷰티"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_raw_data(project_root: Path) -> dict[str, pd.DataFrame]:
    return {name: pd.read_csv(project_root / "data" / "raw" / f"{name}.csv") for name in DATASETS}


def quality_summary(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, df in data.items():
        key = KEYS[name]
        rows.append({
            "dataset": name, "rows": len(df), "columns": len(df.columns),
            "missing_cells": int(df.isna().sum().sum()),
            "full_row_duplicates": int(df.duplicated().sum()),
            "key_missing": int(df[key].isna().sum()), "key_duplicates": int(df[key].duplicated().sum()),
        })
    return pd.DataFrame(rows)


def validate_relationships(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    relations = [
        ("orders", "customer_id", "customers", "customer_id"),
        ("order_items", "order_id", "orders", "order_id"),
        ("order_items", "product_id", "products", "product_id"),
    ]
    return pd.DataFrame([
        {"relationship": f"{child}.{ck} → {parent}.{pk}",
         "invalid_count": int((data[child][ck].isna() | ~data[child][ck].isin(data[parent][pk])).sum())}
        for child, ck, parent, pk in relations
    ])


def _text(value: object) -> str:
    if pd.isna(value):
        return "<NA>"
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return str(value)


def run_preprocessing(project_root: Path) -> dict:
    """원본 4종에서 clean 4파일과 격리 행, 변경 기록, 요약을 만든다."""
    root = Path(project_root).resolve()
    raw = load_raw_data(root)
    raw_hash_before = {f"{name}.csv": sha256(root / "data/raw" / f"{name}.csv") for name in DATASETS}
    before = quality_summary(raw)
    relationship_before = validate_relationships(raw)
    work: dict[str, pd.DataFrame] = {}
    changes, conversions, trim_rows, exclusions = [], [], [], []
    excluded_indices = {name: set() for name in DATASETS}

    def log_changes(name, column, old, new, action):
        for idx in old.index:
            if _text(old.loc[idx]) != _text(new.loc[idx]):
                changes.append({"dataset": name, "raw_row_number": int(idx) + 2, "column": column,
                                "action": action, "before": _text(old.loc[idx]), "after": _text(new.loc[idx])})

    def exclude(name, reasons, stage):
        df = work[name]
        excluded = []
        for idx in df.index:
            matched = [label for label, mask in reasons.items() if bool(mask.loc[idx])]
            if matched:
                exclusions.append({"dataset": name, "raw_row_number": int(idx) + 2,
                                   "stage": stage, "reasons": " | ".join(matched)})
                excluded_indices[name].add(idx)
                excluded.append(idx)
        work[name] = df.drop(index=excluded).copy()

    # 읽을 때의 index를 유지해 원본 CSV 행 번호를 추적한다.
    for name, df in raw.items():
        clean = df.copy(deep=True)
        for col in clean.select_dtypes(include=["object", "string"]).columns:
            old = clean[col].copy()
            new = old.astype("string").str.strip().replace("", pd.NA)
            whitespace_count = int((old.notna() & old.astype("string").ne(old.astype("string").str.strip())).sum())
            blank_count = int(old.astype("string").str.strip().eq("").sum())
            trim_rows.append({"dataset": name, "column": col, "trimmed_cells": whitespace_count,
                              "blank_to_missing": blank_count})
            log_changes(name, col, old, new, "trim_or_blank_to_missing")
            clean[col] = new
        work[name] = clean
        exclude(name, {"full_row_duplicate": clean.duplicated(keep="first")}, "duplicate")

    # 동일 ID에 다른 값이 있으면 첫 행을 임의 선택하지 않고 모두 격리한다.
    for name, df in work.items():
        key = KEYS[name]
        exclude(name, {"missing_primary_key": df[key].isna(),
                       "conflicting_primary_key": df[key].duplicated(keep=False)}, "primary_key")

    def number(name, col, recover_quantity_units=False):
        old = work[name][col].copy()
        unformatted = old.astype("string").str.strip()
        failures_before_formatting = int((old.notna() & pd.to_numeric(unformatted, errors="coerce").isna()).sum())
        comma_count = int(unformatted.str.contains(",", regex=False, na=False).sum())
        text = old.astype("string").str.strip().str.replace(",", "", regex=False)
        unit_mask = text.str.fullmatch(r"\d+개", na=False) if recover_quantity_units else pd.Series(False, index=old.index)
        if recover_quantity_units:
            text = text.mask(unit_mask, text.str.replace(r"개$", "", regex=True))
        converted = pd.to_numeric(text, errors="coerce")
        failure = old.notna() & converted.isna()
        conversions.append({"dataset": name, "column": col, "kind": "numeric",
                            "input_rows": len(old), "original_missing": int(old.isna().sum()),
                            "parse_failures_before_formatting": failures_before_formatting,
                            "comma_removed": comma_count,
                            "recovered_unit_suffix": int(unit_mask.sum()),
                            "new_parse_failures": int(failure.sum()),
                            "missing_after_conversion": int(converted.isna().sum())})
        log_changes(name, col, old, converted, "numeric_conversion")
        work[name][col] = converted
        return failure

    number("customers", "age")
    customers = work["customers"]
    age_median = float(customers.loc[customers["age"].between(18, 100), "age"].median())
    customers["age_imputed"] = customers["age"].isna()
    customers["age_outlier_candidate"] = customers["age"].notna() & ~customers["age"].between(18, 100)
    old_age = customers["age"].copy()
    customers["age"] = customers["age"].fillna(age_median)
    log_changes("customers", "age", old_age, customers["age"], "median_imputation")
    customers["city_imputed"] = customers["city"].isna()
    old_city = customers["city"].copy()
    customers["city"] = customers["city"].fillna("Unknown")
    log_changes("customers", "city", old_city, customers["city"], "unknown_category")

    number("products", "price")
    number("order_items", "quantity", recover_quantity_units=True)
    number("order_items", "unit_price")

    for name, col in [("customers", "signup_date"), ("orders", "order_date")]:
        old = work[name][col].copy()
        converted = pd.to_datetime(old, errors="coerce", format="mixed")
        failure = old.notna() & converted.isna()
        conversions.append({"dataset": name, "column": col, "kind": "date",
                            "input_rows": len(old), "original_missing": int(old.isna().sum()),
                            "parse_failures_before_formatting": int(failure.sum()), "comma_removed": 0,
                            "recovered_unit_suffix": 0, "new_parse_failures": int(failure.sum()),
                            "missing_after_conversion": int(converted.isna().sum())})
        work[name][col] = converted
        work[name][f"{col}_invalid"] = converted.isna()
        work[name][f"{col}_future_candidate"] = converted.gt(AS_OF_DATE)
        log_changes(name, col, old, converted, "date_conversion")

    orders = work["orders"]
    status_before = orders["order_status"].value_counts(dropna=False).rename_axis("order_status").reset_index(name="count")
    old_status = orders["order_status"].copy()
    orders["order_status"] = old_status.str.lower().replace(STATUS_MAP)
    orders["order_status_unexpected"] = ~orders["order_status"].isin(["completed", "cancelled", "refunded"])
    log_changes("orders", "order_status", old_status, orders["order_status"], "status_standardization")
    old_category = work["products"]["category"].copy()
    work["products"]["category"] = old_category.replace(CATEGORY_MAP)
    log_changes("products", "category", old_category, work["products"]["category"], "category_exact_mapping")

    # 계산 불가 또는 비양수 값은 일반 판매 범위에서 분리하고 원래 행을 남긴다.
    p = work["products"]
    exclude("products", {"price_conversion_failed": p["price"].isna(),
                         "nonpositive_price_candidate": p["price"].notna() & p["price"].le(0)}, "numeric_rule")
    i = work["order_items"]
    exclude("order_items", {"quantity_conversion_failed": i["quantity"].isna(),
                            "nonpositive_quantity_candidate": i["quantity"].notna() & i["quantity"].le(0),
                            "unit_price_conversion_failed": i["unit_price"].isna(),
                            "nonpositive_unit_price_candidate": i["unit_price"].notna() & i["unit_price"].le(0)}, "numeric_rule")

    # 원래 참조 대상이 없는 경우와 부모를 제외해 연결이 끊긴 경우를 구분한다.
    o = work["orders"]
    exclude("orders", {"customer_fk_absent_in_raw_master": ~o["customer_id"].isin(raw["customers"]["customer_id"]),
                       "customer_fk_removed_by_cleaning": o["customer_id"].isin(raw["customers"]["customer_id"]) & ~o["customer_id"].isin(work["customers"]["customer_id"])}, "foreign_key")
    i = work["order_items"]
    exclude("order_items", {
        "order_fk_absent_in_raw_master": ~i["order_id"].isin(raw["orders"]["order_id"]),
        "order_fk_removed_by_cleaning": i["order_id"].isin(raw["orders"]["order_id"]) & ~i["order_id"].isin(work["orders"]["order_id"]),
        "product_fk_absent_in_raw_master": ~i["product_id"].isin(raw["products"]["product_id"]),
        "product_fk_removed_by_cleaning": i["product_id"].isin(raw["products"]["product_id"]) & ~i["product_id"].isin(work["products"]["product_id"]),
    }, "foreign_key")

    # 통계적으로 큰 양수는 지우지 않고 후보 플래그로 다음 장에 전달한다.
    candidate_thresholds = {}
    for name, col in [("products", "price"), ("order_items", "quantity")]:
        q1, q3 = work[name][col].quantile([.25, .75])
        upper = float(q3 + 1.5 * (q3 - q1))
        candidate_thresholds[f"{name}.{col}_iqr_upper"] = upper
        work[name][f"{col}_outlier_candidate"] = work[name][col].gt(upper)

    o = work["orders"]
    o["order_month"] = o["order_date"].dt.to_period("M").astype("string")
    o["order_dayofweek"] = o["order_date"].dt.day_name()
    work["order_items"]["line_total"] = work["order_items"]["quantity"] * work["order_items"]["unit_price"]
    clean = {name: df.reset_index(drop=True) for name, df in work.items()}
    after = quality_summary(clean)
    relationship_after = validate_relationships(clean)
    assert after[["full_row_duplicates", "key_missing", "key_duplicates"]].eq(0).all().all()
    assert relationship_after["invalid_count"].eq(0).all()
    assert clean["order_items"]["line_total"].eq(clean["order_items"]["quantity"] * clean["order_items"]["unit_price"]).all()
    assert clean["orders"]["order_status_unexpected"].sum() == 0

    exclusion_table = pd.DataFrame(exclusions, columns=["dataset", "raw_row_number", "stage", "reasons"])
    change_table = pd.DataFrame(changes, columns=["dataset", "raw_row_number", "column", "action", "before", "after"])
    conversion_table = pd.DataFrame(conversions)
    trim_table = pd.DataFrame(trim_rows)
    quarantine = {}
    for name in DATASETS:
        meta = exclusion_table.loc[exclusion_table["dataset"].eq(name)].copy()
        original = raw[name].copy()
        original.insert(0, "raw_row_number", original.index + 2)
        quarantine[name] = meta.merge(original, on="raw_row_number", how="left", validate="one_to_one")
        assert len(raw[name]) == len(clean[name]) + len(quarantine[name])

    out_dir, report_dir, quarantine_dir = root / "data/processed", root / "reports", root / "data/quarantine"
    for folder in (out_dir, report_dir, quarantine_dir):
        folder.mkdir(parents=True, exist_ok=True)
    saved_paths = []
    for name in DATASETS:
        path = out_dir / f"{name}_clean.csv"
        clean[name].to_csv(path, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
        quarantine[name].to_csv(quarantine_dir / f"{name}_quarantine.csv", index=False, encoding="utf-8-sig")
        saved_paths.append(path)

    comparison = before.merge(after, on="dataset", suffixes=("_before", "_after"))
    status_after = clean["orders"]["order_status"].value_counts(dropna=False).rename_axis("order_status").reset_index(name="count")
    tables = {
        "ch05_before_after.csv": comparison,
        "ch05_conversion_checks.csv": conversion_table,
        "ch05_string_checks.csv": trim_table,
        "ch05_processing_audit.csv": change_table,
        "ch05_row_exclusions.csv": exclusion_table,
        "ch05_relationship_before.csv": relationship_before,
        "ch05_relationship_after.csv": relationship_after,
        "ch05_status_before.csv": status_before,
        "ch05_status_after.csv": status_after,
    }
    for filename, frame in tables.items():
        frame.to_csv(report_dir / filename, index=False, encoding="utf-8-sig")
    raw_hash_after = {f"{name}.csv": sha256(root / "data/raw" / f"{name}.csv") for name in DATASETS}
    assert raw_hash_before == raw_hash_after
    manifest = {
        "source_commit": "b1597e1", "reference_date": str(AS_OF_DATE.date()),
        "raw_sha256_before": raw_hash_before, "raw_sha256_after": raw_hash_after,
        "processed_sha256": {p.name: sha256(p) for p in saved_paths},
        "age_imputation_median": age_median,
        "candidate_thresholds": candidate_thresholds,
        "raw_preserved": raw_hash_before == raw_hash_after,
    }
    (report_dir / "ch05_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = dict(raw=raw, clean=clean, before=before, after=after, comparison=comparison,
                  conversions=conversion_table, string_checks=trim_table, audit=change_table,
                  exclusions=exclusion_table, quarantine=quarantine,
                  relationship_before=relationship_before, relationship_after=relationship_after,
                  status_before=status_before, status_after=status_after,
                  manifest=manifest, saved_paths=saved_paths)
    (report_dir / "ch05_preprocessing_summary.md").write_text(build_preprocessing_report(result), encoding="utf-8")
    return result


def build_preprocessing_report(result: dict) -> str:
    c = result["clean"]
    m = result["manifest"]
    excluded = result["exclusions"].groupby(["dataset", "stage"]).size().rename("excluded_rows").reset_index()
    raw_counts = result["raw"]["order_items"].drop_duplicates().groupby("order_id").size()
    clean_counts = c["order_items"].groupby("order_id").size()
    order_rows = c["orders"]
    kept_count = order_rows["order_id"].map(clean_counts).fillna(0)
    original_count = order_rows["order_id"].map(raw_counts).fillna(0)
    partial = kept_count.gt(0) & kept_count.lt(original_count)
    past_completed = order_rows["order_status"].eq("completed") & order_rows["order_date"].notna() & order_rows["order_date"].le(AS_OF_DATE)
    return f'''# Chapter 05 전처리 요약

기준일: 2026-10-08. 강사 저장소 b1597e1의 Chapter 05 전용 오류 포함 샘플을 사용했다.
실제 고객 자료가 아닌 수업용 합성 데이터다. Notebook과 스크립트는 같은 함수를 호출한다.

## 전처리 전후 실제 결과

{result["comparison"].to_markdown(index=False)}

위 결측 셀 수는 파생 컬럼까지 포함한다. orders의 처리 후 결측 9셀은 원래 주문일 3셀과
그 날짜에서 만들어진 월 3셀·요일 3셀이다. 날짜 오류가 9건이라는 뜻은 아니다.
원래 컬럼만 비교하면 customers 6→2셀, products 0→0셀, orders 0→3셀, order_items 0→0셀이다.

## 숫자·날짜 변환

{result["conversions"].to_markdown(index=False)}

`original_missing`과 `new_parse_failures`를 따로 셌다. 이 표는 완전중복 제거 후 변환 시점이다.
`parse_failures_before_formatting`은 쉼표/단위 정리 전, `new_parse_failures`는 정리 후 남은 실패다.
쉼표 제거 횟수도 별도로 기록했다. 수량에서 숫자+`개`로 정확히 해석되는 표기만 복구했다.
`three`, `unknown`은 임의 해석하지 않았다.

## 처리 기준과 실제 변경

- pandas 3의 string dtype을 포함해 문자열 앞뒤 공백을 정리했고 빈 문자열은 결측으로 처리했다.
- 나이 결측/변환 실패 {int(c["customers"]["age_imputed"].sum())}건은 18–100 범위의 관측값 중앙값 {m["age_imputation_median"]:g}로 대체하고 `age_imputed`를 남겼다. 나이 150은 삭제하지 않고 후보 플래그로 보존했다.
- 도시 결측 {int(c["customers"]["city_imputed"].sum())}건은 Unknown으로 구분했다.
- 완전중복만 제거했다. 고유 ID의 충돌은 전부 격리하도록 했고 현재 충돌은 없다. 주문 상세의 주문 ID 반복은 유지했다.
- 상태는 completed/cancelled/refunded로 표준화했다. 카테고리 내부 공백은 명시한 세 가지 표기만 매핑했다.
- 숫자 변환 실패와 비양수 금액/수량은 정상 판매 분석에서 분리했다. 오류로 확정하거나 원본에서 삭제하지 않았으며 원래 행과 사유를 `data/quarantine/`에 남겼다.
- 부모 키가 없는 행과 부모 제외 때문에 연결이 끊긴 행을 별도 사유로 격리했다.
- 날짜 실패는 NaT와 플래그로 보존했다. 미래 날짜는 기준일보다 뒤인지를 표시했으며 날짜 기반 EDA에서 별도 범위를 정하도록 했다.
- 양수이지만 큰 가격/수량은 IQR 상한 후보로 표시하고 보존했다. 임계값: {m["candidate_thresholds"]}.
- 주문 월/요일과 `line_total = quantity × unit_price`를 만들었다. 전체 상세금액 합계는 {c["order_items"]["line_total"].sum():,.0f}원이다. 이 값에는 취소·환불도 포함하므로 매출·순매출로 부르지 않는다.

## 격리 행 수

{excluded.to_markdown(index=False)}

`raw 행 수 = clean 행 수 + quarantine 행 수`를 각 파일에서 확인했다.
자세한 행별 사유는 `ch05_row_exclusions.csv`, 값 변경은 `ch05_processing_audit.csv`에 있다.
한 행에 사유가 둘 이상일 수 있어 사유 건수의 합계와 실제 격리 행 수는 다를 수 있다.

## 전처리 후 PK/FK

{result["relationship_after"].to_markdown(index=False)}

고유 ID 결측·중복과 FK 미연결이 모두 0이다. 모든 금액 계산식을 다시 확인했다.

## 생성된 네 파일

{chr(10).join('- `data/processed/' + p.name + '` — ' + str(p.stat().st_size) + ' bytes' for p in result["saved_paths"])}

원본 SHA-256은 처리 전후 동일하다. `python scripts/preprocess_data.py`를 재실행하면 같은 경로에 같은 정렬·값으로 저장한다.
재실행 해시 및 저장 후 네 CSV 재읽기 검증은 제출 Notebook에 출력했다.

## 한계와 다음 EDA

이 실습의 정상 판매 범위는 실제 회계 기준을 확정한 것이 아니다. 증정·반품 의미와 변환 불가능한 값은 원본 시스템 확인이 필요하다.
나이 대체값은 실제 나이가 아니고, 가격·수량 이상후보를 포함하면 집계가 민감해질 수 있다.
가입일 {int(c["customers"]["signup_date_invalid"].sum())}건과 주문일 {int(c["orders"]["order_date_invalid"].sum())}건이 NaT로 남았다.
주문 미래날짜 후보 {int(c["orders"]["order_date_future_candidate"].sum())}건이 남았다. Chapter 06 금액 비교는 completed이면서 유효 주문일≤2026-10-08인 같은 범위를 사용한다.
상세 일부가 분리되고 나머지만 남은 clean 주문은 {int(partial.sum())}건이며, Chapter 06 completed·유효 과거 범위에도 {int((partial & past_completed).sum())}건이 있다.
그 주문의 남은 상세 합을 원래 전체 청구액으로 해석할 수 없다. 그 범위에서 상세가 전부 빠진 주문도 {int((past_completed & original_count.gt(0) & kept_count.eq(0)).sum())}건 있다.
원자료가 합성 샘플이므로 실제 사업 또는 인과관계로 일반화하지 않는다.
'''
