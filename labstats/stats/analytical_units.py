"""Compute the analytical-test workload contributed by each activity row.

Per spec section 15: an individual test line = 1 analytical test; a package
line = one analytical test per component test defined for it in the master
list. If the same order also contains separate line items for tests that are
already components of a package ordered in that same order, those lines are
"absorbed" into the package's count instead of being counted twice.
"""
import pandas as pd

from labstats.textnorm import normalize


def compute_analytical_units(mapped: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    out = mapped.copy()
    out["analytical_test_units"] = 1
    out["absorbed_by_package"] = False
    out["package_component_note"] = ""

    is_pkg_true = out["is_package"] == True  # noqa: E712 (explicit True to exclude None/NaN)
    for idx in out.index[is_pkg_true]:
        n = out.at[idx, "actual_component_count"] or 0
        if not n:
            n = out.at[idx, "declared_component_count"] or 1
        out.at[idx, "analytical_test_units"] = int(n)

    if "row_number" in master.columns:
        master_by_row = master.set_index("row_number")
    else:
        master_by_row = master

    for order_no, group in out.groupby("order_no", dropna=False):
        package_rows = group[group["is_package"] == True]  # noqa: E712
        if package_rows.empty:
            continue
        for pkg_idx, pkg_row in package_rows.iterrows():
            master_row_num = pkg_row.get("master_row_number")
            if master_row_num is None or master_row_num not in master_by_row.index:
                continue
            components_norm = {normalize(c) for c in master_by_row.loc[master_row_num, "components"]}
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

    return out
