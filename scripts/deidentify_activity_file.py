"""Produce a de-identified copy of a real HIS activity export for use on the
public-hosted demo app. Replaces patient/doctor identifiers with consistent
synthetic placeholders while keeping every field needed for statistics intact
(dates, test descriptions, divisions, patient type, order numbers, etc.).

Usage:
    python scripts/deidentify_activity_file.py <input.xlsx> [output.xlsx]

Output defaults to data/generated/<input-stem>_deidentified.xlsx (already
git-ignored, but the point is to hand this specific file to the public app
yourself - it is never committed).
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from labstats.loaders.activity_file import _find_header_row  # noqa: E402
from labstats.textnorm import clean_display  # noqa: E402


def _sequential_map(values, prefix, width=4):
    mapping = {}
    counter = 0
    for v in values:
        if v not in mapping:
            counter += 1
            mapping[v] = f"{prefix}{counter:0{width}d}"
    return mapping


def deidentify(input_path: str, output_path: str):
    raw = pd.read_excel(input_path, header=None, dtype=object)
    header_row = _find_header_row(raw)
    header_cells = [clean_display(v) for v in raw.iloc[header_row].tolist()]
    col_pos = {name.lower(): i for i, name in enumerate(header_cells) if name}

    body_start = header_row + 1
    out = raw.copy()

    def col(name):
        return col_pos.get(name.lower())

    mrn_col, idnum_col, name_col = col("mrn"), col("id number"), col("patient name")
    doctorid_col, doctorname_col = col("doctorid"), col("doctorname")
    nationality_col = col("nationality")

    if mrn_col is not None:
        mrn_values = raw.iloc[body_start:, mrn_col].tolist()
        mrn_map = _sequential_map(mrn_values, "MRN")
        out.iloc[body_start:, mrn_col] = [mrn_map.get(v, v) for v in mrn_values]
        if name_col is not None:
            # Reuse the same numbering so the same (fake) patient keeps one label.
            out.iloc[body_start:, name_col] = [
                f"Patient {mrn_map.get(v, v)}" if v in mrn_map else "Patient Unknown" for v in mrn_values
            ]

    if idnum_col is not None:
        idnum_values = raw.iloc[body_start:, idnum_col].tolist()
        idnum_map = _sequential_map(idnum_values, "ID")
        out.iloc[body_start:, idnum_col] = [idnum_map.get(v, v) for v in idnum_values]

    if doctorid_col is not None:
        doc_values = raw.iloc[body_start:, doctorid_col].tolist()
        doc_map = _sequential_map(doc_values, "DOC")
        out.iloc[body_start:, doctorid_col] = [doc_map.get(v, v) for v in doc_values]
        if doctorname_col is not None:
            out.iloc[body_start:, doctorname_col] = [
                f"Doctor {doc_map.get(v, v)}" if v in doc_map else "Doctor Unknown" for v in doc_values
            ]

    if nationality_col is not None:
        out.iloc[body_start:, nationality_col] = "Not Disclosed"

    # Anonymize the free-text preamble lines above the header row (hospital name,
    # generated-by line) so the hospital and staff member aren't identifiable either.
    for row_idx in range(header_row):
        for c in range(out.shape[1]):
            if pd.notna(out.iat[row_idx, c]):
                text = str(out.iat[row_idx, c])
                if row_idx == 0:
                    out.iat[row_idx, c] = "Sample Hospital (De-identified Demo Data)"
                elif text.lower().startswith("generated on"):
                    out.iat[row_idx, c] = "Generated on: (de-identified demo export)"

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    out.to_excel(output_path, header=False, index=False, engine="openpyxl")
    print(f"Wrote de-identified file to: {output_path}")
    print(f"Unique patients replaced: {len(mrn_map) if mrn_col is not None else 0}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    input_path = sys.argv[1]
    if len(sys.argv) >= 3:
        output_path = sys.argv[2]
    else:
        stem = Path(input_path).stem
        output_path = str(Path("data/generated") / f"{stem}_deidentified.xlsx")
    deidentify(input_path, output_path)
