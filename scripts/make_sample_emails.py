"""Build the sample trustee emails and their attachments for the Outlook connector demo (all synthetic).
Writes ~/bpa-edp-demo/sample_emails/: SEND_THESE_EMAILS.md plus the files to attach. Dates and volumes line up with the buy-in log
(BI-0002 Jesmond 5, BI-0003 Hollin 6, BI-0028 Carrow 5, BI-0123 Aldwych 5, BI-0211-style Delamere 6)."""
import io, os, random, zipfile
from xml.sax.saxutils import escape
OUT = os.path.expanduser("~/bpa-edp-demo/sample_emails"); os.makedirs(OUT, exist_ok=True)

def col(i): return chr(65 + i)

def xlsx(rows, sheet="Members"):
    cells = []
    for r, row in enumerate(rows, 1):
        cs = []
        for c, v in enumerate(row):
            ref = f"{col(c)}{r}"
            cs.append(f'<c r="{ref}"><v>{v}</v></c>' if isinstance(v, (int, float)) else f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>')
        cells.append(f'<row r="{r}">{"".join(cs)}</row>')
    parts = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{sheet}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(cells)}</sheetData></worksheet>',
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for k, v in parts.items(): z.writestr(k, v)
    return buf.getvalue()

def pdf(lines):
    esc = lambda s: s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = "BT /F1 12 Tf 56 780 Td 16 TL\n" + "\n".join(f"({esc(l)}) Tj T*" for l in lines) + "\nET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 5 0 R /Resources << /Font << /F1 4 0 R >> >> >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"]
    out = b"%PDF-1.4\n"; offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out)); out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    x = len(out); out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for o in offs: out += f"{o:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF\n".encode()
    return out

def members(prefix, n, seed):
    r = random.Random(seed); rows = [["member_ref", "status", "age_band", "annual_pension_gbp", "spouse_pension"]]
    for i in range(1, n + 1):
        rows.append([f"{prefix}-{i:04d}", r.choice(["Pensioner", "Pensioner", "Deferred"]), r.choice(["55-59", "60-64", "65-69", "70-74", "75-79", "80+"]), r.randint(1800, 31000), r.choice(["Y", "N"])])
    return rows

files = {
    "Jesmond5_member_data_pack.xlsx": xlsx(members("JES5", 142, 5)),
    "Hollin6_trustee_signoff.pdf": pdf(["Hollin Pension Scheme 6 - trustee sign-off of member data", "", "The trustees confirm the member data pack dated 12 August 2026 is complete.", "Members in scope for the buy-in: 93.", "", "Signed: D. Patel, on behalf of the trustees", "(Synthetic document for a demo)"]),
    "Aldwych5_member_data_pack.xlsx": xlsx(members("ALD5", 90, 55)),
    "Aldwych5_cover_letter.pdf": pdf(["Aldwych Pension Scheme 5 - cover letter", "", "Please find the member data pack for the 90 members moving.", "Notified: 16 September 2026. Pack sent: 25 September 2026.", "", "A. Hughes", "(Synthetic document for a demo)"]),
    "Delamere6_member_data_pack.xlsx": xlsx(members("DEL6", 273, 66)),
}
for name, data in files.items(): open(os.path.join(OUT, name), "wb").write(data)

EMAILS = [
 ("BPA demo - Jesmond Pension Scheme 5 - member movement confirmation", "Hello,\n\nPlease note the final number of members moving for Jesmond Pension Scheme 5 is 142. We were first notified on 2026-08-20 and the full documents reached you on 28/08/2026. The member data pack is attached.\n\nRegards,\nD. Patel", ["Jesmond5_member_data_pack.xlsx"], "Fills the invalid volume in BI-0002 (Excel says 'approx 120')."),
 ("BPA demo - Hollin Pension Scheme 6 - buy-in documents", "Hi team,\n\nThe trustees have now signed off the member data for Hollin Pension Scheme 6. We sent the pack across on 12 August 2026 and it covers 93 members moving to the insurer. The signed-off letter is attached.\n\nThanks,\nD. Patel", ["Hollin6_trustee_signoff.pdf"], "Gives the received date for BI-0003 (Excel says 'TBC'). The email gives no notification date."),
 ("BPA demo - Carrow Pension Scheme 5 update", "Morning,\n\nJust a quick one. For Carrow Pension Scheme 5 we are looking at around 300 members, give or take a few until the final cleanse is done. Original notification was 7 August.\n\nB. Okafor", [], "A hedged number with no attachment. The app should mark it low or medium confidence."),
 ("BPA demo - Aldwych Pension Scheme 5 - volumes", "Hi,\n\nFollowing our call, Aldwych Pension Scheme 5 will move ninety members. We notified you on the sixteenth of September 2026 and sent everything over on the 25th of September. The pack and a cover letter are attached.\n\nA. Hughes", ["Aldwych5_member_data_pack.xlsx", "Aldwych5_cover_letter.pdf"], "Numbers and dates written in words, with two attachments."),
 ("BPA demo - quick question", "Thanks, that works for us. Can we speak tomorrow about the numbers?\n\nC. Lindqvist", [], "No scheme or figures. The app will not let you confirm it."),
 ("BPA demo - Delamere Pension Scheme 6 - member movement update", "Trustees confirm 273 members to move. Notified 2026-09-14, documents received 2026-09-22. The member data pack is attached.\n\nD. Patel", ["Delamere6_member_data_pack.xlsx"], "A clean email in the same shape as the mailbox log."),
]
md = ["# Sample emails to send to bpa-intake@example.onmicrosoft.com", "",
      "All synthetic. Send each one **to** `bpa-intake@example.onmicrosoft.com` from any account (your outlook.com address is fine).",
      "The subject must start with `BPA demo`: the pipeline only reads those. Attach the files from this folder where listed.",
      "The email's received time will be when you send it; the dates inside the text are the story dates.", ""]
for i, (subj, body, att, why) in enumerate(EMAILS, 1):
    md += [f"## Email {i}", f"**Subject:** {subj}", f"**Attach:** {', '.join(att) if att else 'nothing'}", f"**Why:** {why}", "", "```", body, "```", ""]
open(os.path.join(OUT, "SEND_THESE_EMAILS.md"), "w").write("\n".join(md))
for n in sorted(os.listdir(OUT)): print(n, os.path.getsize(os.path.join(OUT, n)), "bytes")
