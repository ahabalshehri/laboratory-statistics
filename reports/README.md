# reports/

One folder per processed export, each containing the generated report in
several formats. Regenerated on every push that touches `data/incoming/`.

| Format | Committed here | In the workflow artifact | Best for |
|---|:---:|:---:|---|
| `… .pdf`  | ✅ | ✅ | **Sharing with administration / health authority** (letterhead, signable) |
| `… .md`   | ✅ | ✅ | Reading on GitHub |
| `… .html` | ✅ | ✅ | One page, all tables, copy-to-Excel buttons |
| `… .xlsx` | ❌ (too large) | ✅ | Analysts who need the raw sheets |

## Where these are published

- **GitHub Pages:** <https://ahabalshehri.github.io/laboratory-statistics/>
  — a landing page (`index.html`, regenerated each run) linking every report's
  live HTML view and its PDF. The PDF is served with the right type, so the
  link downloads/opens it directly.
- **GitHub Releases:** one per export, tag `report-<stem>`, all four files
  attached — <https://github.com/ahabalshehri/laboratory-statistics/releases>.

## How to download a report

### The PDF (recommended for sharing)

It is committed to this folder, so it has a **direct download link**. On the
file's page on GitHub, click **⋯ → Download**, or use the raw URL:

```
https://github.com/ahabalshehri/laboratory-statistics/raw/master/reports/<FOLDER>/<FILE>.pdf
```

Replace `<FOLDER>`/`<FILE>` with the report you want (spaces become `%20` in a
URL). Anyone you send that link to can download it without a GitHub account
**if the repository is public**; for a private repo they must be a collaborator.

### The Excel workbook (`.xlsx`)

Not committed (it is ~1.5 MB). Get it from the workflow run:

1. Repo → **Actions** → **Ayenati daily report** → open the latest green run.
2. Scroll to **Artifacts** → click **`ayenati-reports-<n>`** to download a zip.
3. The zip contains all four formats.

### Locally

```
python scripts/run_daily.py "data/raw/External LAB AYANATI <dates>.xlsx"
```

writes every format into `reports/<stem>/` on your machine.

## Latest report

See [INDEX.md](INDEX.md) &mdash; it is regenerated on every run and links the
committed formats of every processed export, newest marked `(latest)`.
