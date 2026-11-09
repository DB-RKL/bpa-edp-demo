DROP TABLE IF EXISTS bpa_edp.demo.gold_quote_pipeline
;
CREATE OR REPLACE VIEW bpa_edp.demo.gold_quote_pipeline AS
SELECT q.new_stage AS stage,
       CASE q.new_stage WHEN 'Qualify' THEN 1 WHEN 'Develop' THEN 2 WHEN 'Propose' THEN 3 WHEN 'Close' THEN 4 ELSE 9 END AS stage_order,
       q.new_state AS state,
       COUNT(*) AS quotes,
       ROUND(SUM(q.new_estimatedvalue_gbp_m), 1) AS value_gbp_m
FROM bpa_edp.demo.d365_bpa_quote q
GROUP BY q.new_stage, q.new_state
;
DROP TABLE IF EXISTS bpa_edp.demo.gold_quote_by_scheme
;
CREATE OR REPLACE VIEW bpa_edp.demo.gold_quote_by_scheme AS
SELECT a.name AS scheme,
       COUNT(*) AS quotes,
       SUM(CASE WHEN q.new_state = 'Open' THEN 1 ELSE 0 END) AS open_quotes,
       ROUND(SUM(CASE WHEN q.new_state = 'Open' THEN q.new_estimatedvalue_gbp_m ELSE 0 END), 1) AS open_value_gbp_m
FROM bpa_edp.demo.d365_bpa_quote q
JOIN bpa_edp.demo.d365_account a ON a.Id = q.new_accountid
GROUP BY a.name
