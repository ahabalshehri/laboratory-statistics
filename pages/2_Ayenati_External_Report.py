"""Upload an "External / Ayenati" LIS export and generate the test-wise report.

Runs locally (`streamlit run app.py`, then pick this page in the sidebar - or
`streamlit run pages/2_Ayenati_External_Report.py`). The uploaded file never
leaves your machine; it is de-identified before anything is analysed or shown.
"""
import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from ayenati_external_stats import generate  # noqa: E402
from check_no_phi import check_file  # noqa: E402
from deidentify_ayenati import deidentify  # noqa: E402
from fetch_export import resolve_input  # noqa: E402
from labstats.appauth import is_hosted, require_password  # noqa: E402

st.set_page_config(page_title="Ayenati External Lab Report", layout="wide")
require_password()
HOSTED = is_hosted()

st.title("External / Ayenati Laboratory Report")
st.caption(
    "Upload the raw LIS export (or paste a link). It is de-identified first - "
    "MRNs pseudonymised, patient names and IDs removed - then the test-wise "
    "statistics report is generated in every format."
)
if HOSTED:
    st.warning(
        "Shared deployment: files are de-identified **on the server** before "
        "analysis, and the raw upload is discarded. Prefer uploading a file "
        "that is already de-identified.",
        icon="🔒",
    )

tab_file, tab_url = st.tabs(["Upload a file", "From a link"])
src_path = None
with tab_file:
    up = st.file_uploader("External / Ayenati export (.xlsx)", type=["xlsx"])
    if up is not None:
        tmp = Path(tempfile.mkdtemp()) / up.name
        tmp.write_bytes(up.getbuffer())
        src_path = tmp
with tab_url:
    url = st.text_input("Direct download link to the .xlsx")
    if url and st.button("Fetch"):
        try:
            src_path = resolve_input(url, Path(tempfile.mkdtemp()))
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not fetch: {exc}")

deidentify_first = True
if not HOSTED:
    deidentify_first = st.checkbox("De-identify before analysing (recommended)", value=True)

if src_path is None:
    st.info("Upload a file or fetch a link to begin.")
    st.stop()

work = Path(tempfile.mkdtemp())
try:
    analysed = src_path
    if deidentify_first:
        analysed = work / f"{src_path.stem}.deid.xlsx"
        deidentify(str(src_path), str(analysed))
        problems = check_file(str(analysed))
        if problems:
            st.error("De-identification left patient data - not analysing:\n\n" +
                     "\n".join(f"- {p}" for p in problems))
            st.stop()
        st.success("De-identified and checked - no patient-identifiable data remains.")

    with st.spinner("Analysing and building the report..."):
        res = generate(str(analysed), work / "report", quiet=True)
except ValueError as exc:
    st.error(f"Could not read this file as an Ayenati export: {exc}")
    st.stop()

k = res["kpis"]
c = st.columns(5)
c[0].metric("Tests received", f"{k['Total Tests Received']:,}")
c[1].metric("Samples", f"{k['Unique Samples Received']:,}")
c[2].metric("Patients", f"{k['Unique Patients (MRN)']:,}")
c[3].metric("Orders", f"{k['Unique Orders']:,}")
c[4].metric("Test types", k["Different Test Types"])
st.caption(f"{res['hospital']}  ·  {res['period'] or 'all dates'}")

st.subheader("Download the report")
d = st.columns(4)
labels = [("pdf", "Official PDF", "application/pdf"),
          ("xlsx", "Excel workbook",
           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
          ("html", "Interactive HTML", "text/html"),
          ("md", "Markdown", "text/markdown")]
for col, (key, label, mime) in zip(d, labels):
    p = res.get(key)
    if p and Path(p).is_file():
        col.download_button(label, data=Path(p).read_bytes(),
                            file_name=Path(p).name, mime=mime, use_container_width=True)

tw = res["testwise"]
body = tw[tw["Test Name"] != "TOTAL"]
st.subheader("Test-wise statistics")
st.bar_chart(body.head(15).set_index("Test Name")["Test Count"])
st.dataframe(tw, use_container_width=True, hide_index=True)

with st.expander("Test status by test name"):
    st.dataframe(res["status"], use_container_width=True, hide_index=True)
with st.expander("Daily workload"):
    st.dataframe(res["daily"], use_container_width=True, hide_index=True)
with st.expander("PHC / source analysis"):
    st.dataframe(res["phc"], use_container_width=True, hide_index=True)
with st.expander("Data quality & filter audit"):
    st.dataframe(res["data_quality"], use_container_width=True, hide_index=True)
    for n in res["notes"]:
        st.markdown(f"- {n}")

with st.expander("Full interactive report (embedded)"):
    components.html(Path(res["html"]).read_text(encoding="utf-8"), height=900, scrolling=True)
