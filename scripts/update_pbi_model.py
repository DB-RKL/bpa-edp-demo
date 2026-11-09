"""Re-publish the DirectQuery semantic model definition with a different Databricks connector option set, then test it with DAX.
usage: update_pbi_model.py <variant>   variants: baseline | catalog_null | adbc"""
import sys as _s, os as _o; _s.path.insert(0, _o.path.expanduser("~/bpa-edp-demo/scripts"))
import base64, json, subprocess, time, urllib.request, urllib.error
import wsapi
VARIANT = _s.argv[1]
OPTS = {"baseline": 'Catalog = "bpa_edp", Database = null, EnableAutomaticProxyDiscovery = null',
        "catalog_null": 'Catalog = null, Database = null, EnableAutomaticProxyDiscovery = null',
        "adbc": 'Catalog = null, Database = null, EnableAutomaticProxyDiscovery = null, Implementation = "2.0"'}[VARIANT]
m = json.load(open(_o.path.expanduser("~/bpa-edp-demo/scripts/pbi_model.json"))); WS, MODEL = m["workspace"], m["model"]
HOST = wsapi.H.replace("https://", ""); PATH = "/sql/1.0/warehouses/" + wsapi.WH
VIEWS = {"sla_overall": "pbi_sla_overall", "sla_by_month": "pbi_sla_by_month", "sla_by_trustee": "pbi_sla_by_trustee", "scheme_status": "pbi_scheme_status"}
TYPES = {"STRING": "string", "LONG": "int64", "INT": "int64", "DOUBLE": "double", "DATE": "dateTime", "TIMESTAMP": "dateTime"}
NOSUM = {"breach_rate_pct", "avg_days_late", "pct_members_moved", "month", "target_buyout_date"}
cols = json.load(open("/tmp/pbi_cols.json"))
def table_tmdl(t, view):
    L = [f"table {t}", ""]
    for c, ty in cols[view]:
        dt = TYPES[ty]; L += [f"\tcolumn {c}", f"\t\tdataType: {dt}"]
        if dt == "int64": L.append("\t\tformatString: 0")
        elif dt == "double": L.append("\t\tformatString: 0.0")
        elif dt == "dateTime": L.append("\t\tformatString: " + ("yyyy-MM" if c == "month" else "yyyy-MM-dd"))
        L += [f"\t\tsourceColumn: {c}", "\t\tsummarizeBy: " + ("none" if (dt in ("string", "dateTime") or c in NOSUM) else "sum"), ""]
    L += [f"\tpartition {t} = m", "\t\tmode: directQuery", "\t\tsource =", "\t\t\t\tlet",
          f'\t\t\t\t\tSource = Databricks.Catalogs("{HOST}", "{PATH}", [{OPTS}]),', '\t\t\t\t\tdb = Source{[Name = "bpa_edp", Kind = "Database"]}[Data],',
          '\t\t\t\t\tsch = db{[Name = "demo", Kind = "Schema"]}[Data],', f'\t\t\t\t\tobj = sch{{[Name = "{view}", Kind = "View"]}}[Data]', "\t\t\t\tin", "\t\t\t\t\tobj", ""]
    return "\n".join(L)
parts = {"definition.pbism": json.dumps({"version": "4.0", "settings": {}}), "definition/database.tmdl": "database\n\tcompatibilityLevel: 1604\n",
         "definition/model.tmdl": "model Model\n\tculture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\n" + "\n".join(f"ref table {t}" for t in VIEWS) + "\n"}
for t, v in VIEWS.items(): parts[f"definition/tables/{t}.tmdl"] = table_tmdl(t, v)
body = {"definition": {"parts": [{"path": p, "payload": base64.b64encode(c.encode()).decode(), "payloadType": "InlineBase64"} for p, c in parts.items()]}}
def tok(res): return subprocess.run(["az", "account", "get-access-token", "--tenant", "<CORP_TENANT_ID>", "--resource", res, "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True).stdout.strip()
ft, pt = tok("https://api.fabric.microsoft.com"), tok("https://analysis.windows.net/powerbi/api")
def http(method, url, token, b=None):
    r = urllib.request.Request(url, data=None if b is None else json.dumps(b).encode(), method=method, headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    try:
        x = urllib.request.urlopen(r, timeout=240); return x.status, dict(x.headers), x.read().decode()
    except urllib.error.HTTPError as e: return e.code, dict(e.headers), e.read().decode()
s, h, b = http("POST", f"https://api.fabric.microsoft.com/v1/workspaces/{WS}/semanticModels/{MODEL}/updateDefinition", ft, body)
print("variant:", VARIANT, "| update:", s)
if s == 202:
    for _ in range(30):
        time.sleep(4); s2, h2, b2 = http("GET", h.get("Location") or h.get("location"), ft)
        if json.loads(b2).get("status") in ("Succeeded", "Failed"): print("  operation:", json.loads(b2).get("status")); break
time.sleep(15)
def dax(q):
    s, h, b = http("POST", f"https://api.powerbi.com/v1.0/myorg/groups/{WS}/datasets/{MODEL}/executeQueries", pt, {"queries": [{"query": q}], "serializerSettings": {"includeNulls": True}})
    if s == 200: return json.loads(b)["results"][0]["tables"][0]["rows"]
    try: return "HTTP %d: %s" % (s, [x["detail"]["value"][:230] for x in json.loads(b)["error"]["pbi.error"]["details"]][:1])
    except Exception: return "HTTP %d: %s" % (s, b[:200])
print("  sla_overall:", dax("EVALUATE sla_overall"))
