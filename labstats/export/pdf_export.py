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
from reportlab.lib.pagesizes import A4, landscape
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
    PageBreak,
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
LIGHT_GRAY_BG = colors.Color(246 / 255, 247 / 255, 249 / 255)
GREEN = colors.Color(30 / 255, 160 / 255, 90 / 255)
LIGHT_GREEN = colors.Color(226 / 255, 246 / 255, 236 / 255)
RED = colors.Color(210 / 255, 60 / 255, 60 / 255)
LIGHT_RED = colors.Color(252 / 255, 231 / 255, 231 / 255)
INDIGO = colors.Color(95 / 255, 80 / 255, 190 / 255)
LIGHT_INDIGO = colors.Color(233 / 255, 230 / 255, 250 / 255)


def _rgb255(c: colors.Color) -> tuple[int, int, int]:
    return (int(c.red * 255), int(c.green * 255), int(c.blue * 255))

CONFIDENTIALITY_STATEMENT = (
    "CONFIDENTIAL - For internal hospital management and quality review use only. "
    "Contains aggregated laboratory workload statistics; no individual patient data is included. "
    "Unauthorized distribution is prohibited."
)


def _doc_reference_number(now: datetime) -> str:
    return f"LAB-STAT-{now:%Y%m%d-%H%M}"


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
        width, height = canvas_obj._pagesize
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
        "CardLabel": ParagraphStyle("CardLabel", parent=base["Normal"], fontSize=7.3, textColor=colors.Color(0.4, 0.42, 0.46), fontName="Helvetica-Bold", leading=9.5),
        "CardValue": ParagraphStyle("CardValue", parent=base["Normal"], fontSize=17, textColor=NAVY, fontName="Helvetica-Bold"),
        "InfoLabel": ParagraphStyle("InfoLabel", parent=base["Normal"], fontSize=6.8, textColor=colors.Color(0.5, 0.52, 0.56), fontName="Helvetica-Bold"),
        "InfoValue": ParagraphStyle("InfoValue", parent=base["Normal"], fontSize=9.5, textColor=NAVY, fontName="Helvetica-Bold"),
    }
    return styles


def _indicator_cards(indicators: list[tuple[str, str, str, colors.Color, colors.Color]], styles, columns: int = 3):
    """indicators: list of (icon_name, label, value, accent_color, tint_color).

    Renders a grid of cards, each with a colored top accent strip and a
    matching light tint background - the accent color carries meaning
    (blue = volume, red = needs attention, green = healthy, indigo = insight),
    so the most important numbers are visible before reading any label."""
    card_width = 17.6 * cm / columns
    cells, accents, tints = [], [], []
    for icon_name, label, value, accent, tint in indicators:
        icon_bytes = icon_png_bytes(icon_name, _rgb255(accent), 64)
        img = RLImage(io.BytesIO(icon_bytes), width=0.8 * cm, height=0.8 * cm)
        label_p = Paragraph(label.upper(), styles["CardLabel"])
        header_row = Table([[img, label_p]], colWidths=[1.0 * cm, card_width - 1.4 * cm])
        header_row.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        value_p = Paragraph(str(value), styles["CardValue"])
        card = Table([[header_row], [value_p]], colWidths=[card_width - 1.0 * cm])
        card.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (0, 0), 0),
                    ("BOTTOMPADDING", (0, 0), (0, 0), 5),
                    ("TOPPADDING", (0, 1), (0, 1), 1),
                    ("BOTTOMPADDING", (0, 1), (0, 1), 0),
                ]
            )
        )
        cells.append(card)
        accents.append(accent)
        tints.append(tint)

    rows_of_cells = [cells[i : i + columns] for i in range(0, len(cells), columns)]
    rows_of_accents = [accents[i : i + columns] for i in range(0, len(accents), columns)]
    rows_of_tints = [tints[i : i + columns] for i in range(0, len(tints), columns)]

    style_cmds = [
        ("BOX", (0, 0), (-1, -1), 0.6, GRID_GRAY),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, GRID_GRAY),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]
    for r, (row_cells, row_accents, row_tints) in enumerate(zip(rows_of_cells, rows_of_accents, rows_of_tints)):
        for c, (accent, tint) in enumerate(zip(row_accents, row_tints)):
            style_cmds.append(("LINEABOVE", (c, r), (c, r), 2.6, accent))
            style_cmds.append(("BACKGROUND", (c, r), (c, r), tint))
        while len(row_cells) < columns:
            row_cells.append("")

    grid = Table(rows_of_cells, colWidths=[card_width] * columns)
    grid.setStyle(TableStyle(style_cmds))
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


