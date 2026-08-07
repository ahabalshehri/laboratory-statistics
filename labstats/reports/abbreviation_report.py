"""Report Format 3: Compact Abbreviation Report (spec section 22).

One row per abbreviation - every test that shares an abbreviation (e.g. a
screening and confirmatory assay both labeled "HBsAg" in the HIS) is counted
together under that abbreviation, shown with its full test name so it is
never displayed without a legend. When the same abbreviation covers more
than one genuinely different test, the master list's Data Quality report
still flags that ambiguity separately - merging counts here for the compact
view doesn't hide it from review.
"""
import pandas as pd

from labstats.stats.aggregate import aggregate_by

NO_ABBREVIATION_LABEL = "(no abbreviation on file)"


def build_abbreviation_report(with_units: pd.DataFrame) -> pd.DataFrame:
    df = with_units.copy()
    df = df[df["row_kind"] != "package"]
    df["division"] = df["division"].replace("", "Unclassified / Missing Division")

    has_abbrev = df["abbreviation"] != ""
    with_abbrev = df[has_abbrev].copy()
    without_abbrev = df[~has_abbrev].copy()

    parts = []

    if len(with_abbrev):
        totals = aggregate_by(with_abbrev, ["abbreviation"])
        # Represent each abbreviation by whichever underlying full test name/division
        # contributed the most analytical tests, since a single abbreviation can
        # legitimately cover more than one master-list entry.
        per_identity = (
            with_abbrev.groupby(["abbreviation", "full_test_name", "division"])["analytical_test_units"]
            .sum()
            .reset_index()
        )
        representative = per_identity.loc[per_identity.groupby("abbreviation")["analytical_test_units"].idxmax()]
        merged = totals.merge(representative[["abbreviation", "full_test_name", "division"]], on="abbreviation")
        parts.append(merged)

    if len(without_abbrev):
        without_abbrev["abbreviation"] = NO_ABBREVIATION_LABEL
        unmerged = aggregate_by(without_abbrev, ["abbreviation", "full_test_name", "division"])
        parts.append(unmerged)

    if not parts:
        return pd.DataFrame(
            columns=["abbreviation", "full_test_name", "division", "patient_count", "request_count", "analytical_test_count"]
        )

    table = pd.concat(parts, ignore_index=True, sort=False)
    table = table.rename(
        columns={
            "unique_patients": "patient_count",
            "requests": "request_count",
            "analytical_tests": "analytical_test_count",
        }
    )
    table = table[["abbreviation", "full_test_name", "division", "patient_count", "request_count", "analytical_test_count"]]
    table = table.sort_values(["division", "analytical_test_count"], ascending=[True, False]).reset_index(drop=True)
    return table
