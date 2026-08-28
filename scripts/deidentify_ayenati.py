"""De-identify a raw "External LAB AYANATI" LIS export before it is committed.

Removes patient-identifiable data while keeping every field the statistics
report needs:

    Mrn          -> stable pseudonym  MRN0001, MRN0002, ...   (unique-patient counts preserved)
    Id number    -> stable pseudonym  ID0001, ID0002, ...
    Patient name -> "Patient MRN0001" (follows the MRN pseudonym)
    "Generated on ... by: <emp no> - <staff name>"  -> staff identity stripped

Sample barcode, dates, test descriptions, statuses, Phcc, order numbers,
clinic names and hospital names are left untouched - they are needed for the
report and are not directly patient-identifying.

Usage:
    python scripts/deidentify_ayenati.py <raw_export.xlsx> [output.xlsx]

Default output: data/incoming/<input-stem>.xlsx  (the folder the GitHub
Actions report workflow watches). Only this de-identified file is ever
committed; keep the raw export in data/raw/ (git-ignored).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ayenati_external_stats import detect_header_row  # noqa: E402
from fetch_export import resolve_input  # noqa: E402

GENERATED_BY_RE = re.compile(r"^(.*generated on[:]?.*?)(?:\s*by[:].*)?$", re.IGNORECASE)


def _sequential_map(values, prefix: str, width: int = 4) -> dict:
    mapping: dict = {}
    counter = 0
    for v in values:
        key = "" if pd.isna(v) else str(v).strip()
        if key and key not in mapping:
            counter += 1
            mapping[key] = f"{prefix}{counter:0{width}d}"
    return mapping


def deidentify(input_path: str, output_path: str) -> None:
    header_row = detect_header_row(input_path)
    raw = pd.read_excel(input_path, header=None, dtype=object)
    header = [str(v).strip() if pd.notna(v) else "" for v in raw.iloc[header_row].tolist()]
    pos = {name.lower(): i for i, name in enumerate(header) if name}
    body = header_row + 1
    out = raw.copy()

    def col(name: str):
        return pos.get(name.lower())

    mrn_c, id_c, name_c = col("mrn"), col("id number"), col("patient name")

    mrn_map: dict = {}
    if mrn_c is not None:
        mrn_vals = raw.iloc[body:, mrn_c].tolist()
        mrn_map = _sequential_map(mrn_vals, "MRN")
        out.iloc[body:, mrn_c] = [mrn_map.get(str(v).strip() if pd.notna(v) else "", "") for v in mrn_vals]
        if name_c is not None:
            out.iloc[body:, name_c] = [
                f"Patient {mrn_map[str(v).strip()]}" if pd.notna(v) and str(v).strip() in mrn_map
                else "Patient Unknown"
                for v in mrn_vals
            ]

    if id_c is not None:
        id_vals = raw.iloc[body:, id_c].tolist()
        id_map = _sequential_map(id_vals, "ID")
        out.iloc[body:, id_c] = [id_map.get(str(v).strip() if pd.notna(v) else "", "") for v in id_vals]

    # Strip the staff identity from the "Generated on ... by: <emp> - <name>" preamble line.
    for r in range(header_row):
        for c in range(out.shape[1]):
            v = out.iat[r, c]
            if pd.notna(v) and isinstance(v, str) and "generated on" in v.lower():
                m = GENERATED_BY_RE.match(v.strip())
                out.iat[r, c] = (m.group(1).rstrip() if m else "Generated on: (de-identified)")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    out.to_excel(output_path, header=False, index=False, engine="openpyxl")
    print(f"Wrote de-identified file: {output_path}")
    print(f"Unique patients pseudonymised (MRN): {len(mrn_map)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    inp = str(resolve_input(sys.argv[1]))
    if len(sys.argv) >= 3:
        outp = sys.argv[2]
    else:
        outp = str(Path("data/incoming") / f"{Path(inp).stem}.xlsx")
    deidentify(inp, outp)
