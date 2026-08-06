"""Report Format 3: Compact Abbreviation Report (spec section 22).

Every abbreviation is shown next to its standardized full test name so it is
never displayed without a legend, as required by the spec.
"""
import pandas as pd

from labstats.stats.aggregate import aggregate_by


def build_abbreviation_report(with_units: pd.DataFrame) -> pd.DataFrame:
    df = with_units.copy()
    df["division"] = df["division"].replace("", "Unclassified / Missing Division")
    df["abbreviation_display"] = df["abbreviation"].replace("", "(no abbreviation on file)")

    group_cols = ["abbreviation_display", "standard_report_name", "division"]
    table = aggregate_by(df, group_cols)
    table = table.rename(
        columns={
            "abbreviation_display": "abbreviation",
            "unique_patients": "patient_count",
            "requests": "request_count",
            "analytical_tests": "analytical_test_count",
        }
    )
    table = table[["abbreviation", "standard_report_name", "division", "patient_count", "request_count", "analytical_test_count"]]
    table = table.sort_values(["division", "analytical_test_count"], ascending=[True, False]).reset_index(drop=True)
    return table
