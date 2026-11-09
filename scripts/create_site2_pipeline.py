"""Create and run the Lakeflow Connect SharePoint pipeline on connection `bpa-sharepoint-site2` (the user's new trial-tenant site YOUR-SITE).
Lands NEW tables (sp_site2_*) so the tables the app reads today are not touched until the contents have been compared. Run by hand; no schedule."""
import sys as _s, os as _o; _s.path.insert(0, _o.path.expanduser("~/bpa-edp-demo/scripts"))
import sys, time, json, wsapi
SITE = "https://YOUR-TENANT.sharepoint.com/sites/YOUR-SITE/Shared%20Documents/"
def obj(table, folder):
    return {"table": {"destination_catalog": "bpa_edp", "destination_schema": "demo", "destination_table": table,
            "connector_options": {"sharepoint_options": {"entity_type": "FILE", "url": SITE + folder,
            "file_ingestion_options": {"format": "BINARYFILE", "schema_evolution_mode": "NONE"}}}}}
spec = {"name": "bpa_sharepoint_site2", "catalog": "bpa_edp", "schema": "demo", "serverless": True, "channel": "PREVIEW",
        "ingestion_definition": {"connection_name": "bpa-sharepoint-site2",
                                 "objects": [obj("sp_site2_buyin_logs_raw", "buyin_logs"), obj("sp_site2_scheme_files", "scheme_rules")]}}
tok = wsapi.token()
existing = {p["name"]: p["pipeline_id"] for p in wsapi.call("GET", "/api/2.0/pipelines", tok=tok).get("statuses", [])}
pid = existing.get("bpa_sharepoint_site2")
if pid: print("updating", pid, wsapi.call("PUT", f"/api/2.0/pipelines/{pid}", dict(spec, id=pid), tok))
else:
    d = wsapi.call("POST", "/api/2.0/pipelines", spec, tok); pid = d.get("pipeline_id"); print("created", pid or d)
if not pid: sys.exit(1)
r = wsapi.call("POST", f"/api/2.0/pipelines/{pid}/updates", {"full_refresh": False}, tok); up = r.get("update_id")
if not up: sys.exit(f"could not start: {r}")
print("update", up[:8], flush=True); st = None
for _ in range(60):
    st = wsapi.call("GET", f"/api/2.0/pipelines/{pid}/updates/{up}", tok=tok).get("update", {}).get("state"); print(" ", st, flush=True)
    if st in ("COMPLETED", "FAILED", "CANCELED"): break
    time.sleep(10)
if st != "COMPLETED":
    wsapi.call("POST", f"/api/2.0/pipelines/{pid}/stop", {}, tok)
    for e in wsapi.call("GET", f"/api/2.0/pipelines/{pid}/events?max_results=30&order_by=timestamp%20desc", tok=tok).get("events", []):
        if e.get("level") == "ERROR":
            ex = (e.get("error") or {}).get("exceptions"); print("ERROR:", (ex[0].get("message", "") if ex else e.get("message", ""))[:600]); break
    sys.exit(f"pipeline ended {st} (stopped so it cannot retry in a loop)")
print("pipeline", pid, "COMPLETED")
