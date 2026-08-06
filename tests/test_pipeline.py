"""Unit tests for the core mapping and counting logic, using synthetic data
only (never the real HIS export, which contains patient-identifiable data).
"""
import pandas as pd

from labstats.mapping.patient_type import classify_patient_types
from labstats.mapping.test_mapping import map_activity_tests
from labstats.stats.analytical_units import compute_analytical_units
from labstats.stats.engine import compute_core_counts


def make_master():
    return pd.DataFrame(
        [
            {
                "row_number": 1,
                "his_test_name": "Lipid Profile Panel",
                "his_test_name_norm": "lipid profile panel",
                "is_package": True,
                "division": "Biochemistry",
                "abbreviation": "",
                "full_test_name": "Lipid Profile Panel",
                "declared_component_count": 4,
                "components": ["Cholesterol", "Triglycerides", "HDL", "LDL"],
                "actual_component_count": 4,
                "active": True,
            },
            {
                "row_number": 2,
                "his_test_name": "Glucose (Fasting)",
                "his_test_name_norm": "glucose fasting",
                "is_package": False,
                "division": "Biochemistry",
                "abbreviation": "GLU",
                "full_test_name": "Glucose",
                "declared_component_count": None,
                "components": [],
                "actual_component_count": 0,
                "active": True,
            },
        ]
    )


def make_activity():
    return pd.DataFrame(
        [
            # order 1: package + a duplicate component line that must be absorbed
            {
                "mrn": "P1",
                "id_number": "",
                "order_no": "ORD1",
                "order_datetime": pd.Timestamp("2026-01-05"),
                "test_description": "Lipid Profile Panel",
                "lab_order_status": "Completed",
                "patient_type_raw": "Out Patient",
                "clinic_name": "Outpatient Department",
                "encounter_type_raw": "Outpatient Department",
            },
            {
                "mrn": "P1",
                "id_number": "",
                "order_no": "ORD1",
                "order_datetime": pd.Timestamp("2026-01-05"),
                "test_description": "Cholesterol",  # should be absorbed - it's a component of the package above
                "lab_order_status": "Completed",
                "patient_type_raw": "Out Patient",
                "clinic_name": "Outpatient Department",
                "encounter_type_raw": "Outpatient Department",
            },
            # order 2: same patient, same day -> same visit; individual test
            {
                "mrn": "P1",
                "id_number": "",
                "order_no": "ORD2",
                "order_datetime": pd.Timestamp("2026-01-05"),
                "test_description": "Glucose (Fasting)",
                "lab_order_status": "Completed",
                "patient_type_raw": "Out Patient",
                "clinic_name": "Outpatient Department",
                "encounter_type_raw": "Outpatient Department",
            },
            # order 3: different patient, different day, unmatched test description
            {
                "mrn": "P2",
                "id_number": "",
                "order_no": "ORD3",
                "order_datetime": pd.Timestamp("2026-01-06"),
                "test_description": "Some Unknown Test",
                "lab_order_status": "Completed",
                "patient_type_raw": "In Patient",
                "clinic_name": "Ward 3",
                "encounter_type_raw": "",
            },
        ]
    )


def test_mapping_matches_known_tests_and_reports_unmatched():
    master = make_master()
    activity = make_activity()
    result = map_activity_tests(activity, master)

    matched = result.mapped.set_index("test_description")
    assert matched.loc["Lipid Profile Panel", "matched"]
    assert matched.loc["Glucose (Fasting)", "matched"]
    assert not matched.loc["Some Unknown Test", "matched"]
    # "Cholesterol" is only known to the master list as a package *component* name,
    # not as its own top-level test - it is correctly reported as unmatched for
    # standardization purposes, even though it gets absorbed into the package's
    # analytical test count (see test_analytical_units_absorbs_duplicate_package_component).
    unmatched_names = set(result.unmatched_report["test_description"])
    assert unmatched_names == {"Cholesterol", "Some Unknown Test"}


def test_analytical_units_absorbs_duplicate_package_component():
    master = make_master()
    activity = make_activity()
    mapped = map_activity_tests(activity, master).mapped
    with_units = compute_analytical_units(mapped, master)

    by_test = with_units.set_index("test_description")
    assert by_test.loc["Lipid Profile Panel", "analytical_test_units"] == 4
    assert by_test.loc["Cholesterol", "analytical_test_units"] == 0
    assert by_test.loc["Cholesterol", "absorbed_by_package"]
    # unmatched test still counts as 1 analytical test even without a master match
    assert by_test.loc["Some Unknown Test", "analytical_test_units"] == 1


def test_core_counts_separates_measurements_correctly():
    master = make_master()
    activity = make_activity()
    mapped = map_activity_tests(activity, master).mapped
    classified = classify_patient_types(mapped)
    with_units = compute_analytical_units(classified, master)

    counts = compute_core_counts(with_units)

    assert counts.unique_patients == 2  # P1, P2
    assert counts.requests == 3  # ORD1, ORD2, ORD3
    # P1 has two orders on the same calendar day -> 1 visit; P2 has one order -> 1 visit
    assert counts.patient_visits == 2
    # Lipid Profile Panel (4) + Glucose (1) + unmatched test (1) = 6; absorbed Cholesterol contributes 0
    assert counts.analytical_tests == 6
    assert counts.records_missing_patient_id == 0
