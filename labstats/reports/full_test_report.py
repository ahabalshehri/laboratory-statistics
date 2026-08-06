"""Report Format 2: Detailed Full Test-Name Report (spec section 21)."""
import pandas as pd

from labstats.stats.aggregate import add_percentage_of_total, aggregate_by


def build_full_test_report(with_units: pd.DataFrame) -> pd.DataFrame:
    df = with_units.copy()
    df["division"] = df["division"].replace("", "Unclassified / Missing Division")

    group_cols = ["division", "standard_report_name", "full_test_name", "abbreviation", "is_package"]
    table = aggregate_by(df, group_cols)

    total_workload = table["analytical_tests"].sum()
    table = add_percentage_of_total(table, "analytical_tests", total_workload, "pct_of_total_workload")

    division_totals = table.groupby("division")["analytical_tests"].transform("sum")
    table["pct_of_division_workload"] = (table["analytical_tests"] / division_totals * 100).round(1)

    table = table.sort_values(["division", "analytical_tests"], ascending=[True, False]).reset_index(drop=True)
    table.insert(0, "sequence_number", range(1, len(table) + 1))
    table = table.rename(columns={"is_package": "individual_test_or_package"})
    table["individual_test_or_package"] = table["individual_test_or_package"].map(
        {True: "Package", False: "Individual Test"}
    ).fillna("Unmatched")
    return table
