"""Chapter 10 checkout-time classification with auditable model selection."""

from collections import Counter, defaultdict
import csv
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
TARGET = "is_cancelled"
TARGET_MAP = {"completed": 0, "cancelled": 1}
NUMERIC_FEATURES = ["age", "item_count", "total_quantity", "order_amount", "order_month", "order_dayofweek"]
CATEGORICAL_FEATURES = ["gender", "city", "payment_method"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
BASELINE = "Dummy Most Frequent"
THRESHOLDS = tuple(value / 100 for value in range(20, 81, 5))
METRICS = ["accuracy", "precision", "recall", "f1"]
PUBLIC_COLUMNS = ["record_id", "actual_is_cancelled", "predicted_is_cancelled", "cancel_probability", "model", "threshold"]
FEATURE_NOTES = {
    "age": "주문 접수 때 확인 가능한 고객 나이라고 가정",
    "item_count": "접수 시점에 확인 가능하다고 가정한 주문 상세 행 수",
    "total_quantity": "접수 시점에 확인 가능하다고 가정한 주문 수량 합계",
    "order_amount": "접수 시점에 확인 가능하다고 가정한 수량 × 단가 합계(원)",
    "order_month": "주문 접수일의 월",
    "order_dayofweek": "주문 접수일의 요일(월요일=0)",
    "gender": "주문 접수 시점 고객 프로필로 가정",
    "city": "주문 접수 시점 고객 프로필로 가정",
    "payment_method": "주문 접수 시 선택한 결제 수단이라고 가정",
}
EXCLUDED_FEATURES = {
    "order_status": "사후 확정 상태, 타깃 정의에만 사용",
    TARGET: "정답 라벨",
    "order_id": "주문 병합용 원본 키",
    "customer_id": "고객 병합용 원본 키",
    "product_id": "주문 상세의 원본 상품 키",
    "order_item_id": "주문 상세 원본 키",
    "source_index": "내부 검증 행 참조",
    "cancel_reason": "취소 이후 정보",
    "cancelled_at": "취소 이후 정보",
    "refund_status": "환불 이후 정보",
    "refund_at": "환불 이후 정보",
    "name": "개인 식별 정보",
    "order_date": "일부 파생값 계산 및 감사에만 사용",
    "signup_date": "주문 이전 정보였는지 확인되지 않아 날짜 감사에만 사용",
    "days_since_signup": "가입일이 주문일보다 늦은 행이 관측되어 입력에서 제외",
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _checked_merge(left, right, key, relation, name):
    _require(left[key].notna().all() and right[key].notna().all(), f"{name}: 병합 키 결측")
    merged = left.merge(right, on=key, how="left", validate=relation, indicator=True)
    unmatched = int(merged["_merge"].ne("both").sum())
    preserved = len(left) == len(merged)
    _require(preserved and unmatched == 0, f"{name}: 행 수 또는 미매칭 검증 실패({unmatched}건)")
    check = {"merge": name, "relation": relation, "before_rows": len(left), "after_rows": len(merged),
             "unmatched_count": unmatched, "status": "PASS"}
    return merged.drop(columns="_merge"), check


def build_classification_data(processed_dir):
    """Validate persisted calculations and create an ordered row for each binary-target order."""
    dataset = {name: pd.read_csv(Path(processed_dir) / f"{name}_clean.csv")
               for name in ("customers", "orders", "order_items")}
    customers, orders, items = (dataset[name] for name in ("customers", "orders", "order_items"))
    for frame, key in ((customers, "customer_id"), (orders, "order_id"), (items, "order_item_id")):
        _require(frame[key].notna().all() and frame[key].is_unique, f"{key}: 결측 또는 중복")
    required_items = ["order_id", "product_id", "quantity", "unit_price", "line_total"]
    _require(items[required_items].notna().all(axis=None), "주문 상세 필수값 결측")
    item_numbers = items[["quantity", "unit_price", "line_total"]].apply(pd.to_numeric, errors="raise")
    _require(np.isfinite(item_numbers.to_numpy()).all() and item_numbers.gt(0).all(axis=None),
             "주문 상세의 수량, 단가, 금액은 유한한 양수여야 합니다.")
    expected_line = item_numbers["quantity"] * item_numbers["unit_price"]
    mismatch = int((~np.isclose(item_numbers["line_total"], expected_line, atol=1e-6, rtol=0)).sum())
    _require(mismatch == 0, f"line_total 계산 불일치 {mismatch}건")
    _require(items["order_id"].isin(orders["order_id"]).all(), "주문이 존재하지 않는 상세 행")
    items = items.assign(**item_numbers)
    item_features = items.groupby("order_id", as_index=False).agg(
        item_count=("product_id", "size"), total_quantity=("quantity", "sum"), order_amount=("line_total", "sum")
    )
    duplicate_features = int(item_features["order_id"].duplicated().sum())
    _require(duplicate_features == 0, "주문 단위 특징에 중복 키가 있습니다.")

    orders["order_date"] = pd.to_datetime(orders["order_date"], errors="raise")
    customers["signup_date"] = pd.to_datetime(customers["signup_date"], errors="raise")
    _require(orders[["order_date", "order_status"]].notna().all(axis=None), "주문일 또는 주문 상태 결측")
    profile = customers[["customer_id", "age", "gender", "city", "signup_date"]]
    timing = orders[["customer_id", "order_status", "order_date"]].merge(
        profile[["customer_id", "signup_date"]], on="customer_id", how="left", validate="many_to_one"
    )
    lag_all = (timing["order_date"] - timing["signup_date"]).dt.days

    status = orders["order_status"].value_counts().rename_axis("order_status").reset_index(name="order_count")
    status["used_for_binary_target"] = status["order_status"].isin(TARGET_MAP)
    status["class_label"] = status["order_status"].map(TARGET_MAP).astype("Int64")
    eligible = orders.loc[orders["order_status"].isin(TARGET_MAP)].copy()
    eligible[TARGET] = eligible["order_status"].map(TARGET_MAP).astype(int)
    _require(set(eligible[TARGET]) == {0, 1}, "completed와 cancelled가 모두 필요합니다.")
    with_items, item_merge = _checked_merge(eligible, item_features, "order_id", "one_to_one", "orders → order features")
    model_data, customer_merge = _checked_merge(with_items, profile, "customer_id", "many_to_one", "orders → customers")
    model_data["age"] = pd.to_numeric(model_data["age"], errors="raise")
    model_data["order_month"] = model_data["order_date"].dt.month
    model_data["order_dayofweek"] = model_data["order_date"].dt.dayofweek
    lag_binary = (model_data["order_date"] - model_data["signup_date"]).dt.days
    missing = model_data[FEATURES].isna().sum()
    critical = ["item_count", "total_quantity", "order_amount", "order_month", "order_dayofweek"]
    _require(missing[critical].eq(0).all(), "필수 주문 특징 결측")
    _require(set(FEATURES).isdisjoint(EXCLUDED_FEATURES), "Feature Contract 위반")
    data_quality = pd.DataFrame([
        ("source_order_rows", len(orders)),
        ("source_detail_rows", len(items)),
        ("binary_target_rows", len(model_data)),
        ("excluded_status_rows", len(orders) - len(model_data)),
        ("line_total_mismatch", mismatch),
        ("order_feature_rows", len(item_features)),
        ("order_feature_key_duplicates", duplicate_features),
        ("signup_after_order_all", int(lag_all.lt(0).sum())),
        ("signup_after_order_binary", int(lag_binary.lt(0).sum())),
        ("signup_lag_min_days_binary", lag_binary.min()),
        ("signup_lag_max_days_binary", lag_binary.max()),
        ("signup_lag_missing_binary", int(lag_binary.isna().sum())),
        ("feature_missing_total", int(missing.sum())),
        *((f"feature_missing:{column}", int(count)) for column, count in missing.items()),
    ], columns=["check_item", "count"])
    model_data = model_data.sort_values(["order_date", "order_id"]).reset_index(drop=True)
    return model_data, item_features, status, pd.DataFrame([item_merge, customer_merge]), data_quality


def _independent_raw_checks(raw_dir, processed_dir, model_data, item_features, scope):
    """Recompute every detail total, order aggregate and label with csv and Decimal."""
    raw_dir = Path(raw_dir)
    raw_orders, raw_items = {}, {}
    with (raw_dir / "orders.csv").open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            raw_orders[int(row["order_id"])] = row["order_status"].strip()
    with (raw_dir / "order_items.csv").open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            raw_items[int(row["order_item_id"])] = (
                int(row["order_id"]), Decimal(row["quantity"]), Decimal(row["unit_price"])
            )
    recorded_line = {}
    with (Path(processed_dir) / "order_items_clean.csv").open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            recorded_line[int(row["order_item_id"])] = Decimal(row["line_total"])
    details = defaultdict(list)
    for order_id, quantity, unit_price in raw_items.values():
        details[order_id].append((quantity, quantity * unit_price))
    raw_features = {order_id: (len(rows), sum(q for q, _ in rows), sum(amount for _, amount in rows))
                    for order_id, rows in details.items()}
    expected_labels = {order_id: TARGET_MAP[status] for order_id, status in raw_orders.items() if status in TARGET_MAP}
    observed_labels = dict(zip(model_data["order_id"], model_data[TARGET]))
    observed_features = {int(row.order_id): (int(row.item_count), Decimal(str(row.total_quantity)), Decimal(str(row.order_amount)))
                         for row in item_features.itertuples(index=False)}
    binary_features = {int(row.order_id): (int(row.item_count), Decimal(str(row.total_quantity)), Decimal(str(row.order_amount)))
                       for row in model_data.itertuples(index=False)}
    return pd.DataFrame([
        ("raw_status_frequency", len(raw_orders), Counter(raw_orders.values()) == dict(zip(scope.order_status, scope.order_count))),
        ("raw_detail_line_total", len(raw_items), recorded_line == {key: row[1] * row[2] for key, row in raw_items.items()}),
        ("raw_order_feature_values", len(raw_features), observed_features == raw_features),
        ("raw_binary_order_feature_values", len(expected_labels), binary_features == {key: raw_features[key] for key in expected_labels}),
        ("raw_binary_labels", len(expected_labels), observed_labels == expected_labels),
    ], columns=["check", "rows_compared", "passed"])


def _make_models(random_state):
    estimators = {
        BASELINE: DummyClassifier(strategy="most_frequent"),
        "Logistic Regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
        "Random Forest": RandomForestClassifier(n_estimators=200, random_state=random_state, class_weight="balanced", n_jobs=1),
    }
    models = {}
    for name, estimator in estimators.items():
        numeric = Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())])
        categorical = Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ])
        preprocessor = ColumnTransformer([
            ("num", numeric, NUMERIC_FEATURES), ("cat", categorical, CATEGORICAL_FEATURES),
        ])
        models[name] = Pipeline([("preprocessor", preprocessor), ("model", estimator)])
    return models


