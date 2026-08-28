"""Fail if an Excel file that is about to be committed / processed still
contains patient-identifiable data.

Run on every file under data/incoming/ by the GitHub Actions report workflow
(and usable as a local pre-commit check). Exit code 0 = clean, 1 = PHI found.

Usage:
    python scripts/check_no_phi.py data/incoming/*.xlsx
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ayenati_external_stats import detect_header_row  # noqa: E402

NATIONAL_ID_RE = re.compile(r"^\s*\d{7,11}\s*$")          # bare long numeric id
MRN_TOKEN_RE = re.compile(r"^\s*MRN\d+\s*$", re.IGNORECASE)
ID_TOKEN_RE = re.compile(r"^\s*ID\d+\s*$", re.IGNORECASE)
NAME_TOKEN_RE = re.compile(r"^\s*Patient (MRN\d+|Unknown)\s*$", re.IGNORECASE)
STAFF_PREAMBLE_RE = re.compile(r"by[:]\s*\d+\s*-\s*\S", re.IGNORECASE)


def check_file(path: str) -> list[str]:
    problems: list[str] = []
    header_row = detect_header_row(path)
    raw = pd.read_excel(path, header=None, dtype=str)
    header = [str(v).strip() if pd.notna(v) else "" for v in raw.iloc[header_row].tolist()]
    pos = {n.lower(): i for i, n in enumerate(header) if n}
    body = raw.iloc[header_row + 1:]

    def nonblank(col_idx: int):
        s = body.iloc[:, col_idx].dropna().astype(str).str.strip()
        return s[s != ""]

    if "patient name" in pos:
        bad = nonblank(pos["patient name"])
        offenders = bad[~bad.str.match(NAME_TOKEN_RE)]
        if len(offenders):
            problems.append(f"'Patient name' has {len(offenders)} real name(s), e.g. {offenders.iloc[0]!r}")

    if "id number" in pos:
        bad = nonblank(pos["id number"])
        offenders = bad[~bad.str.match(ID_TOKEN_RE)]
        real_ids = offenders[offenders.str.match(NATIONAL_ID_RE)]
        if len(real_ids):
            problems.append(f"'Id number' has {len(real_ids)} raw national-ID value(s)")
        elif len(offenders):
            problems.append(f"'Id number' has {len(offenders)} value(s) that are not ID#### tokens")

    if "mrn" in pos:
        bad = nonblank(pos["mrn"])
        offenders = bad[~bad.str.match(MRN_TOKEN_RE)]
        if len(offenders):
            problems.append(f"'Mrn' has {len(offenders)} value(s) that are not MRN#### tokens, e.g. {offenders.iloc[0]!r}")

    for r in range(header_row):
        for v in raw.iloc[r].tolist():
            if pd.notna(v) and STAFF_PREAMBLE_RE.search(str(v)):
                problems.append(f"Preamble still names a staff member: {str(v)[:80]!r}")

    return problems


def main() -> None:
    paths: list[str] = []
    for arg in sys.argv[1:]:
        paths.extend(str(p) for p in Path().glob(arg)) if any(c in arg for c in "*?[") else paths.append(arg)
    paths = [p for p in paths if Path(p).is_file()]
    if not paths:
        print("No files to check.")
        return

    failed = False
    for p in paths:
        probs = check_file(p)
        if probs:
            failed = True
            print(f"FAIL  {p}")
            for x in probs:
                print(f"      - {x}")
        else:
            print(f"OK    {p}")

    if failed:
        print("\nPHI detected. De-identify with scripts/deidentify_ayenati.py before committing.")
        sys.exit(1)


if __name__ == "__main__":
    main()
