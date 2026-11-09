"""Create and run the Lakeflow Connect SharePoint pipelines. Needs the UC connection `bpa-sharepoint` (browser sign-in, U2M)."""
import sys as _s, os as _o; _s.path.insert(0, _o.path.expanduser("~/bpa-edp-demo/scripts"))
import sys, wsapi
SITE = "https://YOUR-TENANT.sharepoint.com/sites/YOUR-SITE/Shared%20Documents/"
def obj(table, folder):
    return {"table": {"destination_catalog": "bpa_edp", "destination_schema": "demo", "destination_table": table,
            "connector_options": {"sharepoint_options": {"entity_type": "FILE", "url": SITE + folder,
            "file_ingestion_options": {"format": "BINARYFILE", "schema_evolution_mode": "NONE"}}}}}
PIPES = {
 "bpa_sharepoint_scheme_files": [obj("sharepoint_scheme_files", "scheme_rules")],
 "bpa_sharepoint_buyin": [obj("sp_buyin_logs_raw", "buyin_logs"), obj("sp_email_intake_raw", "email_intake")],
}
tok = wsapi.token()
if not any(c["name"] == "bpa-sharepoint" for c in wsapi.call("GET", "/api/2.1/unity-catalog/connections", tok=tok).get("connections", [])):
    sys.exit("connection bpa-sharepoint does not exist yet: create it in Catalog > Create connection > SharePoint > OAuth (U2M)")
existing = {p["name"]: p["pipeline_id"] for p in wsapi.call("GET", "/api/2.0/pipelines", tok=tok).get("statuses", [])}
for name, objects in PIPES.items():
    pid = existing.get(name)
    if not pid:
        d = wsapi.call("POST", "/api/2.0/pipelines", {"name": name, "catalog": "bpa_edp", "schema": "demo", "serverless": True, "channel": "PREVIEW",
             "ingestion_definition": {"connection_name": "bpa-sharepoint", "objects": objects}}, tok)
        pid = d.get("pipeline_id"); print("created", name, pid or d)
    wsapi.call("POST", f"/api/2.0/pipelines/{pid}/updates", {"full_refresh": False}, tok)
    print(name, wsapi.wait_pipeline(pid, tok))
