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
"""
import pandas as pd

from labstats.mapping.test_mapping import build_lookups
from labstats.textnorm import normalize

ROW_KIND_INDIVIDUAL = "individual"
ROW_KIND_PACKAGE = "package"
ROW_KIND_PACKAGE_COMPONENT = "package_component"
ROW_KIND_UNMATCHED = "unmatched"


def _resolve_component(raw_name: str, lookups: dict, master: pd.DataFrame) -> dict:
    norm = normalize(raw_name)
    for tier in ("by_norm", "by_abbreviation_norm", "by_fullname_norm"):
        idx = lookups[tier].get(norm)
        if idx is not None:
            row = master.loc[idx]
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

    out["row_kind"] = out["is_package"].map(
        {True: ROW_KIND_PACKAGE, False: ROW_KIND_INDIVIDUAL}
    )
    out["row_kind"] = out["row_kind"].fillna(ROW_KIND_UNMATCHED)

    is_pkg = out["is_package"] == True  # noqa: E712 (explicit True excludes None/NaN)
    out.loc[is_pkg, "analytical_test_units"] = 0  # units move to the exploded component rows below

    master_by_row_number = master.set_index("row_number") if "row_number" in master.columns else master
    lookups = build_lookups(master)

    # Absorb duplicate individual lines within the same order that are already
    # covered by a package ordered in that same order.
    for order_no, group in out.groupby("order_no", dropna=False):
        package_rows = group[group["is_package"] == True]  # noqa: E712
        if package_rows.empty:
            continue
        for pkg_idx, pkg_row in package_rows.iterrows():
            master_row_num = pkg_row.get("master_row_number")
            if master_row_num is None or master_row_num not in master_by_row_number.index:
                continue
            components_norm = {normalize(c) for c in master_by_row_number.loc[master_row_num, "components"]}
            if not components_norm:
                continue
            for other_idx, other_row in group.iterrows():
                if other_idx == pkg_idx or out.at[other_idx, "absorbed_by_package"]:
                    continue
                candidate_norm = normalize(other_row["standard_report_name"])
                if candidate_norm and candidate_norm in components_norm:
                    out.at[other_idx, "analytical_test_units"] = 0
                    out.at[other_idx, "absorbed_by_package"] = True
                    out.at[other_idx, "package_component_note"] = (
                        f"Absorbed into package '{pkg_row['standard_report_name']}' "
                        f"(order {order_no}) to avoid double counting."
                    )

    # Explode each package row into one row per component parameter, each worth
    # exactly 1 analytical test, attributed under the component's own standardized
    # identity where the master list recognizes it as its own test.
    component_rows = []
    shared_cols = [c for c in out.columns if c not in ("standard_report_name", "full_test_name", "abbreviation", "division", "is_package", "master_row_number", "matched", "match_method", "row_kind", "analytical_test_units", "absorbed_by_package", "package_component_note")]

    for pkg_idx in out.index[is_pkg]:
        pkg_row = out.loc[pkg_idx]
        master_row_num = pkg_row.get("master_row_number")
        components = []
        if master_row_num is not None and master_row_num in master_by_row_number.index:
            components = master_by_row_number.loc[master_row_num, "components"]
        if not components:
            declared = pkg_row.get("declared_component_count") or pkg_row.get("actual_component_count") or 0
            components = [f"{pkg_row['standard_report_name']} (component {i + 1})" for i in range(int(declared))]

        for component_name in components:
            resolved = _resolve_component(component_name, lookups, master)
            if not resolved["division"]:
                resolved["division"] = pkg_row["division"]  # fall back to the parent package's division
            new_row = {col: pkg_row[col] for col in shared_cols}
            new_row.update(resolved)
            new_row["is_package"] = False
            new_row["match_method"] = "package_component"
            new_row["row_kind"] = ROW_KIND_PACKAGE_COMPONENT
            new_row["analytical_test_units"] = 1
            new_row["absorbed_by_package"] = False
            new_row["package_component_note"] = (
                f"Component of package '{pkg_row['standard_report_name']}' (order {pkg_row['order_no']})."
            )
            component_rows.append(new_row)

    if component_rows:
        out = pd.concat([out, pd.DataFrame(component_rows)], ignore_index=True, sort=False)
    else:
        out = out.reset_index(drop=True)

    return out
