"""Seed bpa_edp.demo.sp_inbound_emails_raw with synthetic emails, in the SAME shape the SharePoint pipeline produces
(path, modificationTime, length, content BINARY holding one JSON file per email, as written by the Power Automate flow).
Use this to rehearse the review page before the flow exists. Once the flow writes real files to the SharePoint folder
`inbound_emails`, drop this table and run scripts/create_inbound_pipeline.py instead (the pipeline creates the same table name)."""
import sys as _s, os as _o; _s.path.insert(0, _o.path.expanduser("~/bpa-edp-demo/scripts"))
import json, run_sql

EMAILS = [
 ("2026-11-03T09:12:00Z", "D. Patel", "d.patel@hollin-trustees.example.com", "RE: Hollin Pension Scheme 6 - buy-in documents",
  "Hi team,\n\nThe trustees have now signed off the member data pack for Hollin Pension Scheme 6. We sent it across on 12 August 2026 and it covers 93 members moving to the insurer.\n\nThanks,\nD. Patel"),
 ("2026-11-03T10:40:00Z", "D. Patel", "d.patel@jesmond-trustees.example.com", "Jesmond Pension Scheme 5 - member movement confirmation",
  "Hello,\n\nPlease note the final number of members moving for Jesmond Pension Scheme 5 is 142. We were first notified on 2026-08-20 and the full documents reached you on 28/08/2026.\n\nRegards,\nD. Patel"),
 ("2026-11-03T11:05:00Z", "B. Okafor", "b.okafor@carrow-trustees.example.com", "Carrow Pension Scheme 5 update",
  "Morning,\n\nJust a quick one. For Carrow Pension Scheme 5 we are looking at around 300 members, give or take a few until the final cleanse is done. Original notification was 7 August.\n\nB. Okafor"),
 ("2026-11-03T13:22:00Z", "A. Hughes", "a.hughes@aldwych-trustees.example.com", "Aldwych Pension Scheme 5 - volumes",
  "Hi,\n\nFollowing our call, Aldwych Pension Scheme 5 will move ninety members. We notified you on the sixteenth of September 2026 and sent everything over on the 25th of September.\n\nA. Hughes"),
 ("2026-11-03T15:48:00Z", "C. Lindqvist", "c.lindqvist@trustees.example.com", "RE: RE: quick question",
  "Thanks, that works for us. Can we speak tomorrow about the numbers?\n\nC. Lindqvist"),
 ("2026-11-04T08:30:00Z", "D. Patel", "d.patel@delamere-trustees.example.com", "Delamere Pension Scheme 6 - member movement update",
  "Trustees confirm 273 members to move. Notified 2026-09-14, documents received 2026-09-22.\n\nD. Patel"),
]

def lit(obj):
    s = json.dumps(obj, ensure_ascii=True).replace("'", "\\u0027")
    return "r'" + s + "'"

rows = []
for i, (ts, name, addr, subj, body) in enumerate(EMAILS, 1):
    msg = {"message_id": f"AAMkAD-demo-{i:04d}", "received_at": ts, "from_name": name, "from_address": addr, "subject": subj, "body_text": body}
    fname = f"{ts[:10]}_{ts[11:13]}{ts[14:16]}_{msg['message_id']}.json"
    rows.append(f"('/Shared Documents/inbound_emails/{fname}', timestamp'{ts[:19].replace('T', ' ')}', {len(json.dumps(msg))}, CAST({lit(msg)} AS BINARY))")

tok = run_sql.token()
for stmt in [
 "DROP TABLE IF EXISTS bpa_edp.demo.sp_inbound_emails_raw",
 "CREATE TABLE bpa_edp.demo.sp_inbound_emails_raw (path STRING, modificationTime TIMESTAMP, length BIGINT, content BINARY)",
 "INSERT INTO bpa_edp.demo.sp_inbound_emails_raw VALUES\n" + ",\n".join(rows),
]:
    d = run_sql.run(stmt, tok)
    print(d["status"]["state"], d["status"].get("error", {}).get("message", "")[:300], "|", stmt.split("\n")[0][:70])
