"""Report Format 7 (lite): Package Utilization.

Packages contribute zero analytical-test units in their own name - their
component parameters carry the workload (see labstats.stats.analytical_units
and the Full Test-Name / Abbreviation reports). This report answers the
separate question of how often each package itself was ordered, and flags
any declared-vs-actual component count mismatch from the master list.
"""
import pandas as pd

from labstats.stats.aggregate import aggregate_by


def build_package_report(with_units: pd.DataFrame) -> pd.DataFrame:
    needed = [
        "row_kind", "standard_report_name", "abbreviation", "division", "order_no",
        "analytical_test_units", "mrn", "id_number", "declared_component_count", "actual_component_count",
    ]
    df = with_units.loc[with_units["row_kind"] == "package", needed].copy()
    if df.empty:
        return pd.DataFrame(
            columns=[
                "package_name",
                "abbreviation",
                "division",
                "unique_patients",
                "package_requests",
                "declared_component_count",
                "actual_component_count",
                "component_count_mismatch",
            ]
        )
    df["division"] = df["division"].replace("", "Unclassified / Missing Division")

    table = aggregate_by(df, ["standard_report_name", "abbreviation", "division"])
    counts = df.groupby(["standard_report_name", "abbreviation", "division"]).agg(
        declared_component_count=("declared_component_count", "first"),
        actual_component_count=("actual_component_count", "first"),
    ).reset_index()

    table = table.merge(counts, on=["standard_report_name", "abbreviation", "division"])
    table["component_count_mismatch"] = table["declared_component_count"] != table["actual_component_count"]
    table = table.rename(columns={"standard_report_name": "package_name", "requests": "package_requests"})
    table = table[
        [
            "package_name",
            "abbreviation",
            "division",
            "unique_patients",
            "package_requests",
            "declared_component_count",
            "actual_component_count",
            "component_count_mismatch",
        ]
    ]
    table = table.sort_values("package_requests", ascending=False).reset_index(drop=True)
    return table