def _preprocessing_audit(models, X_train):
    numeric_data = X_train[NUMERIC_FEATURES]
    categorical_data = X_train[CATEGORICAL_FEATURES]
    medians = numeric_data.median()
    modes = categorical_data.mode().iloc[0]
    filled_numeric = numeric_data.fillna(medians)
    filled_categorical = categorical_data.fillna(modes)
    rows = []
    for name, model in models.items():
        preprocess = model.named_steps["preprocessor"]
        num = preprocess.named_transformers_["num"].named_steps
        cat = preprocess.named_transformers_["cat"].named_steps
        checks = {
            "median": np.allclose(num["imputer"].statistics_, medians.to_numpy()),
            "scaler_mean": np.allclose(num["scaler"].mean_, filled_numeric.mean().to_numpy()),
            "scaler_variance": np.allclose(num["scaler"].var_, filled_numeric.var(ddof=0).to_numpy()),
            "scaler_fit_rows": (np.asarray(num["scaler"].n_samples_seen_) == len(X_train)).all(),
            "categorical_mode": np.array_equal(cat["imputer"].statistics_, modes.to_numpy()),
            "encoded_categories": all(set(actual) == set(filled_categorical[col])
                                      for col, actual in zip(CATEGORICAL_FEATURES, cat["onehot"].categories_)),
            "unknown_categories_ignored": cat["onehot"].handle_unknown == "ignore",
        }
        rows.extend((name, check, len(X_train), bool(ok)) for check, ok in checks.items())
    return pd.DataFrame(rows, columns=["model", "check", "train_rows", "passed"])


