"""One command to turn a raw Ayenati export into a committable report.

    python scripts/run_daily.py "data/raw/External LAB AYANATI <dates>.xlsx"

Steps: de-identify -> PHI guard -> build workbook + Markdown report locally.
Then it prints the git commands to publish (push triggers the CI workflow,
which rebuilds the same reports and uploads them as an artifact).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable


def run(*args: str) -> None:
    print(f"\n$ {' '.join(args)}")
    subprocess.run(args, check=True)


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    raw = Path(sys.argv[1])
    if not raw.is_file():
        sys.exit(f"Not found: {raw}")

    stem = raw.stem
    incoming = Path("data/incoming") / f"{stem}.xlsx"
    report_dir = Path("reports") / stem

    run(PY, str(HERE / "deidentify_ayenati.py"), str(raw), str(incoming))
    run(PY, str(HERE / "check_no_phi.py"), str(incoming))
    run(PY, str(HERE / "ayenati_external_stats.py"), str(incoming), str(report_dir))

    print("\n" + "=" * 60)
    print("Local report ready in:", report_dir)
    print("Publish it (push triggers the GitHub Actions artifact build):\n")
    print(f'  git add "{incoming}" "{report_dir}"/*.md')
    print(f'  git commit -m "Ayenati export {stem}"')
    print("  git push")


if __name__ == "__main__":
    main()