def _data_table_grouped_first_col(headers, rows, col_widths=None):
    """Like _data_table, but shows the first column's value only on the first
    row of each run of consecutive identical values (e.g. grouping test rows
    by Division without repeating the division name on every line). Rows must
    already be sorted so identical first-column values are contiguous.

    A true merged cell (Table SPAN) cannot be split across a page break, which
    crashes reportlab's pagination once a group is long enough to span pages -
    blanking the repeated label instead gets the same grouped look safely."""
    grouped_rows = []
    previous = object()
    for row in rows:
        display_row = list(row)
        if display_row[0] == previous:
            display_row[0] = ""
        else:
            previous = display_row[0]
        grouped_rows.append(display_row)

    table_data = [headers] + grouped_rows
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
    ]
    table.setStyle(TableStyle(style))
    return table


def _totals_table(headers, rows, col_widths=None):
    """Compact summary table with its last row (Grand Total) bolded and highlighted."""
    table_data = [headers] + rows
    table = Table(table_data, colWidths=col_widths)
    last = len(table_data) - 1
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID_GRAY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, last - 1), [colors.white, LIGHT_BLUE]),
        ("BACKGROUND", (0, last), (-1, last), BLUE),
        ("TEXTCOLOR", (0, last), (-1, last), colors.white),
        ("FONTNAME", (0, last), (-1, last), "Helvetica-Bold"),
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
    abbreviation_table_rows: list[list] | None = None,
    highest_volume_division: str | None = None,
    highest_volume_test: str | None = None,
    highest_volume_category: str | None = None,
    logo_path: str | None = None,
    version: str = "1.0",
) -> bytes:
    now = datetime.now()
    doc_ref = _doc_reference_number(now)
    styles = _styles()

    portrait_size = A4
    landscape_size = landscape(A4)
    top_margin, bottom_margin, side_margin = 2.4 * cm, 1.9 * cm, 1.6 * cm

    buffer = io.BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=portrait_size,
        topMargin=top_margin, bottomMargin=bottom_margin, leftMargin=side_margin, rightMargin=side_margin,
    )
    portrait_frame = Frame(
        side_margin, bottom_margin, portrait_size[0] - 2 * side_margin, portrait_size[1] - top_margin - bottom_margin,
        id="portrait_body",
    )
    landscape_frame = Frame(
        side_margin, bottom_margin, landscape_size[0] - 2 * side_margin, landscape_size[1] - top_margin - bottom_margin,
        id="landscape_body",
    )
    doc.addPageTemplates(
        [
            PageTemplate(id="portrait", frames=[portrait_frame], pagesize=portrait_size),
            PageTemplate(id="landscape", frames=[landscape_frame], pagesize=landscape_size),
        ]
    )

    band_title_style = ParagraphStyle("BandTitle", parent=styles["Title"], fontSize=12.5, spaceAfter=2, alignment=0)
    band_subtitle_style = ParagraphStyle("BandSubtitle", parent=styles["Small"], alignment=0)

    title_block = Table(
        [[Paragraph("Official Medical Laboratory Statistics Report", band_title_style)], [Paragraph("Laboratory and Blood Bank Department · " + hospital_name, band_subtitle_style)]],
        colWidths=[6.6 * cm],
    )
    title_block.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (0, 0), 1)]))

    def info_pair(label, value):
        cell = Table(
            [[Paragraph(label.upper(), styles["InfoLabel"])], [Paragraph(str(value), styles["InfoValue"])]],
            colWidths=[3.0 * cm],
        )
        cell.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (0, 0), 2)]))
        return cell

    header_band = Table(
        [
            [
                title_block,
                info_pair("Period", period_label),
                info_pair("Generated", now.strftime("%d-%b-%Y")),
                info_pair("Doc Ref", doc_ref),
                info_pair("Version", version),
            ]
        ],
        colWidths=[6.6 * cm, 2.4 * cm, 2.4 * cm, 3.6 * cm, 1.7 * cm],
    )
    header_band.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY_BG),
                ("LINEBEFORE", (0, 0), (0, 0), 3, BLUE),
                ("LEFTPADDING", (0, 0), (0, 0), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story = [header_band, Spacer(1, 6), Paragraph(CONFIDENTIALITY_STATEMENT, styles["Small"]), Spacer(1, 10)]

    story.append(Paragraph("Executive Indicators", styles["Section"]))

    def _alert_colors(count: int):
        return (RED, LIGHT_RED) if count else (GREEN, LIGHT_GREEN)

    rejected = indicators.get("rejected_samples", 0) or 0
    cancelled = indicators.get("cancelled_tests", 0) or 0
    pending = indicators.get("pending_tests", 0) or 0

    volume_cards = [
        ("patients", "Unique Patients Received", indicators.get("total_unique_patients_received", "-"), BLUE, LIGHT_BLUE),
        ("visits", "Patient Visits", indicators.get("total_patient_visits", "-"), BLUE, LIGHT_BLUE),
        ("samples", "Samples Received", indicators.get("total_samples_received", "-"), BLUE, LIGHT_BLUE),
        ("requests", "Laboratory Requests", indicators.get("total_laboratory_requests", "-"), BLUE, LIGHT_BLUE),
        ("packages", "Package Line Items", indicators.get("total_package_line_items", "-"), BLUE, LIGHT_BLUE),
        ("tests", "Analytical Tests Performed", indicators.get("total_analytical_tests_performed", "-"), BLUE, LIGHT_BLUE),
    ]
    story.append(_indicator_cards(volume_cards, styles))
    story.append(Spacer(1, 8))

    highlight_cards = [
        ("division", "Highest-Volume Division", highest_volume_division or "Not Applicable", INDIGO, LIGHT_INDIGO),
        ("tests", "Highest-Volume Test", highest_volume_test or "Not Applicable", INDIGO, LIGHT_INDIGO),
        ("patients", "Highest-Volume Category", highest_volume_category or "Not Applicable", INDIGO, LIGHT_INDIGO),
    ]
    story.append(_indicator_cards(highlight_cards, styles))
    story.append(Spacer(1, 8))

    average_cards = [
        ("average", "Avg. Patients / Day", indicators.get("average_patients_received_per_day", "-"), BLUE, LIGHT_BLUE),
        ("average", "Avg. Tests / Patient", indicators.get("average_analytical_tests_per_patient", "-"), BLUE, LIGHT_BLUE),
    ]
    story.append(_indicator_cards(average_cards, styles, columns=2))
    story.append(Spacer(1, 8))

    alert_cards = [
        ("alert", "Rejected Samples", rejected, *_alert_colors(rejected)),
        ("alert", "Cancelled Tests", cancelled, *_alert_colors(cancelled)),
        ("alert", "Pending Tests", pending, *_alert_colors(pending)),
    ]
    story.append(_indicator_cards(alert_cards, styles))

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

    if abbreviation_table_rows:
        story.append(NextPageTemplate("landscape"))
        story.append(PageBreak())
        story.append(Paragraph("Report Format 3: Compact Abbreviation Report", styles["Section"]))
        story.append(
            Paragraph(
                "Grouped by laboratory division; each abbreviation's analytical test count is "
                "accumulated per parameter (see Full Test-Name Report methodology).",
                styles["Small"],
            )
        )
        story.append(Spacer(1, 10))

        division_totals: dict[str, int] = {}
        for division, _abbreviation, count in abbreviation_table_rows:
            division_totals[division] = division_totals.get(division, 0) + count
        totals_rows = [[division, total] for division, total in division_totals.items()]
        totals_rows.append(["GRAND TOTAL", sum(division_totals.values())])

        story.append(Paragraph("Division Totals", styles["Body"]))
        story.append(Spacer(1, 4))
        story.append(
            _totals_table(
                ["Division", "Analytical Test Count"],
                totals_rows,
                col_widths=[7.0 * cm, 5.0 * cm],
            )
        )
        story.append(Spacer(1, 16))

        story.append(Paragraph("Detail by Abbreviation", styles["Body"]))
        story.append(Spacer(1, 4))
        story.append(
            _data_table_grouped_first_col(
                ["Division", "Abbreviation", "Analytical Test Count"],
                abbreviation_table_rows,
                col_widths=[6.0 * cm, 8.0 * cm, 6.0 * cm],
            )
        )

    header_footer_fn = _make_header_footer(hospital_name, doc_ref, version, logo_path)
    doc.build(
        story,
        canvasmaker=lambda *a, **kw: _NumberedCanvas(*a, header_footer_fn=header_footer_fn, **kw),
    )
    return buffer.getvalue()
