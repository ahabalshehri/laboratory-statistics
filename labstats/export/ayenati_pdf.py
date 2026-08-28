"""Official External / Ayenati Laboratory Statistics Report (PDF).

Print-ready, signable document for sharing with hospital administration and
health-authority oversight: hospital logo + letterhead, document reference and
version, confidentiality statement, executive indicators, concise workload
summary, data-quality attestation, a Prepared / Reviewed / Approved signature
block with an official stamp area, and full test-wise appendices - letterhead
and page numbering repeated on every page.

Reuses the shared building blocks in labstats.export.pdf_export.
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import gray
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from labstats.export.pdf_export import (
    BLUE,
    GREEN,
    GRID_GRAY,
    LIGHT_BLUE,
    LIGHT_GRAY_BG,
    LIGHT_GREEN,
    NAVY,
    _NumberedCanvas,
    _data_table,
    _indicator_cards,
    _signature_block,
    _styles,
    _totals_table,
)

FOOTER_NOTE = ("CONFIDENTIAL - aggregated laboratory workload only; contains no patient-identifiable "
               "data. Prepared for hospital administration and health-authority review.")


def _doc_ref(now: datetime) -> str:
    return f"EXT-LAB-STAT-{now:%Y%m%d}"


def _header_footer(hospital_name: str, doc_ref: str, version: str, logo_path: str | None):
    def draw(c, page_num, total_pages):
        width, height = c._pagesize
        margin = 1.6 * cm
        if logo_path:
            try:
                c.drawImage(logo_path, margin, height - 2.0 * cm, width=1.4 * cm, height=1.4 * cm,
                            preserveAspectRatio=True, mask="auto")
            except Exception:
                pass
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(NAVY)
        c.drawString(margin + 1.8 * cm, height - 1.35 * cm, hospital_name)
        c.setFont("Helvetica", 9)
        c.setFillColor(gray)
        c.drawString(margin + 1.8 * cm, height - 1.75 * cm, "Laboratory and Blood Bank Department")
        c.setStrokeColor(BLUE)
        c.setLineWidth(1.2)
        c.line(margin, height - 2.15 * cm, width - margin, height - 2.15 * cm)
        c.setStrokeColor(GRID_GRAY)
        c.setLineWidth(0.6)
        c.line(margin, 1.55 * cm, width - margin, 1.55 * cm)
        c.setFont("Helvetica", 7)
        c.setFillColor(gray)
        c.drawString(margin, 1.15 * cm, FOOTER_NOTE)
        c.drawString(margin, 0.85 * cm, f"Document Ref: {doc_ref}  |  Version: {version}")
        c.drawRightString(width - margin, 0.85 * cm, f"Page {page_num} of {total_pages}")
    return draw


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:,.2f}" if abs(v - round(v)) > 1e-9 else f"{int(round(v)):,}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def build_ayenati_pdf(
    *,
    hospital_name: str,
    period_label: str,
    source_filename: str,
    kpis: dict,
    received: int,
    pending: int,
    reception_only: int,
    rejected: int,
    raw_rows: int,
    duplicates_removed: int,
    verified: int,
    daily_rows: list[list],
    day_stats: dict,
    testwise_rows: list[list],
    status_rows: list[list],
    data_quality_rows: list[list],
    notes: list[str],
    pct_sum: float,
    logo_path: str | None = None,
    version: str = "1.0",
) -> bytes:
    now = datetime.now()
    ref = _doc_ref(now)
    styles = _styles()
    size = A4
    top_m, bot_m, side_m = 2.4 * cm, 1.9 * cm, 1.6 * cm

    buffer = io.BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=size,
        topMargin=top_m, bottomMargin=bot_m, leftMargin=side_m, rightMargin=side_m,
    )
    doc.addPageTemplates([PageTemplate(id="body", frames=[Frame(
        side_m, bot_m, size[0] - 2 * side_m, size[1] - top_m - bot_m, id="f")])])

    band_title = ParagraphStyle("BandTitle", parent=styles["Title"], fontSize=12.5,
                                leading=15, spaceAfter=3, alignment=0)
    band_sub = ParagraphStyle("BandSub", parent=styles["Small"], leading=10, alignment=0)

    ref_val = ParagraphStyle("InfoValueSm", parent=styles["InfoValue"], fontSize=8, leading=10)

    def info_pair(label, value, width=3.0 * cm, small=False):
        cell = Table([[Paragraph(label.upper(), styles["InfoLabel"])],
                      [Paragraph(str(value), ref_val if small else styles["InfoValue"])]],
                     colWidths=[width])
        cell.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                                  ("TOPPADDING", (0, 0), (-1, -1), 0),
                                  ("BOTTOMPADDING", (0, 0), (0, 0), 2)]))
        return cell

    title_block = Table(
        [[Paragraph("Official External / Ayenati<br/>Laboratory Statistics Report", band_title)],
         [Paragraph("Tests referred from primary health-care centres, received by the "
                    "hospital laboratory", band_sub)]],
        colWidths=[8.6 * cm])
    title_block.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0),
                                     ("TOPPADDING", (0, 0), (-1, -1), 0),
                                     ("BOTTOMPADDING", (0, 0), (0, 0), 1)]))

    header_band = Table(
        [[title_block,
          info_pair("Reporting Period", period_label, width=2.9 * cm),
          info_pair("Doc Ref", ref, width=4.3 * cm, small=True),
          info_pair("Version", version, width=1.4 * cm)]],
        colWidths=[8.6 * cm, 2.9 * cm, 4.3 * cm, 1.4 * cm])
    header_band.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY_BG),
        ("LINEBEFORE", (0, 0), (0, 0), 3, BLUE),
        ("LEFTPADDING", (0, 0), (0, 0), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))

    confidential = (
        "CONFIDENTIAL - prepared for hospital administration and health-authority review. "
        "Contains aggregated laboratory workload statistics only; no individual patient data "
        "is included. Please handle in line with your organisation's information-governance policy."
    )
    story = [
        header_band, Spacer(1, 6),
        Paragraph(confidential, styles["Small"]), Spacer(1, 12),
        Paragraph("Executive Indicators", styles["Section"]),
    ]

    total = kpis["Total Tests Received"]
    story.append(_indicator_cards([
        ("tests", "Tests Received", _fmt(kpis["Total Tests Received"]), BLUE, LIGHT_BLUE),
        ("samples", "Samples Received", _fmt(kpis["Unique Samples Received"]), BLUE, LIGHT_BLUE),
        ("patients", "Unique Patients", _fmt(kpis["Unique Patients (MRN)"]), BLUE, LIGHT_BLUE),
    ], styles))
    story.append(Spacer(1, 8))
    story.append(_indicator_cards([
        ("requests", "Unique Orders", _fmt(kpis["Unique Orders"]), BLUE, LIGHT_BLUE),
        ("division", "Different Test Types", _fmt(kpis["Different Test Types"]), BLUE, LIGHT_BLUE),
        ("average", "Verified (L1+L2)",
         f"{verified / total * 100:.1f}%" if verified and total else "-", GREEN, LIGHT_GREEN),
    ], styles))
    story.append(Spacer(1, 4))

    story.append(Paragraph("Scope and Method", styles["Section"]))
    story.append(Paragraph(
        "This report covers laboratory tests referred from outside the hospital through the "
        "Ayenati programme (primary health-care centres) and received by the hospital "
        "laboratory during the reporting period. Records are filtered to "
        "<b>Is external lab order = Yes</b> and to specimens marked received by the laboratory. "
        "The counting unit is one analytical <b>test</b>, grouped by a cleaned "
        "<b>Test description</b>; tests, samples, patients and orders are reported as separate "
        f"measurements. Source export: <b>{source_filename}</b>. "
        "No patient-identifiable data is included in this document.", styles["Body"]))
    story.append(Spacer(1, 10))

    excl_total = received + pending + reception_only + rejected
    story.append(KeepTogether([
        Paragraph("Received Workload vs. Excluded Records", styles["Section"]),
        _totals_table(
            ["Specimen state", "Records", "% of external"],
            [["Received by laboratory (counted)", _fmt(received), f"{received / excl_total * 100:.1f}%"],
             ["Pending / not yet received (excluded)", _fmt(pending), f"{pending / excl_total * 100:.1f}%"],
             ["Received by receptionist only (excluded)", _fmt(reception_only), f"{reception_only / excl_total * 100:.1f}%"],
             ["Rejected (excluded)", _fmt(rejected), f"{rejected / excl_total * 100:.1f}%"],
             ["Total external records", _fmt(excl_total), "100.0%"]],
            col_widths=[9.6 * cm, 3.6 * cm, 3.4 * cm]),
    ]))
    story.append(Spacer(1, 12))

    if daily_rows:
        daily_block = [
            Paragraph("Daily Workload", styles["Section"]),
            _totals_table(
                ["Date", "Tests", "Samples", "Patients", "Orders"],
                daily_rows, col_widths=[4.6 * cm, 2.9 * cm, 2.9 * cm, 2.9 * cm, 2.9 * cm]),
        ]
        if day_stats:
            daily_block.append(Spacer(1, 5))
            bits = "&nbsp;&nbsp;|&nbsp;&nbsp;".join(
                f"<b>{k}:</b> {_fmt(v)}" for k, v in day_stats.items())
            daily_block.append(Paragraph(bits, styles["Small"]))
        story.append(KeepTogether(daily_block))
        story.append(Spacer(1, 12))

    story.append(Paragraph("Data Quality and Validation", styles["Section"]))
    story.append(_data_table(
        ["Check", "Value"],
        [[str(a), _fmt(b)] for a, b in data_quality_rows],
        col_widths=[12.6 * cm, 4.0 * cm]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"<b>Validation:</b> the sum of test counts across all test names equals the total "
        f"tests received ({_fmt(total)}); percentages sum to {pct_sum:.2f}%; "
        f"{duplicates_removed} duplicate export record(s) were detected and removed; "
        f"raw rows in file: {_fmt(raw_rows)}.", styles["Small"]))
    for note in notes:
        story.append(Paragraph(f"&bull;&nbsp; {note}", styles["Small"]))

    story.append(Spacer(1, 16))
    story.append(Paragraph("Approval", styles["Section"]))
    story.append(_signature_block(styles))

    # ---- Appendix A: full test-wise table ----
    story.append(PageBreak())
    story.append(Paragraph("Appendix A &mdash; Test-Wise Statistics (complete)", styles["Section"]))
    story.append(Paragraph(
        "All received external / Ayenati tests, by cleaned Test description, highest volume first. "
        "% of Total = test count &divide; total tests received &times; 100.", styles["Small"]))
    story.append(Spacer(1, 8))
    story.append(_totals_table(
        ["Rank", "Test Name", "Count", "% Total", "Samples", "Patients"],
        testwise_rows,
        col_widths=[1.3 * cm, 7.0 * cm, 2.1 * cm, 2.0 * cm, 2.2 * cm, 2.2 * cm]))

    # ---- Appendix B: full test status ----
    if status_rows:
        story.append(PageBreak())
        story.append(Paragraph("Appendix B &mdash; Test Status (complete)", styles["Section"]))
        story.append(Paragraph(
            "Position of each received test in the LIS pipeline. Columns that are zero for every "
            "test are omitted.", styles["Small"]))
        story.append(Spacer(1, 8))
        ncol = len(status_rows[0])
        first = 6.0 * cm
        rest = (16.6 * cm - first) / (ncol - 1)
        story.append(_totals_table(
            ["Test Name", "Total", "Ordered", "Resulted", "Ver. L1", "Ver. L2"][:ncol],
            status_rows, col_widths=[first] + [rest] * (ncol - 1)))

    doc.build(
        story,
        canvasmaker=lambda *a, **kw: _NumberedCanvas(
            *a, header_footer_fn=_header_footer(hospital_name, ref, version, logo_path), **kw),
    )
    return buffer.getvalue()
