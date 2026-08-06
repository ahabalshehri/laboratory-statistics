"""Official PDF Laboratory Statistics Report (spec sections 18 and 32).

Produces a print-ready, signable document: hospital logo and letterhead,
document reference number and version, confidentiality statement, executive
indicators, division and patient-category tables, a methodology section, and
a Prepared/Reviewed/Approved signature block with an official stamp area -
repeated on every page with automatic page numbering.
"""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image as RLImage,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from labstats.export.icons import BADGE_BLUE, BADGE_NAVY, icon_png_bytes

NAVY = colors.Color(20 / 255, 70 / 255, 110 / 255)
BLUE = colors.Color(30 / 255, 150 / 255, 210 / 255)
LIGHT_BLUE = colors.Color(228 / 255, 243 / 255, 250 / 255)
GRID_GRAY = colors.Color(210 / 255, 210 / 255, 210 / 255)

CONFIDENTIALITY_STATEMENT = (
    "CONFIDENTIAL - For internal hospital management and quality review use only. "
    "Contains aggregated laboratory workload statistics; no individual patient data is included. "
    "Unauthorized distribution is prohibited."
)


def _doc_reference_number(now: datetime) -> str:
    return f"LAB-STAT-{now:%Y%m%d-%H%M%S}"


class _NumberedCanvas(pdfcanvas.Canvas):
    """Buffers pages so the footer can show 'Page X of Y' once the total is known.

    Each call to showPage() snapshots the canvas state for that page and then
    resets reportlab's internal drawing buffer via _startPage() - without
    that reset, every page's drawing commands accumulate into the same
    mutable buffer and all pages render stacked on top of each other.
    """

    def __init__(self, *args, header_footer_fn=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self._header_footer_fn = header_footer_fn

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for i, state in enumerate(self._saved_page_states, start=1):
            self.__dict__.update(state)
            if self._header_footer_fn:
                self._header_footer_fn(self, i, total_pages)
            pdfcanvas.Canvas.showPage(self)
        pdfcanvas.Canvas.save(self)


def _make_header_footer(hospital_name: str, doc_ref: str, version: str, logo_path: str | None):
    def draw(canvas_obj, page_num, total_pages):
        width, height = A4
        margin = 1.6 * cm

        if logo_path:
            try:
                canvas_obj.drawImage(
                    logo_path, margin, height - 2.0 * cm, width=1.4 * cm, height=1.4 * cm,
                    preserveAspectRatio=True, mask="auto",
                )
            except Exception:
                pass

        canvas_obj.setFont("Helvetica-Bold", 12)
        canvas_obj.setFillColor(NAVY)
        canvas_obj.drawString(margin + 1.8 * cm, height - 1.35 * cm, hospital_name)
        canvas_obj.setFont("Helvetica", 9)
        canvas_obj.setFillColor(colors.gray)
        canvas_obj.drawString(margin + 1.8 * cm, height - 1.75 * cm, "Laboratory and Blood Bank Department")

        canvas_obj.setStrokeColor(BLUE)
        canvas_obj.setLineWidth(1.2)
        canvas_obj.line(margin, height - 2.15 * cm, width - margin, height - 2.15 * cm)

        canvas_obj.setStrokeColor(GRID_GRAY)
        canvas_obj.setLineWidth(0.6)
        canvas_obj.line(margin, 1.55 * cm, width - margin, 1.55 * cm)
        canvas_obj.setFont("Helvetica", 7)
        canvas_obj.setFillColor(colors.gray)
        canvas_obj.drawString(margin, 1.15 * cm, CONFIDENTIALITY_STATEMENT[:110] + "...")
        canvas_obj.drawString(margin, 0.85 * cm, f"Document Ref: {doc_ref}  |  Version: {version}")
        canvas_obj.drawRightString(width - margin, 0.85 * cm, f"Page {page_num} of {total_pages}")

    return draw


def _styles():
    base = getSampleStyleSheet()
    styles = {
        "Title": ParagraphStyle("ReportTitle", parent=base["Title"], fontSize=17, textColor=NAVY, spaceAfter=4),
        "Subtitle": ParagraphStyle("ReportSubtitle", parent=base["Normal"], fontSize=11, textColor=colors.gray, alignment=TA_CENTER, spaceAfter=10),
        "Section": ParagraphStyle("Section", parent=base["Heading2"], fontSize=12.5, textColor=NAVY, spaceBefore=14, spaceAfter=6),
        "Body": ParagraphStyle("Body", parent=base["Normal"], fontSize=9, leading=13),
        "Small": ParagraphStyle("Small", parent=base["Normal"], fontSize=8, leading=11, textColor=colors.gray),
        "CardLabel": ParagraphStyle("CardLabel", parent=base["Normal"], fontSize=8.5, textColor=colors.gray),
        "CardValue": ParagraphStyle("CardValue", parent=base["Normal"], fontSize=15, textColor=NAVY, fontName="Helvetica-Bold"),
    }
    return styles


def _indicator_cards(indicators: list[tuple[str, str, str]], styles):
    """indicators: list of (icon_name, label, value). Renders a 3-column grid of icon+label+value cards."""
    cells = []
    for icon_name, label, value in indicators:
        icon_bytes = icon_png_bytes(icon_name, BADGE_BLUE, 64)
        img = RLImage(io.BytesIO(icon_bytes), width=0.9 * cm, height=0.9 * cm)
        text_table = Table(
            [[Paragraph(label, styles["CardLabel"])], [Paragraph(str(value), styles["CardValue"])]],
            colWidths=[4.0 * cm],
        )
        text_table.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        inner = Table([[img, text_table]], colWidths=[1.1 * cm, 4.0 * cm])
        inner.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        cells.append(inner)

    rows = [cells[i : i + 3] for i in range(0, len(cells), 3)]
    while rows and len(rows[-1]) < 3:
        rows[-1].append("")

    grid = Table(rows, colWidths=[5.7 * cm] * 3)
    grid.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.6, GRID_GRAY),
                ("INNERGRID", (0, 0), (-1, -1), 0.6, GRID_GRAY),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return grid


