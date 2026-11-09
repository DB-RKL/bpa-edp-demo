"""Create the corrections table and (re)create silver/gold/email objects as views that apply corrections.
For each 'view' object: if it is currently a table, DROP TABLE first (brief gap), otherwise just CREATE OR REPLACE VIEW (atomic)."""
import sys as _s, os as _o; _s.path.insert(0, _o.path.expanduser("~/bpa-edp-demo/scripts"))
import re, run_sql as R
tok = R.token()
def run(sql):
    d = R.run(sql, tok); st = d["status"]
    if st["state"] != "SUCCEEDED": raise SystemExit("FAILED: " + st.get("error", {}).get("message", "")[:400] + "\n" + sql[:200])
    return (d.get("result") or {}).get("data_array")
txt = open(_o.path.expanduser("~/bpa-edp-demo/sql/06_corrections_views.sql")).read()
for stmt in [s.strip() for s in txt.split("\n;\n") if s.strip()]:
    m = re.match(r"-- object: (\w+) \((table|view)\)\n", stmt); name, kind = m.group(1), m.group(2); body = stmt[m.end():]
    if kind == "view":
        cur = run(f"SELECT table_type FROM bpa_edp.information_schema.tables WHERE table_schema='demo' AND table_name='{name}'")
        if cur and cur[0][0] != "VIEW":
            run(f"DROP TABLE bpa_edp.demo.{name}"); print("  dropped table", name)
    run(body); print("ok", kind, name)
