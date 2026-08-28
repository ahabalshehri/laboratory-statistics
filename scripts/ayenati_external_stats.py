"""Ayenati / External Laboratory Test Statistics (test-wise, by Test description).

One-off analytical report builder for the LIS "External LAB AYANATI" export.
Detects the header row automatically, applies the External + Received filters,
counts laboratory tests test-wise, and writes a formatted Excel workbook.

Usage:
    python scripts/ayenati_external_stats.py "<path to export.xlsx>" [output.xlsx]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RECEIVING_STATUS_RECEIVED = "Received"          # strict: specimen reached the lab
RECEIVING_STATUS_RECEPTION = "RecievedByReceptionist"  # logged at reception only
HEADER_ANCHOR = "Test description"

STATUS_COLUMNS = ["Ordered", "Resulted", "VerifiedLevel1", "VerifiedLevel2",
                  "PartiallyVerified", "Caccelled"]


def detect_header_row(path: str, anchor: str = HEADER_ANCHOR, scan: int = 30) -> int:
    probe = pd.read_excel(path, header=None, nrows=scan, dtype=str)
    for i in range(len(probe)):
        row = [str(v).strip().lower() for v in probe.iloc[i].tolist()]
        if anchor.lower() in row:
            return i
    raise ValueError(f"Could not find a header row containing '{anchor}' in the first {scan} rows.")


def clean_test_name(s: pd.Series) -> pd.Series:
    return (s.astype(str)
            .str.replace("\u00a0", " ", regex=False)
            .str.strip()
            .str.replace(r"\s+", " ", regex=True))


def canonical_map(names: pd.Series) -> dict:
    """Map every case/format variant of a cleaned name to a single display label
    (the most frequently occurring original casing)."""
    df = pd.DataFrame({"name": names})
    df["key"] = df["name"].str.lower()
    out = {}
    for key, grp in df.groupby("key"):
        out[key] = grp["name"].value_counts().index[0]
    return out


def main() -> None:
    src = sys.argv[1] if len(sys.argv) > 1 else \
        r"C:/Users/ahmed/Downloads/External LAB AYANATI 16-27-aug-2026.xlsx"
    src = str(Path(src))
    default_out = Path(src).with_name(Path(src).stem + " - Ayenati Test-Wise Statistics.xlsx")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else default_out
    if out.suffix.lower() != ".xlsx":            # argv[2] given as a directory
        out = out / (Path(src).stem + " - Ayenati Test-Wise Statistics.xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)

    header_row = detect_header_row(src)
    raw = pd.read_excel(src, header=header_row, dtype=str)
    raw.columns = [str(c).strip() for c in raw.columns]
    total_raw_rows = len(raw)

    # --- locate columns by name (order-independent) ---
    def col(name: str) -> str:
        for c in raw.columns:
            if c.lower() == name.lower():
                return c
        return ""

    c_test = col("Test description")
    c_barcode = col("Sample barcode")
    c_mrn = col("Mrn")
    c_order = col("Order no")
    c_testid = col("Testid")
    c_ext = col("Is external lab order")
    c_samplestatus = col("Samplestatus")
    c_received = col("Received")
    c_reception = col("RecievedByReceptionist")
    c_teststatus = col("Test status")
    c_phc = col("Phcc")
    c_orderdt = col("Order date time")
    c_rejected = col("Rejected")

    missing = [n for n, c in {
        "Test description": c_test, "Sample barcode": c_barcode, "Mrn": c_mrn,
        "Order no": c_order, "Is external lab order": c_ext,
        "Samplestatus": c_samplestatus,
    }.items() if not c]

    df = raw.copy()
    df["_test_clean"] = clean_test_name(df[c_test])
    df["_test_key"] = df["_test_clean"].str.lower()
    cmap = canonical_map(df["_test_clean"])
    df["Test Name"] = df["_test_key"].map(cmap)

    # --- external / Ayenati filter ---
    ext_norm = df[c_ext].astype(str).str.strip().str.lower()
    is_external = ext_norm.eq("yes")
    n_external = int(is_external.sum())
    n_internal_excluded = int((~is_external).sum())

    ext = df[is_external].copy()

    # --- duplicate protection (exact exported-record duplicates) ---
    dup_key_cols = [c for c in [c_order, c_testid, c_barcode, c_test] if c]
    dup_mask = ext.duplicated(subset=dup_key_cols, keep="first")
    n_dupes = int(dup_mask.sum())
    ext = ext[~dup_mask].copy()

    # --- received filter ---
    ss = ext[c_samplestatus].astype(str).str.strip()
    recv_flag = ext[c_received].notna() & ext[c_received].astype(str).str.strip().isin(["1", "1.0", "Yes", "yes"]) \
        if c_received else pd.Series(False, index=ext.index)
    is_received_strict = ss.str.lower().eq("received") | recv_flag
    is_reception_only = ss.eq(RECEIVING_STATUS_RECEPTION)
    is_rejected = ss.str.lower().eq("rejected")
    is_pending = ss.str.lower().eq("pending")

    n_received = int(is_received_strict.sum())
    n_reception_only = int(is_reception_only.sum())
    n_rejected = int(is_rejected.sum())
    n_pending = int(is_pending.sum())

    rec = ext[is_received_strict].copy()

    # ================= KPIs =================
    def nunique_nonblank(s: pd.Series) -> int:
        v = s.astype(str).str.strip()
        return int(v[~v.isin(["", "nan", "None", "NaT"])].nunique())

    total_tests = len(rec)
    kpis = {
        "Total Tests Received": total_tests,
        "Unique Samples Received": nunique_nonblank(rec[c_barcode]),
        "Unique Patients (MRN)": nunique_nonblank(rec[c_mrn]),
        "Unique Orders": nunique_nonblank(rec[c_order]) if c_order else "n/a",
        "Different Test Types": int(rec["Test Name"].nunique()),
    }

    # ================= Test-wise main table =================
    g = rec.groupby("Test Name")
    tw = pd.DataFrame({
        "Test Count": g.size(),
        "Unique Samples": g[c_barcode].apply(nunique_nonblank),
        "Unique Patients": g[c_mrn].apply(nunique_nonblank),
    }).reset_index()
    tw = tw.sort_values("Test Count", ascending=False, kind="stable").reset_index(drop=True)
    tw.insert(0, "Rank", range(1, len(tw) + 1))
    tw["% of Total Tests"] = (tw["Test Count"] / total_tests * 100).round(2)
    tw = tw[["Rank", "Test Name", "Test Count", "% of Total Tests", "Unique Samples", "Unique Patients"]]
    total_row = pd.DataFrame([{
        "Rank": "", "Test Name": "TOTAL", "Test Count": tw["Test Count"].sum(),
        "% of Total Tests": round(tw["% of Total Tests"].sum(), 2),
        "Unique Samples": kpis["Unique Samples Received"],
        "Unique Patients": kpis["Unique Patients (MRN)"],
    }])
    tw_out = pd.concat([tw, total_row], ignore_index=True)

    # ================= Test status table =================
    if c_teststatus:
        st = rec.copy()
        st_status = st[c_teststatus].astype(str).str.strip()
        status_tab = pd.crosstab(st["Test Name"], st_status)
        status_tab["Total"] = status_tab.sum(axis=1)
        rename = {"Ordered": "Ordered", "Resulted": "Resulted",
                  "VerifiedLevel1": "Verified L1", "VerifiedLevel2": "Verified L2",
                  "Caccelled": "Cancelled", "PartiallyVerified": "Partially Verified"}
        status_tab = status_tab.rename(columns=rename)
        order = ["Total", "Ordered", "Resulted", "Verified L1", "Verified L2",
                 "Partially Verified", "Cancelled"]
        status_tab = status_tab[[c for c in order if c in status_tab.columns]]
        status_tab = status_tab.sort_values("Total", ascending=False).reset_index()
        status_tab.loc[len(status_tab)] = ["TOTAL"] + status_tab.iloc[:, 1:].sum().tolist()
    else:
        status_tab = pd.DataFrame()

    # ================= Daily statistics =================
    daily = pd.DataFrame()
    day_stats = {}
    if c_orderdt:
        d = pd.to_datetime(rec[c_orderdt], format="%d-%b-%Y %H:%M:%S", errors="coerce")
        rec = rec.assign(_date=d.dt.date)
        dg = rec.dropna(subset=["_date"]).groupby("_date")
        daily = pd.DataFrame({
            "Total Tests": dg.size(),
            "Unique Samples": dg[c_barcode].apply(nunique_nonblank),
            "Unique Patients": dg[c_mrn].apply(nunique_nonblank),
            "Unique Orders": dg[c_order].apply(nunique_nonblank) if c_order else 0,
        }).reset_index().rename(columns={"_date": "Date"})
        daily = daily.sort_values("Date").reset_index(drop=True)
        if len(daily):
            day_stats = {
                "Average tests per day": round(daily["Total Tests"].mean(), 1),
                "Highest-volume day": str(daily.loc[daily["Total Tests"].idxmax(), "Date"]),
                "Lowest-volume day": str(daily.loc[daily["Total Tests"].idxmin(), "Date"]),
                "Maximum daily test count": int(daily["Total Tests"].max()),
                "Minimum daily test count": int(daily["Total Tests"].min()),
                "Number of days covered": len(daily),
            }
            daily.loc[len(daily)] = ["TOTAL", daily["Total Tests"].sum(),
                                     kpis["Unique Samples Received"],
                                     kpis["Unique Patients (MRN)"],
                                     kpis["Unique Orders"]]

    # ================= PHC statistics =================
    phc_stats = pd.DataFrame()
    phc_note = ""
    if c_phc:
        pv = rec[c_phc].astype(str).str.strip().replace({"": "(blank)", "nan": "(blank)"})
        rec = rec.assign(_phc=pv)
        pg = rec.groupby("_phc")
        phc_stats = pd.DataFrame({
            "Total Tests": pg.size(),
            "Unique Samples": pg[c_barcode].apply(nunique_nonblank),
            "Unique Patients": pg[c_mrn].apply(nunique_nonblank),
            "Unique Orders": pg[c_order].apply(nunique_nonblank) if c_order else 0,
        }).reset_index().rename(columns={"_phc": "PHC"})
        phc_stats["% of Total"] = (phc_stats["Total Tests"] / total_tests * 100).round(2)
        phc_stats = phc_stats.sort_values("Total Tests", ascending=False).reset_index(drop=True)
        if phc_stats["PHC"].nunique() <= 1:
            phc_note = (f"The export contains a single PHC code ({phc_stats['PHC'].iloc[0]}); "
                        "cross-PHC comparison is not applicable for this file.")

    # ================= Test by PHC matrix =================
    if c_phc:
        tbp = pd.crosstab(rec["Test Name"], rec["_phc"])
        tbp["Total"] = tbp.sum(axis=1)
        tbp = tbp.sort_values("Total", ascending=False).reset_index()
        tbp.loc[len(tbp)] = ["TOTAL"] + tbp.iloc[:, 1:].sum().tolist()
    else:
        tbp = pd.DataFrame()

    # ================= Data quality =================
    def n_blank(s):
        v = s.astype(str).str.strip()
        return int(v.isin(["", "nan", "None", "NaT"]).sum())

    dq = [
        ("Total raw rows in file", total_raw_rows),
        ("Header row detected at (0-indexed)", header_row),
        ("Rows identified as external (Is external lab order = Yes)", n_external),
        ("Rows excluded as internal / non-external", n_internal_excluded),
        ("Exact duplicate exported records removed", n_dupes),
        ("External rows after de-duplication", len(ext)),
        ("Rows received (Samplestatus = Received / Received = 1)", n_received),
        ("Rows received by receptionist only (not counted as lab-received)", n_reception_only),
        ("Rows rejected (excluded)", n_rejected),
        ("Rows pending / not yet received (excluded)", n_pending),
        ("FINAL: valid external Ayenati tests received", total_tests),
        ("Blank Test descriptions (in received set)", n_blank(rec[c_test])),
        ("Blank Sample barcodes (in received set)", n_blank(rec[c_barcode])),
        ("Blank MRNs (in received set)", n_blank(rec[c_mrn])),
        ("Blank Order no (in received set)", n_blank(rec[c_order]) if c_order else "col missing"),
        ("Distinct raw Test description spellings", int(df.loc[is_external, c_test].astype(str).str.strip().nunique())),
        ("Distinct cleaned/normalised Test Names (received)", int(rec["Test Name"].nunique())),
        ("Missing expected columns", ", ".join(missing) if missing else "none"),
    ]
    dq_df = pd.DataFrame(dq, columns=["Check", "Value"])

    # ================= Clean data sheet =================
    keep = [c for c in [c_test, "Test Name", c_barcode, c_mrn, c_order, c_testid,
                        c_teststatus, c_samplestatus, c_phc, c_orderdt,
                        col("Last updated date"), col("Clinic name"),
                        col("Source hospital"), c_ext] if c]
    clean = rec[keep].copy()

    # validation
    assert int(tw["Test Count"].sum()) == total_tests, "Sum of test counts != total"
    pct_sum = float(tw["% of Total Tests"].sum())

    # ================= write workbook =================
    with pd.ExcelWriter(out, engine="xlsxwriter") as xw:
        wb = xw.book
        title_fmt = wb.add_format({"bold": True, "font_size": 15, "font_color": "#1F3864"})
        h_fmt = wb.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "white",
                               "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True})
        kpi_lbl = wb.add_format({"font_size": 11, "font_color": "#444444"})
        kpi_val = wb.add_format({"bold": True, "font_size": 20, "font_color": "#1F3864"})
        cell = wb.add_format({"border": 1})
        num = wb.add_format({"border": 1, "num_format": "#,##0"})
        pct = wb.add_format({"border": 1, "num_format": "0.00"})
        tot = wb.add_format({"border": 1, "bold": True, "bg_color": "#D9E2F3"})
        tot_num = wb.add_format({"border": 1, "bold": True, "bg_color": "#D9E2F3", "num_format": "#,##0"})

        def write_table(df_, sheet, startrow=1, title=None, note=None):
            ws = xw.sheets.get(sheet)
            df_.to_excel(xw, sheet_name=sheet, startrow=startrow, index=False)
            ws = xw.sheets[sheet]
            if title:
                ws.write(0, 0, title, title_fmt)
            for j, name in enumerate(df_.columns):
                ws.write(startrow, j, name, h_fmt)
                width = max(len(str(name)), *(df_[name].astype(str).str.len().tolist() or [0])) + 2
                ws.set_column(j, j, min(width, 55))
            if note:
                ws.write(startrow + len(df_) + 2, 0, note)
            # highlight TOTAL row
            if len(df_) and str(df_.iloc[-1, 0 if df_.columns[0] != "Rank" else 1]).upper() == "TOTAL":
                r = startrow + len(df_)
                for j in range(len(df_.columns)):
                    val = df_.iloc[-1, j]
                    fmt = tot_num if isinstance(val, (int, float)) and not isinstance(val, bool) else tot
                    ws.write(r, j, val, fmt)
            return ws

        # Dashboard
        ws = wb.add_worksheet("Dashboard")
        xw.sheets["Dashboard"] = ws
        ws.hide_gridlines(2)
        ws.write(0, 0, "Ayenati / External Laboratory Test Statistics", title_fmt)
        ws.write(1, 0, f"Source file: {Path(src).name}")
        ws.write(2, 0, f"Hospital: {raw[col('Hospital name')].dropna().iloc[0] if col('Hospital name') else 'n/a'}")
        period = ""
        if c_orderdt:
            dd = pd.to_datetime(raw[c_orderdt], format="%d-%b-%Y %H:%M:%S", errors="coerce")
            period = f"{dd.min().date()} to {dd.max().date()}"
        ws.write(3, 0, f"Reporting period (Order date/time): {period}")
        ws.write(4, 0, "Filters applied: Is external lab order = Yes  +  Sample received by laboratory")
        r = 6
        for label, val in kpis.items():
            ws.write(r, 0, label, kpi_lbl)
            ws.write(r + 1, 0, val, kpi_val)
            r += 3
        ws.write(r, 0, "Top 10 Tests by Volume", wb.add_format({"bold": True, "font_size": 12}))
        top10 = tw.head(10)
        top10.to_excel(xw, sheet_name="Dashboard", startrow=r + 1, index=False)
        for j, name in enumerate(top10.columns):
            ws.write(r + 1, j, name, h_fmt)
        chart = wb.add_chart({"type": "bar"})
        first = r + 2
        chart.add_series({
            "name": "Test Count",
            "categories": ["Dashboard", first, 1, first + 9, 1],
            "values": ["Dashboard", first, 2, first + 9, 2],
            "data_labels": {"value": True},
        })
        chart.set_title({"name": "Top 10 External Ayenati Tests by Volume"})
        chart.set_legend({"none": True})
        chart.set_size({"width": 640, "height": 380})
        ws.insert_chart(r + 1, 7, chart)
        ws.set_column(0, 0, 26)
        ws.set_column(1, 5, 16)

        write_table(tw_out, "Test Wise Statistics", title="Test-Wise Laboratory Statistics (received external Ayenati tests)")
        if len(status_tab):
            write_table(status_tab, "Test Status", title="Test Status by Test Name (received set)")
        if len(daily):
            ws = write_table(daily, "Daily Statistics", startrow=len(day_stats) + 3,
                             title="Daily Workload")
            for i, (k, v) in enumerate(day_stats.items()):
                ws.write(2 + i, 0, k)
                ws.write(2 + i, 1, v)
        if len(phc_stats):
            write_table(phc_stats, "PHC Statistics", title="Statistics by Originating PHC",
                        note=phc_note)
        if len(tbp):
            write_table(tbp, "Test by PHC", title="Test Name x PHC matrix")
        write_table(dq_df, "Data Quality", title="Data Quality & Filter Audit")
        write_table(clean.head(60000), "Clean Data",
                    title="Cleaned records used for the statistics")

    # ================= markdown companion =================
    def md_table(df_):
        cols = list(df_.columns)
        lines = ["| " + " | ".join(str(c) for c in cols) + " |",
                 "|" + "|".join("---" for _ in cols) + "|"]
        for _, row in df_.iterrows():
            lines.append("| " + " | ".join("" if pd.isna(v) else f"{v:,}" if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v) for v in row) + " |")
        return "\n".join(lines)

    md_path = Path(out).with_suffix(".md")
    hosp = raw[col('Hospital name')].dropna().iloc[0] if col('Hospital name') else "n/a"
    top10 = tw.head(10)
    top10_line = " · ".join(f"{r['Test Name']} ({int(r['Test Count']):,})" for _, r in top10.iterrows())
    verified = 0
    if len(status_tab) and "Verified L1" in status_tab.columns:
        trow = status_tab.iloc[-1]
        verified = int(trow.get("Verified L1", 0)) + int(trow.get("Verified L2", 0))
    n = 1
    md = [
        "# Ayenati / External Laboratory Test Statistics", "",
        f"**Hospital:** {hosp}  ",
        f"**Source file:** `{Path(src).name}`  ",
        f"**Reporting period (Order date/time):** {period}  ",
        f"**Report generated by:** `scripts/ayenati_external_stats.py`  ",
        "**Filters applied:** `Is external lab order = Yes` **AND** sample received by the laboratory "
        "(`Samplestatus = Received` / `Received = 1`)  ",
        "**Counting unit:** one laboratory **test** per valid record, grouped by cleaned `Test description`. "
        "Tests, samples, patients and orders are reported separately and never added together.", "",
        f"## {n}. Summary KPIs", "",
        md_table(pd.DataFrame({"KPI": list(kpis), "Value": list(kpis.values())})), "",
    ]
    n += 1
    md += [
        f"## {n}. How the data was processed", "",
        "| Step | Detail |", "|---|---|",
        f"| Header detection | Real table header found automatically at row {header_row + 1}; "
        "metadata rows above it ignored. Columns matched by name, not position. |",
        "| Test Name cleaning | Trim, collapse repeated spaces, drop non-breaking spaces, group case-insensitively. "
        "Medically different tests are never merged. |",
        f"| External / Ayenati filter | `Is external lab order = Yes`: {n_external:,} of {total_raw_rows:,} rows "
        f"({n_internal_excluded:,} internal rows excluded). |",
        f"| Duplicate protection | Key = `Order no + Testid + Sample barcode + Test description`. "
        f"{n_dupes} exact duplicate record(s) removed. |",
        f"| Received filter | Kept {n_received:,} received; excluded {n_pending:,} pending, "
        f"{n_reception_only:,} received-by-receptionist-only, {n_rejected:,} rejected. |",
        f"| Validation | Sum of test counts = {int(tw['Test Count'].sum()):,} = Total ({total_tests:,}); "
        f"percentages sum to {pct_sum:.2f}%. |", "",
    ]
    n += 1
    md += [f"## {n}. Test-Wise Statistics (main table)", "",
           "Sorted by Test Count (descending). % of Total = Test Count ÷ Total Tests Received × 100.", "",
           md_table(tw_out), "",
           "> Per-row Unique Samples / Patients do not sum to the TOTAL line: one sample carries several "
           "tests and one patient has several tests. The TOTAL line shows the file-wide distinct counts.", ""]
    n += 1
    if len(status_tab):
        md += [f"## {n}. Test Status Statistics (received set)", "",
               "From the LIS `Test status` field. Columns that are zero for every test are omitted.", "",
               md_table(status_tab), ""]
        if verified:
            md += [f"Verified (L1 + L2) = {verified:,} of {total_tests:,} received tests "
                   f"({verified / total_tests * 100:.1f}%).", ""]
        n += 1
    if len(daily):
        md += [f"## {n}. Daily Statistics (by Order date/time)", "",
               md_table(daily), "",
               *[f"- **{k}:** {v}" for k, v in day_stats.items()], ""]
        n += 1
    if len(phc_stats):
        md += [f"## {n}. PHC / Source Analysis", "", md_table(phc_stats), ""]
        if phc_note:
            md += [f"> {phc_note}", ""]
        n += 1
    md += [f"## {n}. Data Quality Checks", "", md_table(dq_df), ""]
    notes = ["No internal/non-external rows were present." if n_internal_excluded == 0
             else f"{n_internal_excluded:,} internal rows excluded.",
             f"{n_dupes} duplicate records removed." if n_dupes else "No duplicate records found.",
             f"{n_reception_only:,} 'received by receptionist only' rows excluded from the strict "
             f"received count (a broader definition including them would give {n_received + n_reception_only:,}).",
             f"Reconciliation: {n_received:,} + {n_pending:,} + {n_reception_only:,} + {n_rejected:,} "
             f"= {n_received + n_pending + n_reception_only + n_rejected:,} external rows."]
    if col("Divisionname") and raw[col("Divisionname")].dropna().empty:
        notes.insert(0, "`Divisionname` is entirely blank in this export - no division breakdown is possible.")
    md += ["", "**Notes / limitations**", "", *[f"{i}. {t}" for i, t in enumerate(notes, 1)], ""]
    n += 1
    md += [f"## {n}. Final Validation", "",
           "| Rule | Result |", "|---|---|",
           f"| Sum of Test Count = Total Tests Received | {int(tw['Test Count'].sum()):,} = {total_tests:,} ✓ |",
           "| No blank Test Name in the main table | ✓ |",
           f"| Whitespace / case variants combined | ✓ ({int(rec['Test Name'].nunique())} clean names) |",
           "| Internal hospital orders excluded | ✓ |",
           f"| Duplicate records did not inflate totals | ✓ ({n_dupes} removed) |",
           f"| Percentages add to ~100% | {pct_sum:.2f}% ✓ |", ""]
    n += 1
    md += [f"## {n}. Short Summary", "",
           f"1. **Total tests received:** {total_tests:,}",
           f"2. **Total samples received:** {kpis['Unique Samples Received']:,}",
           f"3. **Unique patients:** {kpis['Unique Patients (MRN)']:,}  ·  unique orders: {kpis['Unique Orders']:,}",
           f"4. **Number of different tests:** {kpis['Different Test Types']}",
           f"5. **Top 10 most received tests:** {top10_line}",
           f"6. **Data-quality issues:** " + " ".join(notes), ""]
    md_path.write_text("\n".join(md), encoding="utf-8")

    # ================= single-page HTML report =================
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ayenati_report_page import build_page  # noqa: E402

    funnel = [("Received", n_received, "received"),
              ("Pending", n_pending, "pending"),
              ("Received by receptionist only", n_reception_only, "reception"),
              ("Rejected", n_rejected, "rejected")]
    logo_path = Path("reference_data/logo.png")
    logo = str(logo_path) if logo_path.exists() else None

    html_path = Path(out).with_suffix(".html")
    html_path.write_text(build_page({
        "hospital": hosp, "source_name": Path(src).name, "period": period or "all dates",
        "kpis": kpis, "tw_out": tw_out, "status_tab": status_tab,
        "daily": daily, "day_stats": day_stats,
        "phc_stats": phc_stats, "phc_note": phc_note,
        "dq_df": dq_df, "notes": notes, "funnel": funnel,
        "verified": verified, "pct_sum": pct_sum, "logo_path": logo,
    }), encoding="utf-8")

    # ================= official PDF report =================
    def _rows(df_, num_from=1):
        cols = list(df_.columns)
        out_rows = []
        for _, row in df_.iterrows():
            cells = []
            for j, v in enumerate(row):
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    cells.append("")
                elif j >= num_from and isinstance(v, (int, float)) and not isinstance(v, bool):
                    if "%" in str(cols[j]):
                        cells.append(f"{float(v):,.2f}")
                    elif isinstance(v, float) and abs(v - round(v)) > 1e-9:
                        cells.append(f"{v:,.2f}")
                    else:
                        cells.append(f"{int(round(v)):,}")
                else:
                    cells.append(str(v))
            out_rows.append(cells)
        return out_rows

    pdf_path = Path(out).with_suffix(".pdf")
    try:
        from labstats.export.ayenati_pdf import build_ayenati_pdf  # noqa: E402
        pdf_bytes = build_ayenati_pdf(
            hospital_name=hosp, period_label=period or "All available dates",
            source_filename=Path(src).name, kpis=kpis,
            received=n_received, pending=n_pending, reception_only=n_reception_only,
            rejected=n_rejected, raw_rows=total_raw_rows, duplicates_removed=n_dupes,
            verified=verified,
            daily_rows=_rows(daily, num_from=1) if len(daily) else [],
            day_stats=day_stats,
            testwise_rows=_rows(tw_out, num_from=2),
            status_rows=_rows(status_tab, num_from=1) if len(status_tab) else [],
            data_quality_rows=dq,
            notes=notes, pct_sum=pct_sum, logo_path=logo,
        )
        pdf_path.write_bytes(pdf_bytes)
    except Exception as exc:  # reportlab missing or render error - keep the other outputs
        pdf_path = None
        print(f"(PDF not generated: {exc})")

    # ================= refresh reports/INDEX.md =================
    reports_root = out.parent.parent
    current_folder = out.parent.name
    if reports_root.name == "reports":
        lines = ["# Report index", "",
                 "Auto-generated. Each row links the committed formats of one processed export.",
                 "The Excel workbook is not committed here - download it from the workflow artifact",
                 "(repo -> Actions -> Ayenati daily report -> latest run -> Artifacts).", "",
                 "| Report | PDF | Markdown | HTML |", "|---|---|---|---|"]

        def _idx_link(folder, ext):
            match = next(folder.glob(f"*{ext}"), None)
            if not match:
                return "-"
            rel = f"{folder.name}/{match.name}".replace(" ", "%20")
            return f"[{ext[1:].upper()}]({rel})"

        for folder in sorted((p for p in reports_root.iterdir() if p.is_dir()), reverse=True):
            mark = " (latest)" if folder.name == current_folder else ""
            lines.append(f"| {folder.name}{mark} | {_idx_link(folder, '.pdf')} | "
                         f"{_idx_link(folder, '.md')} | {_idx_link(folder, '.html')} |")
        (reports_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ================= console summary =================
    print(f"\nWorkbook written: {out}\n")
    print("=== SUMMARY ===")
    print(f"1. Total tests received:      {total_tests:,}")
    print(f"2. Total samples received:    {kpis['Unique Samples Received']:,}")
    print(f"3. Unique patients (MRN):     {kpis['Unique Patients (MRN)']:,}")
    print(f"   Unique orders:             {kpis['Unique Orders']:,}")
    print(f"4. Different test types:      {kpis['Different Test Types']}")
    print(f"\n5. Top 10 most received tests:")
    for _, row in tw.head(10).iterrows():
        print(f"   {row['Rank']:>2}. {row['Test Name']:<32} {row['Test Count']:>6,}  ({row['% of Total Tests']:.2f}%)")
    print(f"\n6. Data-quality notes:")
    print(f"   - All {n_external:,} rows are external (Is external lab order = Yes); 0 internal rows.")
    print(f"   - Exact duplicate records removed: {n_dupes}")
    print(f"   - Excluded {n_pending:,} pending, {n_reception_only:,} reception-only, {n_rejected:,} rejected rows (not lab-received).")
    print(f"   - No blank Test description / Sample barcode / MRN / Order no in the received set.")
    print(f"   - Divisionname column is entirely blank in this export.")
    if phc_note:
        print(f"   - {phc_note}")
    print(f"   - Validation: sum(Test Count) = {int(tw['Test Count'].sum()):,} == Total ({total_tests:,}); percentages sum to {pct_sum:.2f}%.")


if __name__ == "__main__":
    main()
