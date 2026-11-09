"""Create and run the Lakeflow Connect Outlook pipeline on connection `bpa-demo` (tenant example-tenant, a throwaway M365 trial tenant).
Scoped on purpose: ONE mailbox, Inbox only, subjects starting 'BPA demo', non-inline attachments (names, sizes, content), start date 1 Nov 2026.
Lands bpa_edp.demo.outlook_email_messages. Run it by hand; no schedule is set."""
import sys as _s, os as _o; _s.path.insert(0, _o.path.expanduser("~/bpa-edp-demo/scripts"))
import sys, wsapi
MAILBOX = "bpa-intake@example.onmicrosoft.com"
tok = wsapi.token()
obj = {"table": {"source_schema": "default", "source_table": "email_messages", "destination_catalog": "bpa_edp", "destination_schema": "demo",
       "destination_table": "outlook_email_messages",
       "connector_options": {"outlook_options": {"include_mailboxes": [MAILBOX], "include_folders": ["Inbox"], "include_subjects": ["BPA demo*"],
                                                "start_date": "2026-11-01", "body_format": "TEXT_PLAIN", "attachment_mode": "NON_INLINE_ONLY"}}}}
spec = {"name": "bpa_outlook_inbound", "catalog": "bpa_edp", "schema": "demo", "serverless": True, "channel": "PREVIEW",
        "ingestion_definition": {"connection_name": "bpa-demo", "objects": [obj]}}
existing = {p["name"]: p["pipeline_id"] for p in wsapi.call("GET", "/api/2.0/pipelines", tok=tok).get("statuses", [])}
pid = existing.get("bpa_outlook_inbound")
if pid:
    print("updating", pid, wsapi.call("PUT", f"/api/2.0/pipelines/{pid}", dict(spec, id=pid), tok))
else:
    d = wsapi.call("POST", "/api/2.0/pipelines", spec, tok); pid = d.get("pipeline_id"); print("created", pid or d)
if "--no-run" not in sys.argv:
    u = wsapi.call("POST", f"/api/2.0/pipelines/{pid}/updates", {"full_refresh": False}, tok); print("update", u.get("update_id") or u)
    print("result:", wsapi.wait_pipeline(pid, tok))
