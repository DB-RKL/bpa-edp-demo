"""Load synthetic schemes (account) and quotes (new_bpaquote) into the Dataverse Developer environment.
Rows come from the OneLake tables so Dataverse and the lakehouse describe the same schemes. Accounts are tagged
'bpa-edp-demo' in the description so they can be found and deleted."""
import json, os, subprocess, sys, urllib.request, urllib.error
sys.path.insert(0, os.path.expanduser("~/bpa-edp-demo/scripts"))
import run_sql as R

ORG = "https://YOUR-ORG.crm.dynamics.com"; TN = "<CORP_TENANT_ID>"; TAG = "bpa-edp-demo"
tok = subprocess.run(["az", "account", "get-access-token", "--tenant", TN, "--resource", ORG, "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True).stdout.strip()
HDR = {"Authorization": "Bearer " + tok, "Content-Type": "application/json", "OData-MaxVersion": "4.0", "OData-Version": "4.0", "Accept": "application/json"}


def dv(method, path, body=None):
    r = urllib.request.Request(ORG + "/api/data/v9.2/" + path, data=None if body is None else json.dumps(body).encode(), method=method, headers=HDR)
    try:
        x = urllib.request.urlopen(r, timeout=60); return x.status, x.headers, x.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read().decode()[:300]


s, _, b = dv("GET", f"accounts?$filter=startswith(description,'{TAG}')&$select=name&$count=true")
if json.loads(b).get("@odata.count", 0) > 0:
    print("already loaded; aborting to avoid duplicates"); sys.exit(1)

sqltok = R.token()
def rows(sql):
    d = R.run(sql, sqltok); assert d["status"]["state"] == "SUCCEEDED", d["status"]
    return d["result"]["data_array"]

accts = rows("SELECT accountid, name, customertypecode, address1_city FROM bpa_onelake_corp_fabric.dbo.dv_account ORDER BY name")
opps = rows("SELECT opportunityid, name, parentaccountid, estimatedvalue, estimatedclosedate, statecode, stepname FROM bpa_onelake_corp_fabric.dbo.dv_opportunity ORDER BY name")
print(len(accts), "accounts,", len(opps), "quotes to load", flush=True)

idmap = {}
for i, (aid, name, typ, city) in enumerate(accts, 1):
    s, h, b = dv("POST", "accounts", {"name": name, "address1_city": city, "description": f"{TAG} synthetic | type: {typ} | source id: {aid}"})
    if s != 204: print("account fail", name, s, b); sys.exit(1)
    idmap[aid] = h["OData-EntityId"].split("(")[-1].rstrip(")")
    if i % 20 == 0: print("accounts", i, flush=True)

bad = 0
for i, (oid, name, parent, val, close, state, stage) in enumerate(opps, 1):
    body = {"new_name": name, "new_estimatedvalue_gbp_m": round(float(val) / 1e6, 2), "new_closedate": str(close)[:10], "new_stage": stage, "new_state": state,
            "new_accountid@odata.bind": f"/accounts({idmap[parent]})"}
    s, h, b = dv("POST", "new_bpaquotes", body)
    if s != 204: bad += 1; print("quote fail", name, s, b)
    if i % 30 == 0: print("quotes", i, flush=True)

json.dump(idmap, open(os.path.expanduser("~/bpa-edp-demo/docs/dataverse_account_ids.json"), "w"))
print("done; quote failures:", bad)
