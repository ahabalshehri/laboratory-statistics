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


CARD_GRID_WIDTH = 17.6 * cm
CARD_GAP = 0.35 * cm


def _kpi_card(icon_name: str, label: str, value, accent: colors.Color, card_width: float, styles):
    """A single white KPI card: thin colored top accent, uppercase gray label
    with a small colored icon badge in the top-right corner, and a large bold
    value beneath - the flat card-with-accent-border look of a modern ops
    dashboard, not a filled colored box."""
    value_text = str(value)
    if len(value_text) > 16:
        value_style = ParagraphStyle("CardValueSmall", parent=styles["CardValue"], fontSize=11.5, leading=14)
    elif len(value_text) > 9:
        value_style = ParagraphStyle("CardValueMed", parent=styles["CardValue"], fontSize=15, leading=18)
    else:
        value_style = ParagraphStyle("CardValueLarge", parent=styles["CardValue"], fontSize=21, leading=24)

    icon_bytes = icon_png_bytes(icon_name, _rgb255(accent), 64)
    img = RLImage(io.BytesIO(icon_bytes), width=0.55 * cm, height=0.55 * cm)
    label_p = Paragraph(label.upper(), styles["CardLabel"])

    inner_width = card_width - 1.7 * cm
    header = Table([[label_p, img]], colWidths=[inner_width - 0.7 * cm, 0.7 * cm])
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    value_p = Paragraph(value_text, value_style)
    body = Table([[header], [value_p]], colWidths=[inner_width])
    body.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (0, 0), 0),
                ("BOTTOMPADDING", (0, 0), (0, 0), 9),
                ("TOPPADDING", (0, 1), (0, 1), 0),
                ("BOTTOMPADDING", (0, 1), (0, 1), 0),
            ]
        )
    )
    card = Table([[body]], colWidths=[card_width])
    card.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.75, GRID_GRAY),
                ("LINEABOVE", (0, 0), (-1, 0), 3, accent),
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    return card


def _indicator_cards(indicators: list[tuple[str, str, str, colors.Color, colors.Color]], styles, columns: int = 3):
    """indicators: list of (icon_name, label, value, accent_color, _unused).

    Renders a row of independent white cards (each with its own border and
    colored top accent) separated by real gaps, rather than one shared
    bordered grid - so they read as distinct cards, not a filled table."""
    card_width = (CARD_GRID_WIDTH - CARD_GAP * (columns - 1)) / columns
    cards = [_kpi_card(icon_name, label, value, accent, card_width, styles) for icon_name, label, value, accent, _ in indicators]

    col_widths = []
    for i in range(columns):
        col_widths.append(card_width)
        if i < columns - 1:
            col_widths.append(CARD_GAP)

    grid_rows = []
    for i in range(0, len(cards), columns):
        row_cards = cards[i : i + columns]
        row = []
        for j in range(columns):
            if j > 0:
                row.append("")
            row.append(row_cards[j] if j < len(row_cards) else "")
        grid_rows.append(row)

    grid = Table(grid_rows, colWidths=col_widths)
    grid.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), CARD_GAP),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
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


def _matrix_table(headers, rows, col_widths=None):
    """Grid table with both a highlighted Total row (last row) and a
    highlighted Total column (last column) - for the Division x Month
    matrix, where both carry meaning worth calling out."""
    table_data = [headers] + rows
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    last_row = len(table_data) - 1
    last_col = len(headers) - 1
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID_GRAY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, last_row - 1), [colors.white, LIGHT_BLUE]),
        ("BACKGROUND", (0, last_row), (-1, last_row), BLUE),
        ("TEXTCOLOR", (0, last_row), (-1, last_row), colors.white),
        ("FONTNAME", (0, last_row), (-1, last_row), "Helvetica-Bold"),
        ("BACKGROUND", (last_col, 1), (last_col, last_row - 1), LIGHT_INDIGO),
        ("FONTNAME", (last_col, 0), (last_col, last_row - 1), "Helvetica-Bold"),
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
    patients_summary_rows: list[list] | None = None,
    division_month_headers: list[str] | None = None,
    division_month_rows: list[list] | None = None,
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

    if patients_summary_rows:
        story.append(Paragraph("Patients Received Summary", styles["Section"]))
        story.append(
            Paragraph(
                "Total patients received for the period, by nationality and by gender.",
                styles["Small"],
            )
        )
        story.append(Spacer(1, 4))
        story.append(
            _data_table_grouped_first_col(
                ["Category", "Subcategory", "Count"],
                patients_summary_rows,
                col_widths=[6.0 * cm, 6.0 * cm, 5.6 * cm],
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

    has_month_matrix = bool(division_month_headers and division_month_rows)
    if abbreviation_table_rows or has_month_matrix:
        story.append(NextPageTemplate("landscape"))
        story.append(PageBreak())

    if abbreviation_table_rows:
        story.append(Paragraph("Report Format 2: Test Workload by Full Name", styles["Section"]))
        story.append(
            Paragraph(
                "Grouped by laboratory division; each test's analytical test count is "
                "accumulated per parameter, shown under its standardized full name.",
                styles["Small"],
            )
        )
        story.append(Spacer(1, 10))

        division_totals: dict[str, int] = {}
        for division, _full_test_name, count in abbreviation_table_rows:
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

        story.append(Paragraph("Detail by Test", styles["Body"]))
        story.append(Spacer(1, 4))
        story.append(
            _data_table_grouped_first_col(
                ["Division", "Test Full Name", "Analytical Test Count"],
                abbreviation_table_rows,
                col_widths=[6.0 * cm, 8.0 * cm, 6.0 * cm],
            )
        )

    if has_month_matrix:
        story.append(Spacer(1, 16))
        story.append(Paragraph("Division by Month", styles["Section"]))
        story.append(
            Paragraph(
                "Each cell is that division's unique-patient count within that single calendar "
                "month. The Total column is the division's true unique-patient count across the "
                "whole period (not a sum of the month columns). The Total row sums each month "
                "across divisions and can exceed the true overall unique-patient total, since a "
                "patient tested in more than one division that month is counted once per division.",
                styles["Small"],
            )
        )
        story.append(Spacer(1, 10))

        n_cols = len(division_month_headers)
        first_col_width = 4.5 * cm
        other_col_width = (26.0 * cm - first_col_width) / (n_cols - 1)
        col_widths = [first_col_width] + [other_col_width] * (n_cols - 1)
        story.append(_matrix_table(division_month_headers, division_month_rows, col_widths=col_widths))

    header_footer_fn = _make_header_footer(hospital_name, doc_ref, version, logo_path)
    doc.build(
        story,
        canvasmaker=lambda *a, **kw: _NumberedCanvas(*a, header_footer_fn=header_footer_fn, **kw),
    )
    return buffer.getvalue()
