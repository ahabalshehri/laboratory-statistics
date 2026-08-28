"""Resolve a report input that may be a local path OR a URL.

    from fetch_export import resolve_input
    path = resolve_input("https://.../export.xlsx")          # downloads it
    path = resolve_input("data/raw/export.xlsx")             # returns as-is

Handles a few common share-link shapes (SharePoint/OneDrive '?download=1',
Google Drive 'uc?export=download'). Refuses anything that comes back as an
HTML page (usually a login wall) instead of a spreadsheet.

Usage as a script:
    python scripts/fetch_export.py "<url>" [dest_dir]
"""
from __future__ import annotations

import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

_UA = "Mozilla/5.0 (labstats fetch_export)"
_XLSX_MAGIC = b"PK\x03\x04"  # xlsx is a zip
_XLS_MAGIC = b"\xd0\xcf\x11\xe0"  # legacy OLE2


def _looks_like_url(s: str) -> bool:
    return bool(re.match(r"^(https?|file)://", s, re.IGNORECASE))


def _normalise_share_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    qs = urllib.parse.parse_qs(parsed.query)

    # Google Drive: .../file/d/<id>/view  ->  uc?export=download&id=<id>
    m = re.search(r"drive\.google\.com/file/d/([^/]+)", url)
    if m:
        return f"https://drive.google.com/uc?export=download&id={m.group(1)}"

    # SharePoint / OneDrive: force the file download rather than the viewer page
    if ("sharepoint.com" in host or "1drv.ms" in host or "onedrive.live.com" in host) \
            and "download" not in qs:
        sep = "&" if parsed.query else "?"
        return f"{url}{sep}download=1"

    return url


def _filename_from(resp, url: str) -> str:
    cd = resp.headers.get("Content-Disposition", "")
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd)
    name = m.group(1) if m else Path(urllib.parse.urlparse(url).path).name
    name = urllib.parse.unquote(name or "").strip() or "downloaded_export.xlsx"
    if not name.lower().endswith((".xlsx", ".xls")):
        name += ".xlsx"
    # keep it filesystem-safe
    return re.sub(r'[<>:"/\\|?*]', "_", name)


def resolve_input(src: str, dest_dir: str | Path = "data/raw") -> Path:
    if not _looks_like_url(src):
        p = Path(src)
        if not p.is_file():
            raise FileNotFoundError(f"Not found: {src}")
        return p

    url = _normalise_share_url(src)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    print(f"Downloading {url}")
    with urllib.request.urlopen(req, timeout=120) as resp:
        ctype = (resp.headers.get("Content-Type") or "").lower()
        data = resp.read()
        dest = dest_dir / _filename_from(resp, url)

    if data[:4] not in (_XLSX_MAGIC, _XLS_MAGIC):
        hint = ""
        if b"<html" in data[:2048].lower() or "html" in ctype:
            hint = (" The server returned a web page, not a file - the link probably "
                    "needs a login or is a viewer page. Download it manually and pass "
                    "the local path instead.")
        raise ValueError(f"Downloaded content is not an Excel file (type={ctype!r}).{hint}")

    dest.write_bytes(data)
    print(f"Saved {len(data):,} bytes -> {dest}")
    return dest


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out = resolve_input(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "data/raw")
    print(out)
