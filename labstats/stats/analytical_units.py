"""Compute the analytical-test workload contributed by each activity row.

Per spec section 15 and the lab's own counting policy: a package is never
counted as one lump test - it is exploded into its individual component
parameters, and each parameter accumulates its own count. For example, a TFT
package (T3, T4, TSH) ordered once contributes T3: 1, T4: 1, TSH: 1 to the
workload - not "TFT: 3". The package's own order line is kept (with zero
analytical-test units) so request/package-line counts are unaffected; the
units live on the exploded component rows instead.

If the same order also contains a separate line item for a test that is
already a component of a package ordered in that same order, that duplicate
individual line is absorbed (zeroed out) instead of counted twice.

Implementation note: the absorption and explosion logic below works on plain
Python dicts/lists rather than pandas .iterrows()/.at[] - at hospital-scale
data (tens of thousands of activity rows) per-cell pandas access is the
dominant cost, so converting to records once up front and rebuilding a
DataFrame at the end is an order of magnitude faster for the same result.
"""
from collections import defaultdict

import pandas as pd

from labstats.mapping.test_mapping import build_lookups
from labstats.textnorm import normalize

ROW_KIND_INDIVIDUAL = "individual"
ROW_KIND_PACKAGE = "package"
ROW_KIND_PACKAGE_COMPONENT = "package_component"
ROW_KIND_UNMATCHED = "unmatched"


def _resolve_component(raw_name: str, lookups: dict, master_records: dict) -> dict:
    norm = normalize(raw_name)
    for tier in ("by_norm", "by_abbreviation_norm", "by_fullname_norm"):
        idx = lookups[tier].get(norm)
        if idx is not None:
            row = master_records[idx]
            return {
                "standard_report_name": row["his_test_name"],
                "full_test_name": row["full_test_name"] or row["his_test_name"],
                "abbreviation": row["abbreviation"],
                "division": row["division"] or "",
                "master_row_number": row["row_number"],
                "matched": True,
            }
    return {
        "standard_report_name": raw_name,
        "full_test_name": raw_name,
        "abbreviation": "",
        "division": "",
        "master_row_number": None,
        "matched": False,
    }


def compute_analytical_units(mapped: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    out = mapped.copy()
    out["analytical_test_units"] = 1
    out["absorbed_by_package"] = False
    out["package_component_note"] = ""
    out["row_kind"] = out["is_package"].map({True: ROW_KIND_PACKAGE, False: ROW_KIND_INDIVIDUAL})
    out["row_kind"] = out["row_kind"].fillna(ROW_KIND_UNMATCHED)
    out.loc[out["is_package"] == True, "analytical_test_units"] = 0  # noqa: E712

    lookups = build_lookups(master)
    master_records = master.set_index(master.index).to_dict("index")
    components_by_row_number: dict = {}
    if "row_number" in master.columns:
        for row in master_records.values():
            components_by_row_number[row["row_number"]] = row["components"]

    records = out.to_dict("records")
    normalized_names = [normalize(r["standard_report_name"]) for r in records]

    order_groups: dict = defaultdict(list)
    for i, r in enumerate(records):
        order_groups[r["order_no"]].append(i)

    package_indices = [i for i, r in enumerate(records) if r["is_package"] is True]

    # Absorb duplicate individual lines within the same order that are already
    # covered by a package ordered in that same order.
    for pkg_idx in package_indices:
        pkg_record = records[pkg_idx]
        components = components_by_row_number.get(pkg_record.get("master_row_number"))
        if not components:
            continue
        components_norm = {normalize(c) for c in components}
        if not components_norm:
            continue
        for other_idx in order_groups[pkg_record["order_no"]]:
            if other_idx == pkg_idx or records[other_idx]["absorbed_by_package"]:
                continue
            if normalized_names[other_idx] and normalized_names[other_idx] in components_norm:
                records[other_idx]["analytical_test_units"] = 0
                records[other_idx]["absorbed_by_package"] = True
                records[other_idx]["package_component_note"] = (
                    f"Absorbed into package '{pkg_record['standard_report_name']}' "
                    f"(order {pkg_record['order_no']}) to avoid double counting."
                )

    # Explode each package row into one row per component parameter, each worth
    # exactly 1 analytical test, attributed under the component's own standardized
    # identity where the master list recognizes it as its own test.
    exclude_cols = {
        "standard_report_name", "full_test_name", "abbreviation", "division", "is_package",
        "master_row_number", "matched", "match_method", "row_kind", "analytical_test_units",
        "absorbed_by_package", "package_component_note",
    }
    shared_cols = [c for c in out.columns if c not in exclude_cols]

    component_records = []
    for pkg_idx in package_indices:
        pkg_record = records[pkg_idx]
        components = components_by_row_number.get(pkg_record.get("master_row_number"))
        if not components:
            declared = pkg_record.get("declared_component_count") or pkg_record.get("actual_component_count") or 0
            components = [f"{pkg_record['standard_report_name']} (component {i + 1})" for i in range(int(declared))]

        for component_name in components:
            resolved = _resolve_component(component_name, lookups, master_records)
            if not resolved["division"]:
                resolved["division"] = pkg_record["division"]  # fall back to the parent package's division
            new_record = {col: pkg_record[col] for col in shared_cols}
            new_record.update(resolved)
            new_record["is_package"] = False
            new_record["match_method"] = "package_component"
            new_record["row_kind"] = ROW_KIND_PACKAGE_COMPONENT
            new_record["analytical_test_units"] = 1
            new_record["absorbed_by_package"] = False
            new_record["package_component_note"] = (
                f"Component of package '{pkg_record['standard_report_name']}' (order {pkg_record['order_no']})."
            )
            component_records.append(new_record)

    all_records = records + component_records
    return pd.DataFrame.from_records(all_records)
