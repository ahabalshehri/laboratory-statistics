"""Report Format 4: Patient Reception and Laboratory Workload Report (spec section 23)."""
import pandas as pd

from labstats.stats.aggregate import add_percentage_of_total, aggregate_by

CATEGORY_ORDER = [
    "Inpatient",
    "Outpatient",
    "Emergency Department",
    "Primary Healthcare Center",
    "Intensive Care Unit",
    "Day Care",
    "Other",
    "Unknown or Unclassified",
]


def build_patient_reception_report(with_units: pd.DataFrame, total_unique_patients: int) -> pd.DataFrame:
    # No need to copy here - aggregate_by only reads the columns it needs.
    table = aggregate_by(with_units, ["patient_category"])
    total_workload = table["analytical_tests"].sum()

    table = add_percentage_of_total(table, "unique_patients", total_unique_patients, "pct_of_total_patients")
    table = add_percentage_of_total(table, "analytical_tests", total_workload, "pct_of_total_workload")

    table["avg_requests_per_patient"] = table.apply(
        lambda r: round(r["requests"] / r["unique_patients"], 2) if r["unique_patients"] else "Not Applicable",
        axis=1,
    )
    table["avg_tests_per_patient"] = table.apply(
        lambda r: round(r["analytical_tests"] / r["unique_patients"], 2) if r["unique_patients"] else "Not Applicable",
        axis=1,
    )

    table["_order"] = table["patient_category"].apply(
        lambda c: CATEGORY_ORDER.index(c) if c in CATEGORY_ORDER else len(CATEGORY_ORDER)
    )
    table = table.sort_values("_order").drop(columns="_order").reset_index(drop=True)
    return table
