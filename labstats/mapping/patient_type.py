"""Classify each activity record into a standardized patient category.

Per spec section 11: not every non-inpatient record is "Outpatient" - a more
specific location (Emergency Department, ICU, Primary Healthcare Center, Day
Care) takes priority over the generic inpatient/outpatient flag when it can
be identified from the HIS clinic/encounter fields. Original HIS values are
always preserved alongside the standardized category for audit.
"""
import pandas as pd

from labstats.textnorm import normalize

CAT_INPATIENT = "Inpatient"
CAT_OUTPATIENT = "Outpatient"
CAT_ED = "Emergency Department"
CAT_PHC = "Primary Healthcare Center"
CAT_ICU = "Intensive Care Unit"
CAT_DAYCARE = "Day Care"
CAT_OTHER = "Other"
CAT_UNKNOWN = "Unknown or Unclassified"

# Specific-location aliases take priority over the generic inpatient/outpatient flag.
LOCATION_ALIASES = {
    "emergency department": CAT_ED,
    "emergency room": CAT_ED,
    "er": CAT_ED,
    "ed": CAT_ED,
    "accident and emergency": CAT_ED,
    "a&e": CAT_ED,
    "primary healthcare center": CAT_PHC,
    "primary health care center": CAT_PHC,
    "phc": CAT_PHC,
    "intensive care unit": CAT_ICU,
    "icu": CAT_ICU,
    "critical care unit": CAT_ICU,
    "ccu": CAT_ICU,
    "day care": CAT_DAYCARE,
    "daycare": CAT_DAYCARE,
    "day surgery": CAT_DAYCARE,
    "day case": CAT_DAYCARE,
}

PATIENT_TYPE_ALIASES = {
    "in patient": CAT_INPATIENT,
    "inpatient": CAT_INPATIENT,
    "ip": CAT_INPATIENT,
    "admitted": CAT_INPATIENT,
    "out patient": CAT_OUTPATIENT,
    "outpatient": CAT_OUTPATIENT,
    "op": CAT_OUTPATIENT,
}

# HIS locations that describe *where the lab work happened*, not a patient
# care setting, and should not be treated as a location signal.
NON_LOCATION_CLINIC_NAMES = {"laboratory department", "lab department", "laboratory"}


def _location_category(*raw_values: str) -> str | None:
    for raw in raw_values:
        norm = normalize(raw)
        if norm in NON_LOCATION_CLINIC_NAMES:
            continue
        if norm in LOCATION_ALIASES:
            return LOCATION_ALIASES[norm]
    return None


def classify_patient_types(activity: pd.DataFrame) -> pd.DataFrame:
    out = activity.copy()
    categories = []
    sources = []

    for _, row in out.iterrows():
        encounter_type_raw = row.get("encounter_type_raw") or ""
        clinic_name_raw = row.get("clinic_name") or ""
        patient_type_raw = row.get("patient_type_raw") or ""

        location_cat = _location_category(encounter_type_raw, clinic_name_raw)
        if location_cat:
            source = "encounter_type" if normalize(encounter_type_raw) in LOCATION_ALIASES else "clinic_name"
            categories.append(location_cat)
            sources.append(source)
            continue

        pt_cat = PATIENT_TYPE_ALIASES.get(normalize(patient_type_raw))
        if pt_cat:
            categories.append(pt_cat)
            sources.append("patient_type")
            continue

        if normalize(patient_type_raw) or normalize(encounter_type_raw) or normalize(clinic_name_raw):
            categories.append(CAT_OTHER)
            sources.append("unrecognized_value")
        else:
            categories.append(CAT_UNKNOWN)
            sources.append("missing")

    out["patient_category"] = categories
    out["patient_category_source"] = sources
    return out
