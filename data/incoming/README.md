# data/incoming/

Drop **de-identified** daily "External LAB AYANATI" exports here, then commit
and push. The `Ayenati daily report` GitHub Actions workflow
(`.github/workflows/ayenati-report.yml`) picks up any `*.xlsx` added or changed
in this folder, runs `scripts/ayenati_external_stats.py`, and:

1. attaches the Excel workbook + Markdown + single-page HTML + official PDF
   report as a downloadable **workflow artifact**, and
2. commits the Markdown, HTML and PDF reports to `reports/<file-stem>/`
   (see [reports/README.md](../../reports/README.md) for how to download).

## Before you push — de-identify

Never put a raw export here. Raw exports contain patient names, national ID
numbers and MRNs; keep them in `data/raw/` (git-ignored).

```
# one command - accepts a local path OR a download link
python scripts/run_daily.py "data/raw/External LAB AYANATI <dates>.xlsx"
python scripts/run_daily.py "https://.../External LAB AYANATI <dates>.xlsx"

# it de-identifies -> data/incoming/<stem>.xlsx, runs the PHI guard, and
# builds a git-ignored preview/. Then:
git add "data/incoming/External LAB AYANATI <dates>.xlsx"
git commit -m "Ayenati export <dates>"
git push
```

(Or run the steps by hand: `deidentify_ayenati.py` also takes a path or a URL,
then `check_no_phi.py "data/incoming/*.xlsx"` must print `OK`.)

The CI workflow re-runs `check_no_phi.py` and **fails the run** if any file
here still looks like it contains PHI, so a raw file can never be processed or
stored as an artifact.
