"""BPA pricing write-back app: review scheme terms and record assumption overrides.

Reads bpa_edp.demo.pricing_gold and appends to bpa_edp.demo.pricing_assumptions, so the
dashboard and Genie space see the edit on their next query (same governed data).
"""
import os
from datetime import datetime, timezone

import uvicorn
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem as P
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

WAREHOUSE_ID = os.environ["WAREHOUSE_ID"]
CATALOG, SCHEMA = "bpa_edp", "demo"
w = WorkspaceClient()
app = FastAPI()


def query(sql, params=None):
    r = w.statement_execution.execute_statement(statement=sql, warehouse_id=WAREHOUSE_ID, parameters=params or [], wait_timeout="50s")
    if r.status.state.value != "SUCCEEDED":
        raise RuntimeError(r.status.error.message if r.status.error else str(r.status.state))
    cols = [c.name for c in r.manifest.schema.columns]
    return [dict(zip(cols, row)) for row in (r.result.data_array or [])]


class Override(BaseModel):
    accountid: str
    discount_rate_override_pct: float | None = None
    expense_loading_override_pct: float | None = None
    note: str = ""


@app.get("/api/schemes")
def schemes():
    return query(f"SELECT accountid, scheme_name, members, liability_gbp_m, longevity_basis, doc_discount_rate_pct, discount_rate_pct, "
                 f"expense_loading_pct, benchmark_premium_pct, indicative_premium_gbp_m, opportunities, has_override, override_note, updated_by, updated_at "
                 f"FROM {CATALOG}.{SCHEMA}.pricing_gold ORDER BY indicative_premium_gbp_m DESC")


@app.post("/api/override")
def override(o: Override, request: Request):
    who = request.headers.get("x-forwarded-email") or "unknown"
    if o.discount_rate_override_pct is not None and not 0 < o.discount_rate_override_pct < 15:
        return JSONResponse({"error": "discount rate must be between 0 and 15 percent"}, status_code=400)
    if o.expense_loading_override_pct is not None and not 0 <= o.expense_loading_override_pct < 10:
        return JSONResponse({"error": "expense loading must be between 0 and 10 percent"}, status_code=400)
    query(f"INSERT INTO {CATALOG}.{SCHEMA}.pricing_assumptions VALUES (:a, :d, :e, :n, :u, :t)", [
        P("a", o.accountid, "STRING"),
        P("d", None if o.discount_rate_override_pct is None else str(o.discount_rate_override_pct), "DOUBLE"),
        P("e", None if o.expense_loading_override_pct is None else str(o.expense_loading_override_pct), "DOUBLE"),
        P("n", o.note[:500], "STRING"), P("u", who, "STRING"),
        P("t", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "TIMESTAMP")])
    return {"ok": True, "updated_by": who}


@app.get("/")
def index():
    return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("DATABRICKS_APP_PORT", "8000")))
