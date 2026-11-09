CREATE OR REPLACE TABLE bpa_edp.demo.bronze_admin_scheme AS
SELECT name AS scheme,
       300 + abs(hash(name)) % 9000 AS members_total,
       CAST(floor((300 + abs(hash(name)) % 9000) * ((abs(hash(name, 'm')) % 60) / 100.0)) AS INT) AS members_moved_to_date,
       round((abs(hash(name, 'l')) % 7000) / 10.0 + 40, 1) AS liability_gbp_m,
       date_add(DATE'2027-01-31', CAST(abs(hash(name, 'd')) % 180 AS INT)) AS target_buyout_date
FROM bpa_onelake_corp_fabric.dbo.dv_account
;
CREATE OR REPLACE TABLE bpa_edp.demo.bronze_planner_steps AS
WITH steps AS (
  SELECT * FROM VALUES (1, 'Trustee notification'), (2, 'Data cleanse'), (3, 'Member communications'),
                       (4, 'Insurer due diligence'), (5, 'Asset transfer'), (6, 'Buy-in policy issued') AS t(step_no, step_name)
), s AS (
  SELECT scheme, CAST(abs(hash(scheme, 'c')) % 7 AS INT) AS current_step FROM bpa_edp.demo.bronze_admin_scheme
)
SELECT s.scheme, st.step_no, st.step_name,
       element_at(array('A. Hughes', 'B. Okafor', 'C. Lindqvist', 'D. Patel', 'E. Marsh', 'F. Rowe'), CAST(1 + abs(hash(s.scheme, st.step_no)) % 6 AS INT)) AS step_owner,
       date_add(DATE'2026-08-15', CAST(st.step_no * 18 + abs(hash(s.scheme, 'o')) % 15 AS INT)) AS due_date,
       CASE WHEN st.step_no < s.current_step THEN 'Done' WHEN st.step_no = s.current_step THEN 'In progress' ELSE 'Not started' END AS status
FROM s CROSS JOIN steps st
;
CREATE OR REPLACE TABLE bpa_edp.demo.silver_planner_steps AS
SELECT *, (status <> 'Done' AND due_date < current_date()) AS is_overdue
FROM bpa_edp.demo.bronze_planner_steps
;
CREATE OR REPLACE TABLE bpa_edp.demo.silver_scheme_progress AS
WITH b AS (
  SELECT scheme, count(*) AS buyin_entries, sum(movement_volume) AS volume_notified,
         sum(CASE WHEN sla_breached THEN 1 ELSE 0 END) AS sla_breaches,
         sum(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_items,
         round(avg(days_late), 1) AS avg_days_late
  FROM bpa_edp.demo.silver_buyin_log GROUP BY scheme
), p AS (
  SELECT scheme, min_by(step_name, step_no) FILTER (WHERE status <> 'Done') AS current_step,
         sum(CASE WHEN is_overdue THEN 1 ELSE 0 END) AS overdue_steps
  FROM bpa_edp.demo.silver_planner_steps GROUP BY scheme
)
SELECT a.scheme, a.members_total, a.members_moved_to_date, a.liability_gbp_m, a.target_buyout_date,
       COALESCE(b.buyin_entries, 0) AS buyin_entries, COALESCE(b.volume_notified, 0) AS volume_notified,
       COALESCE(b.sla_breaches, 0) AS sla_breaches, COALESCE(b.pending_items, 0) AS pending_items, b.avg_days_late,
       COALESCE(p.current_step, 'Complete') AS current_step, COALESCE(p.overdue_steps, 0) AS overdue_steps
FROM bpa_edp.demo.bronze_admin_scheme a
LEFT JOIN b ON b.scheme = a.scheme
LEFT JOIN p ON p.scheme = a.scheme
;
CREATE OR REPLACE TABLE bpa_edp.demo.gold_buyin_sla_month AS
SELECT notification_month AS month, count(*) AS entries, count(received_date) AS received,
       sum(CASE WHEN sla_breached THEN 1 ELSE 0 END) AS sla_breaches,
       round(100 * sum(CASE WHEN sla_breached THEN 1 ELSE 0 END) / NULLIF(count(received_date), 0), 1) AS breach_rate_pct,
       sum(movement_volume) AS movement_volume
FROM bpa_edp.demo.silver_buyin_log GROUP BY notification_month
;
CREATE OR REPLACE TABLE bpa_edp.demo.gold_buyin_sla_trustee AS
SELECT trustee_contact, count(*) AS entries, count(received_date) AS received,
       sum(CASE WHEN sla_breached THEN 1 ELSE 0 END) AS sla_breaches,
       round(100 * sum(CASE WHEN sla_breached THEN 1 ELSE 0 END) / NULLIF(count(received_date), 0), 1) AS breach_rate_pct,
       round(avg(days_late), 1) AS avg_days_late
FROM bpa_edp.demo.silver_buyin_log GROUP BY trustee_contact
;
CREATE OR REPLACE TABLE bpa_edp.demo.gold_scheme_status AS
SELECT scheme, current_step, overdue_steps, members_total, members_moved_to_date,
       round(100 * members_moved_to_date / members_total, 1) AS pct_members_moved,
       volume_notified, buyin_entries, sla_breaches, pending_items, avg_days_late, target_buyout_date
FROM bpa_edp.demo.silver_scheme_progress
;
CREATE OR REPLACE TABLE bpa_edp.demo.gold_data_quality AS
SELECT column_name, reason, count(*) AS cells, count(DISTINCT log_id) AS rows_affected
FROM bpa_edp.demo.buyin_quarantine GROUP BY column_name, reason
;
CREATE OR REPLACE TABLE bpa_edp.demo.email_lines AS
SELECT regexp_extract(f.path, '[^/]+$', 0) AS file_name, l.line
FROM bpa_edp.demo.sp_email_intake_raw f
LATERAL VIEW explode(split(cast(f.content AS STRING), '\n')) l AS line
WHERE l.line LIKE '%INFO%subject=%'
;
CREATE OR REPLACE TABLE bpa_edp.demo.email_extracted AS
SELECT line, e.*
FROM (
  SELECT line,
    from_json(regexp_extract(ai_query('databricks-gpt-oss-120b',
      concat('Extract fields from this trustee email log line. Reply with ONLY a JSON object, no prose, with keys: scheme (string, the scheme name from the subject without the words member movement update), members_to_move (integer), notified_date (YYYY-MM-DD), received_date (YYYY-MM-DD), trustee (string, the sender name only). Line:\n', line)),
      '(?s)(\\{.*\\})', 1),
      'scheme STRING, members_to_move INT, notified_date DATE, received_date DATE, trustee STRING') AS e
  FROM bpa_edp.demo.email_lines
)
;
CREATE OR REPLACE TABLE bpa_edp.demo.email_suggestions AS
SELECT e.scheme, e.trustee, e.members_to_move, e.notified_date, e.received_date,
       s.log_id, s.source_file, s.movement_volume AS excel_volume,
       CASE WHEN s.log_id IS NULL THEN 'not in Excel log'
            WHEN s.movement_volume IS NULL THEN 'Excel value invalid: use email value'
            WHEN s.movement_volume <> e.members_to_move THEN 'differs from Excel'
            ELSE 'matches Excel' END AS review_status
FROM bpa_edp.demo.email_extracted e
LEFT JOIN bpa_edp.demo.silver_buyin_log s
  ON s.scheme = e.scheme AND s.notification_date = e.notified_date AND (s.received_date = e.received_date OR s.received_date IS NULL)
