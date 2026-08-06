"""Generic grouped-aggregation helper shared by the report builders."""
import pandas as pd

from labstats.stats.engine import derive_patient_id


def aggregate_by(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    work = df.copy()
    work["patient_id"] = derive_patient_id(work)
    work["_is_package_line"] = work["is_package"] == True  # noqa: E712
    work["_is_individual_line"] = work["is_package"] == False  # noqa: E712

    grouped = work.groupby(group_cols, dropna=False)
    result = grouped.agg(
        unique_patients=("patient_id", pd.Series.nunique),
        requests=("order_no", pd.Series.nunique),
        package_line_items=("_is_package_line", "sum"),
        individual_test_line_items=("_is_individual_line", "sum"),
        analytical_tests=("analytical_test_units", "sum"),
        row_count=("order_no", "size"),
    ).reset_index()

    result["package_line_items"] = result["package_line_items"].astype(int)
    result["individual_test_line_items"] = result["individual_test_line_items"].astype(int)
    result["analytical_tests"] = result["analytical_tests"].astype(int)
    return result


def add_percentage_of_total(df: pd.DataFrame, value_col: str, total: float, out_col: str) -> pd.DataFrame:
    out = df.copy()
    if total:
        out[out_col] = (out[value_col] / total * 100).round(1)
    else:
        out[out_col] = "Not Applicable"
    return out
