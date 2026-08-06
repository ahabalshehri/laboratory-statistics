"""Excel export for official reports (spec section 34).

Produces a single workbook with one sheet per report so it can be reviewed,
printed, or shared by email. Sheet names follow spec section 34's list.
"""
import io

import pandas as pd


def _write_sheet(writer, df: pd.DataFrame, sheet_name: str):
    df = df if df is not None and len(df.columns) else pd.DataFrame({"Note": ["No data"]})
    df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    worksheet = writer.sheets[sheet_name[:31]]
    workbook = writer.book
    header_format = workbook.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "white", "border": 1})
    for col_idx, col_name in enumerate(df.columns):
        worksheet.write(0, col_idx, col_name, header_format)
        width = max(12, min(40, int(df[col_name].astype(str).map(len).max() if len(df) else 12) + 2))
        worksheet.set_column(col_idx, col_idx, width)
    worksheet.freeze_panes(1, 0)


def build_workbook(
    executive_indicators: dict,
    methodology: dict,
    division_table: pd.DataFrame,
    full_test_table: pd.DataFrame,
    abbreviation_table: pd.DataFrame,
    package_table: pd.DataFrame,
    patient_reception_table: pd.DataFrame,
    patients_received_summary_table: pd.DataFrame,
    data_quality_table: pd.DataFrame,
    unmatched_table: pd.DataFrame,
) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        exec_df = pd.DataFrame(
            [{"Indicator": k.replace("_", " ").title(), "Value": v} for k, v in executive_indicators.items()]
        )
        _write_sheet(writer, exec_df, "Executive Summary")

        methodology_rows = []
        for k, v in methodology.items():
            if isinstance(v, list):
                for item in v:
                    methodology_rows.append({"Item": k.replace("_", " ").title(), "Detail": item})
            else:
                methodology_rows.append({"Item": k.replace("_", " ").title(), "Detail": v})
        _write_sheet(writer, pd.DataFrame(methodology_rows), "Methodology")

        _write_sheet(writer, division_table, "Division Statistics")
        _write_sheet(writer, full_test_table, "Full Test-Name Sheet")
        _write_sheet(writer, abbreviation_table, "Abbreviation Sheet")
        _write_sheet(writer, package_table, "Package Analysis Sheet")
        _write_sheet(writer, patient_reception_table, "Patient Statistics Sheet")
        _write_sheet(writer, patients_received_summary_table, "Patients Received Summary")
        _write_sheet(writer, data_quality_table, "Data Quality Sheet")
        _write_sheet(writer, unmatched_table, "Unmatched Tests Sheet")

    return buffer.getvalue()
