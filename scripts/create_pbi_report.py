"""Create (or update) the Power BI report 'BPA buy-in SLA' on the DirectQuery semantic model, via the Fabric REST API (PBIR-Legacy layout).
Needs the model from create_pbi_model.py (with its measures). Page: 3 KPI cards, breach rate by month, breach rate by trustee, scheme table.
The visuals only reference measures/columns defined in the model; the numbers come from the Databricks metric views through DirectQuery."""
import sys as _s, os as _o; _s.path.insert(0, _o.path.expanduser("~/bpa-edp-demo/scripts"))
import base64, json, subprocess, time, urllib.request, urllib.error

M = json.load(open(_o.path.expanduser("~/bpa-edp-demo/scripts/pbi_model.json"))); WS, MODEL = M["workspace"], M["model"]
MODEL_NAME, WS_NAME, REPORT = "BPA buy-in (Databricks DirectQuery)", "bpa-edp-demo-corp", "BPA buy-in SLA (Databricks DirectQuery)"
THEME = open(_o.path.expanduser("~/bpa-edp-demo/scripts/pbi_basetheme_CY23SU04.json"), "rb").read()


def lit(v): return {"expr": {"Literal": {"Value": v}}}


def sel(kind, table, prop):
    return {kind: {"Expression": {"SourceRef": {"Source": "t"}}, "Property": prop}, "Name": f"{table}.{prop}", "NativeReferenceName": prop}


def visual(name, vtype, table, selects, roles, x, y, w, h, title, order=None, z=1000):
    """selects: list of (kind, prop); roles: {role: [prop,...]}"""
    q = {"Version": 2, "From": [{"Name": "t", "Entity": table, "Type": 0}], "Select": [sel(k, table, p) for k, p in selects]}
    if order:
        k, p, direction = order
        q["OrderBy"] = [{"Direction": direction, "Expression": {k: {"Expression": {"SourceRef": {"Source": "t"}}, "Property": p}}}]
    proj = {r: [dict({"queryRef": f"{table}.{p}"}, **({"active": True} if r == "Category" else {})) for p in ps] for r, ps in roles.items()}
    cfg = {"name": name, "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": z}}],
           "singleVisual": {"visualType": vtype, "projections": proj, "prototypeQuery": q, "drillFilterOtherVisuals": True, "hasDefaultSort": True,
                            "vcObjects": {"title": [{"properties": {"show": lit("true"), "text": lit("'" + title + "'")}}]}}}
    return {"config": json.dumps(cfg), "filters": "[]", "height": h, "width": w, "x": x, "y": y, "z": z}