def _data_table(headers, rows, col_widths=None):
    table_data = [headers] + rows
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID_GRAY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BLUE]),
    ]
    table.setStyle(TableStyle(style))
    return table


def _signature_block(styles):
    def blank_col(title):
        return [
            Paragraph(f"<b>{title}</b>", styles["Body"]),
            Spacer(1, 26),
            Paragraph("Name: ______________", styles["Small"]),
            Spacer(1, 6),
            Paragraph("Signature: _________", styles["Small"]),
            Spacer(1, 6),
            Paragraph("Date: ______________", styles["Small"]),
        ]

    stamp_cell = [
        Paragraph("<b>Official Stamp</b>", styles["Body"]),
        Spacer(1, 60),
    ]

    prepared = Table([[p] for p in blank_col("Prepared By")])
    reviewed = Table([[p] for p in blank_col("Reviewed By")])
    approved = Table([[p] for p in blank_col("Approved By")])
    stamp = Table([[p] for p in stamp_cell], style=TableStyle([("BOX", (0, 0), (-1, -1), 0.8, GRID_GRAY)]))

    outer = Table([[prepared, reviewed, approved, stamp]], colWidths=[4.2 * cm, 4.2 * cm, 4.2 * cm, 4.0 * cm])
    outer.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 10)]))
    return outer


