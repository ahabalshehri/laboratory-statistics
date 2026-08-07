"""Data Quality Report (spec section 27).

Surfaces issues found during import/mapping so they can be reviewed before
official statistics are generated. Never silently drops or fixes records -
every row stays in the dataset; this report only flags what needs review.
"""
from dataclasses import dataclass

import pandas as pd

from labstats.stats.engine import derive_patient_id
from labstats.textnorm import normalize

DATA_QUALITY_COLUMNS = [
    "issue_type",
    "affected_record_count",
    "example_value",
    "recommended_action",
    "review_status",
]


def _issue_row(issue_type, count, example, action):
    return {
        "issue_type": issue_type,
        "affected_record_count": int(count),
        "example_value": example,
        "recommended_action": action,
        "review_status": "Pending Review",
    }


@dataclass
class DataQualityResult:
    issues: pd.DataFrame
    critical_issue_count: int


def build_data_quality_report(
    mapped: pd.DataFrame,
    master_package_mismatches: pd.DataFrame,
    unmatched_report: pd.DataFrame,
    activity_metadata: dict | None = None,
    master_duplicate_abbreviations: pd.DataFrame | None = None,
) -> DataQualityResult:
    rows = []
    df = mapped.copy()
    df["patient_id"] = derive_patient_id(df)

    missing_patient = df["patient_id"].isna() | (df["patient_id"].astype(str).str.strip() == "")
    if missing_patient.any():
        rows.append(
            _issue_row(
                "Missing Medical Record Number / Patient Identifier",
                missing_patient.sum(),
                "Record has no Mrn or Id number",
                "Review source records; unique-patient totals may undercount until resolved.",
            )
        )

    missing_division = df["division_raw"].fillna("").map(normalize) == ""
    if missing_division.any():
        rows.append(
            _issue_row(
                "Missing Laboratory Division in Source Data",
                missing_division.sum(),
                "Divisionname column blank",
                "Standardized division was filled in from the Test Master List where the test matched; verify remaining rows.",
            )
        )

    missing_patient_type = df["patient_type_raw"].fillna("").map(normalize) == ""
    if missing_patient_type.any():
        rows.append(
            _issue_row(
                "Missing Patient Type",
                missing_patient_type.sum(),
                "Patient type column blank",
                "Confirm patient category assignment (fell back to location or Unknown).",
            )
        )

    if len(unmatched_report):
        rows.append(
            _issue_row(
                "Unmatched HIS Test Description",
                unmatched_report["occurrences"].sum(),
                unmatched_report.iloc[0]["test_description"],
                "Review the Unmatched Tests Report and add a manual mapping or update the master list.",
            )
        )

    if len(master_package_mismatches):
        rows.append(
            _issue_row(
                "Package Component Count Mismatch in Master List",
                len(master_package_mismatches),
                master_package_mismatches.iloc[0]["his_test_name"],
                "Review declared vs. actual component counts for this package in the master list "
                "(duplicated or missing component entries).",
            )
        )

    if master_duplicate_abbreviations is not None and len(master_duplicate_abbreviations):
        example_abbrev = master_duplicate_abbreviations.iloc[0]["abbreviation"]
        example_names = master_duplicate_abbreviations.loc[
            master_duplicate_abbreviations["abbreviation"] == example_abbrev, "his_test_name"
        ].tolist()
        rows.append(
            _issue_row(
                "Same Abbreviation Assigned to Different Tests in Master List",
                master_duplicate_abbreviations["abbreviation"].nunique(),
                f"'{example_abbrev}' used for: {', '.join(example_names)}",
                "The Abbreviation Report counts these together under one abbreviation for the compact "
                "view - confirm this is intentional (e.g. screening/confirmatory pair) or correct the "
                "master list if it's a data-entry error.",
            )
        )

    dup_lines = df.duplicated(subset=["order_no", "test_description"], keep=False)
    if dup_lines.any():
        rows.append(
            _issue_row(
                "Duplicate Test Line Within the Same Request",
                dup_lines.sum(),
                f"Order {df.loc[dup_lines, 'order_no'].iloc[0]}",
                "Confirm whether the test was genuinely repeated or is a duplicate export line.",
            )
        )

    repeat_group = (
        df.loc[~missing_patient]
        .groupby(["patient_id", "standard_report_name"])["order_no"]
        .nunique()
    )
    repeated_across_orders = repeat_group[repeat_group > 1]
    if len(repeated_across_orders):
        rows.append(
            _issue_row(
                "Same Test Repeated for the Same Patient Across Multiple Requests",
                len(repeated_across_orders),
                f"{repeated_across_orders.index[0][1]} for patient {repeated_across_orders.index[0][0]} "
                f"across {int(repeated_across_orders.iloc[0])} separate requests",
                "Confirm these are clinically justified repeats, not duplicate orders (see Coagulation "
                "Profile / PT-INR workload-counting guidance).",
            )
        )

    if activity_metadata and activity_metadata.get("period_start") and activity_metadata.get("period_end"):
        try:
            period_start = pd.Timestamp(activity_metadata["period_start"])
            period_end = pd.Timestamp(activity_metadata["period_end"]) + pd.Timedelta(days=1)
            out_of_range = df["order_datetime"].notna() & (
                (df["order_datetime"] < period_start) | (df["order_datetime"] >= period_end)
            )
            if out_of_range.any():
                rows.append(
                    _issue_row(
                        "Order Date Outside the File's Declared Extraction Period",
                        out_of_range.sum(),
                        str(df.loc[out_of_range, "order_datetime"].iloc[0]),
                        "Confirm the export's stated date range or exclude these rows from period totals.",
                    )
                )
        except (ValueError, TypeError):
            pass

    unparseable_dates = df["order_datetime"].isna().sum()
    if unparseable_dates:
        rows.append(
            _issue_row(
                "Invalid or Unparseable Order Date",
                unparseable_dates,
                "Order date time could not be parsed",
                "These rows are excluded from any period-filtered statistic until corrected.",
            )
        )

    issues = pd.DataFrame(rows, columns=DATA_QUALITY_COLUMNS)
    critical_count = int(missing_patient.sum() + unmatched_report["occurrences"].sum() if len(unmatched_report) else missing_patient.sum())
    return DataQualityResult(issues=issues, critical_issue_count=critical_count)
