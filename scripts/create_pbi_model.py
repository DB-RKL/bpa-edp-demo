"""Create a Power BI semantic model in DirectQuery mode over the pbi_* views in Unity Catalog (Fabric REST, TMDL).
The measures stay defined once in the Databricks metric views; this model only reads the views."""
import sys as _s, os as _o; _s.path.insert(0, _o.path.expanduser("~/bpa-edp-demo/scripts"))
import base64, json, subprocess, time, urllib.request, urllib.error
import wsapi

WS = "<FABRIC_WORKSPACE_ID>"   # Fabric workspace bpa-edp-demo-corp (corp tenant)
NAME = "BPA buy-in (Databricks DirectQuery)"
HOST = wsapi.H.replace("https://", ""); PATH = "/sql/1.0/warehouses/" + wsapi.WH
VIEWS = {"sla_overall": "pbi_sla_overall", "sla_by_month": "pbi_sla_by_month", "sla_by_trustee": "pbi_sla_by_trustee", "scheme_status": "pbi_scheme_status"}
TYPES = {"STRING": "string", "LONG": "int64", "INT": "int64", "DOUBLE": "double", "DATE": "dateTime", "TIMESTAMP": "dateTime"}
NOSUM = {"breach_rate_pct", "avg_days_late", "pct_members_moved", "month", "target_buyout_date"}   # rates/dates: never summed
cols = json.load(open("/tmp/pbi_cols.json"))
# Measures only read Databricks-computed columns (rates are never recomputed here). One row per category, so MAX returns that row's value.
MEASURES = {
 "sla_overall": [("Total entries", "SUM(sla_overall[entries])", "0"), ("Received entries", "SUM(sla_overall[received])", "0"), ("SLA breach count", "SUM(sla_overall[sla_breaches])", "0"),
                 ("Breach rate %", "MAX(sla_overall[breach_rate_pct])", "0.0"), ("Pending count", "SUM(sla_overall[pending_items])", "0"), ("Average days late", "MAX(sla_overall[avg_days_late])", "0.0")],
 "sla_by_month": [("Month entries", "SUM(sla_by_month[entries])", "0"), ("Month breach rate %", "MAX(sla_by_month[breach_rate_pct])", "0.0")],
 "sla_by_trustee": [("Trustee entries", "SUM(sla_by_trustee[entries])", "0"), ("Trustee breach rate %", "MAX(sla_by_trustee[breach_rate_pct])", "0.0")],
 "scheme_status": [("Overdue steps", "SUM(scheme_status[overdue_steps])", "0"), ("Members moved %", "MAX(scheme_status[pct_members_moved])", "0.0"),
                   ("Scheme SLA breaches", "SUM(scheme_status[sla_breaches])", "0"), ("Scheme pending items", "SUM(scheme_status[pending_items])", "0")],
}

def table_tmdl(tname, view):
    L = [f"table {tname}", ""]
    for c, t in cols[view]:
        dt = TYPES[t]
        L += [f"\tcolumn {c}", f"\t\tdataType: {dt}"]
        if dt == "int64": L.append("\t\tformatString: 0")
        elif dt == "double": L.append("\t\tformatString: 0.0")
        elif dt == "dateTime": L.append("\t\tformatString: " + ("yyyy-MM" if c == "month" else "yyyy-MM-dd"))
        L += [f"\t\tsourceColumn: {c}", "\t\tsummarizeBy: " + ("none" if (dt in ("string", "dateTime") or c in NOSUM) else "sum"), ""]
    for mn, expr, fmt in MEASURES.get(tname, []):
        L += [f"\tmeasure '{mn}' = {expr}", f"\t\tformatString: {fmt}", ""]
    L += [f"\tpartition {tname} = m", "\t\tmode: directQuery", "\t\tsource =", "\t\t\t\tlet",
          f'\t\t\t\t\tSource = Databricks.Catalogs("{HOST}", "{PATH}", [Catalog = null, Database = null, EnableAutomaticProxyDiscovery = null, Implementation = "2.0"]),',
          '\t\t\t\t\tdb = Source{[Name = "bpa_edp", Kind = "Database"]}[Data],',
          '\t\t\t\t\tsch = db{[Name = "demo", Kind = "Schema"]}[Data],',
          f'\t\t\t\t\tobj = sch{{[Name = "{view}", Kind = "View"]}}[Data]', "\t\t\t\tin", "\t\t\t\t\tobj", ""]
    return "\n".join(L)

parts = {"definition.pbism": json.dumps({"version": "4.0", "settings": {}}),
         "definition/database.tmdl": "database\n\tcompatibilityLevel: 1604\n",
         "definition/model.tmdl": "model Model\n\tculture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\n" + "\n".join(f"ref table {t}" for t in VIEWS) + "\n"}
for t, v in VIEWS.items(): parts[f"definition/tables/{t}.tmdl"] = table_tmdl(t, v)
body = {"displayName": NAME, "definition": {"parts": [{"path": p, "payload": base64.b64encode(c.encode()).decode(), "payloadType": "InlineBase64"} for p, c in parts.items()]}}

ft = subprocess.run(["az", "account", "get-access-token", "--tenant", "<CORP_TENANT_ID>", "--resource", "https://api.fabric.microsoft.com", "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True).stdout.strip()
def fab(method, url, b=None):
    r = urllib.request.Request(url, data=None if b is None else json.dumps(b).encode(), method=method, headers={"Authorization": "Bearer " + ft, "Content-Type": "application/json"})
    try:
        x = urllib.request.urlopen(r, timeout=120); return x.status, dict(x.headers), (x.read().decode() or "{}")
    except urllib.error.HTTPError as e: return e.code, dict(e.headers), e.read().decode()[:700]
base = "https://api.fabric.microsoft.com/v1/workspaces/" + WS
s, h, b = fab("GET", base + "/semanticModels")
existing = [m for m in json.loads(b).get("value", []) if m["displayName"] == NAME]
if existing:
    s, h, b = fab("POST", base + f"/semanticModels/{existing[0]['id']}/updateDefinition", {"definition": body["definition"]}); print("update existing model:", s)
else:
    s, h, b = fab("POST", base + "/semanticModels", body); print("create:", s)
if s == 202:
    for _ in range(30):
        time.sleep(4); s2, h2, b2 = fab("GET", h.get("Location") or h.get("location"))
        st = json.loads(b2).get("status") if b2.startswith("{") else None
        if st in ("Succeeded", "Failed"): print("operation:", st, b2[:400] if st == "Failed" else ""); break
elif s not in (200, 201): print(b)
s, h, b = fab("GET", base + "/semanticModels")
m = [m for m in json.loads(b).get("value", []) if m["displayName"] == NAME]
print("model:", m[0]["id"] if m else "NOT FOUND")
if m: json.dump({"workspace": WS, "model": m[0]["id"]}, open(_o.path.expanduser("~/bpa-edp-demo/scripts/pbi_model.json"), "w"))
