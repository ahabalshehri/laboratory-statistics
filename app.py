"""Medical Laboratory Statistics and Official Reporting System - Streamlit app.

Run with: streamlit run app.py
"""
import tempfile
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from labstats.export.excel_export import build_workbook
from labstats.export.pdf_export import build_executive_pdf
from labstats.loaders.activity_file import load_activity_file
from labstats.loaders.master_list import load_master_list
from labstats.mapping.patient_type import classify_patient_types
from labstats.mapping.test_mapping import map_activity_tests
from labstats.reports.abbreviation_report import build_abbreviation_report
from labstats.reports.data_quality import build_data_quality_report
from labstats.reports.division_summary import build_division_summary
from labstats.reports.executive_summary import build_executive_summary
from labstats.reports.full_test_report import build_full_test_report
from labstats.reports.package_report import build_package_report
from labstats.reports.patient_reception_report import build_patient_reception_report
from labstats.stats.analytical_units import compute_analytical_units
from labstats.stats.engine import CountingConfig, compute_core_counts

st.set_page_config(page_title="Laboratory Statistics & Reporting System", layout="wide")


def _save_upload(uploaded_file) -> str:
    suffix = Path(uploaded_file.name).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        return tmp.name


@st.cache_data(show_spinner=False)
def _load_master(path_bytes_key, path):
    return load_master_list(path)


@st.cache_data(show_spinner=False)
def _load_activity(path_bytes_key, path, filename):
    return load_activity_file(path, source_filename=filename)


@st.cache_data(show_spinner="Mapping tests and computing analytical units...")
def _build_working_dataset(master_key, activity_key, _master_result, _activity_result):
    """Runs the mapping/classification/analytical-units chain once per uploaded
    file pair (cached on master_key/activity_key). Without this, every sidebar
    filter or date-range change would re-run this - the most expensive part of
    the pipeline - from scratch on every rerun.

    Returns only the unmatched-tests report rather than the full mapping
    result, since mapping_result.mapped is a full-size duplicate dataframe
    superseded by with_units - caching both would roughly double the memory
    this holds onto for the lifetime of the session, which matters once a
    file gets into the tens of thousands of rows."""
    mapping_result = map_activity_tests(_activity_result.data, _master_result.tests)
    classified = classify_patient_types(mapping_result.mapped)
    with_units = compute_analytical_units(classified, _master_result.tests)
    return mapping_result.unmatched_report, with_units


