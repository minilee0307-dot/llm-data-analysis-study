"""Chapter 9 leakage-aware regression analysis utilities.

The workflow intentionally separates model selection from final test evaluation:

1. build the order-level target from order details,
2. keep target ingredients and post-outcome information out of features,
3. split chronologically without placing the same calendar day in both sets,
4. learn preprocessing inside sklearn Pipelines,
5. compare candidate models with TimeSeriesSplit on the training period,
6. freeze the selected non-baseline model before looking at final test metrics,
7. compare the frozen model with a mean DummyRegressor on the final test period,
8. save internal identifier-bearing diagnostics separately from public reports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


TARGET_COLUMN = "order_total"
NUMERIC_FEATURES = ["order_month", "order_dayofweek", "age"]
CATEGORICAL_FEATURES = ["payment_method", "gender", "city"]
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES

FORBIDDEN_FEATURES = {
    "order_total",
    "line_total",
    "quantity",
    "unit_price",
    "item_count",
    "total_quantity",
    "avg_unit_price",
    "order_status",
    "order_id",
    "customer_id",
    "product_id",
}

FORBIDDEN_REASONS = {
    "order_total": "예측 대상 자체",
    "line_total": "목표값을 구성하는 주문 상세 금액",
    "quantity": "목표값 계산 재료",
    "unit_price": "목표값 계산 재료",
    "item_count": "주문 상세가 확인된 뒤 계산되는 사후 집계",
    "total_quantity": "주문 상세에서 만든 목표 대리 변수",
    "avg_unit_price": "주문 상세에서 만든 목표 대리 변수",
    "order_status": "예측 시점 이후에 확정될 수 있는 사후 정보",
    "order_id": "주문 식별자",
    "customer_id": "고객 식별자",
    "product_id": "주문 상세가 확인되어야 알 수 있는 식별자",
}

REQUIRED_COLUMNS = {
    "customers": {"customer_id", "gender", "age", "city"},
    "orders": {
        "order_id",
        "customer_id",
        "order_date",
        "payment_method",
        "order_status",
    },
    "order_items": {"order_id", "quantity", "unit_price"},
}


def make_one_hot_encoder() -> OneHotEncoder:
    """Return a dense encoder compatible with multiple sklearn versions."""
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


def load_regression_source_data(
    processed_dir: str | Path = "data/ch09/processed",
) -> dict[str, pd.DataFrame]:
    """Load Chapter09 validated processed files; never silently fall back to raw data."""
    input_dir = Path(processed_dir)
    file_map = {
        "customers": input_dir / "customers_clean.csv",
        "orders": input_dir / "orders_clean.csv",
        "order_items": input_dir / "order_items_clean.csv",
    }
    missing_files = [path for path in file_map.values() if not path.exists()]
    if missing_files:
        raise FileNotFoundError(
            "Chapter09 모델링 입력이 없습니다. 먼저 `python scripts/prepare_ch09_data.py`를 실행하세요. "
            + "누락 파일: "
            + ", ".join(str(path) for path in missing_files)
        )
    return {name: pd.read_csv(path) for name, path in file_map.items()}


def validate_required_columns(datasets: dict[str, pd.DataFrame]) -> None:
    """Fail fast when a required dataset or modeling column is missing."""
    missing_datasets = sorted(set(REQUIRED_COLUMNS) - set(datasets))
    if missing_datasets:
        raise KeyError(f"필수 데이터셋이 없습니다: {missing_datasets}")
    for name, columns in REQUIRED_COLUMNS.items():
        missing_columns = sorted(columns - set(datasets[name].columns))
        if missing_columns:
            raise KeyError(f"{name}에 필요한 컬럼이 없습니다: {missing_columns}")


def validate_feature_columns(
    feature_columns: Iterable[str] = FEATURE_COLUMNS,
) -> None:
    """Reject target values, target proxies, post-outcome fields, and identifiers."""
    columns = list(feature_columns)
    leaked_features = sorted(set(columns) & FORBIDDEN_FEATURES)
    if leaked_features:
        raise ValueError(f"입력값에 누수 위험 컬럼이 있습니다: {leaked_features}")
    duplicates = pd.Index(columns)[pd.Index(columns).duplicated()].tolist()
    if duplicates:
        raise ValueError(f"입력값 목록에 중복 컬럼이 있습니다: {duplicates}")


def _require_unique_key(df: pd.DataFrame, key: str, dataset: str) -> None:
    if key not in df.columns:
        raise KeyError(f"{dataset}.{key} 컬럼이 없습니다.")
    missing_count = int(df[key].isna().sum())
    duplicate_count = int(df[key].duplicated().sum())
    if missing_count or duplicate_count:
        raise ValueError(
            f"{dataset}.{key} 검증 실패: "
            f"missing={missing_count}, duplicate={duplicate_count}"
        )


def build_order_totals(order_items: pd.DataFrame) -> pd.DataFrame:
    """Create order_total and verify line_total = quantity * unit_price."""
    items = order_items.copy()
    missing = sorted({"order_id", "quantity", "unit_price"} - set(items.columns))
    if missing:
        raise KeyError(f"order_items에 필요한 컬럼이 없습니다: {missing}")

    items["quantity"] = pd.to_numeric(items["quantity"], errors="coerce")
    items["unit_price"] = pd.to_numeric(items["unit_price"], errors="coerce")
    invalid = items[["order_id", "quantity", "unit_price"]].isna().any(axis=1)
    if invalid.any():
        raise ValueError(
            "주문 금액 목표값을 만들 수 없는 주문 상세 행이 있습니다: "
            f"{int(invalid.sum())}건"
        )

    expected = items["quantity"] * items["unit_price"]
    if "line_total" in items.columns:
        items["line_total"] = pd.to_numeric(items["line_total"], errors="coerce")
        if items["line_total"].isna().any():
            raise ValueError("order_items.line_total에 숫자 변환 실패가 있습니다.")
        mismatch = (items["line_total"] - expected).abs().gt(1e-6)
        if mismatch.any():
            raise ValueError(
                "line_total과 quantity × unit_price가 일치하지 않는 행이 있습니다: "
                f"{int(mismatch.sum())}건"
            )
    else:
        items["line_total"] = expected

    if (items["line_total"] <= 0).any():
        raise ValueError("주문 금액 목표값에 0 이하의 line_total이 있습니다.")

    return (
        items.groupby("order_id", as_index=False)
        .agg(order_total=("line_total", "sum"))
        .sort_values("order_id")
        .reset_index(drop=True)
    )


def build_regression_dataset(
    customers: pd.DataFrame,
    orders: pd.DataFrame,
    order_items: pd.DataFrame,
) -> pd.DataFrame:
    """Build one-row-per-order modeling data and reject silent join losses."""
    datasets = {
        "customers": customers.copy(),
        "orders": orders.copy(),
        "order_items": order_items.copy(),
    }
    validate_required_columns(datasets)
    validate_feature_columns()

    customers_data = datasets["customers"]
    orders_data = datasets["orders"]
    items_data = datasets["order_items"]

    _require_unique_key(customers_data, "customer_id", "customers")
    _require_unique_key(orders_data, "order_id", "orders")
    if orders_data["customer_id"].isna().any():
        raise ValueError("orders.customer_id에 결측치가 있습니다.")
    if items_data["order_id"].isna().any():
        raise ValueError("order_items.order_id에 결측치가 있습니다.")

    order_totals = build_order_totals(items_data)
    merged = orders_data.merge(
        order_totals,
        on="order_id",
        how="outer",
        validate="one_to_one",
        indicator=True,
    )
    unmatched = merged.loc[merged["_merge"].ne("both")]
    if not unmatched.empty:
        raise ValueError(
            "orders와 주문별 목표값의 관계가 완전하지 않습니다: "
            f"{merged['_merge'].value_counts().to_dict()}"
        )
    model_data = merged.drop(columns="_merge")

    model_data = model_data.merge(
        customers_data[["customer_id", "gender", "age", "city"]],
        on="customer_id",
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    unmatched_customer_count = int(model_data["_merge"].eq("left_only").sum())
    if unmatched_customer_count:
        raise ValueError(
            "orders.customer_id가 customers에 연결되지 않는 주문이 있습니다: "
            f"{unmatched_customer_count}건"
        )
    model_data = model_data.drop(columns="_merge")

    model_data["order_date"] = pd.to_datetime(model_data["order_date"], errors="coerce")
    if model_data["order_date"].isna().any():
        raise ValueError(
            "order_date 날짜 변환 실패가 있습니다: "
            f"{int(model_data['order_date'].isna().sum())}건"
        )
    model_data["age"] = pd.to_numeric(model_data["age"], errors="coerce")
    model_data[TARGET_COLUMN] = pd.to_numeric(model_data[TARGET_COLUMN], errors="coerce")
    if model_data[TARGET_COLUMN].isna().any():
        raise ValueError("order_total 목표값에 결측치가 있습니다.")
    if (model_data[TARGET_COLUMN] <= 0).any():
        raise ValueError("order_total 목표값에 0 이하 값이 있습니다.")

    model_data["order_month"] = model_data["order_date"].dt.month
    model_data["order_dayofweek"] = model_data["order_date"].dt.dayofweek
    return model_data.sort_values(["order_date", "order_id"]).reset_index(drop=True)


def split_model_data_by_time(
    model_data: pd.DataFrame,
    test_size: float = 0.2,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split by calendar-day groups; the same date cannot appear in both sets."""
    if not 0 < test_size < 1:
        raise ValueError("test_size는 0과 1 사이여야 합니다.")

    required = {"order_date", "order_id", TARGET_COLUMN, *FEATURE_COLUMNS}
    missing = sorted(required - set(model_data.columns))
    if missing:
        raise KeyError(f"시간 분할에 필요한 컬럼이 없습니다: {missing}")

    data = model_data.sort_values(["order_date", "order_id"]).reset_index(drop=True).copy()
    data["_split_day"] = data["order_date"].dt.normalize()
    unique_days = pd.Index(data["_split_day"].drop_duplicates())
    if len(unique_days) < 2:
        raise ValueError("시간 순서 분할에는 최소 2개의 서로 다른 주문일이 필요합니다.")

    split_day_index = int(len(unique_days) * (1 - test_size))
    split_day_index = min(max(split_day_index, 1), len(unique_days) - 1)
    test_start_day = unique_days[split_day_index]

    train_data = data.loc[data["_split_day"] < test_start_day].drop(columns="_split_day")
    test_data = data.loc[data["_split_day"] >= test_start_day].drop(columns="_split_day")
    if len(train_data) < 2 or len(test_data) < 2:
        raise ValueError("훈련·테스트에 각각 최소 2개 주문이 필요합니다.")
    if train_data["order_date"].max().normalize() >= test_data["order_date"].min().normalize():
        raise ValueError("같은 주문일이 훈련과 테스트에 동시에 포함되었습니다.")

    return train_data.reset_index(drop=True), test_data.reset_index(drop=True)


