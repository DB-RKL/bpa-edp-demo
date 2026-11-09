-- Read the text of any new Outlook attachments (idempotent: attachments already read are skipped). Run after each pipeline run.
INSERT INTO bpa_edp.demo.outlook_attachment_text
WITH src AS (
  SELECT m.outlook_message_id AS message_id, a.pos AS attachment_index, a.att.file_name AS file_name, a.att.mime_type AS mime_type, a.att.content AS content,
         lower(regexp_extract(a.att.file_name, '(\\.[^.]+)$', 1)) AS ext
  FROM (SELECT outlook_message_id, attachments FROM bpa_edp.demo.outlook_inbox
        UNION ALL SELECT outlook_message_id, attachments FROM bpa_edp.demo.fake_inbound_emails) m
  LATERAL VIEW posexplode(m.attachments) a AS pos, att
  WHERE a.att.content IS NOT NULL AND coalesce(a.att.is_inline, false) = false
),
todo AS (
  SELECT s.* FROM src s
  WHERE NOT EXISTS (SELECT 1 FROM bpa_edp.demo.outlook_attachment_text t WHERE t.message_id = s.message_id AND t.attachment_index = s.attachment_index)
),
parsed AS (
  SELECT *,
    CASE WHEN ext IN ('.pdf','.docx','.doc','.png','.jpg','.jpeg','.tif','.tiff','.pptx','.ppt') THEN ai_parse_document(content) END AS doc,
    bpa_edp.demo.parse_xlsx_safe(CASE WHEN ext = '.xlsx' THEN content END) AS xl
  FROM todo
),
texted AS (
  SELECT *,
    CASE WHEN doc IS NOT NULL THEN doc:error_status::string END AS err,
    CASE WHEN doc IS NOT NULL THEN array_join(transform(try_cast(doc:document.elements AS ARRAY<VARIANT>), e -> coalesce(e:content::string, '')), '\n')
         WHEN xl IS NOT NULL THEN concat('Excel sheet 1: ', cast(greatest(size(xl) - 1, 0) AS STRING), ' data rows. Columns: ',
              concat_ws(', ', filter(xl[0], c -> c IS NOT NULL)), '. First rows:\n',
              concat_ws('\n', transform(slice(xl, 2, 8), r -> concat_ws(' | ', filter(r, c -> c IS NOT NULL)))))
         WHEN ext IN ('.txt', '.csv') THEN decode(content, 'UTF-8') END AS txt
  FROM parsed
)
SELECT message_id, attachment_index, file_name, mime_type, ext, length(content) AS size_bytes,
  CASE WHEN doc IS NOT NULL THEN 'ai_parse_document' WHEN xl IS NOT NULL THEN 'xlsx reader' WHEN ext IN ('.txt', '.csv') THEN 'plain text' ELSE 'none' END AS method,
  CASE WHEN err IS NOT NULL THEN 'error'
       WHEN txt IS NULL THEN 'not supported'
       WHEN length(trim(txt)) = 0 THEN 'no text'
       ELSE 'read' END AS status,
  left(txt, 20000) AS attachment_text,
  length(left(txt, 20000)) AS char_count,
  CASE WHEN err IS NOT NULL THEN left(err, 300)
       WHEN txt IS NULL AND ext = '.xlsx' THEN 'The file is named .xlsx but could not be opened as an Excel workbook'
       WHEN txt IS NULL THEN concat('File type ', coalesce(nullif(ext, ''), '(none)'), ' is not read: no reader for it') END AS note,
  current_timestamp() AS parsed_at
FROM texted
