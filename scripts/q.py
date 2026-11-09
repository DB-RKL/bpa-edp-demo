"""Run one SQL statement from stdin on the demo warehouse and print the rows as a table. Usage: python3 -I scripts/q.py <<'SQL' ... SQL"""
import sys as _s, os as _o; _s.path.insert(0, _o.path.expanduser("~/bpa-edp-demo/scripts"))
import sys, run_sql
d = run_sql.run(sys.stdin.read().strip().rstrip(";"), run_sql.token())
if d["status"]["state"] != "SUCCEEDED":
    print("FAILED", d["status"].get("error", {}).get("message", "")[:600]); sys.exit(1)
cols = [c["name"] for c in d["manifest"]["schema"]["columns"]]
print(" | ".join(cols))
for r in d.get("result", {}).get("data_array", []) or []: print(" | ".join("" if v is None else str(v) for v in r))
