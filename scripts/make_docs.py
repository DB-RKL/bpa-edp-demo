"""Generate synthetic BPA scheme-rules documents (PDF and DOCX) with the stdlib only.

Each document is a short "Scheme Rules Summary" with the fields the demo extracts with
ai_parse_document + ai_query. Values are deterministic per scheme.
"""
import json, os, random, zipfile, io

OUT = os.path.expanduser("~/bpa-edp-demo/docs/out")
os.makedirs(OUT, exist_ok=True)
schemes = json.load(open(os.path.expanduser("~/bpa-edp-demo/docs/schemes.json")))
truth = []


def esc(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(lines):
    content = ["BT", "/F1 15 Tf", "50 790 Td", "16 TL"]
    for i, ln in enumerate(lines):
        if i == 1:
            content.append("/F1 11 Tf")
        content.append(f"({esc(ln)}) Tj T*")
    content.append("ET")
    stream = "\n".join(content).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + o + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n".encode())
    for o in offs:
        out.write(f"{o:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def make_docx(lines):
    def para(t, bold=False):
        t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
        return f'<w:p><w:r>{rpr}<w:t xml:space="preserve">{t}</w:t></w:r></w:p>'
    body = "".join(para(l, i == 0) for i, l in enumerate(lines))
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + body + "</w:body></w:document>")
    ct = ('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", doc)
    return buf.getvalue()


for i, (acct_id, name) in enumerate(schemes):
    r = random.Random(1000 + i)
    members = r.randint(300, 9000)
    nra = r.choice([60, 62, 65])
    spouse = r.choice([50, 50, 66.7])
    infl = r.choice(["CPI capped at 5.0% per annum", "CPI capped at 2.5% per annum", "RPI capped at 5.0% per annum"])
    discount = round(r.uniform(4.2, 5.6), 2)
    expense = round(r.uniform(0.5, 1.5), 2)
    longevity = r.choice(["S3PA CMI2023", "S4PA CMI2023", "Bespoke VitaCurves"])
    liability = round(r.uniform(40, 800), 1)
    lines = [
        f"{name} - Scheme Rules Summary",
        "Prepared for bulk purchase annuity pricing (synthetic demo document)",
        "",
        "1. Membership",
        f"Total members in scope: {members}",
        "Status: closed to new entrants and to future accrual",
        "",
        "2. Benefits",
        f"Normal retirement age: {nra}",
        f"Spouse pension: {spouse} percent of member pension",
        f"Pension increases in payment: {infl}",
        "Revaluation of deferred pensions: CPI capped at 5.0% per annum",
        "",
        "3. Pricing assumptions provided by the trustees",
        f"Discount rate: {discount} percent",
        f"Longevity basis: {longevity}",
        f"Expense loading: {expense} percent",
        f"Estimated buy-out liability: GBP {liability} million",
    ]
    is_pdf = i % 3 != 2
    fname = f"scheme_rules_{i+1:02d}." + ("pdf" if is_pdf else "docx")
    open(os.path.join(OUT, fname), "wb").write(make_pdf(lines) if is_pdf else make_docx(lines))
    truth.append({"file": fname, "accountid": acct_id, "scheme": name, "members": members, "nra": nra,
                  "spouse_pct": spouse, "increases": infl, "discount_rate_pct": discount,
                  "longevity": longevity, "expense_loading_pct": expense, "liability_gbp_m": liability})

json.dump(truth, open(os.path.expanduser("~/bpa-edp-demo/docs/ground_truth.json"), "w"), indent=1)
print(len(truth), "documents in", OUT)