def build_executive_pdf(
    hospital_name: str,
    period_label: str,
    date_basis: str,
    indicators: dict,
    division_table_rows: list[list],
    reception_table_rows: list[list],
    methodology: dict,
    logo_path: str | None = None,
    version: str = "1.0",
) -> bytes:
    now = datetime.now()
    doc_ref = _doc_reference_number(now)
    styles = _styles()

    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4, topMargin=2.4 * cm, bottomMargin=1.9 * cm, leftMargin=1.6 * cm, rightMargin=1.6 * cm)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame])])

    story = []
    story.append(Paragraph("Official Medical Laboratory Statistics Report", styles["Title"]))
    story.append(Paragraph(f"Reporting Period: {period_label}", styles["Subtitle"]))

    meta_rows = [
        ["Document Reference Number", doc_ref, "Version", version],
        ["Report Generated", now.strftime("%Y-%m-%d %H:%M:%S"), "Date Basis", date_basis],
    ]
    meta_table = Table(meta_rows, colWidths=[4.6 * cm, 5.0 * cm, 2.6 * cm, 4.6 * cm])
    meta_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, 0), (0, -1), LIGHT_BLUE),
                ("BACKGROUND", (2, 0), (2, -1), LIGHT_BLUE),
                ("GRID", (0, 0), (-1, -1), 0.5, GRID_GRAY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 6))
    story.append(Paragraph(CONFIDENTIALITY_STATEMENT, styles["Small"]))

    story.append(Paragraph("Executive Indicators", styles["Section"]))
    card_defs = [
        ("patients", "Unique Patients Received", indicators.get("total_unique_patients_received", "-")),
        ("visits", "Patient Visits", indicators.get("total_patient_visits", "-")),
        ("samples", "Samples Received", indicators.get("total_samples_received", "-")),
        ("requests", "Laboratory Requests", indicators.get("total_laboratory_requests", "-")),
        ("packages", "Package Line Items", indicators.get("total_package_line_items", "-")),
        ("tests", "Analytical Tests Performed", indicators.get("total_analytical_tests_performed", "-")),
        ("average", "Avg. Patients / Day", indicators.get("average_patients_received_per_day", "-")),
        ("average", "Avg. Tests / Patient", indicators.get("average_analytical_tests_per_patient", "-")),
        ("alert", "Rejected / Cancelled / Pending", f"{indicators.get('rejected_samples_or_tests', 0)} / {indicators.get('cancelled_tests', 0)} / {indicators.get('pending_tests', 0)}"),
    ]
    story.append(_indicator_cards(card_defs, styles))

    if division_table_rows:
        story.append(Paragraph("Statistics by Laboratory Division", styles["Section"]))
        story.append(
            _data_table(
                ["Division", "Patients", "Requests", "Package Lines", "Individual Lines", "Analytical Tests", "% of Workload"],
                division_table_rows,
                col_widths=[3.6 * cm, 2.0 * cm, 2.0 * cm, 2.4 * cm, 2.6 * cm, 2.6 * cm, 2.4 * cm],
            )
        )

    if reception_table_rows:
        story.append(Paragraph("Patient Reception by Category", styles["Section"]))
        story.append(
            _data_table(
                ["Patient Category", "Patients", "Requests", "Analytical Tests", "% of Patients", "% of Workload"],
                reception_table_rows,
                col_widths=[4.2 * cm, 2.6 * cm, 2.4 * cm, 2.8 * cm, 2.6 * cm, 2.6 * cm],
            )
        )

    story.append(Paragraph("Methodology / Report Notes", styles["Section"]))
    for key, value in methodology.items():
        label = key.replace("_", " ").title()
        if isinstance(value, list):
            for item in value:
                story.append(Paragraph(f"<b>{label}:</b> {item}", styles["Small"]))
        else:
            story.append(Paragraph(f"<b>{label}:</b> {value}", styles["Small"]))

    story.append(Spacer(1, 16))
    story.append(Paragraph("Approval", styles["Section"]))
    story.append(_signature_block(styles))

    header_footer_fn = _make_header_footer(hospital_name, doc_ref, version, logo_path)
    doc.build(
        story,
        canvasmaker=lambda *a, **kw: _NumberedCanvas(*a, header_footer_fn=header_footer_fn, **kw),
    )
    return buffer.getvalue()