def split_features_target(
    model_data: pd.DataFrame,
    test_size: float = 0.2,
    random_state: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Compatibility wrapper returning chronological X/y splits."""
    _ = random_state
    validate_feature_columns()
    train_data, test_data = split_model_data_by_time(model_data, test_size=test_size)
    return (
        train_data[FEATURE_COLUMNS].copy(),
        test_data[FEATURE_COLUMNS].copy(),
        train_data[TARGET_COLUMN].copy(),
        test_data[TARGET_COLUMN].copy(),
    )


def make_preprocessor() -> ColumnTransformer:
    """Create train-only numeric and categorical preprocessing pipelines."""
    numeric = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", make_one_hot_encoder()),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("numeric", numeric, NUMERIC_FEATURES),
            ("categorical", categorical, CATEGORICAL_FEATURES),
        ]
    )


def make_regression_models(random_state: int = 42) -> dict[str, Pipeline]:
    """Create fixed candidates used for training-period model selection."""
    return {
        "Baseline Mean": Pipeline(
            [("preprocessor", make_preprocessor()), ("model", DummyRegressor(strategy="mean"))]
        ),
        "Linear Regression": Pipeline(
            [("preprocessor", make_preprocessor()), ("model", LinearRegression())]
        ),
        "Random Forest": Pipeline(
            [
                ("preprocessor", make_preprocessor()),
                (
                    "model",
                    RandomForestRegressor(
                        n_estimators=300,
                        min_samples_leaf=5,
                        random_state=random_state,
                        n_jobs=1,  # deterministic, modest-resource execution
                    ),
                ),
            ]
        ),
    }


def evaluate_predictions(
    y_true: pd.Series | np.ndarray,
    y_pred: np.ndarray,
) -> dict[str, float]:
    mse = mean_squared_error(y_true, y_pred)
    return {
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "RMSE": float(np.sqrt(mse)),
        "R2": float(r2_score(y_true, y_pred)),
    }


def _choose_time_series_splits(n_rows: int, max_splits: int = 5) -> int:
    candidates = [
        n
        for n in range(2, min(max_splits, n_rows - 1) + 1)
        if n_rows // (n + 1) >= 2
    ]
    if not candidates:
        raise ValueError(
            "시간 순서 교차검증에는 각 validation fold에 최소 2개 행이 필요합니다."
        )
    return max(candidates)


def cross_validate_regression_models(models, X_train, y_train, max_splits=5, dates=None):
    """TimeSeriesSplit on unique calendar dates, mapped back to order rows.

    This is stricter than the reference row split: no calendar day crosses a
    training/validation boundary. Final Test is not accepted by this function.
    """
    from sklearn.base import clone
    validate_feature_columns(X_train.columns)
    if dates is None:
        raise ValueError("Date-grouped CV requires training dates explicitly")
    days=pd.to_datetime(pd.Series(dates)).dt.normalize().reset_index(drop=True)
    unique_days=pd.Index(days.drop_duplicates())
    if not unique_days.is_monotonic_increasing:
        raise ValueError("Training dates must be sorted")
    n_splits=_choose_time_series_splits(len(unique_days),max_splits)
    splits=[]; fold_rows=[]; scores=[]; preprocessing=[]
    for fold,(train_days,val_days) in enumerate(TimeSeriesSplit(n_splits=n_splits).split(unique_days),1):
        ti=np.flatnonzero(days.isin(unique_days[train_days]).to_numpy())
        vi=np.flatnonzero(days.isin(unique_days[val_days]).to_numpy())
        if days.iloc[ti].max()>=days.iloc[vi].min() or len(vi)<2:
            raise ValueError("CV temporal gate failed")
        splits.append((ti,vi))
        fold_rows.append(dict(fold=fold,train_rows=len(ti),validation_rows=len(vi),
            train_start=days.iloc[ti].min().date().isoformat(),train_end=days.iloc[ti].max().date().isoformat(),
            validation_start=days.iloc[vi].min().date().isoformat(),validation_end=days.iloc[vi].max().date().isoformat(),
            strict_train_before_validation=True))
    for model_name,unfitted in models.items():
        for fold,(ti,vi) in enumerate(splits,1):
            model=clone(unfitted)
            xt=X_train.iloc[ti]; yt=y_train.iloc[ti]
            model.fit(xt,yt)
            pred=model.predict(X_train.iloc[vi])
            metrics=evaluate_predictions(y_train.iloc[vi],pred)
            scores.append(dict(model=model_name,fold=fold,MAE=metrics['MAE'],R2=metrics['R2']))
            pre=model.named_steps['preprocessor']
            num=pre.named_transformers_['numeric']
            cat=pre.named_transformers_['categorical']
            median=np.nanmedian(xt[NUMERIC_FEATURES].to_numpy(dtype=float),axis=0)
            numeric_ok=bool(np.allclose(num.named_steps['imputer'].statistics_,median))
            transformed=num.named_steps['imputer'].transform(xt[NUMERIC_FEATURES])
            scale_ok=bool(np.allclose(num.named_steps['scaler'].mean_,transformed.mean(axis=0)))
            cats=cat.named_steps['imputer'].transform(xt[CATEGORICAL_FEATURES])
            categories_ok=all(set(observed)==set(expected) for observed,expected in
                zip(cat.named_steps['encoder'].categories_,[np.unique(cats[:,j]) for j in range(cats.shape[1])]))
            assert numeric_ok and scale_ok and categories_ok
            preprocessing.append(dict(model=model_name,fold=fold,fit_rows=len(ti),
                numeric_median_matches_train=numeric_ok,scaler_mean_matches_train=scale_ok,
                encoder_categories_match_train=categories_ok,status='PASS'))
    fold_scores=pd.DataFrame(scores)
    rows=[]
    for name,group in fold_scores.groupby('model',sort=False):
        rows.append(dict(model=name,n_splits=n_splits,cv_MAE_mean=float(group.MAE.mean()),
            cv_MAE_std=float(group.MAE.std(ddof=0)),cv_R2_mean=float(group.R2.mean())))
    summary=pd.DataFrame(rows).sort_values(['cv_MAE_mean','model']).reset_index(drop=True)
    summary.attrs['fold_details']=pd.DataFrame(fold_rows)
    summary.attrs['fold_scores']=fold_scores
    summary.attrs['preprocessing_audit']=pd.DataFrame(preprocessing)
    return summary


def select_diagnostic_model(cv_summary: pd.DataFrame) -> str:
    """Freeze the best non-baseline candidate using training-only CV MAE."""
    required = {"model", "cv_MAE_mean"}
    missing = sorted(required - set(cv_summary.columns))
    if missing:
        raise KeyError(f"CV 요약에 필요한 컬럼이 없습니다: {missing}")
    candidates = cv_summary.loc[
        ~cv_summary["model"].eq("Baseline Mean")
    ].sort_values(["cv_MAE_mean", "model"])
    if candidates.empty:
        raise ValueError("선택할 비베이스라인 모델 결과가 없습니다.")
    return str(candidates.iloc[0]["model"])


def train_and_evaluate_models(
    models: dict[str, Pipeline],
    selected_model_name: str,
    X_train: pd.DataFrame,
    X_test: pd.DataFrame,
    y_train: pd.Series,
    y_test: pd.Series,
) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """Evaluate only baseline and the frozen selected model on final test."""
    validate_feature_columns(X_train.columns)
    if list(X_train.columns) != list(X_test.columns):
        raise ValueError("훈련·테스트 입력 컬럼 구성이 다릅니다.")
    if selected_model_name == "Baseline Mean":
        raise ValueError("선택 모델은 비베이스라인 후보여야 합니다.")
    if selected_model_name not in models or "Baseline Mean" not in models:
        raise KeyError("최종 평가에 필요한 모델이 없습니다.")

    rows: list[dict[str, Any]] = []
    predictions: dict[str, np.ndarray] = {}
    for model_name in ["Baseline Mean", selected_model_name]:
        model = models[model_name]
        model.fit(X_train, y_train)
        train_pred = model.predict(X_train)
        test_pred = model.predict(X_test)
        train_metrics = evaluate_predictions(y_train, train_pred)
        test_metrics = evaluate_predictions(y_test, test_pred)
        rows.append(
            {
                "model": model_name,
                "selection_role": (
                    "baseline" if model_name == "Baseline Mean" else "selected_by_train_cv"
                ),
                "train_MAE": train_metrics["MAE"],
                "test_MAE": test_metrics["MAE"],
                "test_RMSE": test_metrics["RMSE"],
                "test_R2": test_metrics["R2"],
            }
        )
        predictions[model_name] = test_pred

    comparison = pd.DataFrame(rows)
    baseline_mae = float(
        comparison.loc[comparison["model"].eq("Baseline Mean"), "test_MAE"].iloc[0]
    )
    if baseline_mae == 0:
        comparison["MAE_improvement_vs_baseline_pct"] = np.nan
    else:
        comparison["MAE_improvement_vs_baseline_pct"] = (
            (baseline_mae - comparison["test_MAE"]) / baseline_mae * 100
        ).round(2)
    return comparison.reset_index(drop=True), predictions


def build_split_summary(train_data: pd.DataFrame, test_data: pd.DataFrame) -> pd.DataFrame:
    total_rows = len(train_data) + len(test_data)
    return pd.DataFrame(
        [
            {
                "split": "train",
                "rows": len(train_data),
                "ratio_pct": round(len(train_data) / total_rows * 100, 2),
                "start_date": train_data["order_date"].min(),
                "end_date": train_data["order_date"].max(),
            },
            {
                "split": "test",
                "rows": len(test_data),
                "ratio_pct": round(len(test_data) / total_rows * 100, 2),
                "start_date": test_data["order_date"].min(),
                "end_date": test_data["order_date"].max(),
            },
        ]
    )


def build_feature_audit():
    reasons={
        'order_month':'주문 접수 시 달력에서 계산하는 월(1~12)',
        'order_dayofweek':'주문 접수 시 달력에서 계산하는 요일(월=0~일=6)',
        'age':'접수 시 사용 가능한 고객 나이로 가정; 과거 시점 이력 없음',
        'payment_method':'접수 초기 고객이 고른 예정 결제수단으로 가정',
        'gender':'접수 시 고객 프로필에 이미 등록된 값으로 가정',
        'city':'접수 시 고객 프로필 도시로 가정; 과거 변경 이력 없음'}
    rows=[dict(column=c,selected=True,available_at_prediction=True,target_ingredient=False,
               post_outcome_or_id=False,role='allowed_feature',reason=reasons[c]) for c in FEATURE_COLUMNS]
    for c in sorted(FORBIDDEN_FEATURES):
        ingredient=c in {'order_total','line_total','quantity','unit_price','item_count','total_quantity','avg_unit_price'}
        rows.append(dict(column=c,selected=False,available_at_prediction=False,target_ingredient=ingredient,
            post_outcome_or_id=c in {'order_status','order_id','customer_id','product_id'},
            role='forbidden',reason=FORBIDDEN_REASONS[c]))
    return pd.DataFrame(rows)


def create_prediction_result(
    test_data: pd.DataFrame,
    y_test: pd.Series,
    y_pred: np.ndarray,
    model_name: str,
) -> pd.DataFrame:
    if len(test_data) != len(y_test) or len(y_test) != len(y_pred):
        raise ValueError("테스트 데이터와 예측값의 길이가 일치하지 않습니다.")
    result = test_data[["order_id", "order_date"]].reset_index(drop=True).copy()
    result["actual_order_total"] = y_test.reset_index(drop=True)
    result["predicted_order_total"] = y_pred
    result["residual"] = result["actual_order_total"] - result["predicted_order_total"]
    result["abs_error"] = result["residual"].abs()
    result["model"] = model_name
    return result.sort_values("abs_error", ascending=False).reset_index(drop=True)


def public_prediction_result(prediction_result):
    """Rank labels are unrelated to original order/customer IDs; omit exact dates."""
    result=prediction_result[['actual_order_total','predicted_order_total','residual','abs_error','model']].copy()
    result.insert(0,'case_label',[f'Error rank {i:02d}' for i in range(1,len(result)+1)])
    return result


def configure_korean_font() -> bool:
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    for font_name in [
        "Malgun Gothic",
        "AppleGothic",
        "NanumGothic",
        "Noto Sans CJK KR",
        "Noto Sans KR",
    ]:
        if font_name in available_fonts:
            plt.rcParams["font.family"] = font_name
            plt.rcParams["axes.unicode_minus"] = False
            return True
    return False


def create_diagnostic_figures(prediction_result, figure_dir='reports/figures'):
    from matplotlib.ticker import FuncFormatter,MaxNLocator
    from src.visualization import setup_korean_font
    import shutil
    setup_korean_font()
    output_dir=Path(figure_dir); output_dir.mkdir(parents=True,exist_ok=True)
    model_name=str(prediction_result.model.iloc[0]); n=len(prediction_result)
    actual=prediction_result.actual_order_total.to_numpy(dtype=float)
    pred=prediction_result.predicted_order_total.to_numpy(dtype=float)
    residual=prediction_result.residual.to_numpy(dtype=float)
    scope=f"Final Test {prediction_result.order_date.min():%Y-%m-%d}~{prediction_result.order_date.max():%Y-%m-%d} | {n}주문 | Train CV 고정 모델"
    money=FuncFormatter(lambda x,pos:f'{x:,.0f}')
    checks=[]
    fig,ax=plt.subplots(figsize=(8.4,6.8))
    pts=ax.scatter(actual,pred,alpha=.65,color='#4177a6',label=model_name)
    np.testing.assert_allclose(np.asarray(pts.get_offsets()),np.column_stack([actual,pred]))
    low=min(0,float(actual.min()),float(pred.min()));high=max(float(actual.max()),float(pred.max()))*1.06
    line,=ax.plot([low,high],[low,high],'--',color='#9a4a38',label='완전 예측 y=x')
    np.testing.assert_array_equal(line.get_xdata(),line.get_ydata())
    ax.set(xlim=(low,high),ylim=(low,high),xlabel='실제 주문 금액 (원)',ylabel='예측 주문 금액 (원)')
    ax.set_title(f'실제값과 예측값 — {model_name}',loc='left',pad=35)
    ax.text(0,1.02,scope,transform=ax.transAxes,color='#555',fontsize=9)
    ax.xaxis.set_major_formatter(money);ax.yaxis.set_major_formatter(money)
    ax.tick_params(axis='x',rotation=25);ax.legend();ax.grid(alpha=.15)
    path1=output_dir/'ch09_actual_vs_predicted.png'
    fig.tight_layout();fig.savefig(path1,dpi=150,bbox_inches='tight',metadata={'Software':'matplotlib / Chapter09'});plt.close(fig)
    checks.extend([['scatter coordinates',n,n,True],['identity line equal x/y',2,2,True]])
    fig,ax=plt.subplots(figsize=(8.8,5.5))
    counts,edges,patches=ax.hist(residual,bins=15,color='#4177a6',edgecolor='white')
    exp_counts,exp_edges=np.histogram(residual,bins=15)
    np.testing.assert_array_equal(counts,exp_counts);np.testing.assert_allclose(edges,exp_edges)
    np.testing.assert_array_equal([p.get_height() for p in patches],exp_counts)
    zero=ax.axvline(0,linestyle='--',color='#9a4a38',label='잔차 0')
    np.testing.assert_array_equal(zero.get_xdata(),[0,0])
    ax.set(xlabel='잔차 = 실제값 - 예측값 (원)',ylabel='주문 수 (건)')
    ax.set_title(f'잔차 분포 — {model_name}',loc='left',pad=35)
    ax.text(0,1.02,scope,transform=ax.transAxes,color='#555',fontsize=9)
    ax.xaxis.set_major_formatter(money);ax.yaxis.set_major_locator(MaxNLocator(integer=True));ax.legend();ax.grid(axis='y',alpha=.15)
    ax.tick_params(axis='x',rotation=25)
    path2=output_dir/'ch09_residual_histogram.png'
    fig.tight_layout();fig.savefig(path2,dpi=150,bbox_inches='tight',metadata={'Software':'matplotlib / Chapter09'});plt.close(fig)
    checks.extend([['histogram count sum',int(counts.sum()),n,int(counts.sum())==n],['zero reference line',0,0,True]])
    canonical=output_dir.parent.parent/'chapter09/images';canonical.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(path1,canonical/'graph01.png');shutil.copyfile(path2,canonical/'graph02.png')
    frame=pd.DataFrame(checks,columns=['check','value','expected','passed'])
    frame['status']=frame.passed.map({True:'PASS',False:'FAIL'})
    frame.to_csv(output_dir.parent/'ch09_regression_artist_checks.csv',index=False,encoding='utf-8-sig')
    return {'actual_vs_predicted_figure':path1,'residual_figure':path2,'artist_checks':frame}


def build_leakage_checklist():
    items=[
        ('예측 시점·프로필 정보 가정 명시','report'),
        ('목표값과 계산 재료를 Feature에서 제외','feature_audit'),
        ('사후 주문 상태와 식별자를 Feature에서 제외','feature_audit'),
        ('각 Train fold에서만 전처리 fit','preprocessing_audit'),
        ('Train/Final Test 날짜 엄격 분리','split_summary'),
        ('CV Train/Validation 날짜 엄격 분리','cv_folds'),
        ('Train CV 최저 MAE로 비Baseline 모델 고정','selection_manifest'),
        ('선택 파일을 먼저 저장한 뒤 Final Test 평가','selection_order'),
        ('Final Test는 Baseline과 고정모델만 비교','model_comparison'),
        ('MAE·RMSE·R²와 낮은 성능도 보고','model_comparison'),
        ('공개 결과에 원본 식별자와 개별 날짜 제외','public_predictions'),
        ('실제 그래프 값과 계산 지표 대조','artist_checks / metric_checks')]
    return pd.DataFrame([{'check_item':i,'status':'PASS','evidence':e} for i,e in items])


def build_regression_validation(
    train_data: pd.DataFrame,
    test_data: pd.DataFrame,
    cv_summary: pd.DataFrame,
    selected_model_name: str,
    model_comparison: pd.DataFrame,
) -> pd.DataFrame:
    """Create machine-checkable evidence for the core Chapter09 rules."""
    leaked_features = sorted(set(FEATURE_COLUMNS) & FORBIDDEN_FEATURES)
    strict_time_order = (
        train_data["order_date"].max().normalize()
        < test_data["order_date"].min().normalize()
    )
    selected_in_cv = selected_model_name in set(cv_summary["model"])
    baseline_present = "Baseline Mean" in set(model_comparison["model"])
    selected_present = selected_model_name in set(model_comparison["model"])
    rows = [
        ["forbidden_feature_overlap", len(leaked_features), not leaked_features],
        ["strict_train_before_test", strict_time_order, strict_time_order],
        ["selected_model_exists_in_train_cv", selected_in_cv, selected_in_cv],
        ["final_test_contains_baseline", baseline_present, baseline_present],
        [
            "final_test_contains_frozen_selected_model",
            selected_present,
            selected_present,
        ],
        ["test_rows_for_r2", len(test_data), len(test_data) >= 2],
    ]
    validation = pd.DataFrame(rows, columns=["check", "value", "passed"])
    validation["status"] = validation["passed"].map({True: "PASS", False: "FAIL"})
    failed = validation.loc[validation["status"].eq("FAIL")]
    if not failed.empty:
        raise ValueError(
            "회귀 분석 핵심 검증에 실패했습니다:\n" + failed.to_string(index=False)
        )
    return validation.drop(columns="passed")


def build_regression_report(model_data,split_summary,feature_audit,cv_summary,selected_model_name,
                            model_comparison,prediction_result,validation,checklist):
    selected=model_comparison.loc[model_comparison.model.eq(selected_model_name)].iloc[0]
    def table(x):
        return x.to_markdown(index=False,floatfmt=',.3f')
    decision='현재 데이터로는 사용 보류' if selected.MAE_improvement_vs_baseline_pct<=0 else '추가 검증 후 사용 가능'
    return '\n\n'.join([
        '# Chapter 09 회귀 분석 보고서',
        '작성·실행일: 2026-11-02. 코드 작성·실행·검토에는 Codex의 도움을 받았다.',
        '## 문제와 데이터\n주문 접수 초기, 예정 결제수단과 고객 프로필은 알지만 장바구니 상세 확정 전이라는 교육용 시점을 가정했다. 주문 1건의 order_total을 예측한다. 현재 프로필의 age·gender·city가 과거 주문 시점에도 알려져 있었다는 가정이며, 실제 as-of 이력은 없어 운영 적용 전에 검증해야 한다. 주문 취소·환불 상태와 관계없이 공통 합성 주문 300건을 사용하며 order_status는 Feature에서 제외했다. target은 기록된 상세 합계이고 회계상 순매출이 아니다.',
        '## Target·Feature\nline_total = quantity × unit_price; order_total = order_id별 line_total 합계. 상세 개수·수량·단가·금액·사후 상태·식별자를 Feature에 넣지 않았다. 원본 Decimal 재계산과 관계 검증은 ch09_regression_target_checks.csv에 저장했다.',
        table(feature_audit),
        '## 날짜순 분리\n최종 분할은 고유 날짜의 마지막 약20%다. 표의 실제 주문 수 비율은 정확히80/20일 필요가 없다. CV도 고유 날짜에 TimeSeriesSplit 5fold를 적용해 같은 날짜가 Train/Validation 경계를 넘지 않도록 공식 행 단위 CV를 강화했다.',
        table(split_summary),
        '## Train CV\n전처리는 매fold Train에서만 median/scaler/most-frequent/one-hot을 fit했다. 고정 후보는 Mean Dummy, Linear Regression, Random Forest(300trees, min_samples_leaf5, seed42)다. 나머지 설정을 Test 결과로 조정하지 않았다.',
        table(cv_summary),
        f'선택 모델: **{selected_model_name}**. 비Baseline 후보 중 Train CV MAE 평균이 가장 낮은 모델을 선택하고 manifest를 Final Test 평가 전에 파일로 고정했다. Baseline이 후보보다 좋더라도 교육용 비교를 위해 비Baseline 후보를 고정 평가한다.',
        '## Final Test: Baseline vs Frozen Model',table(model_comparison),
        f'MAE는 원 단위 평균 절대오차, RMSE는 큰 오차에 더 민감한 원 단위 지표다. 선택 모델의 Baseline 대비 MAE 개선율은 {selected.MAE_improvement_vs_baseline_pct:.2f}%이며 음수면 더 나빴다는 뜻이다. R²는 Test 실제값 평균을 쓰는 상수예측 대비 제곱오차로 계산된다. Dummy는 Train 평균을 예측하므로 R²=0 기준과 정확히 동일하지 않다. 음수 R²는 반드시 실행 오류라는 뜻이 아니다.',
        '## 공개 오차 사례\n순위 라벨을 새로 부여했고 원본 order_id/customer_id와 개별 주문 날짜는 공개하지 않았다.',table(public_prediction_result(prediction_result).head(3)),
        '큰 양수 잔차는 과소예측, 음수 잔차는 과대예측이다. 거래 상세를 Feature에서 제외했으므로 실제 장바구니 차이를 구분하지 못했을 가능성이 있으나 원인으로 확정하지 않는다. 실제 운영에서는 예측 시점에 이미 알려진 상품군·프로모션·고객 과거 구매이력의 시점 유효성을 먼저 확인해야 한다.',
        '## 자동 검증',table(validation),
        '## 검증·해석 체크리스트',table(checklist),
        f'## 최종 판단\n**{decision}**. 작은 합성 데이터와 현재 프로필 가정으로 실제 주문 금액을 보장할 수 없다. 반복 날짜, CV 변동, Baseline 대비 성능, 큰 오차를 함께 보았다. Final Test를 보고 후보나 Feature를 바꾸지 않았다.',
        '## 재현\npython scripts/prepare_ch09_data.py → python scripts/run_regression_analysis.py. 원본은 고정 공식 commit과 SHA-256으로 확인하고 기존 Chapter05~08 입력은 변경하지 않는다. Internal CSV 2개는 생성되지만 Git에서 제외하며 공개 CSV와 Notebook은 순위 라벨만 사용한다.',
    ])+'\n'


def save_regression_outputs(
    model_data: pd.DataFrame,
    split_summary: pd.DataFrame,
    feature_audit: pd.DataFrame,
    cv_summary: pd.DataFrame,
    selected_model_name: str,
    model_comparison: pd.DataFrame,
    prediction_result: pd.DataFrame,
    validation: pd.DataFrame,
    checklist: pd.DataFrame,
    report_dir: str | Path = "reports",
) -> dict[str, Path]:
    output_dir = Path(report_dir)
    figure_dir = output_dir / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "model_data_internal": output_dir / "ch09_regression_model_data_internal.csv",
        "split_summary": output_dir / "ch09_regression_split_summary.csv",
        "feature_audit": output_dir / "ch09_regression_feature_audit.csv",
        "cv_summary": output_dir / "ch09_regression_cv_summary.csv",
        "model_comparison": output_dir / "ch09_regression_model_comparison.csv",
        "predictions_internal": output_dir / "ch09_regression_predictions_internal.csv",
        "validation": output_dir / "ch09_regression_validation.csv",
        "checklist": output_dir / "ch09_regression_checklist.csv",
        "report": output_dir / "ch09_regression_report.md",
    }
    model_data.to_csv(paths["model_data_internal"], index=False, encoding="utf-8-sig")
    split_summary.to_csv(paths["split_summary"], index=False, encoding="utf-8-sig")
    feature_audit.to_csv(paths["feature_audit"], index=False, encoding="utf-8-sig")
    cv_summary.to_csv(paths["cv_summary"], index=False, encoding="utf-8-sig")
    model_comparison.to_csv(paths["model_comparison"], index=False, encoding="utf-8-sig")
    prediction_result.to_csv(
        paths["predictions_internal"], index=False, encoding="utf-8-sig"
    )
    validation.to_csv(paths["validation"], index=False, encoding="utf-8-sig")
    checklist.to_csv(paths["checklist"], index=False, encoding="utf-8-sig")
    report_text = build_regression_report(
        model_data=model_data,
        split_summary=split_summary,
        feature_audit=feature_audit,
        cv_summary=cv_summary,
        selected_model_name=selected_model_name,
        model_comparison=model_comparison,
        prediction_result=prediction_result,
        validation=validation,
        checklist=checklist,
    )
    paths["report"].write_text(report_text, encoding="utf-8")
    paths.update(create_diagnostic_figures(prediction_result, figure_dir))
    return paths


def run_regression_analysis(processed_dir='data/ch09/processed',report_dir='reports',test_size=.2,random_state=42):
    import hashlib,json
    processed_dir,report_dir=Path(processed_dir),Path(report_dir)
    report_dir.mkdir(parents=True,exist_ok=True)
    data=load_regression_source_data(processed_dir)
    model_data=build_regression_dataset(data['customers'],data['orders'],data['order_items'])
    target_checks=_source_target_checks(data,model_data,processed_dir)
    train_data,test_data=split_model_data_by_time(model_data,test_size)
    X_train=train_data[FEATURE_COLUMNS].copy();y_train=train_data[TARGET_COLUMN].copy()
    X_test=test_data[FEATURE_COLUMNS].copy();y_test=test_data[TARGET_COLUMN].copy()
    models=make_regression_models(random_state)
    cv_summary=cross_validate_regression_models(models,X_train,y_train,dates=train_data.order_date)
    fold_details=cv_summary.attrs['fold_details'];fold_scores=cv_summary.attrs['fold_scores']
    preprocessing_audit=cv_summary.attrs['preprocessing_audit']
    selected_model_name=select_diagnostic_model(cv_summary)
    selected_cv=cv_summary.loc[cv_summary.model.eq(selected_model_name)].iloc[0]
    selection_manifest={
        'stage':'train_cv_frozen_before_final_test', 'selected_model':selected_model_name,
        'selection_rule':'minimum mean CV MAE among non-baseline candidates; tie by model name',
        'selected_cv_mae':float(selected_cv.cv_MAE_mean),'cv_summary_sha256':hashlib.sha256(cv_summary.to_csv(index=False).encode()).hexdigest(),
        'cv_split':'TimeSeriesSplit on unique training dates, n_splits=5',
        'test_size_unique_dates':test_size,'random_state':random_state,
        'features':FEATURE_COLUMNS,
        'fixed_candidates':{'Baseline Mean':'DummyRegressor(strategy=mean)','Linear Regression':'LinearRegression()',
                            'Random Forest':{'n_estimators':300,'min_samples_leaf':5,'random_state':random_state,'n_jobs':1}}}
    frozen_path=report_dir/'ch09_regression_selection_manifest.json'
    frozen_path.write_text(json.dumps(selection_manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    frozen_bytes=frozen_path.read_bytes()
    # No test scores exist before this line. The frozen choice is passed unchanged.
    model_comparison,predictions=train_and_evaluate_models(models,selected_model_name,X_train,X_test,y_train,y_test)
    assert frozen_path.read_bytes()==frozen_bytes
    prediction_result=create_prediction_result(test_data,y_test,predictions[selected_model_name],selected_model_name)
    split_summary=build_split_summary(train_data,test_data);feature_audit=build_feature_audit()
    metric_checks=_metric_checks(y_train,y_test,model_comparison,predictions,selected_model_name)
    validation=build_regression_validation(train_data,test_data,cv_summary,selected_model_name,model_comparison)
    additional=[]
    def record(check,value,passed):
        additional.append({'check':check,'value':value,'status':'PASS' if passed else 'FAIL'})
    record('target_and_relationship_checks',len(target_checks),bool(target_checks.status.eq('PASS').all()))
    record('strict_cv_date_groups',len(fold_details),bool(fold_details.strict_train_before_validation.all()))
    record('train_only_preprocessing_audit',len(preprocessing_audit),bool(preprocessing_audit.status.eq('PASS').all()))
    best=cv_summary.loc[~cv_summary.model.eq('Baseline Mean')].sort_values(['cv_MAE_mean','model']).iloc[0].model
    record('selected_is_minimum_train_cv_mae',selected_model_name,selected_model_name==best)
    record('selection_manifest_unchanged',True,frozen_path.read_bytes()==frozen_bytes)
    record('exactly_baseline_and_frozen_final_models',len(model_comparison),set(model_comparison.model)=={'Baseline Mean',selected_model_name} and len(model_comparison)==2)
    record('metrics_independently_recalculated',len(metric_checks),bool(metric_checks.status.eq('PASS').all()))
    public_predictions=public_prediction_result(prediction_result)
    forbidden_public={'order_id','customer_id','product_id','name','email','phone','address','order_date'}
    record('public_prediction_identifier_overlap',len(forbidden_public & set(public_predictions.columns)),not forbidden_public.intersection(public_predictions.columns))
    figures=create_diagnostic_figures(prediction_result,report_dir/'figures')
    artist_checks=figures.pop('artist_checks')
    record('graph_artist_values_match',len(artist_checks),bool(artist_checks.status.eq('PASS').all()))
    validation=pd.concat([validation,pd.DataFrame(additional)],ignore_index=True)
    assert validation.status.eq('PASS').all(),validation.to_string(index=False)
    checklist=build_leakage_checklist()
    output_paths=save_regression_outputs(model_data,split_summary,feature_audit,cv_summary,selected_model_name,
        model_comparison,prediction_result,validation,checklist,report_dir)
    # save_regression_outputs regenerates the same deterministic figures; do not put DataFrames in paths.
    output_paths.pop('artist_checks',None)
    extra_tables={'target_checks':target_checks,'cv_folds':fold_details,'cv_fold_scores':fold_scores,
        'preprocessing_audit':preprocessing_audit,'metric_checks':metric_checks,'public_predictions':public_predictions}
    for name,frame in extra_tables.items():
        path=report_dir/f'ch09_regression_{name}.csv';frame.to_csv(path,index=False,encoding='utf-8-sig');output_paths[name]=path
    output_paths['selection_manifest']=frozen_path
    events=pd.DataFrame({'step':range(1,7),'event':['prepare target and split','train-only CV candidates',
        'select by train CV','write frozen manifest','evaluate baseline and frozen model on final test','validate and save outputs']})
    events.to_csv(report_dir/'ch09_regression_selection_order.csv',index=False,encoding='utf-8-sig')
    output_paths['selection_order']=report_dir/'ch09_regression_selection_order.csv'
    return {'data':data,'model_data':model_data,'train_data':train_data,'test_data':test_data,
        'X_train':X_train,'X_test':X_test,'y_train':y_train,'y_test':y_test,'models':models,
        'cv_summary':cv_summary,'selected_model_name':selected_model_name,'best_model_name':selected_model_name,
        'model_comparison':model_comparison,'predictions':predictions,'prediction_result':prediction_result,
        'public_predictions':public_predictions,'split_summary':split_summary,'feature_audit':feature_audit,
        'validation':validation,'checklist':checklist,'output_paths':output_paths,'target_checks':target_checks,
        'fold_details':fold_details,'fold_scores':fold_scores,'preprocessing_audit':preprocessing_audit,
        'selection_manifest':selection_manifest,'selection_order':events,'artist_checks':artist_checks,'metric_checks':metric_checks}



def _source_target_checks(data, model_data, processed_dir):
    """Validate source PK/FK and independently aggregate the pinned raw detail CSV."""
    import csv
    from decimal import Decimal
    from collections import defaultdict
    products=pd.read_csv(Path(processed_dir)/'products_clean.csv')
    datasets={**data,'products':products}
    rows=[]
    def check(name,value,expected):
        passed=value==expected
        rows.append({'check':name,'value':value,'expected':expected,'status':'PASS' if passed else 'FAIL'})
        if not passed:raise ValueError(f'{name}: {value} != {expected}')
    for name,key in [('customers','customer_id'),('products','product_id'),('orders','order_id'),('order_items','order_item_id')]:
        df=datasets[name]
        check(f'{name}_pk_missing',int(df[key].isna().sum()),0)
        check(f'{name}_pk_duplicate',int(df[key].duplicated().sum()),0)
    for child,fk,parent,pk in [('orders','customer_id','customers','customer_id'),('order_items','order_id','orders','order_id'),('order_items','product_id','products','product_id')]:
        count=int((datasets[child][fk].isna() | ~datasets[child][fk].isin(datasets[parent][pk])).sum())
        check(f'FK_{child}_{fk}',count,0)
    items=data['order_items'];expected=items.quantity*items.unit_price
    check('line_total_mismatch',int((items.line_total!=expected).sum()),0)
    totals=defaultdict(Decimal)
    raw_path=Path(processed_dir).parent/'raw/order_items.csv'
    with raw_path.open(encoding='utf-8-sig',newline='') as f:
        raw_rows=list(csv.DictReader(f))
    for row in raw_rows:
        totals[int(row['order_id'])]+=Decimal(row['quantity'])*Decimal(row['unit_price'])
    found=dict(zip(model_data.order_id.astype(int),model_data.order_total.astype(int)))
    check('raw_detail_count',len(raw_rows),len(items))
    check('raw_order_target_key_count',len(totals),len(found))
    mismatches=sum(int(Decimal(amount)!=totals.get(order_id)) for order_id,amount in found.items())
    check('raw_Decimal_per_order_target_mismatch',mismatches,0)
    check('raw_Decimal_total_amount',int(sum(totals.values())),int(model_data.order_total.sum()))
    check('orders_without_target',len(data['orders'])-len(found),0)
    check('model_rows_equals_order_rows',len(model_data),len(data['orders']))
    return pd.DataFrame(rows)


def _metric_checks(y_train,y_test,comparison,predictions,selected):
    """Recompute sklearn metrics from prediction arrays with plain NumPy formulas."""
    rows=[];actual=y_test.to_numpy(dtype=float)
    for name,pred in predictions.items():
        error=actual-pred
        formulas={'test_MAE':float(np.abs(error).mean()),'test_RMSE':float(np.sqrt(np.square(error).mean())),
                  'test_R2':float(1-np.square(error).sum()/np.square(actual-actual.mean()).sum())}
        row=comparison.loc[comparison.model.eq(name)].iloc[0]
        for metric,value in formulas.items():
            ok=bool(np.isclose(value,float(row[metric]),rtol=1e-12,atol=1e-8))
            rows.append({'check':f'{name}_{metric}','actual':value,'expected':float(row[metric]),'status':'PASS' if ok else 'FAIL'})
    mean=float(y_train.mean())
    baseline_ok=bool(np.allclose(predictions['Baseline Mean'],mean))
    rows.append({'check':'baseline_equals_train_mean','actual':float(predictions['Baseline Mean'][0]),'expected':mean,'status':'PASS' if baseline_ok else 'FAIL'})
    baseline=float(comparison.loc[comparison.model.eq('Baseline Mean'),'test_MAE'].iloc[0])
    selected_row=comparison.loc[comparison.model.eq(selected)].iloc[0]
    improvement=round((baseline-float(selected_row.test_MAE))/baseline*100,2)
    rows.append({'check':'MAE_improvement_pct','actual':improvement,'expected':float(selected_row.MAE_improvement_vs_baseline_pct),
                 'status':'PASS' if improvement==float(selected_row.MAE_improvement_vs_baseline_pct) else 'FAIL'})
    return pd.DataFrame(rows)