V = [
    visual("a1c00000000000000001", "card", "sla_overall", [("Measure", "Total entries")], {"Values": ["Total entries"]}, 20, 20, 290, 120, "Buy-in entries logged", z=1000),
    visual("a1c00000000000000002", "card", "sla_overall", [("Measure", "Breach rate %")], {"Values": ["Breach rate %"]}, 330, 20, 290, 120, "SLA breach rate (%)", z=2000),
    visual("a1c00000000000000003", "card", "sla_overall", [("Measure", "Pending count")], {"Values": ["Pending count"]}, 640, 20, 290, 120, "Pending items", z=3000),
    visual("a1c00000000000000004", "clusteredColumnChart", "sla_by_month", [("Column", "month"), ("Measure", "Month breach rate %")],
           {"Category": ["month"], "Y": ["Month breach rate %"]}, 20, 160, 620, 260, "SLA breach rate by month (%)", order=("Column", "month", 1), z=4000),
    visual("a1c00000000000000005", "clusteredBarChart", "sla_by_trustee", [("Column", "trustee_contact"), ("Measure", "Trustee breach rate %")],
           {"Category": ["trustee_contact"], "Y": ["Trustee breach rate %"]}, 660, 160, 600, 260, "SLA breach rate by trustee contact (%)", order=("Measure", "Trustee breach rate %", 2), z=5000),
    visual("a1c00000000000000006", "tableEx", "scheme_status",
           [("Column", "scheme"), ("Column", "current_step"), ("Measure", "Overdue steps"), ("Measure", "Members moved %"), ("Measure", "Scheme SLA breaches"), ("Measure", "Scheme pending items")],
           {"Values": ["scheme", "current_step", "Overdue steps", "Members moved %", "Scheme SLA breaches", "Scheme pending items"]}, 20, 440, 1240, 260,
           "Schemes: planner step, overdue steps and buy-in SLA (sorted by overdue steps)", order=("Measure", "Overdue steps", 2), z=6000),
]
report = {
    "config": json.dumps({"version": "5.43", "themeCollection": {"baseTheme": {"name": "CY23SU04", "version": "5.43", "type": 2}}, "activeSectionIndex": 0,
                          "defaultDrillFilterOtherVisuals": True, "settings": {"useNewFilterPaneExperience": True, "allowChangeFilterTypes": True, "useStylableVisualContainerHeader": True,
                                                                              "exportDataMode": 1, "useDefaultAggregateDisplayName": True, "useEnhancedTooltips": True}}),
    "layoutOptimization": 0,
    "resourcePackages": [{"resourcePackage": {"disabled": False, "items": [{"name": "CY23SU04", "path": "BaseThemes/CY23SU04.json", "type": 202}], "name": "SharedResources", "type": 2}}],
    "sections": [{"config": "{}", "displayName": "BPA buy-in SLA", "displayOption": 1, "filters": "[]", "height": 720.0, "name": "bpaBuyinSla0001", "ordinal": 0, "visualContainers": V, "width": 1280.0}],
}
pbir = {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json", "version": "4.0",
        "datasetReference": {"byConnection": {"connectionString": f'Data Source="powerbi://api.powerbi.com/v1.0/myorg/{WS_NAME}";initial catalog={MODEL_NAME};integrated security=ClaimsToken;semanticmodelid={MODEL}'}}}
files = {"definition.pbir": json.dumps(pbir, indent=2).encode(), "report.json": json.dumps(report).encode(), "StaticResources/SharedResources/BaseThemes/CY23SU04.json": THEME}
body = {"displayName": REPORT, "definition": {"parts": [{"path": p, "payload": base64.b64encode(c).decode(), "payloadType": "InlineBase64"} for p, c in files.items()]}}

ft = subprocess.run(["az", "account", "get-access-token", "--tenant", "<CORP_TENANT_ID>", "--resource", "https://api.fabric.microsoft.com", "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True).stdout.strip()
def fab(method, url, b=None):
    r = urllib.request.Request(url, data=None if b is None else json.dumps(b).encode(), method=method, headers={"Authorization": "Bearer " + ft, "Content-Type": "application/json"})
    try:
        x = urllib.request.urlopen(r, timeout=120); return x.status, dict(x.headers), (x.read().decode() or "{}")
    except urllib.error.HTTPError as e: return e.code, dict(e.headers), e.read().decode()[:1500]
def lro(s, h, b):
    if s != 202: return s, b
    loc = h.get("Location") or h.get("location")
    for _ in range(40):
        time.sleep(4); s2, h2, b2 = fab("GET", loc)
        j = json.loads(b2) if b2.startswith("{") else {}
        if j.get("status") in ("Succeeded", "Failed"): return j["status"], json.dumps(j.get("error")) if j.get("status") == "Failed" else ""
    return "Timeout", ""
base = f"https://api.fabric.microsoft.com/v1/workspaces/{WS}"
existing = [r for r in json.loads(fab("GET", base + "/reports")[2]).get("value", []) if r["displayName"] == REPORT]
if existing:
    rid = existing[0]["id"]; st = lro(*fab("POST", base + f"/reports/{rid}/updateDefinition", {"definition": body["definition"]})); print("update existing report:", st)
else:
    st = lro(*fab("POST", base + "/reports", body)); print("create report:", st)
reps = [r for r in json.loads(fab("GET", base + "/reports")[2]).get("value", []) if r["displayName"] == REPORT]
if reps:
    json.dump({"workspace": WS, "report": reps[0]["id"]}, open(_o.path.expanduser("~/bpa-edp-demo/scripts/pbi_report.json"), "w"))
    print("report id:", reps[0]["id"], "\nlink: https://app.fabric.microsoft.com/groups/%s/reports/%s" % (WS, reps[0]["id"]))
else: print("NOT CREATED")
