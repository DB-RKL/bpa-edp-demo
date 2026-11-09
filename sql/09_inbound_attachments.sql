CREATE VOLUME IF NOT EXISTS bpa_edp.demo.inbound_attachments COMMENT 'Documents imported from inbound trustee emails (Outlook connector) after a person has viewed them'
;
CREATE TABLE IF NOT EXISTS bpa_edp.demo.inbound_attachment_import (
  import_id STRING, message_id STRING, attachment_index INT, file_name STRING, volume_path STRING, size_bytes BIGINT, sha256 STRING, imported_by STRING, imported_at TIMESTAMP)
