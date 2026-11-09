"""Load the planner steps (copied from bpa_edp.demo.bronze_planner_steps, so the verified numbers stay identical) into Dataverse new_plannerstep."""
import json, os, subprocess, sys, urllib.request, urllib.error, urllib.parse
sys.path.insert(0, os.path.expanduser("~/bpa-edp-demo/scripts"))
import run_sql as R
ORG = "https://YOUR-ORG.crm.dynamics.com"; TN = "<CORP_TENANT_ID>"
tok = subprocess.run(["az", "account", "get-access-token", "--tenant", TN, "--resource", ORG, "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True).stdout.strip()
HDR = {"Authorization": "Bearer " + tok, "Content-Type": "application/json", "OData-MaxVersion": "4.0", "OData-Version": "4.0", "Accept": "application/json"}
def dv(method, path, body=None):
    r = urllib.request.Request(ORG + "/api/data/v9.2/" + path, data=None if body is None else json.dumps(body).encode(), method=method, headers=HDR)
    try:
        x = urllib.request.urlopen(r, timeout=120); return x.status, x.read().decode()
    except urllib.error.HTTPError as e: return e.code, e.read().decode()[:300]
s, b = dv("GET", "new_plannersteps?$select=new_name&$top=1&$count=true")
if s != 200: print("table not queryable yet:", s, b[:200]); sys.exit(1)
if json.loads(b).get("@odata.count", 0) > 0: print("rows already present; aborting to avoid duplicates"); sys.exit(1)
s, b = dv("GET", "accounts?$select=name,accountid&$top=500"); acct = {a["name"]: a["accountid"] for a in json.loads(b)["value"]}
t = R.token(); d = R.run("SELECT scheme, step_no, step_name, step_owner, CAST(due_date AS STRING), status FROM bpa_edp.demo.bronze_planner_steps ORDER BY scheme, step_no", t)
rows = d["result"]["data_array"]; print(len(rows), "planner rows; accounts in Dataverse:", len(acct), flush=True)
missing = sorted({r[0] for r in rows if r[0] not in acct})
if missing: print("schemes without an account:", missing[:5]); sys.exit(1)
bad = 0
for i, (scheme, no, name, owner, due, status) in enumerate(rows, 1):
    body = {"new_name": f"{scheme} | step {no}: {name}", "new_stepno": int(no), "new_stepname": name, "new_stepowner": owner, "new_duedate": due, "new_status": status,
            "new_accountid@odata.bind": f"/accounts({acct[scheme]})"}
    s, b = dv("POST", "new_plannersteps", body)
    if s != 204: bad += 1; print("fail", scheme, no, s, b[:150], flush=True)
    if i % 60 == 0: print("loaded", i, flush=True)
print("done; failures:", bad)