def main():
    st.title("Medical Laboratory Statistics and Official Reporting System")
    st.caption(
        "Aggregated statistics only - no individual patient names or identifiers are shown in any report."
    )

    bundled_master = Path("reference_data/laboratory_test_master_list.xlsx")

    with st.sidebar:
        st.header("1. Laboratory Test Master List")
        if bundled_master.exists():
            st.success("Using the bundled master list.")
            with st.expander("Replace the Master List (optional)"):
                master_upload = st.file_uploader(
                    "Upload an updated Master List (.xlsx)", type=["xlsx"], key="master_upload"
                )
        else:
            st.warning("No bundled master list found - please upload one.")
            master_upload = st.file_uploader("Laboratory Test Master List (.xlsx)", type=["xlsx"], key="master_upload")

        st.header("2. Laboratory Activity File")
        activity_upload = st.file_uploader("Upload the HIS export (.xlsx)", type=["xlsx"])

        use_local_sample = False
        local_activity = Path("data/raw/sample_activity_export.xlsx")
        if not activity_upload and local_activity.exists():
            use_local_sample = st.checkbox("Use local sample file in data/raw/", value=True)

    if master_upload:
        master_path = _save_upload(master_upload)
        master_key = master_upload.name + str(master_upload.size)
    elif bundled_master.exists():
        master_path = str(bundled_master)
        master_key = "bundled_master"
    else:
        st.info("Upload the Laboratory Test Master List to begin.")
        return

    if activity_upload:
        activity_path = _save_upload(activity_upload)
        activity_filename = activity_upload.name
        activity_key = activity_upload.name + str(activity_upload.size)
    elif use_local_sample:
        activity_path = str(local_activity)
        activity_filename = local_activity.name
        activity_key = "local_activity"
    else:
        st.info("Upload the Laboratory Activity File to begin.")
        return

    try:
        master_result = _load_master(master_key, master_path)
        activity_result = _load_activity(activity_key, activity_path, activity_filename)
    except ValueError as exc:
        st.error(f"Could not load the files: {exc}")
        return

    unmatched_report, with_units = _build_working_dataset(master_key, activity_key, master_result, activity_result)

    with st.sidebar:
        st.header("2. Reporting Period")
        min_date = with_units["order_datetime"].min()
        max_date = with_units["order_datetime"].max()
        if pd.isna(min_date) or pd.isna(max_date):
            start_date, end_date = None, None
            st.warning("No valid Order Date values found - showing all records.")
        else:
            date_range = st.date_input(
                "Date range (based on Order Date/Time)",
                value=(min_date.date(), max_date.date()),
                min_value=min_date.date(),
                max_value=max_date.date(),
            )
            start_date, end_date = (date_range if isinstance(date_range, tuple) and len(date_range) == 2
                                     else (date_range, date_range))

        st.header("3. Filters")
        divisions = sorted([d for d in with_units["division"].unique() if d])
        selected_divisions = st.multiselect("Laboratory Division", divisions, default=divisions)
        categories = sorted(with_units["patient_category"].unique())
        selected_categories = st.multiselect("Patient Category", categories, default=categories)

    period_filtered = with_units.copy()
    if start_date is not None:
        period_filtered = period_filtered[
            (period_filtered["order_datetime"] >= pd.Timestamp(start_date))
            & (period_filtered["order_datetime"] < pd.Timestamp(end_date) + pd.Timedelta(days=1))
        ]
    display_filtered = period_filtered[
        period_filtered["division"].isin(selected_divisions) & period_filtered["patient_category"].isin(selected_categories)
    ]

    core_counts = compute_core_counts(display_filtered)
    executive = build_executive_summary(
        with_units, activity_result.metadata, start_date, end_date, period_label=""
    )
    division_result = build_division_summary(display_filtered, core_counts.operational_days)
    full_test_table = build_full_test_report(display_filtered)
    abbreviation_table = build_abbreviation_report(display_filtered)
    package_table = build_package_report(display_filtered)
    reception_table = build_patient_reception_report(display_filtered, core_counts.unique_patients)
    dq_result = build_data_quality_report(
        with_units, master_result.package_component_mismatches, unmatched_report, activity_result.metadata
    )

    tabs = st.tabs(
        [
            "Executive Summary",
            "Division Statistics",
            "Full Test-Name Report",
            "Abbreviation Report",
            "Package Utilization",
            "Patient Reception",
            "Data Quality",
            "Unmatched Tests",
            "Export",
        ]
    )

    with tabs[0]:
        st.subheader(activity_result.metadata.get("hospital_name") or "Laboratory")
        st.caption("Laboratory and Blood Bank Department - Official Laboratory Statistics Report")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Unique Patients Received", core_counts.unique_patients)
        c2.metric("Patient Visits", core_counts.patient_visits)
        c3.metric("Samples Received", core_counts.samples_received)
        c4.metric("Laboratory Requests", core_counts.requests)
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Individual Test Line Items", core_counts.individual_test_line_items)
        c6.metric("Package Line Items", core_counts.package_line_items)
        c7.metric("Analytical Tests Performed", core_counts.analytical_tests)
        c8.metric("Records Missing Patient ID", core_counts.records_missing_patient_id)

        st.markdown("**Highest-Volume Indicators**")
        c9, c10, c11 = st.columns(3)
        c9.metric("Highest-Volume Division", executive.highest_volume_division)
        c10.metric("Highest-Volume Test", executive.highest_volume_test)
        c11.metric("Highest-Volume Patient Category", executive.highest_volume_patient_category)

        st.markdown("**Averages**")
        st.json(
            {
                k: v
                for k, v in executive.indicators.items()
                if k.startswith("average") or k in ("rejected_samples_or_tests", "cancelled_tests", "pending_tests")
            }
        )

        with st.expander("Methodology / Report Notes"):
            st.json(executive.methodology)

        if len(division_result.table):
            fig = px.bar(
                division_result.table,
                x="division",
                y="analytical_tests",
                title="Analytical Tests by Laboratory Division",
                text="analytical_tests",
            )
            st.plotly_chart(fig, width="stretch")

    with tabs[1]:
        st.subheader("Report Format 1: Statistics by Laboratory Division")
        st.caption(division_result.note)
        st.dataframe(division_result.table, width="stretch")
        st.json(division_result.grand_total)

    with tabs[2]:
        st.subheader("Report Format 2: Detailed Full Test-Name Report")
        st.dataframe(full_test_table, width="stretch")

    with tabs[3]:
        st.subheader("Report Format 3: Compact Abbreviation Report")
        st.caption(
            "Packages are excluded here - their component parameters (e.g. TFT's T3/T4/TSH) "
            "each accumulate their own count instead of being lumped under the package name. "
            "See Package Utilization for package-level ordering counts."
        )
        st.dataframe(abbreviation_table, width="stretch")

    with tabs[4]:
        st.subheader("Report Format 7: Package Utilization")
        st.caption(
            "How often each package itself was ordered, and whether its declared component count "
            "(from the master list) matches the actual list of components on file."
        )
        st.dataframe(package_table, width="stretch")
        mismatches = package_table[package_table["component_count_mismatch"]] if len(package_table) else package_table
        if len(mismatches):
            st.warning(f"{len(mismatches)} package(s) have a declared vs. actual component count mismatch - review the master list.")

    with tabs[5]:
        st.subheader("Report Format 4: Patient Reception and Workload Report")
        st.dataframe(reception_table, width="stretch")
        if len(reception_table):
            fig = px.pie(
                reception_table, names="patient_category", values="unique_patients",
                title="Unique Patients by Category",
            )
            st.plotly_chart(fig, width="stretch")

    with tabs[6]:
        st.subheader("Report Format 8: Data Quality Report")
        if dq_result.issues.empty:
            st.success("No data quality issues detected.")
        else:
            st.dataframe(dq_result.issues, width="stretch")

    with tabs[7]:
        st.subheader("Unmatched Tests Report")
        if unmatched_report.empty:
            st.success("Every test description in the activity file matched the master list.")
        else:
            st.dataframe(unmatched_report, width="stretch")

    with tabs[8]:
        st.subheader("Export")
        workbook_bytes = build_workbook(
            executive.indicators,
            executive.methodology,
            division_result.table,
            full_test_table,
            abbreviation_table,
            package_table,
            reception_table,
            dq_result.issues,
            unmatched_report,
        )
        st.download_button(
            "Download Excel Workbook (all reports)",
            data=workbook_bytes,
            file_name="laboratory_statistics_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        st.divider()
        logo_path = Path("reference_data/logo.png")
        period_label = (
            f"{start_date} to {end_date}" if start_date is not None else "All available dates"
        )
        div_rows = division_result.table[
            ["division", "unique_patients", "requests", "package_line_items", "individual_test_line_items", "analytical_tests", "pct_of_total_workload"]
        ].values.tolist()
        rec_rows = reception_table[
            ["patient_category", "unique_patients", "requests", "analytical_tests", "pct_of_total_patients", "pct_of_total_workload"]
        ].values.tolist()
        abbrev_rows = abbreviation_table[
            ["division", "abbreviation", "analytical_test_count"]
        ].values.tolist()
        pdf_bytes = build_executive_pdf(
            hospital_name=activity_result.metadata.get("hospital_name") or "Laboratory",
            period_label=period_label,
            date_basis=executive.methodology["date_basis"],
            indicators=executive.indicators,
            division_table_rows=div_rows,
            reception_table_rows=rec_rows,
            methodology=executive.methodology,
            abbreviation_table_rows=abbrev_rows,
            logo_path=str(logo_path) if logo_path.exists() else None,
        )
        st.download_button(
            "Download Official PDF Report (signable, print-ready)",
            data=pdf_bytes,
            file_name="official_laboratory_statistics_report.pdf",
            mime="application/pdf",
        )


if __name__ == "__main__":
    main()