def _metrics(y, prediction):
    tn, fp, fn, tp = confusion_matrix(y, prediction, labels=[0, 1]).ravel().astype(int)
    return {
        "accuracy": accuracy_score(y, prediction),
        "precision": precision_score(y, prediction, zero_division=0),
        "recall": recall_score(y, prediction, zero_division=0),
        "f1": f1_score(y, prediction, zero_division=0),
        "tn": tn, "fp": fp, "fn": fn, "tp": tp,
    }


def _positive_probability(model, X):
    class_position = list(model.classes_).index(1)
    probability = model.predict_proba(X)[:, class_position]
    _require(np.isfinite(probability).all() and ((probability >= 0) & (probability <= 1)).all(), "유효하지 않은 취소 확률")
    return probability


def _metric_audit(evaluations):
    """Independently recount TP/TN/FP/FN and derive all metrics."""
    rows = []
    for name, y, pred, observed in evaluations:
        counts = Counter(zip(y, pred))
        tn, fp, fn, tp = (counts[pair] for pair in ((0, 0), (0, 1), (1, 0), (1, 1)))
        expected = {
            "tn": tn, "fp": fp, "fn": fn, "tp": tp,
            "accuracy": (tp + tn) / len(y),
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "recall": tp / (tp + fn) if tp + fn else 0.0,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
        }
        rows.extend((name, metric, value, observed[metric], np.isclose(value, observed[metric], atol=1e-12, rtol=0))
                    for metric, value in expected.items())
    return pd.DataFrame(rows, columns=["evaluation", "metric", "recalculated", "observed", "passed"])


