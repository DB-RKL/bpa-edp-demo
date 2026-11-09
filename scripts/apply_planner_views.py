"""Apply sql/07_planner_from_dataverse.sql: for each view, drop an existing TABLE or VIEW of that name first, then create it."""
import sys as _s, os as _o; _s.path.insert(0, _o.path.expanduser("~/bpa-edp-demo/scripts"))
import re, run_sql as R
tok = R.token()
def run(s):
    d = R.run(s, tok); st = d["status"]; return st["state"], (d.get("result") or {}).get("data_array"), st.get("error", {}).get("message", "")[:200]
for stmt in [x.strip() for x in open(_o.path.expanduser("~/bpa-edp-demo/sql/07_planner_from_dataverse.sql")).read().split("\n;\n") if x.strip()]:
    body = "\n".join(l for l in stmt.split("\n") if not l.startswith("--")).strip()
    name = re.search(r"VIEW (bpa_edp\.demo\.\w+)", body).group(1)
    st, rows, err = run(f"SELECT table_type FROM bpa_edp.information_schema.tables WHERE table_schema='demo' AND table_name='{name.split('.')[-1]}'")
    kind = rows[0][0] if rows else None
    if kind == "VIEW": pass
    elif kind: print("  dropping table", name, run(f"DROP TABLE {name}")[0])
    print(name, run(body)[0], run(body)[2] if False else "")
