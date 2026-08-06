"""Loader for the Laboratory Activity File exported from the HIS.

Real HIS exports vary in header wording and sometimes carry a few free-text
metadata lines (hospital name, extraction period, generated-by) above the
actual column header row. This loader is tolerant of both, auto-detects the
header row, maps recognized column headers onto canonical system field
names via an alias table, and preserves every original column untouched
(prefixed raw_) alongside the standardized ones - nothing from the source
file is dropped or overwritten.
"""
import re
from dataclasses import dataclass, field

import pandas as pd

from labstats.textnorm import clean_display, normalize

# canonical_field -> list of header spellings/aliases seen in real HIS exports
FIELD_ALIASES = {
    "mrn": ["mrn", "medical record number", "patient mrn"],
    "id_number": ["id number", "national id", "patient identifier", "identifier number"],
    "id_type": ["id type", "identifier type"],
    "patient_name": ["patient name"],
    "gender": ["gender", "sex"],
    "nationality": ["nationality"],
    "clinic_name": ["clinic name", "requesting facility", "ward", "location", "requesting location"],
    "doctor_id": ["doctorid", "doctor id"],
    "doctor_name": ["doctorname", "doctor name", "ordering physician"],
    "order_datetime": ["order date time", "order date", "order datetime"],
    "order_no": ["order no", "order number", "request number", "request no"],
    "order_type": ["order type", "priority"],
    "lab_order_status": ["lab order status", "test status", "status", "order status"],
    "test_id": ["testid", "test id", "test code"],
    "test_description": ["test description", "test name", "his test name"],
    "is_package_raw": ["ispackage", "is package"],
    "division_raw": ["divisionname", "division name", "division", "laboratory division", "section"],
    "patient_type_raw": ["patient type"],
    "age": ["age"],
    "encounter_type_raw": ["encounter type", "encounter"],
    "specimen_no": ["specimen number", "specimen no", "accession number", "accession no"],
    "collection_datetime": ["collection date time", "collection date"],
    "received_datetime": ["laboratory received date time", "received date time", "received date"],
    "result_datetime": ["result date time", "result date"],
    "verification_datetime": ["verification date time", "verification date"],
    "encounter_no": ["encounter number", "visit number", "encounter no", "visit no"],
}

REQUIRED_CANONICAL_FIELDS = ["test_description", "order_no"]

_ALIAS_LOOKUP = {
    normalize(alias): canonical for canonical, aliases in FIELD_ALIASES.items() for alias in aliases
}


@dataclass
class ActivityLoadResult:
    data: pd.DataFrame
    column_map: dict
    unmapped_columns: list
    metadata: dict
    load_warnings: list = field(default_factory=list)


def _find_header_row(raw: pd.DataFrame, max_scan_rows: int = 15) -> int:
    for row_idx in range(min(max_scan_rows, len(raw))):
        row_norms = {normalize(v) for v in raw.iloc[row_idx].tolist()}
        # A real header row will match several known aliases at once.
        hits = sum(1 for norm in row_norms if norm in _ALIAS_LOOKUP)
        if hits >= 4:
            return row_idx
    raise ValueError(
        "Could not detect a column header row in the activity file. "
        "Expected to find several recognizable columns (e.g. Mrn, Order no, Test description)."
    )


def _parse_metadata(raw: pd.DataFrame, header_row: int, source_filename: str) -> dict:
    lines = []
    for row_idx in range(header_row):
        cells = [clean_display(v) for v in raw.iloc[row_idx].tolist() if clean_display(v)]
        if cells:
            lines.append(" ".join(cells))

    metadata = {
        "source_filename": source_filename,
        "free_text_lines": lines,
        "hospital_name": lines[0] if lines else None,
        "period_start": None,
        "period_end": None,
        "generated_at": None,
        "generated_by": None,
    }

    for line in lines:
        period_match = re.search(r"between\s+([\d\-/]+)\s*-\s*([\d\-/]+)", line, re.IGNORECASE)
        if period_match:
            metadata["period_start"] = period_match.group(1)
            metadata["period_end"] = period_match.group(2)
        gen_match = re.search(r"Generated on:\s*(.+?)\s+by:\s*(.+)$", line, re.IGNORECASE)
        if gen_match:
            metadata["generated_at"] = gen_match.group(1).strip()
            metadata["generated_by"] = gen_match.group(2).strip()

    return metadata


def load_activity_file(path: str, source_filename: str | None = None) -> ActivityLoadResult:
    source_filename = source_filename or path
    raw = pd.read_excel(path, header=None, dtype=object)
    header_row = _find_header_row(raw)
    metadata = _parse_metadata(raw, header_row, source_filename)

    header_cells = [clean_display(v) for v in raw.iloc[header_row].tolist()]
    column_map = {}  # canonical_field -> original header text
    unmapped_columns = []
    position_to_canonical = {}
    for pos, header_text in enumerate(header_cells):
        if not header_text:
            continue
        canonical = _ALIAS_LOOKUP.get(normalize(header_text))
        if canonical:
            column_map[canonical] = header_text
            position_to_canonical[pos] = canonical
        else:
            unmapped_columns.append(header_text)

    warnings = []
    missing_required = [f for f in REQUIRED_CANONICAL_FIELDS if f not in column_map]
    if missing_required:
        raise ValueError(
            f"Activity file is missing required column(s) for: {missing_required}. "
            f"Detected headers: {header_cells}"
        )

    body = raw.iloc[header_row + 1 :].reset_index(drop=True)
    # Drop fully blank rows.
    body = body.dropna(how="all").reset_index(drop=True)

    out = pd.DataFrame(index=body.index)
    for pos, header_text in enumerate(header_cells):
        if pos >= body.shape[1]:
            continue
        raw_col_name = f"raw_{normalize(header_text).replace(' ', '_')}"
        out[raw_col_name] = body[pos].map(clean_display)
        canonical = position_to_canonical.get(pos)
        if canonical:
            out[canonical] = out[raw_col_name]

    for canonical in FIELD_ALIASES:
        if canonical not in out.columns:
            out[canonical] = pd.NA

    if "order_datetime" in column_map:
        out["order_datetime"] = pd.to_datetime(out["order_datetime"], errors="coerce", format="mixed")
        bad_dates = out["order_datetime"].isna().sum()
        if bad_dates:
            warnings.append(f"{bad_dates} row(s) had an unparseable Order date time value.")

    out["source_row_number"] = out.index + header_row + 2  # 1-based spreadsheet row

    return ActivityLoadResult(
        data=out,
        column_map=column_map,
        unmapped_columns=unmapped_columns,
        metadata=metadata,
        load_warnings=warnings,
    )
