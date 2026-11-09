-- Run AFTER pipeline bpa_d365_dataverse has landed bpa_edp.demo.d365_planner_step (Dataverse table new_plannerstep).
-- silver_planner_steps was a table built from synthetic bronze_planner_steps; it becomes a view over the Dataverse data
-- (apply with scripts/apply_planner_views.py, which drops a table or view of the same name first).
CREATE OR REPLACE VIEW bpa_edp.demo.silver_planner_steps AS
SELECT a.name AS scheme,
       CAST(p.new_stepno AS INT) AS step_no,
       p.new_stepname AS step_name,
       p.new_stepowner AS step_owner,
       CAST(p.new_duedate AS DATE) AS due_date,
       p.new_status AS status,
       (p.new_status <> 'Done' AND CAST(p.new_duedate AS DATE) < current_date()) AS is_overdue
FROM bpa_edp.demo.d365_planner_step p
JOIN bpa_edp.demo.d365_account a ON a.Id = p.new_accountid
;
CREATE OR REPLACE VIEW bpa_edp.demo.gold_planner_status AS
SELECT step_no, step_name, status, COUNT(*) AS schemes,
       SUM(CASE WHEN is_overdue THEN 1 ELSE 0 END) AS overdue_steps
FROM bpa_edp.demo.silver_planner_steps
GROUP BY step_no, step_name, status
;
CREATE OR REPLACE VIEW bpa_edp.demo.gold_planner_overdue_by_scheme AS
SELECT scheme,
       COUNT(*) AS steps,
       SUM(CASE WHEN status = 'Done' THEN 1 ELSE 0 END) AS steps_done,
       SUM(CASE WHEN is_overdue THEN 1 ELSE 0 END) AS overdue_steps,
       min_by(step_name, step_no) FILTER (WHERE status <> 'Done') AS current_step
FROM bpa_edp.demo.silver_planner_steps
GROUP BY scheme