def _save_graphs(distribution, comparison, thresholds, matrix, selected_threshold, image_dir):
    """Save the four assignment figures and verify their plotted values."""
    image_dir.mkdir(parents=True, exist_ok=True)
    paths, checks = {}, []

    def save(fig, filename):
        path = image_dir / filename
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        paths[filename] = path

    fig, ax = plt.subplots(figsize=(5.5, 3.25), layout="constrained")
    bars = ax.bar(distribution["class_label"], distribution["count"], color=["#246b88", "#b84d1f"], width=0.55)
    labels = [f"{row.count} ({row.ratio:.1%})" for row in distribution.itertuples(index=False)]
    ax.bar_label(bars, labels=labels, padding=4)
    ax.set(title=f"Class distribution | {distribution['count'].sum()} eligible orders",
           ylabel="Number of orders", ylim=(0, distribution["count"].max() * 1.22))
    checks.append(("class_ratio_bars", np.array_equal([bar.get_height() for bar in bars], distribution["count"])))
    save(fig, "step02_class_ratio.png")

    fig, ax = plt.subplots(figsize=(8, 4), layout="constrained")
    model_order = [BASELINE, "Logistic Regression", "Random Forest"]
    plot_metrics = comparison.set_index("model").loc[model_order, METRICS]
    x = np.arange(len(model_order))
    metrics_match = []
    colors = ["#386186", "#216f60", "#a15221", "#7c4685"]
    for offset, (metric, color) in enumerate(zip(METRICS, colors)):
        bars = ax.bar(x + (offset - 1.5) * 0.18, plot_metrics[metric], width=0.18, color=color, label=metric.title())
        metrics_match.append(np.array_equal([bar.get_height() for bar in bars], plot_metrics[metric]))
    ax.set(title="Validation | default class predictions", ylabel="Score (0 to 1)", ylim=(0, 1))
    ax.set_xticks(x, model_order)
    ax.legend(ncol=4, loc="upper center", frameon=False)
    checks.append(("validation_metric_bars", all(metrics_match)))
    save(fig, "step03_baseline.png")

    fig, ax = plt.subplots(figsize=(7, 3.9), layout="constrained")
    threshold_match = []
    for metric, color in zip(METRICS[1:], colors[1:]):
        line, = ax.plot(thresholds["threshold"], thresholds[metric], marker="o", ms=4, color=color, label=metric.title())
        threshold_match.append(np.array_equal(line.get_xdata(), thresholds["threshold"]) and
                               np.array_equal(line.get_ydata(), thresholds[metric]))
    marker = ax.axvline(selected_threshold, color="#323b44", linestyle="--", label=f"Frozen: {selected_threshold:.2f}")
    ax.set(title="Validation | threshold comparison", xlabel="Threshold (cancel probability)", ylabel="Score (0 to 1)", ylim=(-0.04, 1.05))
    ax.set_xticks(THRESHOLDS[::2])
    ax.legend(ncol=2, frameon=False)
    checks.append(("threshold_curves_and_marker", all(threshold_match) and np.allclose(marker.get_xdata(), selected_threshold)))
    save(fig, "step05_threshold.png")

    fig, ax = plt.subplots(figsize=(5.3, 4.1), layout="constrained")
    values = matrix.to_numpy()
    tile = ax.imshow(values, cmap="Blues", vmin=0, vmax=max(1, values.max()))
    labels = [["TN", "FP"], ["FN", "TP"]]
    for (row, column), value in np.ndenumerate(values):
        color = "white" if value > values.max() / 2 else "#173047"
        ax.text(column, row, f"{labels[row][column]}: {value}", ha="center", va="center", color=color, fontsize=13)
    ax.set(title=f"Final Test | threshold {selected_threshold:.2f}", xlabel="Predicted class", ylabel="Actual class")
    ax.set_xticks([0, 1], ["Completed (0)", "Cancelled (1)"])
    ax.set_yticks([0, 1], ["Completed (0)", "Cancelled (1)"])
    fig.colorbar(tile, ax=ax, label="Number of orders")
    checks.append(("final_confusion_matrix_cells", np.array_equal(tile.get_array(), values)))
    save(fig, "step06_confusion_matrix.png")
    return paths, pd.DataFrame(checks, columns=["check", "passed"])


