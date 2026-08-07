"""Patients Received Summary - matches the hospital's own internal monthly
reporting template: total patients received, broken down by nationality
(Saudi/Non-Saudi) and gender (Male/Female), plus a division-by-month matrix
of unique patients received.
"""
import pandas as pd

from labstats.stats.engine import derive_patient_id
from labstats.textnorm import normalize

SUMMARY_COLUMNS = ["Category", "Subcategory", "Count"]


def build_patients_received_summary(with_units: pd.DataFrame) -> pd.DataFrame:
    df = with_units[["mrn", "id_number", "nationality", "gender"]].copy()
    df["patient_id"] = derive_patient_id(df)
    patients = df.dropna(subset=["patient_id"])
    patients = patients[patients["patient_id"].astype(str).str.strip() != ""]
    patients = patients.drop_duplicates(subset=["patient_id"])

    total_patients = int(patients["patient_id"].nunique())

    nationality_norm = patients.get("nationality", pd.Series(dtype=object)).fillna("").map(normalize)
    saudi_count = int((nationality_norm == "saudi").sum())
    non_saudi_count = total_patients - saudi_count

    gender_norm = patients.get("gender", pd.Series(dtype=object)).fillna("").map(normalize)
    male_count = int((gender_norm == "male").sum())
    female_count = int((gender_norm == "female").sum())
    unclassified_gender = total_patients - male_count - female_count

    rows = [
        ["Patients Received", "", total_patients],
        ["Patients Received", "SAUDI", saudi_count],
        ["", "Non-SAUDI", non_saudi_count],
        ["Patients Received", "Male", male_count],
        ["", "Female", female_count],
    ]
    if unclassified_gender:
        rows.append(["", "Unspecified", unclassified_gender])

    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def build_division_month_matrix(with_units: pd.DataFrame) -> pd.DataFrame:
    """Division x Month matrix of unique patients received.

    Each cell is that division's unique-patient count within that single
    calendar month - not additive across months for the same patient if they
    were seen in more than one month, same non-additive caveat as elsewhere
    in this system. The Total column is each division's true unique-patient
    count across the whole period (not a sum of the month columns), and the
    Total row sums each month's columns across divisions (a patient tested
    in more than one division that month is counted once per division).
    """
    needed = ["order_datetime", "division", "mrn", "id_number"]
    df = with_units.loc[with_units["order_datetime"].notna(), needed].copy()
    df["patient_id"] = derive_patient_id(df)
    df = df[df["patient_id"].astype(str).str.strip() != ""]
    if df.empty:
        return pd.DataFrame(columns=["Division", "Total"])

    df["division"] = df["division"].replace("", "Unclassified / Missing Division")
    df["month_period"] = df["order_datetime"].dt.to_period("M")

    pivot = df.groupby(["division", "month_period"])["patient_id"].nunique().unstack(fill_value=0)
    pivot = pivot.reindex(sorted(pivot.columns), axis=1)
    pivot.columns = [p.strftime("%b %Y") for p in pivot.columns]

    division_totals = df.groupby("division")["patient_id"].nunique()
    pivot["Total"] = division_totals

    pivot = pivot.sort_values("Total", ascending=False)
    pivot.loc["Total"] = pivot.sum(numeric_only=True)

    pivot = pivot.reset_index().rename(columns={"division": "Division"})
    return pivot
