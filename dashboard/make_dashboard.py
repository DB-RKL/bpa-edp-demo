import json, subprocess, urllib.request, os
import json as _json, os as _os
_cfg = _json.load(open(_os.path.expanduser("~/bpa-edp-demo/scripts/workspace.json")))
H = _cfg["host"]; WH = _cfg["warehouse_id"]
tok = subprocess.run(["az", "account", "get-access-token", "--tenant", "<SANDBOX_TENANT_ID>", "--resource",
    "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d", "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True).stdout.strip()

GOLD = "SELECT * FROM bpa_edp.demo.pricing_gold"

def counter(name, expr, title, x, w=2):
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": {"datasetName": "gold", "fields": [{"name": "v", "expression": expr}], "disaggregated": False}}],
            "spec": {"version": 2, "widgetType": "counter", "encodings": {"value": {"fieldName": "v", "displayName": title}}, "frame": {"title": title, "showTitle": True}}},
            "position": {"x": x, "y": 0, "width": w, "height": 3}}

bar = {"widget": {"name": "premium_by_scheme", "queries": [{"name": "main_query", "query": {"datasetName": "gold", "fields": [
        {"name": "scheme_name", "expression": "`scheme_name`"}, {"name": "premium", "expression": "SUM(`indicative_premium_gbp_m`)"}], "disaggregated": False}}],
       "spec": {"version": 3, "widgetType": "bar", "encodings": {
           "x": {"fieldName": "scheme_name", "scale": {"type": "categorical"}, "displayName": "Scheme"},
           "y": {"fieldName": "premium", "scale": {"type": "quantitative"}, "displayName": "Indicative premium (GBP m)"}},
           "frame": {"title": "Indicative premium by scheme", "showTitle": True}}},
       "position": {"x": 0, "y": 3, "width": 6, "height": 7}}

cols = ["scheme_name", "members", "liability_gbp_m", "longevity_basis", "discount_rate_pct", "expense_loading_pct", "benchmark_premium_pct", "indicative_premium_gbp_m", "opportunities", "open_pipeline_gbp_m", "has_override", "source_document"]
table = {"widget": {"name": "scheme_table", "queries": [{"name": "main_query", "query": {"datasetName": "gold", "fields": [{"name": c, "expression": f"`{c}`"} for c in cols], "disaggregated": True}}],
         "spec": {"version": 1, "widgetType": "table", "encodings": {"columns": [{"fieldName": c, "displayName": c.replace("_", " ")} for c in cols]},
                  "frame": {"title": "Scheme pricing (document terms + pipeline + benchmark)", "showTitle": True}}},
         "position": {"x": 0, "y": 10, "width": 6, "height": 9}}

dash = {"datasets": [{"name": "gold", "displayName": "pricing_gold", "queryLines": [GOLD]}],
        "pages": [{"name": "overview", "displayName": "BPA pricing on the EDP", "pageType": "PAGE_TYPE_CANVAS", "layout": [
            counter("c_liab", "SUM(`liability_gbp_m`)", "Liability in scope (GBP m)", 0),
            counter("c_prem", "SUM(`indicative_premium_gbp_m`)", "Indicative premium (GBP m)", 2),
            counter("c_pipe", "SUM(`open_pipeline_gbp_m`)", "Open pipeline (GBP m)", 4),
            bar, table]}]}

body = {"display_name": "BPA pricing and reporting (EDP demo)", "warehouse_id": WH,
        "parent_path": "/Workspace/Users/you@example.com", "serialized_dashboard": json.dumps(dash)}
r = urllib.request.Request(H + "/api/2.0/lakeview/dashboards", data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
try:
    d = json.load(urllib.request.urlopen(r))
    print("created", d["dashboard_id"], d.get("path"))
    json.dump(d, open(os.path.expanduser("~/bpa-edp-demo/dashboard/created.json"), "w"))
except urllib.error.HTTPError as e:
    print(e.code, e.read().decode()[:600])
