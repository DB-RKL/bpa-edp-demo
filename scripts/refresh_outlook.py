"""One command after you send new emails: run the Outlook pipeline once, stop it (it retries failed runs by itself), then read the text of any
new attachments into bpa_edp.demo.outlook_attachment_text. Safe to re-run."""
import sys as _s, os as _o; _s.path.insert(0, _o.path.expanduser("~/bpa-edp-demo/scripts"))
import sys, time, wsapi, run_sql
PID = "<OUTLOOK_PIPELINE_ID>"
tok = wsapi.token()
r = wsapi.call("POST", f"/api/2.0/pipelines/{PID}/updates", {"full_refresh": False}, tok); up = r.get("update_id")
if not up: sys.exit(f"could not start the pipeline: {r}")
print("pipeline update", up[:8], flush=True); st = None
for _ in range(60):
    st = wsapi.call("GET", f"/api/2.0/pipelines/{PID}/updates/{up}", tok=tok).get("update", {}).get("state"); print(" ", st, flush=True)
    if st in ("COMPLETED", "FAILED", "CANCELED"): break
    time.sleep(10)
wsapi.call("POST", f"/api/2.0/pipelines/{PID}/stop", {}, tok)
if st != "COMPLETED": sys.exit(f"pipeline ended {st}: check the pipeline events (a 403 means the Entra app permissions or the connection token)")
t = run_sql.token()
for sql in open(_o.path.expanduser("~/bpa-edp-demo/sql/10b_attachment_text_refresh.sql")).read().split("\n;\n"):
    d = run_sql.run(sql.strip(), t); print("attachment text:", d["status"]["state"], d["status"].get("error", {}).get("message", "")[:200])
d = run_sql.run("SELECT (SELECT count(*) FROM bpa_edp.demo.outlook_email_messages), (SELECT count(*) FROM bpa_edp.demo.outlook_attachment_text)", t)
print("emails landed, attachments read:", d["result"]["data_array"][0])
