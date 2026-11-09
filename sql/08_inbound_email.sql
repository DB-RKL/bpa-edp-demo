-- Seeded sample emails (made up; not used by the app any more). The live view bpa_edp.demo.inbound_emails is defined in sql/10.
CREATE OR REPLACE VIEW bpa_edp.demo.inbound_emails_sharepoint AS
SELECT file_name, landed_at, message_id, received_at, from_name, from_address, subject, body_text,
       'Sample (seeded data)' AS source, '[]' AS attachments_json FROM (
  SELECT regexp_extract(path, '[^/]+$', 0) AS file_name, modificationTime AS landed_at,
         j.message_id, to_timestamp(j.received_at) AS received_at, j.from_name, j.from_address, j.subject, j.body_text,
         row_number() OVER (PARTITION BY j.message_id ORDER BY modificationTime DESC) AS rn
  FROM (SELECT path, modificationTime, from_json(cast(content AS STRING),
          'message_id STRING, received_at STRING, from_name STRING, from_address STRING, subject STRING, body_text STRING') AS j
        FROM bpa_edp.demo.sp_inbound_emails_raw)
  WHERE j.message_id IS NOT NULL) WHERE rn = 1
;
CREATE TABLE IF NOT EXISTS bpa_edp.demo.inbound_email_review (
  review_id STRING, message_id STRING, status STRING, payload_json STRING, original_json STRING, reason STRING, edited_by STRING, edited_at TIMESTAMP)
;
CREATE OR REPLACE VIEW bpa_edp.demo.inbound_email_latest AS
SELECT * EXCEPT (rn) FROM (
  SELECT *, row_number() OVER (PARTITION BY message_id ORDER BY edited_at DESC) AS rn FROM bpa_edp.demo.inbound_email_review) WHERE rn = 1
