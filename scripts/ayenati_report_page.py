"""Render the Ayenati external-lab statistics as a single self-contained HTML
page - every table on one page, each with copy-to-clipboard (TSV for Excel /
Markdown) so any part can be lifted into an official report.

Called by scripts/ayenati_external_stats.py; not run directly.
"""
from __future__ import annotations

import base64
import datetime
import html
import mimetypes
from pathlib import Path
from typing import Any

import pandas as pd

FONTS = ("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600"
         "&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap")


def _fmt(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.2f}" if abs(v - round(v)) > 1e-9 else f"{int(round(v)):,}"
    return str(v)


def _is_num_col(s: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(s)


def html_table(df: pd.DataFrame, tid: str) -> str:
    num_cols = {c for c in df.columns if _is_num_col(df[c])}
    pct_cols = {c for c in df.columns if "%" in str(c)}
    head = "".join(
        f'<th class="{"num" if c in num_cols else ""}">{html.escape(str(c))}</th>'
        for c in df.columns
    )
    body_rows = []
    for _, row in df.iterrows():
        first = str(row.iloc[0]).strip().upper()
        second = str(row.iloc[1]).strip().upper() if len(row) > 1 else ""
        cls = ' class="total"' if "TOTAL" in (first, second) else ""
        cells = ""
        for c, v in zip(df.columns, row):
            if c in pct_cols and isinstance(v, (int, float)) and not isinstance(v, bool):
                text = f"{float(v):,.2f}"
            else:
                text = _fmt(v)
            cells += f'<td class="{"num" if c in num_cols else ""}">{html.escape(text)}</td>'
        body_rows.append(f"<tr{cls}>{cells}</tr>")
    return (
        f'<div class="tablewrap"><table id="{tid}">'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody>"
        f"</table></div>"
    )


def _bars(pairs: list[tuple[str, float]], unit: str = "") -> str:
    mx = max((v for _, v in pairs), default=1) or 1
    rows = []
    for label, v in pairs:
        pct = v / mx * 100
        rows.append(
            f'<div class="bar"><span class="bar-l">{html.escape(label)}</span>'
            f'<span class="bar-track"><span class="bar-fill" style="width:{pct:.1f}%"></span></span>'
            f'<span class="bar-v">{_fmt(int(v) if float(v).is_integer() else v)}{unit}</span></div>'
        )
    return f'<div class="bars">{"".join(rows)}</div>'


def _section(num: str, sid: str, title: str, use_for: str, table_html: str,
             extra: str = "") -> str:
    return f"""
<section id="{sid}">
  <div class="sec-head">
    <div><span class="eyebrow">{num}</span><h2>{html.escape(title)}</h2>
      <p class="use-for">{use_for}</p></div>
    <div class="copy-group">
      <button class="copy-btn" data-target="{sid}" data-format="tsv">Copy for Excel</button>
      <button class="copy-btn" data-target="{sid}" data-format="md">Copy as Markdown</button>
    </div>
  </div>
  {extra}
  {table_html}
</section>"""


def _logo_data_uri(path: str | None) -> str:
    if not path or not Path(path).is_file():
        return ""
    mime = mimetypes.guess_type(path)[0] or "image/png"
    data = base64.b64encode(Path(path).read_bytes()).decode()
    return f"data:{mime};base64,{data}"


def build_page(ctx: dict) -> str:
    k = ctx["kpis"]
    kpi_defs = [
        ("Tests received", k["Total Tests Received"], "individual analytical tests"),
        ("Samples received", k["Unique Samples Received"], "distinct sample barcodes"),
        ("Patients", k["Unique Patients (MRN)"], "distinct MRN"),
        ("Orders", k["Unique Orders"], "distinct order numbers"),
        ("Test types", k["Different Test Types"], "distinct test names"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="kpi-v">{_fmt(v)}</div>'
        f'<div class="kpi-k">{html.escape(lbl)}</div>'
        f'<div class="kpi-sub">{html.escape(sub)}</div></div>'
        for lbl, v, sub in kpi_defs
    )

    f = ctx["funnel"]  # list of (label, count, css-class)
    ftotal = sum(c for _, c, _ in f) or 1
    funnel_seg = "".join(
        f'<span class="fn-seg fn-{cls}" style="width:{c / ftotal * 100:.2f}%" '
        f'title="{html.escape(lbl)}: {c:,}"></span>'
        for lbl, c, cls in f
    )
    funnel_legend = "".join(
        f'<span class="fn-key"><span class="fn-dot fn-{cls}"></span>'
        f'{html.escape(lbl)} &nbsp;<b>{c:,}</b></span>'
        for lbl, c, cls in f
    )

    tw = ctx["tw_out"]
    top_n = tw[tw["Test Name"] != "TOTAL"].head(15)
    top_bars = _bars(list(zip(top_n["Test Name"], top_n["Test Count"])))

    daily = ctx["daily"]
    daily_extra = ""
    if len(daily):
        db = daily[daily["Date"].astype(str).str.upper() != "TOTAL"]
        daily_extra = _bars(list(zip(db["Date"].astype(str), db["Total Tests"])))
        ds = ctx["day_stats"]
        daily_extra += ('<ul class="stat-list">' + "".join(
            f"<li><span>{html.escape(str(kk))}</span><b>{html.escape(_fmt(vv))}</b></li>"
            for kk, vv in ds.items()) + "</ul>")

    sections = []
    sections.append(_section(
        "01", "test-wise", "Test-Wise Statistics",
        "The core workload table &mdash; test counts, share of total, and the samples / patients behind each test.",
        html_table(tw, "test-wise"),
        extra=f'<div class="chart"><h3>Top 15 by volume</h3>{top_bars}</div>',
    ))
    if len(ctx["status_tab"]):
        v = ctx.get("verified", 0)
        vnote = (f'<p class="use-for">Verified (L1 + L2) = {v:,} of '
                 f'{k["Total Tests Received"]:,} received '
                 f'({v / k["Total Tests Received"] * 100:.1f}%).</p>') if v else ""
        sections.append(_section(
            "02", "status", "Test Status",
            "Where each test stands in the LIS pipeline &mdash; ordered, resulted, verified L1 / L2.",
            html_table(ctx["status_tab"], "status"), extra=vnote))
    if len(daily):
        sections.append(_section(
            "03", "daily", "Daily Workload",
            "Tests, samples, patients and orders per calendar day (by order date/time).",
            html_table(daily, "daily"), extra=daily_extra))
    if len(ctx["phc_stats"]):
        note = f'<p class="use-for">{html.escape(ctx["phc_note"])}</p>' if ctx.get("phc_note") else ""
        sections.append(_section(
            "04", "phc", "PHC / Source Analysis",
            "Workload by originating primary-health-care centre.",
            html_table(ctx["phc_stats"], "phc"), extra=note))
    notes_html = "<ol class='notes'>" + "".join(
        f"<li>{html.escape(x)}</li>" for x in ctx["notes"]) + "</ol>"
    sections.append(_section(
        "05", "quality", "Data Quality &amp; Filter Audit",
        "Every row accounted for &mdash; raw count, exclusions, duplicates, blanks.",
        html_table(ctx["dq_df"], "quality"),
        extra=f'<div class="chart"><h3>Notes &amp; limitations</h3>{notes_html}</div>'))

    nav = "".join(
        f'<a href="#{sid}">{lbl}</a>' for sid, lbl in [
            ("test-wise", "Test-wise"), ("status", "Status"), ("daily", "Daily"),
            ("phc", "PHC"), ("quality", "Data quality")]
        if sid in "".join(sections))

    logo_uri = _logo_data_uri(ctx.get("logo_path"))
    logo_img = f'<img class="crest" src="{logo_uri}" alt="">' if logo_uri else ""
    doc_ref = f"EXT-LAB-STAT-{datetime.date.today():%Y%m%d}"
    generated = datetime.date.today().strftime("%d %b %Y")

    body = f"""<div class="page">
  <div class="letterhead">
    {logo_img}
    <div class="lh-org">
      <p class="lh-name">{html.escape(ctx['hospital'])}</p>
      <p class="lh-dept">Laboratory &amp; Blood Bank Department</p>
    </div>
    <div class="lh-meta">
      <span>Doc ref &nbsp;<b>{doc_ref}</b></span>
      <span>Generated &nbsp;<b>{generated}</b></span>
      <span>Version &nbsp;<b>1.0</b></span>
    </div>
  </div>
  <p class="confidential">Confidential &mdash; for hospital administration and health-authority
    review. Aggregated laboratory workload only; contains no patient-identifiable data.</p>

  <header>
    <p class="eyebrow">External / Ayenati laboratory workload</p>
    <h1>Ayenati Test-Wise Statistics</h1>
    <p class="lede">{html.escape(ctx['period'])}
      &nbsp;&middot;&nbsp; source export <code>{html.escape(ctx['source_name'])}</code></p>
    <p class="filters">Filters: <code>Is external lab order = Yes</code> &nbsp;<b>and</b>&nbsp;
      specimen received by the laboratory. Counting unit: one <b>test</b> per record,
      grouped by cleaned <code>Test description</code>. Tests, samples, patients and orders
      are separate measurements.</p>
  </header>

  <div class="kpis">{kpi_html}</div>

  <div class="funnel">
    <div class="fn-bar">{funnel_seg}</div>
    <div class="fn-legend">{funnel_legend}</div>
  </div>

  <nav class="toc">{nav}</nav>

  {''.join(sections)}

  <section id="approval" class="approval">
    <div class="sec-head"><div><span class="eyebrow">Sign-off</span>
      <h2>Approval</h2>
      <p class="use-for">For the signed record, use the PDF edition of this report.</p></div></div>
    <div class="sign-grid">
      <div class="sign"><span>Prepared by</span><div class="sign-line"></div><small>Name / title / date</small></div>
      <div class="sign"><span>Reviewed by</span><div class="sign-line"></div><small>Laboratory manager / date</small></div>
      <div class="sign"><span>Approved by</span><div class="sign-line"></div><small>Medical director / date</small></div>
    </div>
  </section>

  <footer>
    <p>Generated by <code>scripts/ayenati_external_stats.py</code> from a de-identified export.
      Aggregate counts only &mdash; no patient identifiers. Validation: &Sigma;&nbsp;test&nbsp;count
      = {k['Total Tests Received']:,} = total received; percentages sum to {ctx['pct_sum']:.2f}%.</p>
  </footer>
</div>
<div id="toast" role="status" aria-live="polite"></div>
<script>{JS}</script>
"""
    return _document("Ayenati Test-Wise Statistics", CSS, body)


def _document(title: str, css: str, body: str, extra_head: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{FONTS}">
{extra_head}
<style>{css}</style>
</head>
<body>
{body}
</body>
</html>
"""


def build_index(reports_root: Path, hospital: str, logo_path: str | None = None) -> str:
    """Landing page for GitHub Pages: lists every published report folder with
    links to its live HTML view and its downloadable PDF / Markdown."""
    logo_uri = _logo_data_uri(logo_path)
    logo_img = f'<img class="crest" src="{logo_uri}" alt="">' if logo_uri else ""
    generated = datetime.date.today().strftime("%d %b %Y")

    rows = []
    folders = sorted((p for p in reports_root.iterdir() if p.is_dir()), reverse=True)
    for folder in folders:
        def find(ext):
            m = next(folder.glob(f"*{ext}"), None)
            return f"{folder.name}/{m.name}".replace(" ", "%20") if m else None
        html_rel, pdf_rel, md_rel = find(".html"), find(".pdf"), find(".md")
        links = []
        if html_rel:
            links.append(f'<a class="btn primary" href="{html_rel}">View report</a>')
        if pdf_rel:
            links.append(f'<a class="btn" href="{pdf_rel}">PDF</a>')
        if md_rel:
            links.append(f'<a class="btn" href="{md_rel}">Markdown</a>')
        rows.append(
            f'<li><div class="rep-name">{html.escape(folder.name)}</div>'
            f'<div class="rep-links">{"".join(links)}</div></li>'
        )
    listing = "\n".join(rows) or "<li><em>No reports published yet.</em></li>"

    css = CSS + r"""
.rep-list{list-style:none;padding:0;margin:1.5rem 0 0;display:flex;flex-direction:column;gap:.7rem}
.rep-list li{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
  padding:1rem 1.2rem;display:flex;justify-content:space-between;align-items:center;
  gap:1rem;flex-wrap:wrap;box-shadow:var(--shadow)}
.rep-name{font-weight:600;font-family:"IBM Plex Mono",monospace;font-size:.9rem}
.rep-links{display:flex;gap:.5rem;flex-wrap:wrap}
.btn{font-family:"IBM Plex Mono",monospace;font-size:.76rem;font-weight:500;text-decoration:none;
  border:1px solid var(--line-strong);color:var(--ink);padding:.42rem .8rem;border-radius:6px}
.btn:hover{background:var(--accent-soft);border-color:var(--accent);color:var(--accent-ink)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary:hover{background:var(--accent-ink);color:#fff}
"""
    body = f"""<div class="page">
  <div class="letterhead">
    {logo_img}
    <div class="lh-org">
      <p class="lh-name">{html.escape(hospital)}</p>
      <p class="lh-dept">Laboratory &amp; Blood Bank Department</p>
    </div>
    <div class="lh-meta"><span>Updated &nbsp;<b>{generated}</b></span></div>
  </div>
  <p class="confidential">Confidential &mdash; aggregated laboratory workload only; contains no
    patient-identifiable data. For hospital administration and health-authority review.</p>
  <header>
    <p class="eyebrow">External / Ayenati laboratory workload</p>
    <h1>Ayenati Laboratory Reports</h1>
    <p class="lede">Test-wise statistics for laboratory tests referred from primary health-care
      centres and received by the hospital laboratory. Each entry links a full interactive report
      and a signable PDF.</p>
  </header>
  <ul class="rep-list">
    {listing}
  </ul>
  <footer><p>Generated by <code>scripts/ayenati_external_stats.py</code>.
    Published via GitHub Pages from <code>reports/</code>.</p></footer>
</div>
"""
    return _document("Ayenati Laboratory Reports", css, body,
                     extra_head='<meta name="robots" content="noindex">')


CSS = r"""
:root{
  --paper:#f5f7f9; --surface:#ffffff; --ink:#141d26; --muted:#5a6675;
  --line:#e3e8ed; --line-strong:#cfd6de;
  --accent:#0d6d88; --accent-ink:#0a5568; --accent-soft:#e4eff2;
  --good:#2f7d4f; --warn:#a86a12; --crit:#b23a1e; --hold:#8a94a0;
  --shadow:0 1px 2px rgba(20,29,38,.06),0 8px 24px -12px rgba(20,29,38,.14);
  --radius:10px;
}
:root:not([data-theme="light"]){ @media (prefers-color-scheme:dark){
  --paper:#0d141b; --surface:#141f29; --ink:#e8edf2; --muted:#9aa7b4;
  --line:#233140; --line-strong:#32424f;
  --accent:#3fb6d3; --accent-ink:#7fd0e4; --accent-soft:#16323c;
  --good:#5cc88a; --warn:#e0b062; --crit:#eb8163; --hold:#7c8794;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px -14px rgba(0,0,0,.6);
}}
:root[data-theme="dark"]{
  --paper:#0d141b; --surface:#141f29; --ink:#e8edf2; --muted:#9aa7b4;
  --line:#233140; --line-strong:#32424f;
  --accent:#3fb6d3; --accent-ink:#7fd0e4; --accent-soft:#16323c;
  --good:#5cc88a; --warn:#e0b062; --crit:#eb8163; --hold:#7c8794;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px -14px rgba(0,0,0,.6);
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:"IBM Plex Sans",system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
  line-height:1.55;-webkit-font-smoothing:antialiased}
.page{max-width:1080px;margin:0 auto;padding:clamp(1.5rem,4vw,3.5rem) clamp(1rem,3vw,2rem) 4rem}
code{font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  font-size:.88em;background:var(--accent-soft);color:var(--accent-ink);
  padding:.08em .38em;border-radius:4px}
.eyebrow{font-family:"IBM Plex Mono",monospace;text-transform:uppercase;
  letter-spacing:.14em;font-size:.7rem;font-weight:600;color:var(--accent-ink);margin:0 0 .5rem}
.letterhead{display:flex;align-items:center;gap:1rem;padding-bottom:1rem;
  border-bottom:2px solid var(--accent)}
.crest{height:52px;width:auto;flex-shrink:0}
.lh-org{flex:1;min-width:0}
.lh-name{font-weight:700;font-size:1.05rem;margin:0;letter-spacing:-.01em}
.lh-dept{margin:.1rem 0 0;font-size:.82rem;color:var(--muted)}
.lh-meta{display:flex;flex-direction:column;gap:.15rem;text-align:right;
  font-family:"IBM Plex Mono",monospace;font-size:.68rem;color:var(--muted);
  text-transform:uppercase;letter-spacing:.06em}
.lh-meta b{color:var(--ink);font-weight:600}
.confidential{font-size:.72rem;color:var(--muted);margin:.7rem 0 1.8rem;
  padding:.5rem .7rem;background:var(--paper);border-left:3px solid var(--warn);border-radius:0 4px 4px 0}
header{border-bottom:1px solid var(--line);padding-bottom:1.8rem;margin-bottom:2rem}
h1{font-size:clamp(1.8rem,4.5vw,2.7rem);font-weight:700;letter-spacing:-.02em;
  margin:.1rem 0 .6rem;text-wrap:balance}
.lede{font-size:1.02rem;color:var(--ink);margin:.2rem 0 .8rem}
.filters{font-size:.9rem;color:var(--muted);margin:0;max-width:65ch}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;
  background:var(--line);border:1px solid var(--line);border-radius:var(--radius);
  overflow:hidden;margin-bottom:1.5rem}
.kpi{background:var(--surface);padding:1.1rem 1.15rem}
.kpi-v{font-family:"IBM Plex Mono",monospace;font-size:1.7rem;font-weight:600;
  letter-spacing:-.02em;font-variant-numeric:tabular-nums;color:var(--accent-ink)}
.kpi-k{font-weight:600;font-size:.92rem;margin-top:.15rem}
.kpi-sub{font-size:.78rem;color:var(--muted)}
.funnel{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
  padding:1.1rem 1.2rem;margin-bottom:2.5rem;box-shadow:var(--shadow)}
.fn-bar{display:flex;height:22px;border-radius:5px;overflow:hidden;background:var(--line)}
.fn-seg{display:block;height:100%}
.fn-received{background:var(--accent)} .fn-pending{background:var(--hold)}
.fn-reception{background:var(--warn)} .fn-rejected{background:var(--crit)}
.fn-legend{display:flex;flex-wrap:wrap;gap:.4rem 1.3rem;margin-top:.7rem;font-size:.82rem;color:var(--muted)}
.fn-key{display:inline-flex;align-items:center;gap:.4rem}
.fn-key b{color:var(--ink);font-variant-numeric:tabular-nums}
.fn-dot{width:10px;height:10px;border-radius:3px;display:inline-block}
.toc{position:sticky;top:0;z-index:5;display:flex;flex-wrap:wrap;gap:.3rem;
  background:color-mix(in srgb,var(--paper) 88%,transparent);backdrop-filter:blur(8px);
  padding:.6rem 0;margin-bottom:1rem;border-bottom:1px solid var(--line)}
.toc a{font-family:"IBM Plex Mono",monospace;font-size:.76rem;text-decoration:none;
  color:var(--muted);padding:.3rem .6rem;border-radius:6px;text-transform:uppercase;letter-spacing:.06em}
.toc a:hover{background:var(--accent-soft);color:var(--accent-ink)}
section{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
  padding:1.5rem clamp(1rem,2.5vw,1.7rem);margin-bottom:1.5rem;box-shadow:var(--shadow)}
.sec-head{display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;
  flex-wrap:wrap;margin-bottom:1.1rem}
.sec-head h2{font-size:1.3rem;font-weight:700;letter-spacing:-.01em;margin:.15rem 0 .3rem}
.use-for{font-size:.88rem;color:var(--muted);margin:0;max-width:60ch}
.copy-group{display:flex;gap:.4rem;flex-shrink:0}
.copy-btn{font-family:"IBM Plex Mono",monospace;font-size:.74rem;font-weight:500;
  cursor:pointer;border:1px solid var(--line-strong);background:var(--surface);
  color:var(--ink);padding:.4rem .7rem;border-radius:6px;transition:background .12s,border-color .12s}
.copy-btn:hover{background:var(--accent-soft);border-color:var(--accent);color:var(--accent-ink)}
.copy-btn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:8px}
table{border-collapse:collapse;width:100%;font-size:.86rem}
thead th{background:var(--accent-soft);color:var(--accent-ink);font-weight:600;
  text-align:left;padding:.55rem .8rem;white-space:nowrap;position:sticky;top:0}
td{padding:.5rem .8rem;border-top:1px solid var(--line)}
th.num,td.num{text-align:right;font-family:"IBM Plex Mono",monospace;
  font-variant-numeric:tabular-nums;white-space:nowrap}
tbody tr:hover{background:var(--accent-soft)}
tr.total td{font-weight:700;border-top:2px solid var(--line-strong);background:var(--paper)}
.chart{margin-bottom:1.2rem}
.chart h3,.stat-list+*{margin:0 0 .7rem}
.chart h3{font-size:.8rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);font-weight:600}
.bars{display:flex;flex-direction:column;gap:.3rem}
.bar{display:grid;grid-template-columns:minmax(90px,26%) 1fr auto;align-items:center;gap:.7rem;font-size:.8rem}
.bar-l{color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar-track{background:var(--line);border-radius:4px;height:12px;overflow:hidden}
.bar-fill{display:block;height:100%;background:var(--accent);border-radius:4px}
.bar-v{font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums;color:var(--muted)}
.stat-list{list-style:none;padding:0;margin:1rem 0 0;display:grid;
  grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:.5rem}
.stat-list li{display:flex;justify-content:space-between;gap:1rem;background:var(--paper);
  border:1px solid var(--line);border-radius:7px;padding:.5rem .75rem;font-size:.82rem}
.stat-list b{font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}
.notes{margin:0;padding-left:1.2rem;font-size:.86rem;color:var(--muted);display:flex;flex-direction:column;gap:.35rem}
.approval .sign-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1.4rem;margin-top:.5rem}
.sign span{font-size:.78rem;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.sign-line{height:2.2rem;border-bottom:1.5px solid var(--line-strong);margin:.4rem 0 .35rem}
.sign small{font-size:.72rem;color:var(--muted)}
footer{margin-top:2.5rem;padding-top:1.4rem;border-top:1px solid var(--line);
  font-size:.82rem;color:var(--muted);max-width:70ch}
#toast{position:fixed;left:50%;bottom:2rem;transform:translateX(-50%) translateY(12px);
  background:var(--ink);color:var(--paper);padding:.6rem 1.1rem;border-radius:8px;
  font-size:.85rem;font-weight:500;opacity:0;pointer-events:none;transition:opacity .2s,transform .2s;z-index:20}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
@media print{.toc,.copy-group,#toast{display:none}section{box-shadow:none;break-inside:avoid}
  body{background:#fff}}
"""

JS = r"""
(function(){
  function cellText(el){return el.innerText.replace(/ /g,' ').trim();}
  function grid(table){
    var out=[];
    table.querySelectorAll('tr').forEach(function(tr){
      var cells=tr.querySelectorAll('th,td');
      if(!cells.length)return;
      out.push(Array.prototype.map.call(cells,cellText));
    });
    return out;
  }
  function toTSV(g){return g.map(function(r){return r.join('\t');}).join('\n');}
  function toMD(g){
    if(!g.length)return '';
    var head='| '+g[0].join(' | ')+' |';
    var sep='|'+g[0].map(function(){return '---';}).join('|')+'|';
    var body=g.slice(1).map(function(r){return '| '+r.join(' | ')+' |';}).join('\n');
    return [head,sep,body].join('\n');
  }
  var toast=document.getElementById('toast'),t;
  function flash(msg){
    toast.textContent=msg;toast.classList.add('show');
    clearTimeout(t);t=setTimeout(function(){toast.classList.remove('show');},1800);
  }
  document.querySelectorAll('.copy-btn').forEach(function(btn){
    btn.addEventListener('click',function(){
      var sec=document.getElementById(btn.dataset.target);
      var table=sec&&sec.querySelector('table');
      if(!table)return;
      var g=grid(table);
      var text=btn.dataset.format==='md'?toMD(g):toTSV(g);
      var done=function(){flash(btn.dataset.format==='md'?'Markdown table copied':'Copied — paste into Excel');};
      if(navigator.clipboard&&navigator.clipboard.writeText){
        navigator.clipboard.writeText(text).then(done,function(){fallback(text,done);});
      }else{fallback(text,done);}
    });
  });
  function fallback(text,done){
    var ta=document.createElement('textarea');ta.value=text;
    ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);
    ta.select();try{document.execCommand('copy');done();}catch(e){flash('Copy failed');}
    document.body.removeChild(ta);
  }
})();
"""
