-- object: buyin_corrections (table)
CREATE TABLE IF NOT EXISTS bpa_edp.demo.buyin_corrections (
  correction_id STRING COMMENT 'uuid of the edit',
  log_id STRING COMMENT 'buy-in log entry, e.g. BI-0119',
  column_name STRING COMMENT 'movement_volume | received_date | notification_date',
  corrected_value STRING COMMENT 'new value as text (integer or ISO date); null for a reject',
  action STRING COMMENT 'apply | reject',
  reason STRING COMMENT 'free-text reason given by the editor',
  source STRING COMMENT 'quarantine | email',
  edited_by STRING COMMENT 'signed-in user from the app header',
  edited_at TIMESTAMP COMMENT 'when the edit was made')
COMMENT 'Manual corrections to the buy-in log made in the buy-in editor app. Latest apply per (log_id, column_name) wins in silver_buyin_log.'
;
-- object: silver_buyin_log (view)
CREATE OR REPLACE VIEW bpa_edp.demo.silver_buyin_log AS
WITH t0 AS (
  SELECT *,
    COALESCE(
      CASE WHEN try_cast(notification_date_raw AS DOUBLE) IS NOT NULL THEN date_add(DATE'1899-12-30', CAST(notification_date_raw AS DOUBLE) :: INT) END,
      try_to_date(notification_date_raw, 'dd.MM.yyyy')) AS notification_date_x,
    COALESCE(
      CASE WHEN try_cast(received_date_raw AS DOUBLE) IS NOT NULL THEN date_add(DATE'1899-12-30', CAST(received_date_raw AS DOUBLE) :: INT) END,
      try_to_date(received_date_raw, 'dd.MM.yyyy')) AS received_date_x,
    try_cast(movement_volume_raw AS INT) AS movement_volume_x,
    try_cast(sla_days_raw AS INT) AS sla_days
  FROM bpa_edp.demo.bronze_buyin_log
), corr AS (
  SELECT log_id, column_name, corrected_value
  FROM (SELECT log_id, column_name, corrected_value, action,
               row_number() OVER (PARTITION BY log_id, column_name ORDER BY edited_at DESC) AS rn
        FROM bpa_edp.demo.buyin_corrections)
  WHERE rn = 1 AND action = 'apply'
), typed AS (
  SELECT t0.*,
    COALESCE(try_to_date(cn.corrected_value, 'yyyy-MM-dd'), t0.notification_date_x) AS notification_date,
    COALESCE(try_to_date(cr.corrected_value, 'yyyy-MM-dd'), t0.received_date_x) AS received_date,
    COALESCE(try_cast(cv.corrected_value AS INT), t0.movement_volume_x) AS movement_volume,
    (cn.log_id IS NOT NULL OR cr.log_id IS NOT NULL OR cv.log_id IS NOT NULL) AS has_correction
  FROM t0
  LEFT JOIN corr cn ON cn.log_id = t0.log_id AND cn.column_name = 'notification_date'
  LEFT JOIN corr cr ON cr.log_id = t0.log_id AND cr.column_name = 'received_date'
  LEFT JOIN corr cv ON cv.log_id = t0.log_id AND cv.column_name = 'movement_volume'
)
SELECT source_file, source_row, log_id, scheme, trustee_contact, source, entered_by, notes,
       notification_date, received_date, movement_volume, sla_days,
       date_trunc('MONTH', notification_date) AS notification_month,
       CASE WHEN received_date IS NULL THEN 'pending' ELSE 'received' END AS status,
       CASE WHEN received_date IS NOT NULL AND notification_date IS NOT NULL
            THEN GREATEST(0, datediff(received_date, notification_date) - sla_days) END AS days_late,
       CASE WHEN received_date IS NOT NULL AND notification_date IS NOT NULL
            THEN datediff(received_date, notification_date) > sla_days END AS sla_breached,
       (try_cast(notification_date_raw AS DOUBLE) IS NULL AND notification_date IS NOT NULL) AS date_fixed_from_text,
       has_correction
FROM typed
;
-- object: silver_scheme_progress (view)
CREATE OR REPLACE VIEW bpa_edp.demo.silver_scheme_progress AS
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
-- object: gold_buyin_sla_month (view)
CREATE OR REPLACE VIEW bpa_edp.demo.gold_buyin_sla_month AS
SELECT notification_month AS month, count(*) AS entries, count(received_date) AS received,
       sum(CASE WHEN sla_breached THEN 1 ELSE 0 END) AS sla_breaches,
       round(100 * sum(CASE WHEN sla_breached THEN 1 ELSE 0 END) / NULLIF(count(received_date), 0), 1) AS breach_rate_pct,
       sum(movement_volume) AS movement_volume
FROM bpa_edp.demo.silver_buyin_log GROUP BY notification_month
;
-- object: gold_buyin_sla_trustee (view)
CREATE OR REPLACE VIEW bpa_edp.demo.gold_buyin_sla_trustee AS
SELECT trustee_contact, count(*) AS entries, count(received_date) AS received,
       sum(CASE WHEN sla_breached THEN 1 ELSE 0 END) AS sla_breaches,
       round(100 * sum(CASE WHEN sla_breached THEN 1 ELSE 0 END) / NULLIF(count(received_date), 0), 1) AS breach_rate_pct,
       round(avg(days_late), 1) AS avg_days_late
FROM bpa_edp.demo.silver_buyin_log GROUP BY trustee_contact
;
-- object: gold_scheme_status (view)
CREATE OR REPLACE VIEW bpa_edp.demo.gold_scheme_status AS
SELECT scheme, current_step, overdue_steps, members_total, members_moved_to_date,
       round(100 * members_moved_to_date / members_total, 1) AS pct_members_moved,
       volume_notified, buyin_entries, sla_breaches, pending_items, avg_days_late, target_buyout_date
FROM bpa_edp.demo.silver_scheme_progress
;
-- object: email_suggestions (view)
CREATE OR REPLACE VIEW bpa_edp.demo.email_suggestions AS
SELECT e.scheme, e.trustee, e.members_to_move, e.notified_date, e.received_date,
       s.log_id, s.source_file, s.movement_volume AS excel_volume,
       CASE WHEN s.log_id IS NULL THEN 'not in Excel log'
            WHEN s.movement_volume IS NULL THEN 'Excel value invalid: use email value'
            WHEN s.movement_volume <> e.members_to_move THEN 'differs from Excel'
            ELSE 'matches Excel' END AS review_status
FROM bpa_edp.demo.email_extracted e
LEFT JOIN bpa_edp.demo.silver_buyin_log s
  ON s.scheme = e.scheme AND s.notification_date = e.notified_date AND (s.received_date = e.received_date OR s.received_date IS NULL)
