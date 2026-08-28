# Medical Laboratory Statistics and Official Reporting System

A local Python/Streamlit application that turns a hospital lab's HIS activity
export and Laboratory Test Master List into aggregated, official-grade
statistics: patients, patient visits, samples, requests, packages, and
analytical tests, calculated as **separate, clearly labeled measurements** -
never combined into a single ambiguous total.

Reports never display individual patient names or identifiers - only
counts, percentages, and aggregated workload figures.

## Setup

```
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Running the app

```
streamlit run app.py
```

Upload your Laboratory Test Master List and Laboratory Activity File
(both `.xlsx`), or check "Use local sample files in data/raw/" if you've
placed files there for local testing (see **Data privacy** below).

## Ayenati / External-lab daily report (GitHub Actions)

Separate from the Streamlit app: a test-wise statistics report for the
**"External LAB AYANATI"** LIS export (PHC-referred workload). One raw export
becomes an Excel workbook + Markdown report, published as a GitHub Actions
artifact and committed under `reports/`.

**Local, per day:**

```
# raw export stays in data/raw/ (git-ignored, contains PHI)
python scripts/run_daily.py "data/raw/External LAB AYANATI 16-27-aug-2026.xlsx"
```

`run_daily.py` de-identifies (`scripts/deidentify_ayenati.py` - MRN/ID
pseudonymised, patient names replaced, staff name stripped), runs the PHI
guard (`scripts/check_no_phi.py`), and builds the report into `reports/<stem>/`.
Then:

```
git add "data/incoming/<stem>.xlsx" "reports/<stem>"/*.md
git commit -m "Ayenati export <dates>"
git push
```

The push triggers `.github/workflows/ayenati-report.yml`, which re-runs the
PHI guard (**fails the run if any file in `data/incoming/` still contains
patient data**), rebuilds the workbook + Markdown, uploads them as the
`ayenati-reports-<run>` artifact (30-day retention), and commits the Markdown
back to `reports/`. Only de-identified data ever reaches GitHub.

Report internals: `scripts/ayenati_external_stats.py` - auto-detects the
header row, filters to `Is external lab order = Yes` + received specimens,
counts tests test-wise by cleaned `Test description`, and emits Dashboard /
Test Wise / Test Status / Daily / PHC / Test-by-PHC / Data Quality / Clean
Data sheets.

## Running tests

```
pytest tests/
```

Tests use synthetic fixtures only - never real patient data.

## Data privacy

Real HIS activity exports contain patient-identifiable information (MRNs,
national ID numbers, names). `data/raw/` and all `.xlsx`/`.csv` files are
git-ignored by default - keep your real source files local and never commit
them. Only synthetic fixtures under `data/sample_synthetic/` (if any) are
tracked in git.

## How counting works (methodology)

The engine treats five measurements as distinct and never sums them together:

| Measurement | Definition used |
|---|---|
| Unique Patients | Distinct Medical Record Number (falls back to Id Number when MRN is blank) |
| Patient Visits | One visit per distinct (patient, calendar day) - a configurable fallback used because this HIS export has no Encounter/Visit Number |
| Samples Received | One sample per distinct Order No - a configurable fallback used because this HIS export has no Specimen/Accession Number (documented as a lower-bound limitation) |
| Laboratory Requests | One request per distinct Order No |
| Analytical Tests | 1 per individual test line; for a package, the component count from the Test Master List. Duplicate component lines appearing in the same order as their parent package are absorbed into the package's count to avoid double counting. |

Every report exposes these rules in a "Methodology" section so results are
reproducible and auditable, per the source specification.

## Project layout

```
labstats/
  loaders/          Master list & HIS activity file loaders (tolerant header detection)
  mapping/          Test-name matching engine, patient-type/location classification
  stats/            Core counting engine, analytical-unit computation, aggregation helpers
  reports/          Report builders (division summary, full test name, abbreviation,
                     patient reception, executive summary, data quality)
  export/           Excel workbook export
app.py              Streamlit UI (upload, filters, dashboard, export)
tests/              Pytest suite using synthetic fixtures
data/raw/           Local-only real source files (git-ignored)
```

## Current scope vs. full specification

This is the MVP slice of a much larger specification (37 sections covering
19 report formats, manual mapping-review workflows, multi-user audit trails,
PDF export with signatures, etc.). Implemented so far:

- Master list + HIS activity file loaders with tolerant header detection
- Test-name mapping engine (exact/normalized/abbreviation/full-name tiers,
  manual alias override, unmatched-tests report)
- Patient-type/location classification (Inpatient/Outpatient/ED/PHC/ICU/Day
  Care/Other/Unknown)
- Core counting engine with documented, configurable fallback rules
- Data Quality report
- Division Summary, Full Test-Name, Abbreviation, and Patient Reception
  reports
- Executive Summary indicators with methodology notes
- Excel export (multi-sheet workbook)
- Interactive Streamlit dashboard with filters and charts

Not yet built: PDF export with signature/stamp fields, annual/comparison
reports (month-to-month, year-to-year), package/component consistency report
(Format 7), location-detail report (Format 6), manual mapping-review UI,
multi-user login and audit trail persistence.
