import json, subprocess, urllib.request, os
import json as _json, os as _os
_cfg = _json.load(open(_os.path.expanduser("~/bpa-edp-demo/scripts/workspace.json")))
H = _cfg["host"]; WH = _cfg["warehouse_id"]
tok = subprocess.run(["az", "account", "get-access-token", "--tenant", "<SANDBOX_TENANT_ID>", "--resource",
    "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d", "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True).stdout.strip()

DATASETS = {
 "kpi": "SELECT count(*) AS entries, round(100 * sum(CASE WHEN sla_breached THEN 1 ELSE 0 END) / count(received_date), 1) AS breach_rate_pct, sum(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_items FROM bpa_edp.demo.silver_buyin_log",
 "month": "SELECT date_format(month, 'yyyy-MM') AS month, breach_rate_pct, entries, sla_breaches FROM bpa_edp.demo.gold_buyin_sla_month ORDER BY month",
 "trustee": "SELECT trustee_contact, breach_rate_pct, entries, avg_days_late FROM bpa_edp.demo.gold_buyin_sla_trustee ORDER BY breach_rate_pct DESC",
 "scheme": "SELECT scheme, current_step, overdue_steps, pct_members_moved, volume_notified, sla_breaches, pending_items, avg_days_late FROM bpa_edp.demo.gold_scheme_status ORDER BY overdue_steps DESC, sla_breaches DESC",
 "dq": "SELECT column_name, reason, cells, rows_affected FROM bpa_edp.demo.gold_data_quality ORDER BY cells DESC",
 "emails": "SELECT scheme, trustee, members_to_move, excel_volume, review_status, log_id FROM bpa_edp.demo.email_suggestions ORDER BY review_status, scheme",
 "planner": "SELECT step_name, step_no, SUM(overdue_steps) AS overdue_steps FROM bpa_edp.demo.gold_planner_status GROUP BY step_name, step_no ORDER BY step_no",
 "planner_schemes": "SELECT scheme, overdue_steps, steps_done, current_step FROM bpa_edp.demo.gold_planner_overdue_by_scheme ORDER BY overdue_steps DESC, scheme LIMIT 10",
}

def counter(name, ds, expr, title, x):
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": {"datasetName": ds, "fields": [{"name": "v", "expression": expr}], "disaggregated": False}}],
            "spec": {"version": 2, "widgetType": "counter", "encodings": {"value": {"fieldName": "v", "displayName": title}}, "frame": {"title": title, "showTitle": True}}},
            "position": {"x": x, "y": 0, "width": 2, "height": 3}}

def bar(name, ds, xf, yf, title, xt, yt, x, y, w):
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": {"datasetName": ds, "fields": [
            {"name": xf, "expression": f"`{xf}`"}, {"name": yf, "expression": f"SUM(`{yf}`)"}], "disaggregated": False}}],
            "spec": {"version": 3, "widgetType": "bar", "encodings": {"x": {"fieldName": xf, "scale": {"type": "categorical"}, "displayName": xt},
            "y": {"fieldName": yf, "scale": {"type": "quantitative"}, "displayName": yt}}, "frame": {"title": title, "showTitle": True}}},
            "position": {"x": x, "y": y, "width": w, "height": 6}}

def table(name, ds, cols, title, x, y, w, h):
    return {"widget": {"name": name, "queries": [{"name": "main_query", "query": {"datasetName": ds, "fields": [{"name": c, "expression": f"`{c}`"} for c in cols], "disaggregated": True}}],
            "spec": {"version": 1, "widgetType": "table", "encodings": {"columns": [{"fieldName": c, "displayName": c.replace("_", " ")} for c in cols]}, "frame": {"title": title, "showTitle": True}}},
            "position": {"x": x, "y": y, "width": w, "height": h}}

layout = [
  counter("c_entries", "kpi", "SUM(`entries`)", "Buy-in entries logged", 0),
  counter("c_breach", "kpi", "MAX(`breach_rate_pct`)", "SLA breach rate (%)", 2),
  counter("c_pending", "kpi", "SUM(`pending_items`)", "Pending items", 4),
  bar("b_month", "month", "month", "breach_rate_pct", "SLA breach rate by month (%)", "Month notified", "Breach rate %", 0, 3, 3),
  bar("b_trustee", "trustee", "trustee_contact", "breach_rate_pct", "SLA breach rate by trustee contact (%)", "Trustee contact", "Breach rate %", 3, 3, 3),
  table("t_scheme", "scheme", ["scheme", "current_step", "overdue_steps", "pct_members_moved", "volume_notified", "sla_breaches", "pending_items", "avg_days_late"], "Scheme status: planner step, SLA and movement (buy-in joined with buyout and planner)", 0, 9, 6, 9),
  table("t_dq", "dq", ["column_name", "reason", "cells", "rows_affected"], "Invalid Excel values caught (quarantined, load not failed)", 0, 18, 3, 6),
  table("t_email", "emails", ["scheme", "trustee", "members_to_move", "excel_volume", "review_status", "log_id"], "Email extraction: suggestions for staff to confirm", 3, 18, 3, 6),
  bar("b_planner", "planner", "step_name", "overdue_steps", "Overdue steps by planner step (Dataverse via Lakeflow Connect)", "Planner step", "Overdue steps", 0, 24, 3),
  table("t_pschemes", "planner_schemes", ["scheme", "overdue_steps", "steps_done", "current_step"], "Schemes with the most overdue steps (Dataverse via Lakeflow Connect)", 3, 24, 3, 6),
]
dash = {"datasets": [{"name": k, "displayName": k, "queryLines": [v]} for k, v in DATASETS.items()],
        "pages": [{"name": "overview", "displayName": "Buy-in SLA and KPIs", "pageType": "PAGE_TYPE_CANVAS", "layout": layout}]}
body = {"display_name": "BPA buy-in SLA and KPIs (EDP demo)", "warehouse_id": WH, "parent_path": "/Workspace/Users/you@example.com", "serialized_dashboard": json.dumps(dash)}
def call(method, path, b):
    r = urllib.request.Request(H + path, data=json.dumps(b).encode(), method=method, headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    try: return json.load(urllib.request.urlopen(r))
    except urllib.error.HTTPError as e: return {"error": e.code, "body": e.read().decode()[:500]}
_prev = os.path.expanduser("~/bpa-edp-demo/dashboard/created_buyin.json")
if os.path.exists(_prev):
    _id = json.load(open(_prev))["dashboard_id"]
    d = call("PATCH", f"/api/2.0/lakeview/dashboards/{_id}", {"display_name": body["display_name"], "warehouse_id": WH, "serialized_dashboard": body["serialized_dashboard"]})
    d.setdefault("dashboard_id", _id); print("update:", {k: d.get(k) for k in ["dashboard_id", "error", "body"]})
else:
    d = call("POST", "/api/2.0/lakeview/dashboards", body); print("create:", {k: d.get(k) for k in ["dashboard_id", "path", "error", "body"]})
if "dashboard_id" in d:
    print("publish:", call("POST", f"/api/2.0/lakeview/dashboards/{d['dashboard_id']}/published", {"embed_credentials": True, "warehouse_id": WH}).get("display_name"))
    json.dump(d, open(os.path.expanduser("~/bpa-edp-demo/dashboard/created_buyin.json"), "w"))
# every dataset query must run
import sys; sys.path.insert(0, os.path.expanduser("~/bpa-edp-demo/scripts")); import run_sql as R
for k, v in DATASETS.items():
    s = R.run(v, tok)["status"]; print(" dataset", k, s["state"], s.get("error", {}).get("message", "")[:120])
