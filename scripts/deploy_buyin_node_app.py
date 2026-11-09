"""Create, grant, upload and deploy the Node.js buy-in editor app (separate from the Streamlit one)."""
import sys as _s, os as _o; _s.path.insert(0, _o.path.expanduser("~/bpa-edp-demo/scripts"))
import json, subprocess, time
import wsapi
NAME = "bpa-buyin-editor-node"; PATH = "/Workspace/Users/you@example.com/bpa-buyin-editor-node"; SRC = _o.path.expanduser("~/bpa-edp-demo/app_buyin_node")
tok = wsapi.token()
if "_error" in wsapi.call("GET", f"/api/2.0/apps/{NAME}", tok=tok):
    print("create:", wsapi.call("POST", "/api/2.0/apps", {"name": NAME, "description": "Buy-in operations, Node.js version of the buy-in editor (synthetic data)"}, tok).get("name"))
for _ in range(40):
    a = wsapi.call("GET", f"/api/2.0/apps/{NAME}", tok=tok)
    if a.get("compute_status", {}).get("state") == "ACTIVE": break
    time.sleep(10)
spc = a["service_principal_client_id"]; print("app url:", a.get("url"), "| compute:", a.get("compute_status", {}).get("state"), "| service principal:", spc)
grants = [f"GRANT USE CATALOG ON CATALOG bpa_edp TO `{spc}`", f"GRANT USE SCHEMA ON SCHEMA bpa_edp.demo TO `{spc}`"]
grants += [f"GRANT SELECT ON TABLE bpa_edp.demo.{t} TO `{spc}`" for t in ("buyin_quarantine", "silver_buyin_log", "email_suggestions", "email_extracted", "mv_buyin_sla", "sp_inbound_emails_raw", "inbound_emails", "inbound_emails_sharepoint", "outlook_email_messages", "outlook_attachment_text", "fake_inbound_emails", "email_messages", "outlook_inbox", "inbound_email_latest")]
grants += [f"GRANT SELECT, MODIFY ON TABLE bpa_edp.demo.{t} TO `{spc}`" for t in ("buyin_corrections", "inbound_email_review", "inbound_attachment_import")]
grants += [f"GRANT READ VOLUME, WRITE VOLUME ON VOLUME bpa_edp.demo.inbound_attachments TO `{spc}`"]
grants += [f"GRANT EXECUTE ON FUNCTION bpa_edp.demo.html_to_text TO `{spc}`"]
open("/tmp/buyin_node_grants.sql", "w").write("\n;\n".join(grants))
subprocess.run([_s.executable, "-I", _o.path.expanduser("~/bpa-edp-demo/scripts/run_sql.py"), "/tmp/buyin_node_grants.sql"], check=True)
print("warehouse:", wsapi.call("PATCH", f"/api/2.0/permissions/sql/warehouses/{wsapi.WH}", {"access_control_list": [{"service_principal_name": spc, "permission_level": "CAN_USE"}]}, tok).get("object_id"))
# ai_query uses the pay-per-token foundation model endpoint databricks-gpt-oss-120b, which has no endpoint id to grant on; it is open to workspace users by default. Not verified for the app service principal.
env = dict(_o.environ, DATABRICKS_HOST=wsapi.H, DATABRICKS_TOKEN=tok)
subprocess.run(["databricks", "workspace", "import-dir", SRC, PATH, "--overwrite"], env=env, check=True, capture_output=True)
d = wsapi.call("POST", f"/api/2.0/apps/{NAME}/deployments", {"source_code_path": PATH}, tok); print("deploy:", d.get("deployment_id") or d)
for i in range(45):
    a = wsapi.call("GET", f"/api/2.0/apps/{NAME}", tok=tok); st = a.get("app_status", {}).get("state"); dep = (a.get("pending_deployment") or a.get("active_deployment") or {}).get("status", {})
    print(f"  {i+1}: app={st} deployment={dep.get('state')} {dep.get('message', '')[:100]}")
    if st == "RUNNING" or dep.get("state") == "FAILED": break
    time.sleep(10)
print("final:", a.get("app_status"), "| url:", a.get("url"))
