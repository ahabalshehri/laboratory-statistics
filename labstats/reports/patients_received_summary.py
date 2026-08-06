"""Patients Received Summary - matches the hospital's own internal monthly
reporting template: total patients received, broken down by nationality
(Saudi/Non-Saudi), gender (Male/Female), and by laboratory division, with a
Total row.

Note: like the Division Summary report, the per-division "Total" is a simple
sum of each division's unique-patient count - a patient tested in more than
one division is counted once per division, so this total can exceed the
true overall unique-patient count. This mirrors the hospital's own template
convention rather than the stricter non-additive guidance used elsewhere in
this system; the overall "Patients Received" figure at the top of the table
is the correct deduplicated total.
"""
import pandas as pd

from labstats.reports.division_summary import build_division_summary
from labstats.stats.engine import derive_patient_id
from labstats.textnorm import normalize

SUMMARY_COLUMNS = ["Category", "Subcategory", "Count"]


def build_patients_received_summary(with_units: pd.DataFrame, month_label: str = "") -> pd.DataFrame:
    df = with_units.copy()
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

    division_table = build_division_summary(with_units).table

    rows = [
        ["Patients Received", "", total_patients],
        ["Patients Received", "SAUDI", saudi_count],
        ["", "Non-SAUDI", non_saudi_count],
        ["Patients Received", "Male", male_count],
        ["", "Female", female_count],
    ]
    if unclassified_gender:
        rows.append(["", "Unspecified", unclassified_gender])

    rows.append(["Division", "Month", month_label or "Not Applicable"])
    for _, row in division_table.iterrows():
        rows.append([row["division"], "", int(row["unique_patients"])])
    rows.append(["Total", "", int(division_table["unique_patients"].sum())])

    table = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    # The Month row mixes a text label into what's otherwise a numeric column -
    # keep the whole column as text so it renders consistently everywhere
    # (Arrow-based table display included) rather than as a mixed-type column.
    table["Count"] = table["Count"].astype(str)
    return table
