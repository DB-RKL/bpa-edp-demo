"""Rehearse a live change: set one planner step's status in Dataverse and follow it to Databricks.
usage: rehearse_planner_edit.py edit <new_status>   (picks the step and records state in /tmp/planner_rehearsal.json)
       rehearse_planner_edit.py follow               (waits for the export window to close, runs the pipeline, prints before/after)"""
import sys as _s, os as _o; _s.path.insert(0, _o.path.expanduser("~/bpa-edp-demo/scripts"))
import json, re, subprocess, time, urllib.request, urllib.parse, urllib.error
import run_sql as R, wsapi
ORG = "https://YOUR-ORG.crm.dynamics.com"; SA = "YOUR_STORAGE_ACCOUNT"; C = "dataverse-YOUR-ORG-UNIQUE-ID"; STATE = "/tmp/planner_rehearsal.json"
def dvtok(): return subprocess.run(["az", "account", "get-access-token", "--tenant", "<CORP_TENANT_ID>", "--resource", ORG, "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True).stdout.strip()
def sq(s):
    d = R.run(s, R.token()); return d["result"]["data_array"] if d["status"]["state"] == "SUCCEEDED" else "ERR " + d["status"]["error"]["message"][:200]
def snapshot(scheme):
    return {"scheme_row": sq(f"SELECT current_step, steps_done, overdue_steps FROM bpa_edp.demo.gold_planner_overdue_by_scheme WHERE scheme = '{scheme}'"),
            "totals": sq("SELECT sum(overdue_steps), (SELECT count(*) FROM bpa_edp.demo.silver_planner_steps WHERE status='Done') FROM bpa_edp.demo.gold_planner_status")}
def stor():
    d = json.load(open(_o.path.expanduser("~/.bpa-edp/corp/sp.json")))
    data = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": d["appId"], "client_secret": d["password"], "scope": "https://storage.azure.com/.default"}).encode()
    return json.load(urllib.request.urlopen(f"https://login.microsoftonline.com/{d['tenant']}/oauth2/v2.0/token", data, timeout=30))["access_token"]
def get(url, t):
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": "Bearer " + t, "x-ms-version": "2023-11-03"}), timeout=60); return r.status, r.read().decode()
    except urllib.error.HTTPError as e: return e.code, ""
if _s.argv[1] == "edit":
    new = _s.argv[2]
    if new == "Done":
        row = sq("SELECT p.Id, a.name, p.new_stepno, p.new_stepname, p.new_status FROM bpa_edp.demo.d365_planner_step p JOIN bpa_edp.demo.d365_account a ON a.Id = p.new_accountid WHERE p.new_status = 'In progress' AND CAST(p.new_duedate AS DATE) < current_date() AND p.new_stepno = 3 ORDER BY a.name LIMIT 1")[0]
    else:
        row = json.load(open(STATE))["target"]
    pid, scheme, no, name, old = row
    before = snapshot(scheme); t0 = time.time()
    r = urllib.request.Request(f"{ORG}/api/data/v9.2/new_plannersteps({pid})", data=json.dumps({"new_status": new}).encode(), method="PATCH", headers={"Authorization": "Bearer " + dvtok(), "Content-Type": "application/json", "OData-Version": "4.0"})
    print("PATCH", urllib.request.urlopen(r, timeout=60).status, f"{scheme} step {no} {name}: {old} -> {new}")
    json.dump({"target": [pid, scheme, no, name, old if new == "Done" else "Done"], "new": new, "edit_epoch": t0, "before": before}, open(STATE, "w"))
    print("before:", before)
else:
    st = json.load(open(STATE)); pid = st["target"][0]; t = stor(); hit = None; t0 = st["edit_epoch"]
    for i in range(36):
        s, b = get(f"https://{SA}.dfs.core.windows.net/{C}?resource=filesystem&recursive=true&maxResults=5000", t)
        paths = json.loads(b).get("paths", []) if s == 200 else []
        for p in paths:
            n = p["name"]
            from email.utils import parsedate_to_datetime
            written = parsedate_to_datetime(p["lastModified"]).timestamp() if p.get("lastModified") else 0
            if n.endswith(".csv") and "/new_plannerstep/" in n and re.match(r"^\d{4}-\d\d-\d\dT", n) and "Athena" not in n and written > t0 - 2:
                s2, body = get(f"https://{SA}.dfs.core.windows.net/{C}/{n}", t)
                if pid in body and st["new"] in body: hit = (n, round(time.time() - t0)); break
        if hit: break
        time.sleep(15)
    print("row appears in export:", hit)
    if not hit: _s.exit("not in export yet")
    folder = hit[0].split("/")[0]
    for i in range(30):
        s, ch = get(f"https://{SA}.dfs.core.windows.net/{C}/Changelog/changelog.info", t)
        if ch.strip() > folder: print(f"window closed (change log now {ch.strip()}) after {round(time.time()-t0)}s"); break
        time.sleep(15)
    else: _s.exit("window not closed yet")
    tok = wsapi.token(); pipe = json.load(open(_o.path.expanduser("~/bpa-edp-demo/scripts/d365_pipeline.json")))["pipeline"]
    tp = time.time(); uid = wsapi.call("POST", f"/api/2.0/pipelines/{pipe}/updates", {"full_refresh": False}, tok).get("update_id"); stt = None
    for i in range(40):
        time.sleep(10); stt = (wsapi.call("GET", f"/api/2.0/pipelines/{pipe}/updates/{uid}", tok=tok).get("update") or {}).get("state")
        if stt in ("COMPLETED", "FAILED", "CANCELED"): break
    print("pipeline:", stt, f"in {round(time.time()-tp)}s | total edit-to-table {round(time.time()-t0)}s")
    print("record now:", sq(f"SELECT new_status, SinkModifiedOn FROM bpa_edp.demo.d365_planner_step WHERE Id = '{pid}'"))
    print("before:", st["before"]); print("after :", snapshot(st["target"][1]))
    print("row counts:", sq("SELECT count(*) FROM bpa_edp.demo.d365_planner_step"))
