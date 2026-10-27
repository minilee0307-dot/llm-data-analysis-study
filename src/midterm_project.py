"""Chapter 08: 원본부터 다시 실행하는 검증 가능한 쇼핑몰 분석.

공식 Chapter08의 Gate와 공개 산출물 계약을 유지하고, Chapter05의 오류 포함
원본에 맞춰 날짜 범위 제외 이력과 csv/Decimal 독립 재계산을 추가했다.
기존 raw/processed 및 Chapter05~07 산출물은 덮어쓰지 않는다.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
import hashlib
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd

from src.preprocessing import DATASETS, KEYS, run_preprocessing, validate_relationships
from src.visualization import (
    plot_category_sales, plot_monthly_sales, plot_top_customers, setup_korean_font,
)

AS_OF = pd.Timestamp("2026-10-08 23:59:59")
WRITTEN_DATE = "2026-10-27"
PUBLIC_CUSTOMER_COLUMNS = [
    "customer_label", "city", "order_count", "total_sales", "avg_order_value",
]
FORBIDDEN_CUSTOMER_COLUMNS = {"customer_id", "name", "email", "phone", "address"}
PROJECT_QUESTIONS = [
    "카테고리별 completed 주문 기준 금액은 어떻게 다른가?",
    "월별 completed 주문 금액과 고유 주문 수는 어떻게 변하는가?",
    "completed 주문 금액 상위 익명 고객의 구매 횟수와 평균 주문금액은 어떤가?",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def input_hashes(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): sha256(p)
            for folder in ("raw", "processed")
            for p in sorted((root / "data" / folder).glob("*.csv"))}


def summarize_datasets(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.DataFrame([
        {"dataset": name, "rows": len(df), "columns": len(df.columns),
         "missing_values": int(df.isna().sum().sum()),
         "duplicated_rows": int(df.duplicated().sum())}
        for name, df in data.items()
    ])


def build_key_duplicate_checks(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, key in KEYS.items():
        missing = int(data[name][key].isna().sum())
        duplicates = int(data[name][key].dropna().duplicated().sum())
        rows.append({"dataset": name, "key": key, "missing_count": missing,
                     "duplicate_count": duplicates,
                     "status": "PASS" if missing == duplicates == 0 else "FAIL"})
    return pd.DataFrame(rows)


def _checked_merge(left, right, *, on, validate, label):
    before = len(left)
    merged = left.merge(right, on=on, how="left", validate=validate, indicator=True)
    unmatched = int(merged["_merge"].ne("both").sum())
    passed = before == len(merged) and unmatched == 0
    check = {"merge": label, "validate": validate, "before_rows": before,
             "after_rows": len(merged), "row_count_preserved": before == len(merged),
             "unmatched_count": unmatched, "status": "PASS" if passed else "FAIL"}
    assert passed, check
    return merged.drop(columns="_merge"), check


def _rebuild_raw(root: Path) -> tuple[dict, pd.DataFrame]:
    """기존 전처리를 임시 작업 폴더에서 실행하고 기존 clean과 재현성을 비교한다."""
    with TemporaryDirectory(prefix="llm-ch08-") as directory:
        temporary = Path(directory)
        raw_dir = temporary / "data/raw"
        raw_dir.mkdir(parents=True)
        for name in DATASETS:
            shutil.copyfile(root / "data/raw" / f"{name}.csv", raw_dir / f"{name}.csv")
        result = run_preprocessing(temporary)
        reproduction = []
        for name in DATASETS:
            regenerated = temporary / "data/processed" / f"{name}_clean.csv"
            existing = root / "data/processed" / f"{name}_clean.csv"
            actual, expected = sha256(regenerated), sha256(existing)
            reproduction.append({"dataset": name, "regenerated_sha256": actual,
                                 "existing_ch05_sha256": expected,
                                 "status": "PASS" if actual == expected else "FAIL"})
        reproduction = pd.DataFrame(reproduction)
        assert reproduction.status.eq("PASS").all(), "재생성 clean이 Chapter05와 불일치"
        return result, reproduction


def _parse_raw_date(value: str):
    value = value.strip()
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            continue
    return None


def _raw_number(value: str, *, quantity=False) -> Decimal:
    text = value.strip().replace(",", "")
    if quantity and text.endswith("개") and text[:-1].isdigit():
        text = text[:-1]
    return Decimal(text)


def _independent_raw_recalculation(root: Path, exclusions: pd.DataFrame) -> dict:
    """병합 표를 사용하지 않고 원본 CSV와 격리 행 번호에서 Decimal로 별도 계산한다."""
    excluded = {name: set(exclusions.loc[exclusions.dataset.eq(name), "raw_row_number"])
                for name in DATASETS}

    def retained_rows(name):
        with (root / "data/raw" / f"{name}.csv").open(encoding="utf-8-sig", newline="") as file:
            return [row for row_number, row in enumerate(csv.DictReader(file), 2)
                    if row_number not in excluded[name]]

    orders = {}
    for row in retained_rows("orders"):
        status = row["order_status"].strip().lower()
        date = _parse_raw_date(row["order_date"])
        if status in {"completed", "complete", "완료"} and date is not None and date <= AS_OF.to_pydatetime():
            orders[int(_raw_number(row["order_id"]))] = row | {"_date": date}
    category_map = {"생활 용품": "생활용품", "전자 기기": "전자기기", "뷰 티": "뷰티"}
    categories = {}
    for row in retained_rows("products"):
        text = row["category"].strip()
        categories[int(_raw_number(row["product_id"]))] = category_map.get(text, text)
    amount = Decimal(0)
    category, monthly, customer = defaultdict(Decimal), defaultdict(Decimal), defaultdict(Decimal)
    selected_orders, monthly_orders = set(), defaultdict(set)
    row_count = 0
    for row in retained_rows("order_items"):
        order_id = int(_raw_number(row["order_id"]))
        if order_id not in orders:
            continue
        order = orders[order_id]
        line = _raw_number(row["quantity"], quantity=True) * _raw_number(row["unit_price"])
        month = order["_date"].strftime("%Y-%m")
        customer_id = int(_raw_number(order["customer_id"]))
        product_id = int(_raw_number(row["product_id"]))
        amount += line
        category[categories[product_id]] += line
        monthly[month] += line
        customer[customer_id] += line
        monthly_orders[month].add(order_id)
        selected_orders.add(order_id)
        row_count += 1
    return dict(amount=amount, category=category, monthly=monthly, customer=customer,
                monthly_orders=monthly_orders, selected_orders=selected_orders,
                detail_rows=row_count, eligible_orders=len(orders))


def _consistency(source_total, category, monthly, customer):
    amounts = [("completed_source", source_total),
               ("category", category.total_sales.sum()),
               ("monthly", monthly.total_sales.sum()),
               ("customer", customer.total_sales.sum())]
    return pd.DataFrame([
        {"source": source, "amount": int(amount),
         "difference_from_completed": int(amount - source_total),
         "matches_completed": int(amount) == int(source_total),
         "status": "PASS" if int(amount) == int(source_total) else "FAIL"}
        for source, amount in amounts
    ])


def build_analysis_tables(processed_data, raw_data, exclusions, root):
    """같은 금액 모집단을 확정하기 전의 FAIL과 해결 후 표를 함께 반환한다."""
    c, p, o, i = [processed_data[name].copy() for name in DATASETS]
    o["order_date"] = pd.to_datetime(o.order_date, errors="coerce")
    o["order_month"] = o.order_date.dt.strftime("%Y-%m")
    expected = i.quantity * i.unit_price
    mismatch = int((~np.isclose(i.line_total.astype(float), expected.astype(float), rtol=0, atol=0)).sum())
    line_total_check = pd.DataFrame([{
        "check": "line_total = quantity × unit_price", "source": "existing rechecked",
        "row_count": len(i), "mismatch_count": mismatch,
        "status": "PASS" if mismatch == 0 else "FAIL",
    }])
    assert mismatch == 0, "line_total 검증 실패"
    i["line_total"] = expected
    order_sales, merge_order = _checked_merge(
        i, o[["order_id", "customer_id", "order_date", "order_month", "order_status"]],
        on="order_id", validate="many_to_one", label="order_items → orders")
    completed = order_sales.order_status.eq("completed")
    valid_date = order_sales.order_date.notna()
    not_future = order_sales.order_date.le(AS_OF)
    selected = completed & valid_date & not_future
    initial = order_sales.loc[completed].copy()
    invalid = initial.order_date.isna()
    future = initial.order_date.gt(AS_OF)
    initial_total = int(initial.line_total.sum())
    monthly_initial = int(initial.loc[initial.order_month.notna(), "line_total"].sum())
    before_validation = pd.DataFrame([
        {"check": "completed_rows_with_invalid_order_date", "value": int(invalid.sum()),
         "expected": 0, "affected_amount": int(initial.loc[invalid, "line_total"].sum()),
         "status": "PASS" if not invalid.any() else "FAIL"},
        {"check": "monthly_total_before_scope_resolution", "value": monthly_initial,
         "expected": initial_total, "affected_amount": initial_total - monthly_initial,
         "status": "PASS" if monthly_initial == initial_total else "FAIL"},
        {"check": "completed_rows_after_fixed_as_of", "value": int(future.sum()),
         "expected": 0, "affected_amount": int(initial.loc[future, "line_total"].sum()),
         "status": "PASS" if not future.any() else "FAIL"},
    ])
    masks = [("all_order_items_not_revenue", pd.Series(True, index=order_sales.index)),
             ("completed_before_date_scope", completed),
             ("excluded_invalid_date_completed", completed & ~valid_date),
             ("excluded_after_fixed_as_of_completed", completed & valid_date & ~not_future),
             ("final_completed_valid_date_as_of", selected)]
    amount_scope = pd.DataFrame([
        {"scope": label, "amount": int(order_sales.loc[mask, "line_total"].sum()),
         "detail_rows": int(mask.sum()), "order_count": int(order_sales.loc[mask, "order_id"].nunique())}
        for label, mask in masks
    ])
    date_resolution = pd.DataFrame([
        {"stage": "before", "rule": "completed invalid dates", "detail_rows": int((completed & ~valid_date).sum()),
         "orders": int(order_sales.loc[completed & ~valid_date, "order_id"].nunique()),
         "amount": int(order_sales.loc[completed & ~valid_date, "line_total"].sum()),
         "action": "날짜를 추정하지 않고 세 금액 집계의 공통 범위에서 명시적으로 제외", "status": "FAIL" if invalid.any() else "PASS"},
        {"stage": "before", "rule": "completed date after 2026-10-08", "detail_rows": int((completed & valid_date & ~not_future).sum()),
         "orders": int(order_sales.loc[completed & valid_date & ~not_future, "order_id"].nunique()),
         "amount": int(order_sales.loc[completed & valid_date & ~not_future, "line_total"].sum()),
         "action": "고정 기준일을 넘으므로 모든 금액 집계에서 공통 제외", "status": "FAIL" if future.any() else "PASS"},
        {"stage": "after", "rule": "completed + valid date + date <= fixed_as_of", "detail_rows": int(selected.sum()),
         "orders": int(order_sales.loc[selected, "order_id"].nunique()),
         "amount": int(order_sales.loc[selected, "line_total"].sum()),
         "action": "원래 NaT/후보 플래그는 보존하고 분석 대상만 한정", "status": "PASS"},
    ])
    sales, merge_product = _checked_merge(
        order_sales.loc[selected].copy(), p[["product_id", "product_name", "category", "price"]],
        on="product_id", validate="many_to_one", label="completed details → products")
    assert sales.category.notna().all()
    category = sales.groupby("category", as_index=False, dropna=False).agg(
        total_quantity=("quantity", "sum"), total_sales=("line_total", "sum"),
        order_count=("order_id", "nunique"))
    category = category.sort_values("total_sales", ascending=False).reset_index(drop=True)
    total = int(sales.line_total.sum())
    category["sales_ratio"] = (category.total_sales / total * 100).round(2)
    category["quantity_weighted_unit_price"] = category.total_sales / category.total_quantity
    monthly = sales.groupby("order_month", as_index=False).agg(
        total_sales=("line_total", "sum"), order_count=("order_id", "nunique")).sort_values("order_month")
    months = pd.period_range(sales.order_date.min(), sales.order_date.max(), freq="M").astype(str)
    monthly = monthly.set_index("order_month").reindex(months).rename_axis("order_month").reset_index()
    monthly["observed_in_selected_data"] = monthly.total_sales.notna()
    monthly["zero_amount_observed"] = monthly.observed_in_selected_data & monthly.total_sales.eq(0)
    monthly["month_start"] = pd.to_datetime(monthly.order_month + "-01")
    monthly["avg_order_value"] = monthly.total_sales / monthly.order_count.replace(0, np.nan)
    customer = sales.groupby("customer_id", as_index=False, dropna=False).agg(
        order_count=("order_id", "nunique"), total_sales=("line_total", "sum"))
    customer["avg_order_value"] = customer.total_sales / customer.order_count
    customer, merge_customer = _checked_merge(customer, c[["customer_id", "city"]],
        on="customer_id", validate="one_to_one", label="customer aggregates → customers")
    customer = customer.sort_values(["total_sales", "customer_id"], ascending=[False, True]).reset_index(drop=True)
    customer["customer_label"] = [f"Customer {j:02d}" for j in range(1, len(customer) + 1)]
    customer_public = customer[PUBLIC_CUSTOMER_COLUMNS].copy()
    assert not FORBIDDEN_CUSTOMER_COLUMNS.intersection(customer_public.columns)
    status = o.order_status.value_counts(dropna=False).rename_axis("order_status").reset_index(name="order_count")
    status["order_ratio"] = (status.order_count / len(o) * 100).round(2)
    checks = pd.DataFrame([merge_order, merge_product, merge_customer])
    date_checks = pd.DataFrame([
        {"check": "completed rows with invalid order_date", "invalid_count": int(sales.order_date.isna().sum()),
         "affected_amount": int(sales.loc[sales.order_date.isna(), "line_total"].sum()),
         "status": "PASS" if sales.order_date.notna().all() else "FAIL"},
        {"check": "completed rows after fixed_as_of", "invalid_count": int(sales.order_date.gt(AS_OF).sum()),
         "affected_amount": int(sales.loc[sales.order_date.gt(AS_OF), "line_total"].sum()),
         "status": "PASS" if sales.order_date.le(AS_OF).all() else "FAIL"},
    ])
    consistency = _consistency(total, category, monthly, customer_public)
    raw_counts = raw_data["order_items"].drop_duplicates().groupby("order_id").order_item_id.nunique()
    clean_counts = i.groupby("order_id").order_item_id.nunique()
    partial = clean_counts.index[(clean_counts > 0) & (clean_counts < raw_counts.reindex(clean_counts.index))]
    selected_partial = sales.loc[sales.order_id.isin(partial)]
    sensitivity = pd.DataFrame([
        {"scope": label, "detail_rows": len(frame), "order_count": frame.order_id.nunique(),
         "amount": int(frame.line_total.sum())}
        for label, frame in [("retained_valid_details_including_partial_orders", sales),
                             ("exclude_entire_partially_retained_orders", sales.loc[~sales.order_id.isin(partial)])]
    ])
    eligible_ids = o.loc[o.order_status.eq("completed") & o.order_date.notna() & o.order_date.le(AS_OF), "order_id"]
    independent = _independent_raw_recalculation(root, exclusions)
    category_dict = {row.category: Decimal(int(row.total_sales)) for row in category.itertuples()}
    month_dict = {row.order_month: Decimal(int(row.total_sales)) for row in monthly.loc[monthly.observed_in_selected_data].itertuples()}
    customer_dict = {int(row.customer_id): Decimal(int(row.total_sales)) for row in customer.itertuples()}
    independent_checks = pd.DataFrame([
        {"check": "raw csv Decimal completed total", "actual": str(independent["amount"]), "expected": str(total),
         "status": "PASS" if independent["amount"] == Decimal(total) else "FAIL"},
        {"check": "raw csv independent category amounts", "actual": len(independent["category"]), "expected": len(category),
         "status": "PASS" if dict(independent["category"]) == category_dict else "FAIL"},
        {"check": "raw csv independent monthly amounts", "actual": len(independent["monthly"]), "expected": len(monthly),
         "status": "PASS" if dict(independent["monthly"]) == month_dict else "FAIL"},
        {"check": "raw csv independent customer amounts", "actual": len(independent["customer"]), "expected": len(customer),
         "status": "PASS" if dict(independent["customer"]) == customer_dict else "FAIL"},
        {"check": "raw csv independent monthly unique orders", "actual": sum(map(len, independent["monthly_orders"].values())),
         "expected": int(monthly.order_count.sum()), "status": "PASS" if all(
             len(independent["monthly_orders"][row.order_month]) == row.order_count
             for row in monthly.loc[monthly.observed_in_selected_data].itertuples()) else "FAIL"},
        {"check": "raw csv independent selected detail rows", "actual": independent["detail_rows"], "expected": len(sales),
         "status": "PASS" if independent["detail_rows"] == len(sales) else "FAIL"},
    ])
    assert independent_checks.status.eq("PASS").all(), independent_checks.to_string(index=False)
    parameters = pd.DataFrame([
        ["analysis_as_of", "2026-10-08"], ["written_date", WRITTEN_DATE],
        ["date_start", sales.order_date.min().date().isoformat()], ["date_end", sales.order_date.max().date().isoformat()],
        ["eligible_orders_before_detail_join", len(eligible_ids)], ["orders_with_retained_details", sales.order_id.nunique()],
        ["eligible_orders_without_details", int((~eligible_ids.isin(sales.order_id)).sum())],
        ["selected_detail_rows", len(sales)], ["purchasing_customers", len(customer)],
        ["selected_partially_retained_orders", selected_partial.order_id.nunique()],
        ["selected_partial_detail_rows", len(selected_partial)], ["selected_partial_amount", int(selected_partial.line_total.sum())],
        ["calendar_months", len(monthly)], ["unobserved_months", int((~monthly.observed_in_selected_data).sum())],
        ["observed_zero_amount_months", int(monthly.zero_amount_observed.sum())],
    ], columns=["parameter", "value"])
    return dict(order_sales=order_sales, completed_order_sales=sales, completed_sales_items=sales,
        category_sales=category, monthly_sales=monthly, customer_sales=customer,
        customer_sales_public=customer_public, order_status_summary=status,
        amount_scope_summary=amount_scope, merge_checks=checks, line_total_check=line_total_check,
        date_checks=date_checks, total_consistency_check=consistency, before_validation=before_validation,
        date_resolution=date_resolution, independent_recalculation=independent_checks,
        partial_sensitivity=sensitivity, parameters=parameters)


def build_project_validation(key_duplicate_checks, relationship_checks, analysis_tables,
                             *, processed_reproduction=None, input_preservation=None):
    a = analysis_tables
    ratio = float(a["category_sales"].sales_ratio.sum())
    rows = []

    def record(name, value, expected, passed):
        rows.append({"check": name, "value": value, "expected": expected,
                     "status": "PASS" if passed else "FAIL"})

    pk = key_duplicate_checks.status.eq("PASS").all()
    record("pk_integrity", "all PASS" if pk else "FAIL present", "all PASS", pk)
    fk = int(relationship_checks.invalid_count.sum())
    record("fk_integrity", fk, 0, not relationship_checks.empty and fk == 0)
    merge = a["merge_checks"].status.eq("PASS").all()
    record("merge_checks_pass", "all PASS" if merge else "FAIL present", "all PASS", merge)
    mismatch = int(a["line_total_check"].mismatch_count.sum())
    record("line_total_consistency", mismatch, 0, mismatch == 0)
    totals = a["total_consistency_check"].matches_completed.all()
    record("completed_total_consistency", "all match" if totals else "mismatch", "all match", totals)
    record("category_sales_ratio_pct_sum", ratio, 100, np.isclose(ratio, 100, rtol=0, atol=.05))
    invalid = int(a["completed_order_sales"].order_date.isna().sum())
    record("completed_rows_with_invalid_order_date", invalid, 0, invalid == 0)
    future = int(a["completed_order_sales"].order_date.gt(AS_OF).sum())
    record("completed_rows_after_fixed_as_of", future, 0, future == 0)
    public = a["customer_sales_public"]
    forbidden = sorted(FORBIDDEN_CUSTOMER_COLUMNS.intersection(public.columns))
    privacy = not forbidden and list(public.columns) == PUBLIC_CUSTOMER_COLUMNS
    record("public_customer_columns_safe", ", ".join(forbidden) or "no forbidden columns", "no forbidden columns", privacy)
    complete = a["completed_order_sales"].order_status.eq("completed").all()
    record("completed_scope_consistent", bool(complete), True, complete)
    raw = a["independent_recalculation"].status.eq("PASS").all()
    record("raw_csv_Decimal_recalculation", "all match" if raw else "mismatch", "all match", raw)
    if "artist_checks" in a:
        artists = a["artist_checks"]["통과"].all()
        record("graph_artist_values_match", int(a["artist_checks"]["통과"].sum()), len(a["artist_checks"]), artists)
    if processed_reproduction is not None:
        ok = processed_reproduction.status.eq("PASS").all()
        record("raw_to_clean_reproduction", int(processed_reproduction.status.eq("PASS").sum()), len(processed_reproduction), ok)
    if input_preservation is not None:
        ok = input_preservation.status.eq("PASS").all()
        record("existing_raw_clean_inputs_preserved", int(input_preservation.status.eq("PASS").sum()), len(input_preservation), ok)
    return pd.DataFrame(rows)


def create_project_figures(analysis_tables, figure_dir, show=False):
    """Chapter07의 검증된 그리기 함수를 같은 Chapter08 집계에 적용한다."""
    setup_korean_font()
    a, out = analysis_tables, Path(figure_dir)
    out.mkdir(parents=True, exist_ok=True)
    date_range = "~".join(a["parameters"].set_index("parameter").loc[["date_start", "date_end"], "value"].astype(str))
    cat = a["category_sales"].rename(columns={"total_sales": "completed_amount", "sales_ratio": "amount_ratio_pct"})
    monthly = a["monthly_sales"].rename(columns={"total_sales": "completed_amount"})
    customer = a["customer_sales_public"].rename(columns={"total_sales": "completed_amount"})
    calls = [(plot_category_sales, cat, "graph01.png", "category_sales"),
             (plot_monthly_sales, monthly, "graph02.png", "monthly_sales"),
             (plot_top_customers, customer, "graph03.png", "top_customers")]
    paths, validations = [], []
    for function, table, filename, label in calls:
        chart = function(table, out / filename, show=show, data_range=date_range)
        paths.append(chart.path)
        validations.append(chart.validation.assign(graph=label))
    return paths, pd.concat(validations, ignore_index=True)


def build_interpretation_notes(analysis_tables):
    a = analysis_tables
    top = a["category_sales"].iloc[0]
    monthly = a["monthly_sales"]
    max_month, min_month = monthly.loc[monthly.total_sales.idxmax()], monthly.loc[monthly.total_sales.idxmin()]
    customers = a["customer_sales_public"]
    top10 = customers.head(10)
    rows = [
        ["category", f"{top.category} {int(top.total_sales):,}원·{top.sales_ratio:.2f}%로 최대",
         "현재 범위의 완료 상세 금액 기여가 가장 크다", "수량·단가·원가 없이 선호나 이익의 원인으로 단정하지 않는다",
         "카테고리별 수량과 수량가중 거래 단가를 나누어 비교한다"],
        ["monthly", f"최대 {max_month.order_month} {int(max_month.total_sales):,}원; 최소 {min_month.order_month} {int(min_month.total_sales):,}원",
         "월별 금액과 주문 수·평균 주문금액을 함께 확인한다", "경계 월 수집 완전성과 광고·재고·계절성은 확인하지 못했다",
         "금액 차이가 큰 월의 주문 수와 카테고리 구성을 비교한다"],
        ["customers", f"구매고객 {len(customers)}명; 상위10명 {int(top10.total_sales.sum()):,}원; 주문 수 {int(top10.order_count.min())}~{int(top10.order_count.max())}회",
         "상위10명은 기간 내 반복 구매 고객이다", "상위10명은 전체 고객 분포가 아니며 미래 충성도는 모른다",
         "기간·금액 기준을 바꿔 반복 구매와 고액 1회 고객을 따로 비교한다"],
    ]
    return pd.DataFrame(rows, columns=["analysis", "observation", "interpretation", "caution", "next_question"])


def save_project_tables(result, report_dir):
    out = Path(report_dir)
    out.mkdir(parents=True, exist_ok=True)
    a = result["analysis_tables"]
    frames = {
        "dataset_summary": result["dataset_summary"],
        "preprocessing_comparison": result["preprocessing_comparison"],
        "key_duplicate_checks": result["key_duplicate_checks"],
        "relationship_checks": result["relationship_checks"],
        "merge_checks": a["merge_checks"], "line_total_check": a["line_total_check"],
        "date_checks": a["date_checks"], "amount_scope_summary": a["amount_scope_summary"],
        "total_consistency_check": a["total_consistency_check"],
        "project_validation": result["project_validation"],
        "category_sales": a["category_sales"], "monthly_sales": a["monthly_sales"],
        "customer_sales": a["customer_sales_public"],
        "order_status_summary": a["order_status_summary"],
        "interpretation_notes": result["interpretation_notes"],
        "column_schema": result["column_schema"],
        "preprocessing_exclusions": result["preprocessing_exclusions"],
        "preprocessing_rules": result["preprocessing_rules"],
        "date_resolution": a["date_resolution"], "before_validation": a["before_validation"],
        "independent_recalculation": a["independent_recalculation"],
        "partial_sensitivity": a["partial_sensitivity"], "parameters": a["parameters"],
        "artist_checks": a["artist_checks"],
        "input_preservation": result["input_preservation"],
        "processed_reproduction": result["processed_reproduction"],
    }
    paths = []
    for name, frame in frames.items():
        path = out / f"ch08_{name}.csv"
        frame.to_csv(path, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
        paths.append(path)
    return paths


def build_midterm_report(result):
    def table(frame):
        safe = frame.map(lambda value: value.replace("|", r"\|") if isinstance(value, str) else value)
        return safe.to_markdown(index=False, floatfmt=",.2f")
    a = result["analysis_tables"]
    sections = [
        "# Chapter 08 작은 데이터 분석 프로젝트 보고서",
        f"작성·실행일: {WRITTEN_DATE}. 분석 기준일은 2026-10-08로 고정했다. 코드 작성·실행·검증에 Codex의 도움을 받았다.",
        "## 분석 목적과 범위\n" + "\n".join(f"- {q}" for q in PROJECT_QUESTIONS),
        "금액은 completed이고 유효 주문일이 고정 기준일 이하인, 정제 후 남은 유효 상세의 quantity×unit_price 합계다. 회계상 순매출이나 이익은 아니다. 원본은 변경하지 않고 기존 Chapter05 전처리를 임시 폴더에서 원본부터 다시 실행했다.",
        "## 원본 4파일\n" + table(result["dataset_summary"]),
        "## 전처리 전후 변화\n" + table(result["preprocessing_comparison"]),
        "## 제외 규칙과 행 수\n" + table(result["preprocessing_exclusions"]),
        "## PK\n" + table(result["key_duplicate_checks"]),
        "## FK\n" + table(result["relationship_checks"]),
        "## 안전한 병합\n" + table(a["merge_checks"]),
        "## line_total\n" + table(a["line_total_check"]),
        "## 해결 전 FAIL 기록\n" + table(a["before_validation"]),
        "## 날짜 범위의 명시적 해결\n" + table(a["date_resolution"]),
        "원래 NaT와 미래 후보는 남겼다. 모든 금액 집계의 공통 대상만 한정했고 날짜를 추정하거나 보완하여 PASS로 만든 것은 아니다.",
        "## 분모와 분석 범위\n" + table(a["parameters"]),
        "## 전체 상세·completed·날짜 제외\n" + table(a["amount_scope_summary"]),
        "## 독립 원본 CSV 재계산\n" + table(a["independent_recalculation"]),
        "독립 검산은 전처리의 격리 행 번호를 적용한 원본 CSV를 csv.DictReader로 다시 읽고, 원본 orders의 상태·날짜로 주문을 선택해 원본 order_items의 quantity×unit_price를 Decimal로 별도 계산했다. 같은 병합 DataFrame끼리의 총합 비교에만 의존하지 않았다.",
        "## 같은 의미의 총합\n" + table(a["total_consistency_check"]),
        "## 카테고리\n" + table(a["category_sales"]),
        "## 월별\n" + table(a["monthly_sales"]),
        "## 익명 고객 Top10\n" + table(a["customer_sales_public"].head(10)),
        "## 전체 clean 주문 상태\n" + table(a["order_status_summary"]),
        "## 일부 상세가 남은 주문의 민감도\n" + table(a["partial_sensitivity"]),
        "일부 상세가 격리된 18주문을 기본 범위에 포함하므로 원래 청구총액과 다를 수 있다. 18주문을 모두 제외한 민감도도 비교했다. 총액 차이만으로 카테고리 순위나 월별 모양이 같다고 주장하지 않는다.",
        "## 실제 그래프 값과의 대조\n" + table(a["artist_checks"]),
        "## 공개 고객 결과의 익명화\n공개 CSV는 customer_label, city, order_count, total_sales, avg_order_value만 포함한다. 라벨은 금액 순위로 새로 붙였고 원본 customer_id·name·email·phone·address는 저장하지 않는다. 저장 CSV도 다시 읽어 컬럼과 값을 확인했다.",
        "## 최종 Validation\n" + table(result["project_validation"]),
        "## 관찰·판단·한계\n" + table(result["interpretation_notes"]),
        "## 재현성\nNotebook과 python scripts/run_midterm_project.py는 같은 함수를 호출한다. 기존 raw/clean 8파일의 해시 보존과 재생성 clean 4파일의 일치를 확인했다.",
        "## 남은 한계\n광고·원가·할인·재고·추출기간의 완전성은 모른다. 월별 변동을 인과로 설명하지 않고 고객 미래가치나 충성도를 단정하지 않는다. 자동 PASS는 정해 둔 구조·수치 조건의 통과이며 데이터의 진실성이나 해석의 원인을 증명하지 않는다. 자세한 질문·관찰·판단·LLM 기록은 chapter08/chapter08.ipynb에 있다.",
    ]
    # 표/목록 앞의 빈 줄과 사유 문자열 내부의 |를 보존해 Markdown을 안정적으로 표시한다.
    sections = [part.replace("\n", "\n\n", 1) if part.startswith("## ") and "\n" in part else part
                for part in sections]
    return "\n\n".join(sections) + "\n"


def run_midterm_project(project_root, show_figures=False):
    """원본4→임시 전처리→Gate→집계→그림→공개 보고서를 실행한다."""
    root = Path(project_root).resolve()
    before_hashes = input_hashes(root)
    assert len(before_hashes) == 8, "raw4+기존 processed4가 필요하다"
    pre, reproduction = _rebuild_raw(root)
    raw, clean = pre["raw"], pre["clean"]
    schema = pd.DataFrame([
        {"dataset": name, "column": column, "raw_dtype": str(frame[column].dtype),
         "raw_missing": int(frame[column].isna().sum()),
         "clean_dtype": str(clean[name][column].dtype), "clean_missing": int(clean[name][column].isna().sum())}
        for name, frame in raw.items() for column in frame.columns
    ])
    keys = build_key_duplicate_checks(clean)
    relationships = validate_relationships(clean)
    relationships["status"] = np.where(relationships.invalid_count.eq(0), "PASS", "FAIL")
    assert keys.status.eq("PASS").all() and relationships.status.eq("PASS").all()
    analysis = build_analysis_tables(clean, raw, pre["exclusions"], root)
    figures, artists = create_project_figures(analysis, root / "chapter08/images", show=show_figures)
    analysis["artist_checks"] = artists
    official_dir = root / "reports/figures"
    official_dir.mkdir(parents=True, exist_ok=True)
    official_figures = []
    for source, filename in zip(figures, ["ch08_category_sales.png", "ch08_monthly_sales.png", "ch08_top_customers.png"]):
        target = official_dir / filename
        shutil.copyfile(source, target)
        assert sha256(source) == sha256(target)
        official_figures.append(target)
    preserved = pd.DataFrame([
        {"file": filename, "sha256_before": value, "sha256_after": sha256(root / filename),
         "status": "PASS" if value == sha256(root / filename) else "FAIL"}
        for filename, value in before_hashes.items()
    ])
    rules = pre["audit"].groupby(["dataset", "column", "action"], as_index=False).size().rename(columns={"size": "changed_cells"})
    exclusions = pre["exclusions"].groupby(["dataset", "stage", "reasons"], as_index=False).size().rename(columns={"size": "excluded_rows"})
    result = dict(raw_data=raw, processed_data=clean, dataset_summary=summarize_datasets(raw),
        preprocessing_comparison=pre["comparison"], key_duplicate_checks=keys,
        relationship_checks=relationships, analysis_tables=analysis,
        column_schema=schema, preprocessing_rules=rules, preprocessing_exclusions=exclusions,
        processed_reproduction=reproduction, input_preservation=preserved,
        date_resolution=analysis["date_resolution"], before_validation=analysis["before_validation"],
        independent_recalculation=analysis["independent_recalculation"],
        partial_sensitivity=analysis["partial_sensitivity"],
        saved_figures=figures, official_figures=official_figures)
    result["project_validation"] = build_project_validation(keys, relationships, analysis,
        processed_reproduction=reproduction, input_preservation=preserved)
    result["interpretation_notes"] = build_interpretation_notes(analysis)
    result["saved_tables"] = save_project_tables(result, root / "reports")
    saved_customer = pd.read_csv(root / "reports/ch08_customer_sales.csv")
    assert saved_customer.columns.tolist() == PUBLIC_CUSTOMER_COLUMNS
    assert not FORBIDDEN_CUSTOMER_COLUMNS.intersection(saved_customer.columns)
    pd.testing.assert_frame_equal(saved_customer, analysis["customer_sales_public"], check_dtype=False, rtol=1e-12, atol=1e-9)
    report_path = root / "reports/ch08_midterm_report.md"
    report_path.write_text(build_midterm_report(result), encoding="utf-8")
    result["report_path"] = report_path
    assert result["project_validation"].status.eq("PASS").all(), result["project_validation"].to_string(index=False)
    assert input_hashes(root) == before_hashes
    return result
