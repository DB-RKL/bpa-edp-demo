"""Create/refresh the Lakeflow Connect Dynamics 365 connection and pipeline (Synapse Link CSV export -> Unity Catalog).
Prerequisites (all done by hand in Power Apps/Azure): a Synapse Link "Create link to data lake" on storage account YOUR_STORAGE_ACCOUNT with
 - Enable Incremental Update Folder Structure ON (connector needs Changelog/changelog.info), Synapse workspace option OFF
 - tables account + new_bpaquote only; the app bpa-edp-demo-corp holding Storage Blob Data Contributor on the account.
The container name is created by the link; read it from the account (dataverse-<org>-unq...)."""
import sys as _s, os as _o; _s.path.insert(0, _o.path.expanduser("~/bpa-edp-demo/scripts"))
import json, time, wsapi
SA = "YOUR_STORAGE_ACCOUNT"; CONTAINER = "dataverse-YOUR-ORG-UNIQUE-ID"
d = json.load(open(_o.path.expanduser("~/.bpa-edp/corp/sp.json"))); tok = wsapi.token()
conns = {c["name"] for c in wsapi.call("GET", "/api/2.1/unity-catalog/connections", tok=tok).get("connections", [])}
if "bpa-d365-dataverse" not in conns:
    print("connection:", wsapi.call("POST", "/api/2.1/unity-catalog/connections", {"name": "bpa-d365-dataverse", "connection_type": "DYNAMICS365", "options": {
        "tenant_id": d["tenant"], "client_id": d["appId"], "client_secret": d["password"], "azure_storage_account_name": SA,
        "azure_container_name": CONTAINER, "oauth_scope": "https://storage.azure.com/.default"}}, tok).get("name"))
objs = [{"table": {"source_schema": "objects", "source_table": t, "destination_catalog": "bpa_edp", "destination_schema": "demo", "destination_table": dest}}
        for t, dest in (("account", "d365_account"), ("new_bpaquote", "d365_bpa_quote"))]
spec = {"name": "bpa_d365_dataverse", "catalog": "bpa_edp", "schema": "demo", "serverless": True, "channel": "PREVIEW",
        "ingestion_definition": {"connection_name": "bpa-d365-dataverse", "objects": objs}}
ex = {p["name"]: p["pipeline_id"] for p in wsapi.call("GET", "/api/2.0/pipelines", tok=tok).get("statuses", [])}
pid = ex.get("bpa_d365_dataverse") or wsapi.call("POST", "/api/2.0/pipelines", spec, tok).get("pipeline_id")
wsapi.call("POST", f"/api/2.0/pipelines/{pid}/updates", {"full_refresh": False}, tok)
print("pipeline", pid, wsapi.wait_pipeline(pid, tok))
