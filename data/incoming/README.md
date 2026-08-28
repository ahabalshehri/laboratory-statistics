# data/incoming/

Drop **de-identified** daily "External LAB AYANATI" exports here, then commit
and push. The `Ayenati daily report` GitHub Actions workflow
(`.github/workflows/ayenati-report.yml`) picks up any `*.xlsx` added or changed
in this folder, runs `scripts/ayenati_external_stats.py`, and:

1. attaches the Excel workbook + Markdown report as a downloadable **workflow
   artifact**, and
2. commits the Markdown report to `reports/<file-stem>/`.

## Before you push — de-identify

Never put a raw export here. Raw exports contain patient names, national ID
numbers and MRNs; keep them in `data/raw/` (git-ignored).

```
# raw export stays local in data/raw/
python scripts/deidentify_ayenati.py "data/raw/External LAB AYANATI <dates>.xlsx"
#  -> writes data/incoming/External LAB AYANATI <dates>.xlsx  (pseudonymised)

python scripts/check_no_phi.py "data/incoming/*.xlsx"   # must print OK

git add "data/incoming/External LAB AYANATI <dates>.xlsx"
git commit -m "Ayenati export <dates>"
git push
```

The CI workflow re-runs `check_no_phi.py` and **fails the run** if any file
here still looks like it contains PHI, so a raw file can never be processed or
stored as an artifact.
