"""Data access for the buy-in editor. Every statement goes through the Databricks SDK statement-execution API with bound parameters."""
import os
import time
from datetime import date, timedelta

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem

SCHEMA = "bpa_edp.demo"
EDITABLE = {"movement_volume", "received_date", "notification_date"}
ACTIONS = {"apply", "reject"}
SOURCES = {"quarantine", "email"}
_client = None


def _w():
    global _client
    if _client is None:
        _client = WorkspaceClient()
    return _client


def run(sql, params=None):
    """Run one statement and return a list of dict rows (empty list for DML)."""
    plist = [StatementParameterListItem(name=k, value=None if v is None else str(v), type="STRING") for k, v in (params or {}).items()]
    w = _w()
    r = w.statement_execution.execute_statement(statement=sql, warehouse_id=os.environ["WAREHOUSE_ID"], parameters=plist, wait_timeout="50s")
    for _ in range(60):
        if r.status.state.value not in ("PENDING", "RUNNING"):
            break
        time.sleep(2)
        r = w.statement_execution.get_statement(r.statement_id)
    if r.status.state.value != "SUCCEEDED":
        raise RuntimeError(r.status.error.message if r.status.error else str(r.status.state))
    cols = [c.name for c in r.manifest.schema.columns] if r.manifest and r.manifest.schema else []
    rows = r.result.data_array if r.result and r.result.data_array else []
    return [dict(zip(cols, row)) for row in rows]


def validate(column_name, value, notification_date=None):
    """Return (True, cleaned_text) or (False, message). Used by the UI and again before every save."""
    if column_name not in EDITABLE:
        return False, f"{column_name} cannot be edited here."
    text = "" if value is None else str(value).strip()
    if not text:
        return False, "Enter a value."
    if column_name == "movement_volume":
        try:
            n = int(text)
        except ValueError:
            return False, "Volume must be a whole number."
        if n < 0:
            return False, "Volume cannot be negative."
        return True, str(n)
    try:
        d = date.fromisoformat(text)
    except ValueError:
        return False, "Use the date format YYYY-MM-DD."
    if column_name == "received_date" and notification_date:
        n = date.fromisoformat(str(notification_date)[:10])
        if d < n:
            return False, f"Received date cannot be before the notification date ({n.isoformat()})."
        if d > n + timedelta(days=365):
            return False, "Received date is more than a year after notification; check it."
    return True, d.isoformat()


def unresolved_cells():
    """Invalid Excel cells that still have no correction (auto-corrected text dates are skipped)."""
    return run(f"""
        SELECT q.log_id, q.scheme, q.column_name, q.raw_value, q.reason, s.notification_date,
               e.members_to_move AS email_volume, e.received_date AS email_received_date
        FROM {SCHEMA}.buyin_quarantine q
        JOIN {SCHEMA}.silver_buyin_log s ON s.log_id = q.log_id
        LEFT JOIN (SELECT log_id, max(members_to_move) AS members_to_move, max(received_date) AS received_date
                   FROM {SCHEMA}.email_suggestions WHERE log_id IS NOT NULL GROUP BY log_id) e ON e.log_id = q.log_id
        WHERE q.fixed_value IS NULL AND q.column_name IN ('movement_volume', 'received_date')
          AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.buyin_corrections c WHERE c.log_id = q.log_id AND c.column_name = q.column_name)
        ORDER BY q.log_id, q.column_name""")


def review_emails():
    """Email extractions that do not match the Excel log and have not been decided yet."""
    return run(f"""
        SELECT es.scheme, es.trustee, es.members_to_move, es.notified_date, es.received_date, es.log_id, es.excel_volume, es.review_status
        FROM {SCHEMA}.email_suggestions es
        WHERE es.review_status <> 'matches Excel'
          AND NOT EXISTS (SELECT 1 FROM {SCHEMA}.buyin_corrections c WHERE c.log_id = es.log_id AND c.source = 'email')
        ORDER BY es.scheme""")


def email_counts():
    rows = run(f"SELECT review_status, count(*) AS n FROM {SCHEMA}.email_suggestions GROUP BY review_status")
    return {r["review_status"]: int(r["n"]) for r in rows}


def recent_corrections(limit=15):
    return run(f"""SELECT edited_at, edited_by, log_id, column_name, corrected_value, action, source, reason
                   FROM {SCHEMA}.buyin_corrections ORDER BY edited_at DESC LIMIT {int(limit)}""")


def save_correction(log_id, column_name, value, action, reason, source, edited_by):
    """Append one correction row. Validates again server-side; raises ValueError on bad input."""
    if action not in ACTIONS or source not in SOURCES or column_name not in EDITABLE:
        raise ValueError("Unsupported action, source or column.")
    if not log_id:
        raise ValueError("A log entry is required.")
    corrected = None
    if action == "apply":
        notif = None
        if column_name == "received_date":
            rows = run(f"SELECT notification_date FROM {SCHEMA}.silver_buyin_log WHERE log_id = :log_id", {"log_id": log_id})
            notif = rows[0]["notification_date"] if rows else None
        ok, res = validate(column_name, value, notif)
        if not ok:
            raise ValueError(res)
        corrected = res
    run(f"""INSERT INTO {SCHEMA}.buyin_corrections
            SELECT uuid(), :log_id, :column_name, :corrected_value, :action, :reason, :source, :edited_by, current_timestamp()""",
        {"log_id": log_id, "column_name": column_name, "corrected_value": corrected, "action": action,
         "reason": (reason or "")[:500], "source": source, "edited_by": edited_by or "unknown"})


def accept_email(log_id, volume, edited_by):
    save_correction(log_id, "movement_volume", volume, "apply", "Accepted the value extracted from the trustee email", "email", edited_by)


