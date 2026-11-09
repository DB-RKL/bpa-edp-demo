# Buy-in log editor (Streamlit Databricks App)

App `bpa-buyin-editor`: https://bpa-buyin-editor-0000000000000000.0.azure.databricksapps.com (needs a Databricks sign-in).
Synthetic data. Corrections live in Databricks only; the Excel files on SharePoint are never changed.

## Pages
1. Fix invalid cells: the 14 quarantined cells that still need a value (9 movement volumes such as "approx 120" / #N/A, 5 received dates "TBC").
   Shows the raw value, scheme, notification date and any value from the trustee email. Validation: volume is a whole number >= 0;
   received date is ISO (YYYY-MM-DD), not before the notification date and within a year of it. The 5 text dates that were auto-corrected are not listed.
2. Review emails: email extractions that do not match the Excel log (2 today: BI-0119, BI-0211). Accept writes an 'apply' correction (source 'email'),
   Reject writes a 'reject' row (hides it, changes no figures). Also shows how many emails match (26).
Both pages end with a "Recent corrections" table (read-only audit list). The editor is the signed-in user (X-Forwarded-Email header), else 'unknown'.

## How a correction reaches the dashboards
`bpa_edp.demo.buyin_corrections` (Delta, append-only) holds one row per edit. `silver_buyin_log` is now a VIEW that applies the latest 'apply' correction per
(log_id, column_name) for movement_volume, received_date and notification_date on top of the Excel values, and adds `has_correction`. These are VIEWS too, so edits show at once:
silver_scheme_progress, gold_buyin_sla_month, gold_buyin_sla_trustee, gold_scheme_status, email_suggestions (and everything above them: metric views, pbi_* views, dashboards, Genie).
Still tables: bronze_*, buyin_quarantine, gold_data_quality (static view of the original invalid cells), email_extracted (ai_query output).
Delta history on the corrections table is a second audit trail. Undo = delete the row.

## Files
- app.py: Streamlit pages. data.py: all SQL (statement-execution API, bound parameters, validation re-checked on save). app.yaml, requirements.txt.
- ../sql/06_corrections_views.sql and ../scripts/apply_corrections_views.py: create the table and (re)create the views (drops a table first only if the name is currently a table).
- ../scripts/deploy_buyin_app.py: raw-API create (the CLI adds a bad budget policy), grants, upload, deploy.

## Access
App service principal: USE CATALOG, USE SCHEMA; SELECT on buyin_quarantine, silver_buyin_log, email_suggestions; SELECT + MODIFY on buyin_corrections only; CAN_USE on the warehouse.

## Rebuild order
sql/02, sql/03 (these create TABLES), sql/05, then `python3 -I scripts/apply_corrections_views.py` (converts them to views), then `python3 -I scripts/deploy_buyin_app.py`.
Do not re-run sql/03 after the conversion: its CREATE OR REPLACE TABLE statements fail on views.

## Gotchas found
- `INSERT ... VALUES (uuid(), ...)` fails (non-deterministic function in an inline table); use `INSERT ... SELECT uuid(), ...`.
- If your network blocks PyPI, point `pip` at a mirror you can reach when you build a test venv.

## Tested (no browser)
data.py against the workspace: validation cases, unresolved list (14), email list (2), save, bad saves refused, accept/reject, KPI effect, cleanup to baseline.
app.py with Streamlit's headless AppTest (1.66.1): both pages render with no exceptions, a volume save (14 -> 13 waiting, confirmation shown), an invalid date is refused with a message,
an email accept (matching 26 -> 27, needing a decision 2 -> 1). Test rows removed; baseline restored.
NOT tested: the real UI in a browser, the X-Forwarded-Email header (AppTest has none), the service principal actually reading the views (relies on view-owner rights; privileges checked via the effective-permissions API).
