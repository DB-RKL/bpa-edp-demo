"""Generate synthetic buy-in logs (3 monthly .xlsx) and a mailbox intake log (.log), stdlib only.

Models a typical buy-in log: trustee notification/receipt dates, movement volumes, SLA target and a calculated
lateness column, entered by hand from emails, with a few invalid cells (the kind that break a Fabric load).
"""
import datetime as dt, io, os, random, sys, zipfile
from xml.sax.saxutils import escape
sys.path.insert(0, os.path.expanduser("~/bpa-edp-demo/scripts"))
import run_sql as R

OUT = os.path.expanduser("~/bpa-edp-demo/buyin"); os.makedirs(OUT, exist_ok=True)
tok = R.token()
d = R.run("SELECT name FROM bpa_onelake_corp_fabric.dbo.dv_account ORDER BY name", tok)
schemes = [r[0] for r in d["result"]["data_array"]]
EPOCH = dt.date(1899, 12, 30)
serial = lambda x: (x - EPOCH).days
HEAD = ["log_id", "scheme", "trustee_contact", "notification_date", "received_date", "movement_volume", "sla_days", "days_late", "source", "entered_by", "notes"]
TRUSTEES = ["A. Hughes", "B. Okafor", "C. Lindqvist", "D. Patel", "E. Marsh", "F. Rowe"]
STAFF = ["ops.analyst1", "ops.analyst2", "ops.analyst3"]


def col(n): return "ABCDEFGHIJK"[n]

def cell(ref, v, style=0):
    if v is None: return ""
    if isinstance(v, tuple) and v[0] == "err": return f'<c r="{ref}" t="e"><v>{v[1]}</v></c>'
    if isinstance(v, tuple) and v[0] == "f": return f'<c r="{ref}" s="{style}"><f>{escape(v[1])}</f><v>{v[2]}</v></c>' if not isinstance(v[2], str) else f'<c r="{ref}" t="e"><f>{escape(v[1])}</f><v>{v[2]}</v></c>'
    if isinstance(v, str): return f'<c r="{ref}" t="inlineStr" s="{style}"><is><t>{escape(v)}</t></is></c>'
    return f'<c r="{ref}" s="{style}"><v>{v}</v></c>'


def make_xlsx(rows):
    sheet = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
    sheet.append('<row r="1">' + "".join(cell(f"{col(i)}1", h, 2) for i, h in enumerate(HEAD)) + "</row>")
    for n, r in enumerate(rows, 2):
        sheet.append(f'<row r="{n}">' + "".join(cell(f"{col(i)}{n}", v, 1 if i in (3, 4) else 0) for i, v in enumerate(r)) + "</row>")
    sheet.append("</sheetData></worksheet>")
    parts = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Buy-in log" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        "xl/styles.xml": '<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="1"><numFmt numFmtId="164" formatCode="dd/mm/yyyy"/></numFmts><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs></styleSheet>',
        "xl/worksheets/sheet1.xml": "".join(sheet)}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in parts.items(): z.writestr(k, v)
    return buf.getvalue()


all_rows, mail = {}, []
for mi, (month, nrows, last_day) in enumerate([(8, 34, 31), (9, 36, 30), (10, 30, 27)]):
    r = random.Random(500 + month); rows = []; counter = (month - 8) * 100
    for i in range(nrows):
        counter += 1
        scheme = r.choice(schemes); contact = r.choice(TRUSTEES); sla = r.choice([5, 5, 5, 7, 10])
        notif = dt.date(2026, month, r.randint(1, last_day - 10 if month != 10 else 16))
        recv = notif + dt.timedelta(days=max(0, round(r.gauss(sla - 2.5, 3.0))))
        vol = r.randint(8, 420); src = r.choice(["email", "email", "email", "portal", "phone"]); who = r.choice(STAFF); note = ""
        n_cell, r_cell, v_cell = serial(notif), serial(recv), vol
        late = max(0, (recv - notif).days - sla); late_cell = late
        row_n = i + 2; bad = r.random()
        if bad < 0.05:   r_cell, late_cell, note = "TBC", ("err", "#VALUE!"), "waiting on trustee confirmation"
        elif bad < 0.09: v_cell, note = ("err", "#N/A"), "volume lookup failed"
        elif bad < 0.13: v_cell, note = "approx 120", "per email, to confirm"
        elif bad < 0.17: n_cell, late_cell, note = notif.strftime("%d.%m.%Y"), ("err", "#VALUE!"), "date typed as text"
        elif bad < 0.21: r_cell, late_cell, note = None, None, "not yet received"
        rows.append([f"BI-{counter:04d}", scheme, contact, n_cell, r_cell, v_cell, sla,
                     ("f", f"MAX(0,E{row_n}-D{row_n}-G{row_n})", late_cell) if not isinstance(late_cell, tuple) and late_cell is not None else (("f", f"MAX(0,E{row_n}-D{row_n}-G{row_n})", late_cell[1]) if late_cell else None),
                     src, who, note])
        if src == "email" and r.random() < 0.7 and month >= 9:
            when = dt.datetime.combine(recv, dt.time(r.randint(7, 17), r.randint(0, 59), r.randint(0, 59)))
            mail.append((when, scheme, contact, notif, recv, vol))
    all_rows[month] = rows
    fn = f"buyin_log_2026_{month:02d}.xlsx"; open(os.path.join(OUT, fn), "wb").write(make_xlsx(rows)); print(fn, len(rows), "rows")

r = random.Random(77); mail.sort(); lines = []
for when, scheme, contact, notif, recv, vol in mail:
    ts = when.strftime("%Y-%m-%dT%H:%M:%SZ"); mid = f"<{r.randint(10**9, 10**10)}@mail.example.com>"
    lines.append(f'{ts} INFO  mailbox=bpa-buyin@example.com msg_id={mid} from="{contact} <trustee@{scheme.split()[0].lower()}-trustees.example.com>" subject="{scheme} - member movement update" '
                 f'body="Trustees confirm {vol} members to move. Notified {notif.isoformat()}, documents received {recv.isoformat()}."')
    x = r.random()
    if x < 0.12: lines.append(f'{ts} WARN  mailbox=bpa-buyin@example.com msg_id={mid} attachment_unreadable=true action=manual_entry_required')
    elif x < 0.20: lines.append(f'{ts} WARN  mailbox=bpa-buyin@example.com msg_id={mid} possible_duplicate=true action=review')
lines.append(f'{dt.datetime(2026, 10, 27, 17, 5).strftime("%Y-%m-%dT%H:%M:%SZ")} ERROR mailbox=bpa-buyin@example.com job=nightly_export reason="excel upload rejected: invalid value in column received_date"')
open(os.path.join(OUT, "email_intake.log"), "w").write("\n".join(lines) + "\n"); print("email_intake.log", len(lines), "lines")
