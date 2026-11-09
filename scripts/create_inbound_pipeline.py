"""Create and run the Lakeflow Connect pipeline for the SharePoint folder `inbound_emails` (written by the Power Automate flow).
Run AFTER the folder exists and the flow has saved at least one email. The seed table from seed_inbound_emails.py has the same name
as the pipeline's table, so pass --replace-seed to drop it first."""
import sys as _s, os as _o; _s.path.insert(0, _o.path.expanduser("~/bpa-edp-demo/scripts"))
import sys, wsapi, run_sql
SITE = "https://YOUR-TENANT.sharepoint.com/sites/YOUR-SITE/Shared%20Documents/inbound_emails"
tok = wsapi.token()
if "--replace-seed" in sys.argv:
    d = run_sql.run("DROP TABLE IF EXISTS bpa_edp.demo.sp_inbound_emails_raw", run_sql.token()); print("drop seed:", d["status"]["state"])
obj = {"table": {"destination_catalog": "bpa_edp", "destination_schema": "demo", "destination_table": "sp_inbound_emails_raw",
       "connector_options": {"sharepoint_options": {"entity_type": "FILE", "url": SITE,
       "file_ingestion_options": {"format": "BINARYFILE", "schema_evolution_mode": "NONE"}}}}}
existing = {p["name"]: p["pipeline_id"] for p in wsapi.call("GET", "/api/2.0/pipelines", tok=tok).get("statuses", [])}
pid = existing.get("bpa_sharepoint_inbound_email")
if not pid:
    d = wsapi.call("POST", "/api/2.0/pipelines", {"name": "bpa_sharepoint_inbound_email", "catalog": "bpa_edp", "schema": "demo", "serverless": True, "channel": "PREVIEW",
         "ingestion_definition": {"connection_name": "bpa-sharepoint", "objects": [obj]}}, tok)
    pid = d.get("pipeline_id"); print("created", pid or d)
wsapi.call("POST", f"/api/2.0/pipelines/{pid}/updates", {"full_refresh": False}, tok)
print("pipeline", pid, wsapi.wait_pipeline(pid, tok))
