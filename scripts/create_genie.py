"""Create the two Genie spaces (pricing, buy-in). Tables must be sorted by identifier for the API."""
import sys as _s, os as _o; _s.path.insert(0, _o.path.expanduser("~/bpa-edp-demo/scripts"))
import json, sys, time
import wsapi

SPACES = {
 "pricing": {"title": "BPA pricing and reporting (EDP demo)", "description": "Ask questions about scheme terms, pipeline and indicative premiums. Synthetic data.",
  "tables": [
   ("bpa_edp.demo.pricing_gold", "One row per pension scheme: terms extracted from the scheme rules document, Dataverse opportunity pipeline, benchmark pricing from historical quotes, and the indicative premium. Pricing-team overrides are already applied."),
   ("bpa_edp.demo.silver_opportunities", "Dataverse opportunities (one row per quote opportunity), read in place from the Fabric lakehouse over OneLake."),
   ("bpa_edp.demo.silver_quote_benchmarks", "Historical bulk annuity quote outcomes by longevity basis: average premium as a percent of liability and win rate.")],
  "text": "Amounts ending in _gbp_m are in GBP millions. Discount rates and loadings are percentages. has_override is true when the pricing team has edited the assumptions in the write-back app. indicative_premium_gbp_m is liability times the benchmark premium percent, adjusted for the discount rate and expense loading."},
 "buyin": {"title": "BPA buy-in operations (EDP demo)", "description": "Buy-in SLA, planner progress and data quality. Synthetic data.",
  "tables": [
   ("bpa_edp.demo.gold_scheme_status", "One row per scheme: current planner step, overdue planner steps, share of members moved, volume notified, SLA breaches, pending items, average days late. Buy-in log joined with buyout (administration) data and planner steps."),
   ("bpa_edp.demo.gold_buyin_sla_month", "Buy-in SLA by month notified: entries, received, SLA breaches, breach rate percent, movement volume."),
   ("bpa_edp.demo.gold_buyin_sla_trustee", "Buy-in SLA by trustee contact: entries, breaches, breach rate percent, average days late."),
   ("bpa_edp.demo.silver_buyin_log", "One row per buy-in log entry from the SharePoint Excel logs, typed and cleaned. days_late and sla_breached are recalculated from the dates. status is pending when no received date."),
   ("bpa_edp.demo.buyin_quarantine", "Invalid cells found in the Excel logs (text in date or number columns). These are caught here instead of failing the load."),
   ("bpa_edp.demo.email_suggestions", "Values extracted from trustee emails by ai_query, with a review_status comparing them to the Excel log.")],
  "text": "An SLA breach means days between notification and received date is greater than sla_days. Lateness is recalculated in the silver layer, not taken from the Excel formula. Pending means no received date yet. All data is synthetic."},
 "semantic": {"title": "BPA buy-in semantic layer (EDP demo)", "description": "Governed buy-in SLA and scheme progress measures defined once as Unity Catalog metric views. Synthetic data.",
  "tables": [
   ("bpa_edp.demo.mv_buyin_sla", "Metric view for buy-in SLA. Dimensions: notification_month, trustee_contact, scheme, source_channel, status, entered_by. Measures: entries, received, sla_breaches, breach_rate_pct, pending_items, avg_days_late, movement_volume. Always query measures with MEASURE()."),
   ("bpa_edp.demo.mv_scheme_progress", "Metric view for scheme progress to buyout. Dimensions: scheme, current_step, target_buyout_date. Measures: schemes, members_total, members_moved, pct_members_moved, overdue_steps, sla_breaches, pending_items, volume_notified. Always query measures with MEASURE()."),
   ("bpa_edp.demo.buyin_quarantine", "Invalid cells found in the Excel buy-in logs (text in date or number columns), caught instead of failing the load."),
   ("bpa_edp.demo.gold_planner_status", "Planner steps from Dataverse (Lakeflow Connect): per step and status, schemes and overdue_steps. Overdue means not done and past the due date, so it changes daily."),
   ("bpa_edp.demo.gold_planner_overdue_by_scheme", "Planner progress per scheme from Dataverse: steps, steps_done, overdue_steps (changes daily), current_step.")],
  "text": "Use the metric views for SLA and progress questions and reference measures with MEASURE(). breach_rate_pct is already a percentage. An SLA breach means days between notification and received date is greater than the SLA days; pending means no received date yet. All data is synthetic."},
}
which = sys.argv[1:] or list(SPACES)
tok = wsapi.token()
out = json.load(open("~/bpa-edp-demo/scripts/genie_spaces.json")) if __import__("os").path.exists("~/bpa-edp-demo/scripts/genie_spaces.json") else {}
for k in which:
    sp = SPACES[k]
    space = {"version": 2, "data_sources": {"tables": [{"identifier": i, "description": [d]} for i, d in sorted(sp["tables"])]},
             "instructions": {"text_instructions": [{"content": [sp["text"]]}]}}
    d = wsapi.call("POST", "/api/2.0/genie/spaces", {"title": sp["title"], "description": sp["description"], "warehouse_id": wsapi.WH, "serialized_space": json.dumps(space)}, tok)
    print(k, d.get("space_id") or d); out[k] = d.get("space_id")
json.dump(out, open("~/bpa-edp-demo/scripts/genie_spaces.json", "w"))
