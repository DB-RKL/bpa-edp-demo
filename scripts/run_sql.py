import json, subprocess, sys, urllib.request, time
import json as _json, os as _os
_cfg = _json.load(open(_os.path.expanduser("~/bpa-edp-demo/scripts/workspace.json")))
H = _cfg["host"]; WH = _cfg["warehouse_id"]
def token():
    return subprocess.run(["az", "account", "get-access-token", "--tenant", "<SANDBOX_TENANT_ID>",
        "--resource", "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d", "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True).stdout.strip()
def run(sql, tok):
    body = json.dumps({"warehouse_id": WH, "statement": sql, "wait_timeout": "50s"}).encode()
    r = urllib.request.Request(H + "/api/2.0/sql/statements", data=body, headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(r, timeout=120))
    while d["status"]["state"] in ("PENDING", "RUNNING"):
        time.sleep(5)
        r = urllib.request.Request(H + "/api/2.0/sql/statements/" + d["statement_id"], headers={"Authorization": "Bearer " + tok})
        d = json.load(urllib.request.urlopen(r, timeout=120))
    return d
if __name__ == "__main__":
    tok = token()
    for i, stmt in enumerate([s.strip() for s in open(sys.argv[1]).read().split("\n;\n") if s.strip()], 1):
        d = run(stmt, tok); s = d["status"]
        print(i, s["state"], s.get("error", {}).get("message", "")[:400], "|", stmt.split("\n")[0][:70])
        if s["state"] != "SUCCEEDED": sys.exit(1)