def run_classification_analysis(processed_dir=None, report_dir=None, image_dir=None, raw_dir=None, random_state=42):
    """Fit on Train, choose on Validation, persist the choice, then run Final Test once."""
    processed_dir = Path(processed_dir) if processed_dir is not None else ROOT / "data/ch10/processed"
    raw_dir = Path(raw_dir) if raw_dir is not None else ROOT / "data/ch10/raw"
    report_dir = Path(report_dir) if report_dir is not None else ROOT / "reports"
    image_dir = Path(image_dir) if image_dir is not None else ROOT / "chapter10/images"
    report_dir.mkdir(parents=True, exist_ok=True)

    model_data, item_features, status_scope, merge_checks, data_quality = build_classification_data(processed_dir)
    raw_audit = _independent_raw_checks(raw_dir, processed_dir, model_data, item_features, status_scope)
    _require(raw_audit["passed"].all(), "원본 독립 검산 결과가 분석 데이터와 일치하지 않습니다.")
    counts = model_data[TARGET].value_counts().sort_index()
    distribution = pd.DataFrame({TARGET: counts.index, "class_label": ["completed", "cancelled"],
                                 "count": counts.to_numpy(), "ratio": counts.to_numpy() / counts.sum()})
    feature_audit = pd.DataFrame([
        *((name, True, "numeric" if name in NUMERIC_FEATURES else "categorical", FEATURE_NOTES[name]) for name in FEATURES),
        *((name, False, "excluded", reason) for name, reason in EXCLUDED_FEATURES.items()),
    ], columns=["column", "selected", "role", "reason"])

    X, y = model_data[FEATURES], model_data[TARGET]
    X_rest, X_test, y_rest, y_test = train_test_split(X, y, test_size=0.20, stratify=y, random_state=random_state)
    X_train, X_val, y_train, y_val = train_test_split(X_rest, y_rest, test_size=0.25, stratify=y_rest, random_state=random_state)
    splits = {"Train": y_train, "Validation": y_val, "Test": y_test}
    split_summary = pd.DataFrame([
        (name, len(labels), int(labels.eq(0).sum()), int(labels.eq(1).sum()), float(labels.mean()))
        for name, labels in splits.items()
    ], columns=["split", "orders", "completed", "cancelled", "cancelled_ratio"])
    overlap_rows = []
    for left, right in (("Train", "Validation"), ("Train", "Test"), ("Validation", "Test")):
        first, second = model_data.loc[splits[left].index], model_data.loc[splits[right].index]
        overlap_rows.append((left, right, len(set(first.order_id) & set(second.order_id)),
                             len(set(first.customer_id) & set(second.customer_id)),
                             len(set(first.order_date) & set(second.order_date))))
    split_overlap = pd.DataFrame(overlap_rows, columns=["split_a", "split_b", "shared_orders", "shared_customers", "shared_dates"])
    _require(split_overlap["shared_orders"].eq(0).all() and split_summary["orders"].sum() == len(model_data), "분할 행 수 또는 중복 검증 실패")
    _require(all(set(labels.unique()) == {0, 1} for labels in splits.values()), "어떤 분할에 한 클래스가 누락되었습니다.")

    models, comparisons, validations, evaluated = _make_models(random_state), [], {}, []
    for name, model in models.items():
        model.fit(X_train, y_train)
        predicted = model.predict(X_val)
        scores = _metrics(y_val, predicted)
        comparisons.append({"model": name, "evaluation_split": "validation", **scores})
        validations[name] = _positive_probability(model, X_val)
        evaluated.append((f"validation:{name}", y_val, predicted, scores))
    preprocessing_audit = _preprocessing_audit(models, X_train)
    _require(preprocessing_audit["passed"].all(), "학습용 전처리 통계가 Train과 일치하지 않습니다.")
    comparison = pd.DataFrame(comparisons)
    ranking = ["f1", "recall", "precision"]
    chosen = comparison.loc[comparison["model"].ne(BASELINE)].sort_values(
        ranking + ["model"], ascending=[False, False, False, True]
    ).iloc[0]
    selected_name = str(chosen["model"])
    validation_probability = validations[selected_name]
    threshold_rows = []
    for threshold in THRESHOLDS:
        predicted = (validation_probability >= threshold).astype(int)
        scores = _metrics(y_val, predicted)
        threshold_rows.append({"threshold": threshold, **scores})
        evaluated.append((f"validation:threshold={threshold:.2f}", y_val, predicted, scores))
    thresholds = pd.DataFrame(threshold_rows)
    best = thresholds.sort_values(ranking + ["threshold"], ascending=[False, False, False, True]).iloc[0]
    selected_threshold = float(best["threshold"])
    selection = {
        "selection_split": "validation",
        "model": selected_name,
        "threshold": selected_threshold,
        "model_rule": "non-Dummy default predictions: highest F1, recall, precision; then alphabetical model name",
        "threshold_rule": "highest F1, recall, precision; then lower threshold",
        "threshold_grid": THRESHOLDS,
        "positive_rule": "cancel_probability >= threshold",
        "random_state": random_state,
        "train_orders": len(y_train),
        "validation_orders": len(y_val),
        "validation_default_f1": float(chosen["f1"]),
        "validation_frozen_f1": float(best["f1"]),
    }
    selection_path = report_dir / "ch10_frozen_selection.json"
    selection_bytes = (json.dumps(selection, ensure_ascii=False, indent=2) + "\n").encode()
    selection_path.write_bytes(selection_bytes)
    frozen = json.loads(selection_path.read_text(encoding="utf-8"))

    # The first and only scored use of Final Test is below, after the validation-only file write.
    test_probability = _positive_probability(models[frozen["model"]], X_test)
    test_prediction = (test_probability >= frozen["threshold"]).astype(int)
    test_scores = _metrics(y_test, test_prediction)
    test_metrics = pd.DataFrame([{"model": frozen["model"], "evaluation_split": "test_final",
                                 "threshold": frozen["threshold"], "selection_status": "frozen_before_test", **test_scores}])
    evaluated.append(("test_final:frozen_pair", y_test, test_prediction, test_scores))
    metric_audit = _metric_audit(evaluated)
    matrix = pd.DataFrame([[test_scores["tn"], test_scores["fp"]], [test_scores["fn"], test_scores["tp"]]],
                          index=pd.Index(["actual_completed", "actual_cancelled"], name="actual"),
                          columns=["pred_completed", "pred_cancelled"])
    local_predictions = pd.DataFrame({
        "source_index": X_test.index, "order_id": model_data.loc[X_test.index, "order_id"].to_numpy(),
        "customer_id": model_data.loc[X_test.index, "customer_id"].to_numpy(),
        "actual_is_cancelled": y_test.to_numpy(), "predicted_is_cancelled": test_prediction,
        "cancel_probability": test_probability, "model": frozen["model"], "threshold": frozen["threshold"],
    })
    local_predictions.insert(0, "record_id", [f"test_{index:04d}" for index in range(1, len(local_predictions) + 1)])
    public_predictions = local_predictions[PUBLIC_COLUMNS].copy()
    graph_paths, graph_audit = _save_graphs(distribution, comparison, thresholds, matrix, selected_threshold, image_dir)

    # Every PASS row is derived from observed data or a checked execution invariant.
    quality = data_quality.set_index("check_item")["count"]
    validation_values = [
        ("exact_binary_scope_and_label", raw_audit.loc[raw_audit["check"].eq("raw_binary_labels"), "passed"].item()),
        ("raw_inputs_reconciled", raw_audit["passed"].all()),
        ("line_total_and_order_key", quality["line_total_mismatch"] == quality["order_feature_key_duplicates"] == 0),
        ("merges_preserve_rows_without_unmatched", merge_checks["status"].eq("PASS").all() and merge_checks["unmatched_count"].eq(0).all()),
        ("features_have_no_target_ids_or_post_outcome", set(X_train).isdisjoint(EXCLUDED_FEATURES) and list(X_train) == FEATURES),
        ("invalid_tenure_excluded_and_rows_preserved", "days_since_signup" not in X_train and len(model_data) == distribution["count"].sum()),
        ("split_complete_and_no_order_overlap", split_overlap["shared_orders"].eq(0).all() and split_summary["orders"].sum() == len(model_data)),
        ("both_classes_in_every_split", split_summary[["completed", "cancelled"]].gt(0).all(axis=None)),
        ("preprocessing_statistics_match_train", preprocessing_audit["passed"].all()),
        ("selection_is_non_dummy_and_on_validation", selected_name != BASELINE and chosen["evaluation_split"] == "validation"),
        ("frozen_threshold_from_validation_grid", selected_threshold in THRESHOLDS and frozen["selection_split"] == "validation"),
        ("frozen_file_unchanged", selection_path.read_bytes() == selection_bytes),
        ("one_frozen_pair_in_final_test", len(test_metrics) == 1 and frozen["model"] == selected_name and frozen["threshold"] == selected_threshold),
        ("public_predictions_allowlisted", list(public_predictions) == PUBLIC_COLUMNS and public_predictions["record_id"].is_unique),
        ("predictions_match_frozen_threshold", np.array_equal(test_prediction, (public_predictions["cancel_probability"] >= selected_threshold).astype(int))),
        ("final_matrix_reconciles_to_test_counts", matrix.to_numpy().sum() == len(y_test) and test_scores["fn"] + test_scores["tp"] == int(y_test.sum())),
        ("manual_metric_recount", metric_audit["passed"].all()),
        ("four_graphs_match_calculations", graph_audit["passed"].all() and len(graph_paths) == 4),
    ]
    validation = pd.DataFrame(validation_values, columns=["check", "value"])
    validation["status"] = np.where(validation["value"], "PASS", "FAIL")
    _require(validation["value"].all(), "Chapter 10 validation failed:\n" + validation.loc[~validation["value"]].to_string(index=False))

    tables = {
        "status_scope": status_scope, "target_distribution": distribution, "feature_audit": feature_audit,
        "merge_checks": merge_checks, "data_quality_checks": data_quality, "split_summary": split_summary,
        "split_overlap": split_overlap, "validation_model_comparison": comparison, "validation_threshold_metrics": thresholds,
        "test_metrics": test_metrics, "classification_predictions": public_predictions, "confusion_matrix": matrix.reset_index(),
        "classification_validation": validation, "raw_audit": raw_audit, "preprocessing_audit": preprocessing_audit,
        "metric_audit": metric_audit, "graph_audit": graph_audit,
        "classification_model_data_internal": model_data[["order_id", "customer_id", TARGET] + FEATURES],
        "classification_predictions_internal": local_predictions,
    }
    output_paths = {"frozen_selection": selection_path, **graph_paths}
    for name, table in tables.items():
        path = report_dir / f"ch10_{name}.csv"
        table.to_csv(path, index=False, encoding="utf-8-sig")
        output_paths[name] = path
    report_path = report_dir / "ch10_classification_summary.md"
    report_path.write_text(
        "# Chapter 10 실행 요약\n\n"
        f"대상 주문 {len(model_data)}건, 완료 {counts.loc[0]}건, 취소 {counts.loc[1]}건. "
        f"Validation에서 {selected_name}, 임계값 {selected_threshold:.2f} 고정.\n\n"
        f"Final Test {len(y_test)}건의 accuracy {test_scores['accuracy']:.4f}, precision {test_scores['precision']:.4f}, "
        f"recall {test_scores['recall']:.4f}, F1 {test_scores['f1']:.4f}, FP {test_scores['fp']}건, FN {test_scores['fn']}건.\n\n"
        f"자동 검증 {len(validation)}개 PASS. 선택 파일 SHA-256 `{sha256(selection_bytes).hexdigest()}`. "
        "재실행 결과는 합성 표본의 코드 계약을 확인한다. 운영 타당성은 시간순 평가와 별도 업무 검증이 필요하다.\n",
        encoding="utf-8",
    )
    output_paths["classification_summary"] = report_path
    return {
        "model_data_shape": model_data.shape, "features": FEATURES, "target_distribution": distribution,
        "status_scope": status_scope, "feature_audit": feature_audit, "merge_checks": merge_checks,
        "data_quality_checks": data_quality, "split_summary": split_summary, "split_overlap": split_overlap,
        "validation_model_comparison": comparison, "selected_model_name": selected_name, "selected_threshold": selected_threshold,
        "selection": frozen, "selection_sha256": sha256(selection_bytes).hexdigest(), "threshold_metrics": thresholds,
        "test_metrics": test_metrics, "confusion_matrix": matrix, "prediction_result": public_predictions,
        "validation": validation, "raw_audit": raw_audit, "preprocessing_audit": preprocessing_audit,
        "metric_audit": metric_audit, "graph_audit": graph_audit, "image_paths": graph_paths, "output_paths": output_paths,
    }
