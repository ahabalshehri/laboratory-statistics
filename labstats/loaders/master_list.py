"""Loader for the Laboratory Test Master List reference file.

The master list is the source of truth for standardized test names,
abbreviations, laboratory divisions, and package/component definitions.
The HIS activity file's raw test descriptions are matched against this
table; this file's values are never inferred from activity data.
"""
from dataclasses import dataclass, field

import pandas as pd

from labstats.textnorm import clean_display, normalize

# Known HIS spelling corrections for laboratory division names.
DIVISION_CORRECTIONS = {
    "hematolgy": "Hematology",
    "haematology": "Hematology",
    "hormones": "Hormone",
    "biochemstry": "Biochemistry",
    "microbiolgy": "Microbiology",
    "serologey": "Serology",
}

REQUIRED_HEADERS = ["Test description", "Package", "Section", "Abbreviation", "Test name"]


@dataclass
class MasterListResult:
    tests: pd.DataFrame
    duplicate_his_names: pd.DataFrame
    package_component_mismatches: pd.DataFrame
    duplicate_abbreviations: pd.DataFrame
    load_warnings: list = field(default_factory=list)


def _find_header_row(raw: pd.DataFrame, max_scan_rows: int = 10) -> int:
    for row_idx in range(min(max_scan_rows, len(raw))):
        row_values = {clean_display(v) for v in raw.iloc[row_idx].tolist()}
        if "Test description" in row_values and "Section" in row_values:
            return row_idx
    raise ValueError(
        "Could not find a header row containing 'Test description' and 'Section' "
        "in the first rows of the master list file."
    )


def _standardize_division(raw_division: str) -> str:
    display = clean_display(raw_division)
    if not display:
        return ""
    key = normalize(display)
    return DIVISION_CORRECTIONS.get(key, display)


def load_master_list(path: str) -> MasterListResult:
    raw = pd.read_excel(path, header=None, dtype=object, engine="calamine")
    header_row = _find_header_row(raw)

    header_cells = [clean_display(v) for v in raw.iloc[header_row].tolist()]
    col_index = {name: i for i, name in enumerate(header_cells) if name}

    missing = [h for h in REQUIRED_HEADERS if h not in col_index]
    if missing:
        raise ValueError(f"Master list is missing required column(s): {missing}")

    num_components_col = col_index.get("Number of test per package")
    # Any column to the right of the last known header is a package-component slot.
    known_positions = list(col_index.values())
    last_known = max(known_positions)
    component_start = last_known + 1

    data = raw.iloc[header_row + 1 :].reset_index(drop=True)

    records = []
    warnings = []
    for i, row in data.iterrows():
        his_name = clean_display(row.get(col_index["Test description"]))
        if not his_name:
            continue  # blank spacer row

        package_flag_raw = clean_display(row.get(col_index["Package"]))
        is_package = package_flag_raw.strip().lower() == "yes"

        division_raw = clean_display(row.get(col_index["Section"]))
        division = _standardize_division(division_raw)

        abbreviation = clean_display(row.get(col_index["Abbreviation"]))
        full_test_name = clean_display(row.get(col_index["Test name"]))

        declared_count = None
        if num_components_col is not None:
            val = row.get(num_components_col)
            if pd.notna(val):
                try:
                    declared_count = int(val)
                except (ValueError, TypeError):
                    warnings.append(
                        f"Row {header_row + 2 + i}: non-numeric 'Number of test per package' value {val!r}"
                    )

        components = []
        for col in range(component_start, raw.shape[1]):
            val = clean_display(row.get(col))
            if val:
                components.append(val)

        records.append(
            {
                "row_number": header_row + 2 + i,  # 1-based spreadsheet row for traceability
                "his_test_name": his_name,
                "his_test_name_norm": normalize(his_name),
                "is_package": is_package,
                "package_flag_raw": package_flag_raw,
                "division": division,
                "division_raw": division_raw,
                "abbreviation": abbreviation,
                "full_test_name": full_test_name,
                "declared_component_count": declared_count,
                "components": components,
                "actual_component_count": len(components),
                "active": True,
            }
        )

    tests = pd.DataFrame.from_records(records)

    duplicate_mask = tests["his_test_name_norm"].duplicated(keep=False)
    duplicate_his_names = tests.loc[duplicate_mask].sort_values("his_test_name_norm")

    mismatch_mask = (
        tests["is_package"]
        & tests["declared_component_count"].notna()
        & (tests["declared_component_count"] != tests["actual_component_count"])
    )
    package_component_mismatches = tests.loc[mismatch_mask]

    # Flag one abbreviation assigned to more than one genuinely different test
    # name - per spec, tests must never be silently combined just because they
    # share an abbreviation; this needs a human to confirm it's intentional
    # (e.g. a screening/confirmatory pair) or a master-list data-entry error.
    with_abbrev = tests[tests["abbreviation"] != ""]
    ambiguous_abbrevs = (
        with_abbrev.groupby("abbreviation")["his_test_name"]
        .nunique()
        .loc[lambda s: s > 1]
        .index
    )
    duplicate_abbreviations = with_abbrev[with_abbrev["abbreviation"].isin(ambiguous_abbrevs)].sort_values(
        "abbreviation"
    )

    return MasterListResult(
        tests=tests,
        duplicate_his_names=duplicate_his_names,
        package_component_mismatches=package_component_mismatches,
        duplicate_abbreviations=duplicate_abbreviations,
        load_warnings=warnings,
    )
