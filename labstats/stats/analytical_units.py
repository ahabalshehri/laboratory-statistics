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

Implementation note: the absorption loop needs random per-row read/write
access keyed by order number, which pandas can't do without either slow
.iterrows()/.at[] calls or materializing full-row dicts for every record.
Since packages are typically a small fraction of rows, this only builds
full-row dicts for the package subset (needed to build the exploded
component rows) and does the O(n) absorption pass over lightweight
per-column Python lists instead - full-row dicts for every one of a hospital's
tens of thousands of activity rows was the previous approach, and at that
scale it was memory-hungry enough to hit Streamlit Cloud's free-tier RAM
limit on large files.
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
    n = len(out)
    out["analytical_test_units"] = 1
    out["absorbed_by_package"] = False
    out["package_component_note"] = ""
    out["row_kind"] = out["is_package"].map({True: ROW_KIND_PACKAGE, False: ROW_KIND_INDIVIDUAL})
    out["row_kind"] = out["row_kind"].fillna(ROW_KIND_UNMATCHED)
    is_pkg_mask = out["is_package"] == True  # noqa: E712
    out.loc[is_pkg_mask, "analytical_test_units"] = 0  # units move to the exploded component rows below

    lookups = build_lookups(master)
    master_records = master.to_dict("index")
    components_by_row_number: dict = {}
    if "row_number" in master.columns:
        for row in master_records.values():
            components_by_row_number[row["row_number"]] = row["components"]

    # Lightweight per-column lists for the O(n) absorption pass - avoids
    # materializing a full-row dict for every activity row.
    order_no_list = out["order_no"].tolist()
    master_row_number_list = out["master_row_number"].tolist()
    standard_name_list = out["standard_report_name"].tolist()
    standard_name_norm_list = [normalize(v) for v in standard_name_list]
    units_list = out["analytical_test_units"].tolist()
    absorbed_list = [False] * n
    note_list = [""] * n

    order_groups: dict = defaultdict(list)
    for i, order_no in enumerate(order_no_list):
        order_groups[order_no].append(i)

    package_positions = is_pkg_mask.to_numpy().nonzero()[0].tolist()

    for pkg_pos in package_positions:
        components = components_by_row_number.get(master_row_number_list[pkg_pos])
        if not components:
            continue
        components_norm = {normalize(c) for c in components}
        if not components_norm:
            continue
        pkg_order = order_no_list[pkg_pos]
        pkg_name = standard_name_list[pkg_pos]
        for other_pos in order_groups[pkg_order]:
            if other_pos == pkg_pos or absorbed_list[other_pos]:
                continue
            if standard_name_norm_list[other_pos] and standard_name_norm_list[other_pos] in components_norm:
                units_list[other_pos] = 0
                absorbed_list[other_pos] = True
                note_list[other_pos] = (
                    f"Absorbed into package '{pkg_name}' (order {pkg_order}) to avoid double counting."
                )

    out["analytical_test_units"] = units_list
    out["absorbed_by_package"] = absorbed_list
    out["package_component_note"] = note_list

    # Explode each package row into one row per component parameter. Packages
    # are typically a small fraction of total rows, so building full-row
    # dicts just for this subset is cheap regardless of overall file size.
    exclude_cols = {
        "standard_report_name", "full_test_name", "abbreviation", "division", "is_package",
        "master_row_number", "matched", "match_method", "row_kind", "analytical_test_units",
        "absorbed_by_package", "package_component_note",
    }
    shared_cols = [c for c in out.columns if c not in exclude_cols]

    component_records = []
    if package_positions:
        package_records = out.iloc[package_positions].to_dict("records")
        for pkg_record in package_records:
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

    if component_records:
        return pd.concat([out, pd.DataFrame.from_records(component_records)], ignore_index=True, sort=False)
    return out.reset_index(drop=True)
