"""Add or remove ONE made-up test email (with an Excel attachment) so the Excel path can be tried without sending real mail.
It lives in bpa_edp.demo.fake_inbound_emails and is labelled "Test email (made up, not from Outlook)" everywhere in the app.
  python3 -I scripts/fake_email.py add      # insert it and read its attachment text
  python3 -I scripts/fake_email.py remove   # delete it, its attachment text and any review decision on it"""
import sys as _s, os as _o; _s.path.insert(0, _o.path.expanduser("~/bpa-edp-demo/scripts"))
import sys, base64, run_sql
MID = "FAKE-TEST-0001"
t = run_sql.token()

def run(sql):
    d = run_sql.run(sql, t); st = d["status"]
    if st["state"] != "SUCCEEDED": sys.exit("FAILED: " + st.get("error", {}).get("message", "")[:300])
    return d

if len(sys.argv) < 2 or sys.argv[1] not in ("add", "remove"): sys.exit(__doc__)
if sys.argv[1] == "add":
    xlsx = open(_o.path.expanduser("~/bpa-edp-demo/sample_emails/Jesmond5_member_data_pack.xlsx"), "rb").read()
    body = ("Hello,\n\nPlease note the final number of members moving for Jesmond Pension Scheme 5 is 142. We were first notified on 2026-08-20 "
            "and the full documents reached you on 28/08/2026. The member data pack is attached.\n\nRegards,\nD. Patel")
    lit = "'" + body.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n") + "'"
    run("DELETE FROM bpa_edp.demo.fake_inbound_emails WHERE outlook_message_id = '" + MID + "'")
    run("INSERT INTO bpa_edp.demo.fake_inbound_emails SELECT 'test-mailbox', '" + MID + "', 'Inbox', 'd.patel@jesmond-trustees.example.com', "
        "'BPA demo - Jesmond Pension Scheme 5 - member movement confirmation', " + lit + ", " + lit + ", current_timestamp(), "
        "array(named_struct('content', unbase64('" + base64.b64encode(xlsx).decode() + "'), 'attachment_id', 'FAKE-ATT-1', "
        "'file_name', 'Jesmond5_member_data_pack.xlsx', 'mime_type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', "
        "'size', CAST(" + str(len(xlsx)) + " AS BIGINT), 'attachment_kind', 'fileAttachment', 'is_inline', false))")
    for sql in open(_o.path.expanduser("~/bpa-edp-demo/sql/10b_attachment_text_refresh.sql")).read().split("\n;\n"): run(sql.strip())
    print("added", MID, "and read its attachment")
else:
    run("DELETE FROM bpa_edp.demo.fake_inbound_emails WHERE outlook_message_id = '" + MID + "'")
    run("DELETE FROM bpa_edp.demo.outlook_attachment_text WHERE message_id = '" + MID + "'")
    run("DELETE FROM bpa_edp.demo.inbound_email_review WHERE message_id = '" + MID + "'")
    print("removed", MID)
