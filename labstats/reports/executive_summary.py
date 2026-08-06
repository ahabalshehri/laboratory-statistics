"""Monthly/Annual Executive Laboratory Statistics Report (spec sections 18-19),
condensed to the indicators the current data model can support accurately.
"""
from dataclasses import dataclass, field

import pandas as pd

from labstats.reports.division_summary import build_division_summary
from labstats.reports.full_test_report import build_full_test_report
from labstats.reports.patient_reception_report import build_patient_reception_report
from labstats.mapping.patient_type import NON_LOCATION_CLINIC_NAMES
from labstats.stats.engine import CoreCounts, compute_core_counts, percentage_change, safe_average
from labstats.textnorm import normalize

REJECTED_KEYWORDS = {"reject", "rejected"}
CANCELLED_KEYWORDS = {"cancel", "cancelled", "canceled"}
PENDING_KEYWORDS = {"pending", "ordered", "in progress", "collected"}


def _status_count(df: pd.DataFrame, keywords: set[str]) -> int:
    statuses = df["lab_order_status"].fillna("").map(normalize)
    return int(statuses.apply(lambda s: any(k in s for k in keywords)).sum())


@dataclass
class ExecutiveSummary:
    period_label: str
    core_counts: CoreCounts
    indicators: dict
    highest_volume_division: str
    highest_volume_test: str
    highest_volume_patient_category: str
    highest_volume_requesting_location: str
    comparison: dict = field(default_factory=dict)
    methodology: dict = field(default_factory=dict)


def build_executive_summary(
    with_units: pd.DataFrame,
    activity_metadata: dict,
    start_date=None,
    end_date=None,
    previous_core_counts: CoreCounts | None = None,
    period_label: str = "",
) -> ExecutiveSummary:
    core = compute_core_counts(with_units, start_date, end_date)

    filtered = with_units
    if start_date is not None:
        filtered = filtered[filtered["order_datetime"] >= pd.Timestamp(start_date)]
    if end_date is not None:
        filtered = filtered[filtered["order_datetime"] < pd.Timestamp(end_date) + pd.Timedelta(days=1)]

    division_result = build_division_summary(filtered, core.operational_days)
    full_test_table = build_full_test_report(filtered)
    reception_table = build_patient_reception_report(filtered, core.unique_patients)

    highest_division = division_result.table.iloc[0]["division"] if len(division_result.table) else "Not Applicable"
    highest_test = (
        full_test_table.iloc[0]["standard_report_name"] if len(full_test_table) else "Not Applicable"
    )
    highest_category_row = (
        reception_table.sort_values("analytical_tests", ascending=False).iloc[0]
        if len(reception_table)
        else None
    )
    highest_category = highest_category_row["patient_category"] if highest_category_row is not None else "Not Applicable"

    location_col = "clinic_name" if "clinic_name" in filtered.columns else None
    if location_col:
        locations = filtered[location_col].replace("", pd.NA).dropna()
        locations = locations[~locations.map(normalize).isin(NON_LOCATION_CLINIC_NAMES)]
        loc_counts = locations.value_counts()
        highest_location = loc_counts.index[0] if len(loc_counts) else "Not Applicable"
    else:
        highest_location = "Not Applicable"

    indicators = {
        "total_unique_patients_received": core.unique_patients,
        "total_patient_visits": core.patient_visits,
        "total_samples_received": core.samples_received,
        "total_laboratory_requests": core.requests,
        "total_individual_test_line_items": core.individual_test_line_items,
        "total_package_line_items": core.package_line_items,
        "total_analytical_tests_performed": core.analytical_tests,
        "average_patients_received_per_day": safe_average(core.unique_patients, core.operational_days),
        "average_samples_per_patient": safe_average(core.samples_received, core.unique_patients),
        "average_requests_per_patient": safe_average(core.requests, core.unique_patients),
        "average_analytical_tests_per_patient": safe_average(core.analytical_tests, core.unique_patients),
        "average_analytical_tests_per_day": safe_average(core.analytical_tests, core.operational_days),
        "rejected_samples_or_tests": _status_count(filtered, REJECTED_KEYWORDS),
        "cancelled_tests": _status_count(filtered, CANCELLED_KEYWORDS),
        "pending_tests": _status_count(filtered, PENDING_KEYWORDS),
        "records_missing_patient_identifier": core.records_missing_patient_id,
    }

    comparison = {}
    if previous_core_counts is not None:
        comparison = {
            "previous_period_unique_patients": previous_core_counts.unique_patients,
            "unique_patients_change_pct": percentage_change(
                core.unique_patients, previous_core_counts.unique_patients
            ),
            "previous_period_analytical_tests": previous_core_counts.analytical_tests,
            "analytical_tests_change_pct": percentage_change(
                core.analytical_tests, previous_core_counts.analytical_tests
            ),
            "previous_period_requests": previous_core_counts.requests,
            "requests_change_pct": percentage_change(core.requests, previous_core_counts.requests),
        }

    methodology = {
        "source_file": activity_metadata.get("source_filename"),
        "hospital_name": activity_metadata.get("hospital_name"),
        "date_basis": "Order Date/Time (only date field present in this HIS export)",
        "patient_counting_rule": "Distinct Medical Record Number (falls back to Id number when Mrn is blank)",
        "encounter_counting_rule": "Fallback: one visit per distinct (patient, calendar day) - no Encounter Number in source",
        "sample_counting_rule": "Fallback: one sample per Order No - no Specimen/Accession Number in source",
        "request_counting_rule": "One request = one distinct Order No",
        "package_counting_rule": "Package requests count as 1 request each; analytical test count uses the "
        "component count from the Test Master List, with duplicate component lines within the same "
        "order absorbed into the package's count to avoid double counting.",
        "limitations": core.limitations,
    }

    return ExecutiveSummary(
        period_label=period_label,
        core_counts=core,
        indicators=indicators,
        highest_volume_division=highest_division,
        highest_volume_test=highest_test,
        highest_volume_patient_category=highest_category,
        highest_volume_requesting_location=highest_location,
        comparison=comparison,
        methodology=methodology,
    )
