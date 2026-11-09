"""Create (raw API; the CLI adds a bad budget policy), grant, upload and deploy the pricing write-back app."""
import sys as _s, os as _o; _s.path.insert(0, _o.path.expanduser("~/bpa-edp-demo/scripts"))
import json, os, subprocess, sys, time, wsapi
NAME = "bpa-pricing-edp"; PATH = "/Workspace/Users/you@example.com/bpa-pricing-edp"
tok = wsapi.token()
if "_error" in wsapi.call("GET", f"/api/2.0/apps/{NAME}", tok=tok):
    print("create", wsapi.call("POST", "/api/2.0/apps", {"name": NAME, "description": "BPA pricing assumptions write-back (EDP demo, synthetic)"}, tok).get("name"))
for _ in range(30):
    a = wsapi.call("GET", f"/api/2.0/apps/{NAME}", tok=tok)
    if a.get("compute_status", {}).get("state") == "ACTIVE": break
    time.sleep(10)
spc = a["service_principal_client_id"]; print("app", a.get("url"), spc)
sql = f"GRANT USE CATALOG ON CATALOG bpa_edp TO `{spc}`\n;\nGRANT USE SCHEMA, SELECT, MODIFY ON SCHEMA bpa_edp.demo TO `{spc}`"
open("/tmp/app_grants.sql", "w").write(sql)
subprocess.run([sys.executable, "-I", os.path.expanduser("~/bpa-edp-demo/scripts/run_sql.py"), "/tmp/app_grants.sql"], check=True)
print("warehouse", wsapi.call("PATCH", f"/api/2.0/permissions/sql/warehouses/{wsapi.WH}", {"access_control_list": [{"service_principal_name": spc, "permission_level": "CAN_USE"}]}, tok).get("object_id"))
env = dict(os.environ, DATABRICKS_HOST=wsapi.H, DATABRICKS_TOKEN=tok)
yml = open(os.path.expanduser("~/bpa-edp-demo/app/app.yaml")).read()
import re; open(os.path.expanduser("~/bpa-edp-demo/app/app.yaml"), "w").write(re.sub(r'value: "[0-9a-f]{16}"', f'value: "{wsapi.WH}"', yml))
subprocess.run(["databricks", "workspace", "import-dir", os.path.expanduser("~/bpa-edp-demo/app"), PATH, "--overwrite"], env=env, check=True, capture_output=True)
d = wsapi.call("POST", f"/api/2.0/apps/{NAME}/deployments", {"source_code_path": PATH}, tok); print("deploy", d.get("deployment_id") or d)
for _ in range(30):
    a = wsapi.call("GET", f"/api/2.0/apps/{NAME}", tok=tok)
    if a.get("app_status", {}).get("state") == "RUNNING": print("RUNNING", a.get("url")); break
    time.sleep(10)
