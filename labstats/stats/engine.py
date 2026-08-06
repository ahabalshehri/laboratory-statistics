"""Core counting engine: patients, visits, samples, requests, and analytical
tests, computed as separate measurements per spec section 7 - never combined
into a single total.

Every count here is a documented, reproducible rule rather than an assumption
that one row equals one patient/sample/request. Where the source data lacks a
field the ideal rule needs (e.g. no Specimen/Accession Number, no Encounter
Number in this HIS export), a configurable fallback rule is used and the
limitation is recorded so it can be surfaced in report methodology sections.
"""
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class CountingConfig:
    date_field: str = "order_datetime"
    date_basis_label: str = "Order Date/Time (only date field present in this HIS export)"
    visit_rule: str = "patient_per_day"  # fallback: no Encounter Number available in this export
    sample_rule: str = "one_per_request"  # fallback: no Specimen/Accession Number available
    include_statuses: list | None = None  # None = include every status present


@dataclass
class CoreCounts:
    unique_patients: int
    patient_visits: int
    samples_received: int
    requests: int
    package_line_items: int
    individual_test_line_items: int
    analytical_tests: int
    records_missing_patient_id: int
    filtered_row_count: int
    operational_days: int
    limitations: list = field(default_factory=list)


def derive_patient_id(df: pd.DataFrame) -> pd.Series:
    return df["mrn"].where(df["mrn"].astype(str).str.strip() != "", df["id_number"])


def filter_period(df: pd.DataFrame, start_date=None, end_date=None, config: CountingConfig | None = None):
    config = config or CountingConfig()
    out = df
    if start_date is not None:
        out = out[out[config.date_field] >= pd.Timestamp(start_date)]
    if end_date is not None:
        end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1)
        out = out[out[config.date_field] < end_ts]
    if config.include_statuses:
        out = out[out["lab_order_status"].isin(config.include_statuses)]
    return out


def compute_core_counts(
    df_with_units: pd.DataFrame,
    start_date=None,
    end_date=None,
    config: CountingConfig | None = None,
) -> CoreCounts:
    config = config or CountingConfig()
    df = filter_period(df_with_units, start_date, end_date, config).copy()

    limitations = [
        f"Samples Received uses '{config.sample_rule}' because the source file has no "
        "Specimen/Accession Number - it is a lower bound on true specimen count whenever "
        "a single request submits more than one physical specimen.",
        f"Patient Visits uses the '{config.visit_rule}' fallback rule because the source "
        "file has no Encounter/Visit Number.",
        f"All period filtering uses {config.date_basis_label}.",
    ]

    patient_id = derive_patient_id(df)
    missing_patient_id = patient_id.isna() | (patient_id.astype(str).str.strip() == "")
    df = df.assign(patient_id=patient_id, missing_patient_id=missing_patient_id)

    valid_patients = df.loc[~df["missing_patient_id"]]
    unique_patients = int(valid_patients["patient_id"].nunique())

    if config.visit_rule == "patient_per_day":
        visit_dates = valid_patients[config.date_field].dt.date
        visit_keys = list(zip(valid_patients["patient_id"], visit_dates))
        patient_visits = len(set(visit_keys))
    else:
        patient_visits = valid_patients["order_no"].nunique()

    requests = int(df["order_no"].nunique())
    package_line_items = int((df["is_package"] == True).sum())  # noqa: E712
    individual_test_line_items = int((df["is_package"] == False).sum())  # noqa: E712

    if config.sample_rule == "one_per_request":
        samples_received = requests
    else:
        samples_received = requests

    analytical_tests = int(df["analytical_test_units"].sum())

    if start_date is not None and end_date is not None:
        operational_days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days + 1
    else:
        span = df[config.date_field].max() - df[config.date_field].min() if len(df) else None
        operational_days = span.days + 1 if pd.notna(span) else 0

    return CoreCounts(
        unique_patients=unique_patients,
        patient_visits=patient_visits,
        samples_received=samples_received,
        requests=requests,
        package_line_items=package_line_items,
        individual_test_line_items=individual_test_line_items,
        analytical_tests=analytical_tests,
        records_missing_patient_id=int(missing_patient_id.sum()),
        filtered_row_count=len(df),
        operational_days=max(operational_days, 0),
        limitations=limitations,
    )


def percentage_change(current: float, previous: float):
    if previous in (0, None) or pd.isna(previous):
        return "New" if current else "No Previous Data"
    return round((current - previous) / previous * 100, 1)


def safe_average(numerator: float, denominator: float, not_applicable_label: str = "Not Applicable"):
    if not denominator:
        return not_applicable_label
    return round(numerator / denominator, 2)
