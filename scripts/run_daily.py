"""One command to turn a raw Ayenati export into a committable data file.

    python scripts/run_daily.py "data/raw/External LAB AYANATI <dates>.xlsx"
    python scripts/run_daily.py "https://.../External LAB AYANATI <dates>.xlsx"

A URL is downloaded to data/raw/ first (see fetch_export.py for supported
link shapes). Steps: fetch -> de-identify -> PHI guard -> build a local
PREVIEW of every report format under preview/<stem>/ (git-ignored). You
commit only the de-identified data file; GitHub Actions rebuilds the reports,
commits them to reports/, publishes GitHub Pages, and cuts a Release.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_export import resolve_input  # noqa: E402

HERE = Path(__file__).resolve().parent
PY = sys.executable


def run(*args: str) -> None:
    print(f"\n$ {' '.join(args)}")
    subprocess.run(args, check=True)


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    try:
        raw = resolve_input(sys.argv[1])
    except (FileNotFoundError, ValueError, OSError) as exc:
        sys.exit(str(exc))

    stem = raw.stem
    incoming = Path("data/incoming") / f"{stem}.xlsx"
    preview_dir = Path("preview") / stem

    run(PY, str(HERE / "deidentify_ayenati.py"), str(raw), str(incoming))
    run(PY, str(HERE / "check_no_phi.py"), str(incoming))
    run(PY, str(HERE / "ayenati_external_stats.py"), str(incoming), str(preview_dir))

    print("\n" + "=" * 60)
    print("Local preview (git-ignored) ready in:", preview_dir)
    print("Open the .html / .pdf to review, then publish the DATA file only:\n")
    print(f'  git add "{incoming}"')
    print(f'  git commit -m "Ayenati export {stem}"')
    print("  git push")
    print("\nGitHub Actions then rebuilds reports/, updates the Pages site")
    print("(https://ahabalshehri.github.io/laboratory-statistics/), and cuts a Release.")


if __name__ == "__main__":
    main()
