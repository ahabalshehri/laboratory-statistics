"""Tests for the Ayenati external-lab daily report pipeline
(de-identify -> PHI guard -> test-wise statistics), using synthetic data only.
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


stats = _load("ayenati_external_stats")
deident = _load("deidentify_ayenati")
guard = _load("check_no_phi")

HEADER = [
    "Test description", "Sample barcode", "Mrn", "Test status", "Patient name",
    "Id number", "Divisionname", "Phcc", "Source hospital", "Order date time",
    "Last updated date", "Is external lab order", "Order no", "Lab order status",
    "Samplestatus", "Clinic name", "Testid", "Received", "Pending", "Collected",
    "Rejected", "RecievedByReceptionist", "Caccelled", "Ordered", "Resulted",
    "PartiallyVerified", "VerifiedLevel1", "VerifiedLevel2", "Hospital name",
]


def _row(test, barcode, mrn, name, idnum, order, samplestatus, teststatus, date="16-AUG-2026 09:00:00"):
    r = {c: None for c in HEADER}
    r.update({
        "Test description": test, "Sample barcode": barcode, "Mrn": mrn,
        "Test status": teststatus, "Patient name": name, "Id number": idnum,
        "Phcc": "340", "Source hospital": "Test Hospital", "Order date time": date,
        "Last updated date": date, "Is external lab order": "Yes", "Order no": order,
        "Lab order status": "Pending", "Samplestatus": samplestatus,
        "Clinic name": "PHC 340", "Testid": "1", "Hospital name": "Test Hospital",
    })
    return r


def _write_raw(path: Path):
    preamble = [["Test Hospital"] + [None] * 28,
                ["Data retrieved between 2026-08-16 - 2026-08-27"] + [None] * 28,
                ["Generated on: 8/27/2026, 2:54:29 PM by: 7227738 - Jane Staff"] + [None] * 28,
                [None] * 29]
    rows = [
        _row("HBA1C ", "B1", "11337", "MOHAMMED AHMED ASIRI", "1070212673", "O1", "Received", "VerifiedLevel2"),
        _row("hba1c", "B2", "22448", "SARA ALI", "1099887766", "O2", "Received", "VerifiedLevel1"),
        _row("CBC & Auto Differential", "B1", "11337", "MOHAMMED AHMED ASIRI", "1070212673", "O1", "Received", "Ordered"),
        _row("TSH", "B3", "33559", "OMAR SAID", "1055443322", "O3", "Pending", "Ordered"),          # not received
        _row("TSH", "B4", "44660", "LINA NOOR", "1033221100", "O4", "Rejected", "Caccelled"),        # rejected
        _row("Creatinine", "B5", "55771", "KHALID Z", "1011223344", "O5", "RecievedByReceptionist", "Ordered"),  # reception only
    ]
    df = pd.DataFrame(preamble + [HEADER] + [[r[c] for c in HEADER] for r in rows])
    df.to_excel(path, header=False, index=False, engine="openpyxl")


def test_header_detection(tmp_path):
    raw = tmp_path / "raw.xlsx"
    _write_raw(raw)
    assert stats.detect_header_row(str(raw)) == 4


def test_deidentify_then_guard_passes(tmp_path):
    raw = tmp_path / "raw.xlsx"
    _write_raw(raw)
    assert guard.check_file(str(raw)), "guard must flag the raw file"

    out = tmp_path / "incoming" / "raw.xlsx"
    deident.deidentify(str(raw), str(out))
    assert guard.check_file(str(out)) == [], "de-identified file must pass the guard"

    d = pd.read_excel(out, header=4, dtype=str)
    assert d["Patient name"].str.match(r"Patient MRN\d+").all()
    assert d["Mrn"].str.match(r"MRN\d+").all()
    # same real patient keeps one pseudonym -> unique-patient count preserved
    assert d.loc[d["Sample barcode"] == "B1", "Mrn"].nunique() == 1


def test_stats_applies_external_and_received_filters(tmp_path, capsys, monkeypatch):
    raw = tmp_path / "raw.xlsx"
    _write_raw(raw)
    incoming = tmp_path / "incoming" / "raw.xlsx"
    deident.deidentify(str(raw), str(incoming))

    report_dir = tmp_path / "reports"
    monkeypatch.setattr(sys, "argv", ["prog", str(incoming), str(report_dir)])
    stats.main()

    wb = report_dir / "raw - Ayenati Test-Wise Statistics.xlsx"
    assert wb.is_file()

    page = (report_dir / "raw - Ayenati Test-Wise Statistics.html").read_text(encoding="utf-8")
    assert "<title>Ayenati Test-Wise Statistics</title>" in page
    assert 'id="test-wise"' in page and "copy-btn" in page
    assert "HBA1C" in page

    pdf = report_dir / "raw - Ayenati Test-Wise Statistics.pdf"
    assert pdf.is_file() and pdf.read_bytes()[:5] == b"%PDF-"
    assert pdf.stat().st_size > 10_000
    tw = pd.read_excel(wb, sheet_name="Test Wise Statistics", header=1)
    total = tw[tw["Test Name"] == "TOTAL"].iloc[0]
    # received only: 2x HBA1C + 1x CBC = 3 ; TSH(pending/rejected), Creatinine(reception) excluded
    assert total["Test Count"] == 3
    body = tw[tw["Test Name"] != "TOTAL"]
    assert body["Test Count"].sum() == 3
    assert set(body["Test Name"]) == {"HBA1C", "CBC & Auto Differential"}
    # HBA1C written once despite 'HBA1C ' / 'hba1c' spelling variants
    assert (body["Test Name"] == "HBA1C").sum() == 1
    assert body.loc[body["Test Name"] == "HBA1C", "Test Count"].iloc[0] == 2
