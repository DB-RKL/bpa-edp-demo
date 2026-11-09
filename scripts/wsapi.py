"""Tiny REST helper for the Azure Databricks workspace named in workspace.json (az token for the sandbox tenant)."""
import json, os, subprocess, time, urllib.request, urllib.error
_cfg = json.load(open(os.path.expanduser("~/bpa-edp-demo/scripts/workspace.json")))
H, WH = _cfg["host"], _cfg["warehouse_id"]


def token():
    return subprocess.run(["az", "account", "get-access-token", "--tenant", "<SANDBOX_TENANT_ID>", "--resource",
                           "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d", "--query", "accessToken", "-o", "tsv"], capture_output=True, text=True).stdout.strip()


def call(method, path, body=None, tok=None):
    r = urllib.request.Request(H + path, data=None if body is None else json.dumps(body).encode(), method=method,
                               headers={"Authorization": "Bearer " + (tok or token()), "Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(r, timeout=120).read().decode() or "{}", strict=False)
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:600]}


def wait_pipeline(pid, tok=None, tries=40):
    for _ in range(tries):
        d = call("GET", f"/api/2.0/pipelines/{pid}", tok=tok)
        st = (d.get("latest_updates") or [{}])[0].get("state")
        if st in ("COMPLETED", "FAILED", "CANCELED"):
            return st
        time.sleep(10)
    return "TIMEOUT"
