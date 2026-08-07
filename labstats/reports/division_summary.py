"""Report Format 1: Statistics by Laboratory Division (spec section 20).

Note: a patient can have tests in more than one division, so per-division
unique-patient counts must never be summed to approximate the overall unique
patient total - the caller must always source that figure from the core
counting engine, not from this table. This limitation is carried in
`DivisionSummaryResult.note`.
"""
from dataclasses import dataclass

import pandas as pd

from labstats.stats.aggregate import add_percentage_of_total, aggregate_by

NOTE_UNIQUE_PATIENTS_NOT_ADDITIVE = (
    "A patient may have tests in more than one laboratory division. Division-level unique-patient "
    "counts must not be summed to estimate the laboratory's overall unique-patient count - use the "
    "Monthly/Annual Executive Report total for that figure."
)


@dataclass
class DivisionSummaryResult:
    table: pd.DataFrame
    grand_total: dict
    note: str


def build_division_summary(with_units: pd.DataFrame, operational_days: int = 0) -> DivisionSummaryResult:
    # Select only what's needed before copying - with_units carries ~30 columns
    # (every raw HIS passthrough field included), and a full-width copy here
    # is wasted cost at hospital scale since this report only touches a few.
    df = with_units[["division", "order_no", "row_kind", "analytical_test_units", "mrn", "id_number"]].copy()
    df["division"] = df["division"].replace("", "Unclassified / Missing Division")

    table = aggregate_by(df, ["division"])
    total_analytical_tests = table["analytical_tests"].sum()
    table = add_percentage_of_total(table, "analytical_tests", total_analytical_tests, "pct_of_total_workload")
    table["avg_tests_per_patient"] = table.apply(
        lambda r: round(r["analytical_tests"] / r["unique_patients"], 2) if r["unique_patients"] else "Not Applicable",
        axis=1,
    )
    table["avg_tests_per_day"] = table.apply(
        lambda r: round(r["analytical_tests"] / operational_days, 2) if operational_days else "Not Applicable",
        axis=1,
    )
    table = table.sort_values("analytical_tests", ascending=False).reset_index(drop=True)
    table.insert(0, "sequence_number", range(1, len(table) + 1))

    grand_total = {
        "division": "GRAND TOTAL",
        "requests": int(table["requests"].sum()),
        "package_line_items": int(table["package_line_items"].sum()),
        "individual_test_line_items": int(table["individual_test_line_items"].sum()),
        "analytical_tests": int(total_analytical_tests),
    }

    return DivisionSummaryResult(table=table, grand_total=grand_total, note=NOTE_UNIQUE_PATIENTS_NOT_ADDITIVE)
