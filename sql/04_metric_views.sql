CREATE OR REPLACE VIEW bpa_edp.demo.mv_buyin_sla
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Buy-in SLA semantic layer. One definition of breach rate, pending and lateness for dashboards, Genie and Power BI."
source: bpa_edp.demo.silver_buyin_log
dimensions:
  - name: notification_month
    expr: date_trunc('MONTH', notification_date)
    comment: Month the trustee notified us
  - name: trustee_contact
    expr: trustee_contact
    comment: Trustee contact who sent the notification
  - name: scheme
    expr: scheme
    comment: Pension scheme
  - name: source_channel
    expr: source
    comment: How the notification arrived (email, portal or phone)
  - name: status
    expr: status
    comment: received or pending
  - name: entered_by
    expr: entered_by
    comment: Operations analyst who keyed the entry
measures:
  - name: entries
    expr: COUNT(1)
    comment: Buy-in log entries
  - name: received
    expr: COUNT(received_date)
    comment: Entries with a received date
  - name: sla_breaches
    expr: COUNT(1) FILTER (WHERE sla_breached)
    comment: Entries received later than the SLA allows
  - name: breach_rate_pct
    expr: ROUND(100 * COUNT(1) FILTER (WHERE sla_breached) / NULLIF(COUNT(received_date), 0), 1)
    comment: SLA breaches as a percentage of received entries
  - name: pending_items
    expr: COUNT(1) FILTER (WHERE status = 'pending')
    comment: Entries with no received date yet
  - name: avg_days_late
    expr: ROUND(AVG(days_late), 1)
    comment: Average days beyond the SLA, recalculated from the dates
  - name: movement_volume
    expr: SUM(movement_volume)
    comment: Members notified as moving
$$
;
CREATE OR REPLACE VIEW bpa_edp.demo.mv_scheme_progress
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Scheme progress semantic layer: buy-in activity joined with buyout and planner data."
source: bpa_edp.demo.silver_scheme_progress
dimensions:
  - name: scheme
    expr: scheme
    comment: Pension scheme
  - name: current_step
    expr: current_step
    comment: Current planner step on the way to buyout
  - name: target_buyout_date
    expr: target_buyout_date
    comment: Target buyout date
measures:
  - name: schemes
    expr: COUNT(1)
    comment: Number of schemes
  - name: members_total
    expr: SUM(members_total)
    comment: Members in scope
  - name: members_moved
    expr: SUM(members_moved_to_date)
    comment: Members moved to date
  - name: pct_members_moved
    expr: ROUND(100 * SUM(members_moved_to_date) / NULLIF(SUM(members_total), 0), 1)
    comment: Share of members moved
  - name: overdue_steps
    expr: SUM(overdue_steps)
    comment: Planner steps past their due date and not done
  - name: sla_breaches
    expr: SUM(sla_breaches)
    comment: Buy-in SLA breaches
  - name: pending_items
    expr: SUM(pending_items)
    comment: Buy-in entries still pending
  - name: volume_notified
    expr: SUM(volume_notified)
    comment: Members notified as moving
$$
;
CREATE OR REPLACE VIEW bpa_edp.demo.pbi_sla_by_month AS
SELECT notification_month AS month, MEASURE(entries) AS entries, MEASURE(received) AS received, MEASURE(sla_breaches) AS sla_breaches,
       MEASURE(breach_rate_pct) AS breach_rate_pct, MEASURE(pending_items) AS pending_items, MEASURE(avg_days_late) AS avg_days_late,
       MEASURE(movement_volume) AS movement_volume
FROM bpa_edp.demo.mv_buyin_sla GROUP BY ALL
;
CREATE OR REPLACE VIEW bpa_edp.demo.pbi_sla_by_trustee AS
SELECT trustee_contact, MEASURE(entries) AS entries, MEASURE(received) AS received, MEASURE(sla_breaches) AS sla_breaches,
       MEASURE(breach_rate_pct) AS breach_rate_pct, MEASURE(pending_items) AS pending_items, MEASURE(avg_days_late) AS avg_days_late,
       MEASURE(movement_volume) AS movement_volume
FROM bpa_edp.demo.mv_buyin_sla GROUP BY ALL
;
CREATE OR REPLACE VIEW bpa_edp.demo.pbi_scheme_status AS
SELECT scheme, current_step, target_buyout_date, MEASURE(members_total) AS members_total, MEASURE(members_moved) AS members_moved,
       MEASURE(pct_members_moved) AS pct_members_moved, MEASURE(overdue_steps) AS overdue_steps, MEASURE(sla_breaches) AS sla_breaches,
       MEASURE(pending_items) AS pending_items, MEASURE(volume_notified) AS volume_notified
FROM bpa_edp.demo.mv_scheme_progress GROUP BY ALL
;
CREATE OR REPLACE VIEW bpa_edp.demo.pbi_sla_overall AS
SELECT MEASURE(entries) AS entries, MEASURE(received) AS received, MEASURE(sla_breaches) AS sla_breaches,
       MEASURE(breach_rate_pct) AS breach_rate_pct, MEASURE(pending_items) AS pending_items, MEASURE(avg_days_late) AS avg_days_late,
       MEASURE(movement_volume) AS movement_volume
FROM bpa_edp.demo.mv_buyin_sla