def reject_email(log_id, edited_by):
    save_correction(log_id, "movement_volume", None, "reject", "Rejected the value extracted from the trustee email", "email", edited_by)


# ---- Inbound emails (Power Automate -> SharePoint -> Lakeflow Connect) -------------------------------------------
PAYLOAD_FIELDS = ("scheme", "trustee", "movement_volume", "notification_date", "received_date")
REVIEW_STATUSES = {"confirmed", "rejected"}
MODEL = "databricks-gpt-oss-120b"


def inbound_emails():
    """Every email the flow delivered, newest first, with the latest review decision if there is one."""
    return run(f"""
        SELECT e.message_id, e.received_at, e.from_name, e.from_address, e.subject, e.body_text, e.file_name,
               coalesce(r.status, 'to review') AS review_status, r.payload_json, r.edited_by, r.edited_at, r.reason
        FROM {SCHEMA}.inbound_emails e
        LEFT JOIN {SCHEMA}.inbound_email_latest r ON r.message_id = e.message_id
        ORDER BY e.received_at DESC""")


def _prompt(subject, sender, body):
    return ("You read one email sent to a pension buy-in operations team and turn it into a record. Reply with ONLY a JSON object, no prose, "
            "with these keys: scheme (string, the pension scheme name exactly as written, or null), trustee (string, the name of whoever signed the email if there is a signature, otherwise the sender name), "
            "movement_volume (integer number of members moving, or null if no firm number is given), notification_date (YYYY-MM-DD, date the "
            "trustees first notified us, or null), received_date (YYYY-MM-DD, date the documents were sent or received, or null), "
            "confidence (high, medium or low), note (one short sentence on anything vague, missing or inferred). "
            "Never guess: use null when the email does not say. If a date has no year use 2026.\n\n"
            f"From: {sender}\nSubject: {subject}\n\n{body}")


def extract_payload(subject, sender, body):
    """Run ai_query over one email. Returns (payload dict, raw text). Never raises on a bad model reply: returns empty fields and a note."""
    import json
    import re
    rows = run(f"SELECT ai_query('{MODEL}', :prompt) AS reply", {"prompt": _prompt(subject, sender, body)[:6000]})
    raw = rows[0]["reply"] if rows else ""
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        obj = json.loads(m.group(0)) if m else {}
    except ValueError:
        obj = {}
    payload = {k: obj.get(k) for k in PAYLOAD_FIELDS}
    payload["confidence"] = obj.get("confidence") if obj.get("confidence") in ("high", "medium", "low") else "low"
    payload["note"] = obj.get("note") or ("The model reply could not be read; fill the fields by hand." if not obj else "")
    # Confidence is not left to the model: a hedged number is low, and a missing key field caps it at medium.
    if payload["movement_volume"] is not None and re.search(r"\b(around|approx\w*|about|roughly|circa|give or take|estimate\w*|ish)\b", body or "", re.I):
        payload["confidence"] = "low"
        payload["note"] = "The email hedges the number of members (for example 'around'), so check it. " + payload["note"]
    elif payload["confidence"] == "high" and any(payload[k] is None for k in ("movement_volume", "notification_date", "received_date")):
        payload["confidence"] = "medium"
    return payload, raw


def log_matches(scheme, notification_date):
    """Existing buy-in log entries this email might belong to. With a notification date: same scheme and date. Without one: the scheme's pending entries."""
    if not scheme:
        return []
    if not notification_date:
        return run(f"""SELECT log_id, scheme, notification_date, received_date, movement_volume, status
                       FROM {SCHEMA}.silver_buyin_log WHERE scheme = :scheme AND status = 'pending' ORDER BY log_id""", {"scheme": scheme})
    return run(f"""SELECT log_id, scheme, notification_date, received_date, movement_volume, status
                   FROM {SCHEMA}.silver_buyin_log WHERE scheme = :scheme AND notification_date = :nd ORDER BY log_id""",
               {"scheme": scheme, "nd": notification_date})


def validate_payload(p):
    """Return (clean payload, list of problems). Reuses the same rules as the cell editor."""
    problems, clean = [], {"scheme": (p.get("scheme") or "").strip(), "trustee": (p.get("trustee") or "").strip()}
    if not clean["scheme"]:
        problems.append("Scheme is required.")
    for col in ("movement_volume", "notification_date", "received_date"):
        raw = p.get(col)
        if raw is None or str(raw).strip() == "":
            clean[col] = None
            continue
        ok, res = validate(col, raw, clean.get("notification_date") if col == "received_date" else None)
        if ok:
            clean[col] = int(res) if col == "movement_volume" else res
        else:
            clean[col] = None
            problems.append(f"{col.replace('_', ' ').capitalize()}: {res}")
    return clean, problems


def save_email_review(message_id, status, payload, original, reason, edited_by):
    """Append one review row. status is confirmed or rejected; a confirmed payload must validate."""
    import json
    if status not in REVIEW_STATUSES:
        raise ValueError("Unsupported status.")
    if not message_id:
        raise ValueError("An email is required.")
    stored = None
    if status == "confirmed":
        clean, problems = validate_payload(payload)
        if problems:
            raise ValueError(" ".join(problems))
        clean.update({"source": "email", "message_id": message_id})
        stored = json.dumps(clean)
    elif not (reason or "").strip():
        raise ValueError("Say why the email is rejected.")
    run(f"""INSERT INTO {SCHEMA}.inbound_email_review
            SELECT uuid(), :message_id, :status, :payload, :original, :reason, :edited_by, current_timestamp()""",
        {"message_id": message_id, "status": status, "payload": stored, "original": json.dumps(original or {}),
         "reason": (reason or "")[:500], "edited_by": edited_by or "unknown"})
