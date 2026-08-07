"""Report Format 2: Detailed Full Test-Name Report (spec section 21).

Shows accumulated workload per standardized parameter - a parameter's total
is the same number whether it was ordered individually or arrived as a
package component (e.g. TSH ordered on its own plus TSH measured as part of
a TFT package both add into one TSH total). Packages themselves are excluded
from this view (they always carry zero analytical-test units - see
labstats.stats.analytical_units); see Report Format 7 (Package Utilization)
for package-level request/patient counts.
"""
import pandas as pd

from labstats.stats.aggregate import add_percentage_of_total, aggregate_by


def build_full_test_report(with_units: pd.DataFrame) -> pd.DataFrame:
    # Select only what's needed before copying/filtering - see division_summary.py.
    needed = ["division", "standard_report_name", "full_test_name", "abbreviation", "row_kind", "order_no", "analytical_test_units", "mrn", "id_number"]
    df = with_units[needed]
    df = df[df["row_kind"] != "package"].copy()
    df["division"] = df["division"].replace("", "Unclassified / Missing Division")

    group_cols = ["division", "standard_report_name", "full_test_name", "abbreviation"]
    table = aggregate_by(df, group_cols)

    total_workload = table["analytical_tests"].sum()
    table = add_percentage_of_total(table, "analytical_tests", total_workload, "pct_of_total_workload")

    division_totals = table.groupby("division")["analytical_tests"].transform("sum")
    table["pct_of_division_workload"] = (table["analytical_tests"] / division_totals.replace(0, pd.NA) * 100).round(1)

    table = table.sort_values(["division", "analytical_tests"], ascending=[True, False]).reset_index(drop=True)
    table.insert(0, "sequence_number", range(1, len(table) + 1))
    return table
