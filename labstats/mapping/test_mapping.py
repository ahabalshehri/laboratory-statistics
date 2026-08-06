"""Match HIS test descriptions to the standardized Laboratory Test Master List.

Matching is tiered and deliberately conservative: an automated tier only
fires when the key is unambiguous in the master list. Tests that cannot be
matched are never guessed at or silently merged with a similarly named test -
they are reported in the Unmatched Tests Report for manual review, per the
"do not automatically combine clinically different tests" requirement.
"""
import difflib
from dataclasses import dataclass, field

import pandas as pd

from labstats.textnorm import normalize

MATCH_MANUAL_ALIAS = "manual_alias"
MATCH_EXACT_HIS_NAME = "exact_his_name"
MATCH_NORMALIZED_NAME = "normalized_name"
MATCH_ABBREVIATION = "abbreviation"
MATCH_FULL_NAME = "full_name"
MATCH_NONE = "unmatched"


@dataclass
class TestMappingResult:
    mapped: pd.DataFrame
    unmatched_report: pd.DataFrame
    match_method_counts: dict = field(default_factory=dict)


def _unique_lookup(master: pd.DataFrame, key_col: str) -> dict:
    non_empty = master[master[key_col] != ""]
    counts = non_empty[key_col].value_counts()
    unique_keys = set(counts[counts == 1].index)
    return {row[key_col]: idx for idx, row in non_empty.iterrows() if row[key_col] in unique_keys}


def build_lookups(master: pd.DataFrame) -> dict:
    m = master.copy()
    m["abbreviation_norm"] = m["abbreviation"].map(normalize)
    m["full_test_name_norm"] = m["full_test_name"].map(normalize)
    return {
        "by_raw_exact": _unique_lookup(m, "his_test_name"),
        "by_norm": _unique_lookup(m, "his_test_name_norm"),
        "by_abbreviation_norm": _unique_lookup(m, "abbreviation_norm"),
        "by_fullname_norm": _unique_lookup(m, "full_test_name_norm"),
    }


def _suggest_match(norm_value: str, master: pd.DataFrame) -> str | None:
    if not norm_value:
        return None
    candidates = {
        row["his_test_name_norm"]: row["his_test_name"]
        for _, row in master.iterrows()
        if row["his_test_name_norm"]
    }
    close = difflib.get_close_matches(norm_value, list(candidates.keys()), n=1, cutoff=0.72)
    if close:
        return candidates[close[0]]
    return None


def map_activity_tests(
    activity: pd.DataFrame,
    master: pd.DataFrame,
    manual_aliases: dict | None = None,
) -> TestMappingResult:
    manual_aliases = manual_aliases or {}
    lookups = build_lookups(master)
    master_by_index = master

    cache: dict = {}

    def resolve(raw_value: str):
        if raw_value in cache:
            return cache[raw_value]

        norm_value = normalize(raw_value)
        method = MATCH_NONE
        master_idx = None

        if raw_value in manual_aliases:
            alias_target = manual_aliases[raw_value]
            matches = master_by_index.index[master_by_index["his_test_name"] == alias_target]
            if len(matches):
                master_idx = matches[0]
                method = MATCH_MANUAL_ALIAS
        if master_idx is None and raw_value in lookups["by_raw_exact"]:
            master_idx = lookups["by_raw_exact"][raw_value]
            method = MATCH_EXACT_HIS_NAME
        if master_idx is None and norm_value in lookups["by_norm"]:
            master_idx = lookups["by_norm"][norm_value]
            method = MATCH_NORMALIZED_NAME
        if master_idx is None and norm_value in lookups["by_abbreviation_norm"]:
            master_idx = lookups["by_abbreviation_norm"][norm_value]
            method = MATCH_ABBREVIATION
        if master_idx is None and norm_value in lookups["by_fullname_norm"]:
            master_idx = lookups["by_fullname_norm"][norm_value]
            method = MATCH_FULL_NAME

        result = (master_idx, method)
        cache[raw_value] = result
        return result

    out = activity.copy()
    match_methods = []
    standard_report_names = []
    full_test_names = []
    abbreviations = []
    divisions = []
    is_packages = []
    master_row_numbers = []
    declared_component_counts = []
    actual_component_counts = []

    for raw_value in out["test_description"].fillna(""):
        master_idx, method = resolve(raw_value)
        match_methods.append(method)
        if master_idx is not None:
            row = master_by_index.loc[master_idx]
            standard_report_names.append(row["his_test_name"])
            full_test_names.append(row["full_test_name"] or row["his_test_name"])
            abbreviations.append(row["abbreviation"])
            divisions.append(row["division"])
            is_packages.append(row["is_package"])
            master_row_numbers.append(row["row_number"])
            declared_component_counts.append(row["declared_component_count"])
            actual_component_counts.append(row["actual_component_count"])
        else:
            standard_report_names.append(raw_value)
            full_test_names.append(raw_value)
            abbreviations.append("")
            divisions.append("")
            is_packages.append(None)
            master_row_numbers.append(None)
            declared_component_counts.append(None)
            actual_component_counts.append(None)

    out["match_method"] = match_methods
    out["matched"] = out["match_method"] != MATCH_NONE
    out["standard_report_name"] = standard_report_names
    out["full_test_name"] = full_test_names
    out["abbreviation"] = abbreviations
    out["division"] = divisions
    out["is_package"] = is_packages
    out["master_row_number"] = master_row_numbers
    out["declared_component_count"] = declared_component_counts
    out["actual_component_count"] = actual_component_counts

    unmatched = out.loc[~out["matched"]]
    group_keys = ["test_description"] + (["test_id"] if "test_id" in out.columns else [])
    if len(unmatched):
        grouped = (
            unmatched.groupby(group_keys, dropna=False)
            .size()
            .reset_index(name="occurrences")
            .sort_values("occurrences", ascending=False)
        )
        grouped["suggested_match"] = grouped["test_description"].map(
            lambda v: _suggest_match(normalize(v), master)
        )
    else:
        grouped = pd.DataFrame(columns=group_keys + ["occurrences", "suggested_match"])

    return TestMappingResult(
        mapped=out,
        unmatched_report=grouped,
        match_method_counts=out["match_method"].value_counts().to_dict(),
    )
