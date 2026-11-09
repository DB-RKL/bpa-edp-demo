CREATE OR REPLACE TABLE bpa_edp.demo.docs_parsed AS
SELECT regexp_extract(path, '[^/]+$', 0) AS file_name,
       path,
       concat_ws('\n', transform(j.document.elements, e -> e.content)) AS doc_text
FROM (
  SELECT path,
         from_json(cast(ai_parse_document(content) AS string),
                   'document STRUCT<elements ARRAY<STRUCT<content STRING, type STRING>>>') AS j
  FROM read_files('/Volumes/bpa_edp/demo/scheme_docs/', format => 'binaryFile')
)
;
CREATE OR REPLACE TABLE bpa_edp.demo.docs_extracted AS
SELECT file_name,
       r.*
FROM (
  SELECT file_name,
         from_json(
           regexp_extract(
             ai_query('databricks-gpt-oss-120b',
               concat('Extract these fields from the pension scheme document below. Reply with ONLY a JSON object, no prose, with keys: scheme_name (string, the scheme title without the words Scheme Rules Summary), members (integer), normal_retirement_age (integer), spouse_pension_pct (number), pension_increases (string), discount_rate_pct (number), longevity_basis (string), expense_loading_pct (number), liability_gbp_m (number). Document:\n', doc_text)),
             '(?s)(\\{.*\\})', 1),
           'scheme_name STRING, members INT, normal_retirement_age INT, spouse_pension_pct DOUBLE, pension_increases STRING, discount_rate_pct DOUBLE, longevity_basis STRING, expense_loading_pct DOUBLE, liability_gbp_m DOUBLE') AS r
  FROM bpa_edp.demo.docs_parsed
)
;
CREATE TABLE IF NOT EXISTS bpa_edp.demo.pricing_assumptions (
  accountid STRING,
  discount_rate_override_pct DOUBLE,
  expense_loading_override_pct DOUBLE,
  note STRING,
  updated_by STRING,
  updated_at TIMESTAMP
)
;
CREATE OR REPLACE VIEW bpa_edp.demo.silver_accounts AS
SELECT accountid, name AS scheme_name, customertypecode AS customer_type, address1_city AS city, CAST(createdon AS DATE) AS created_on
FROM bpa_onelake_corp_fabric.dbo.dv_account
;
CREATE OR REPLACE VIEW bpa_edp.demo.silver_opportunities AS
SELECT opportunityid, name AS opportunity_name, parentaccountid AS accountid, CAST(estimatedvalue AS DOUBLE) / 1e6 AS est_value_gbp_m,
       CAST(estimatedclosedate AS DATE) AS est_close_date, statecode AS state, stepname AS stage
FROM bpa_onelake_corp_fabric.dbo.dv_opportunity
;
CREATE OR REPLACE VIEW bpa_edp.demo.silver_quote_benchmarks AS
SELECT longevity_basis,
       COUNT(*) AS quotes,
       AVG(premium_pct) AS avg_premium_pct,
       AVG(CASE WHEN outcome = 'won' THEN premium_pct END) AS won_premium_pct,
       AVG(CASE WHEN outcome = 'won' THEN 1.0 ELSE 0.0 END) AS win_rate
FROM (SELECT longevity_basis, premium_pct_of_liability AS premium_pct, outcome FROM bpa_onelake_corp_fabric.dbo.edp_historical_quotes)
GROUP BY longevity_basis
;
CREATE OR REPLACE VIEW bpa_edp.demo.pricing_gold AS
WITH opp AS (
  SELECT accountid, COUNT(*) AS opportunities,
         SUM(CASE WHEN state = 'Open' THEN est_value_gbp_m ELSE 0 END) AS open_pipeline_gbp_m
  FROM bpa_edp.demo.silver_opportunities GROUP BY accountid
),
ovr AS (
  SELECT accountid, discount_rate_override_pct, expense_loading_override_pct, note, updated_by, updated_at
  FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY accountid ORDER BY updated_at DESC) AS rn FROM bpa_edp.demo.pricing_assumptions)
  WHERE rn = 1
)
SELECT a.accountid, a.scheme_name, a.city, d.file_name AS source_document,
       d.members, d.liability_gbp_m, d.longevity_basis, d.pension_increases,
       d.discount_rate_pct AS doc_discount_rate_pct,
       COALESCE(o.discount_rate_override_pct, d.discount_rate_pct) AS discount_rate_pct,
       COALESCE(o.expense_loading_override_pct, d.expense_loading_pct) AS expense_loading_pct,
       o.discount_rate_override_pct IS NOT NULL OR o.expense_loading_override_pct IS NOT NULL AS has_override,
       o.note AS override_note, o.updated_by, o.updated_at,
       b.won_premium_pct AS benchmark_premium_pct, b.win_rate AS benchmark_win_rate,
       ROUND(d.liability_gbp_m * (b.won_premium_pct / 100)
             * (1 - 12 * (COALESCE(o.discount_rate_override_pct, d.discount_rate_pct) - 4.9) / 100)
             * (1 + COALESCE(o.expense_loading_override_pct, d.expense_loading_pct) / 100), 1) AS indicative_premium_gbp_m,
       COALESCE(p.opportunities, 0) AS opportunities, ROUND(COALESCE(p.open_pipeline_gbp_m, 0), 1) AS open_pipeline_gbp_m
FROM bpa_edp.demo.silver_accounts a
JOIN bpa_edp.demo.docs_extracted d ON regexp_replace(trim(d.scheme_name), '\\s*-\\s*$', '') = a.scheme_name
LEFT JOIN bpa_edp.demo.silver_quote_benchmarks b ON b.longevity_basis = d.longevity_basis
LEFT JOIN opp p ON p.accountid = a.accountid
LEFT JOIN ovr o ON o.accountid = a.accountid
