-- Text read from Outlook attachments. The connector's own table (outlook_email_messages) is managed by the pipeline, so the extra
-- columns live in this table and are joined into the inbound_emails view. Refresh after every pipeline run with sql/10b.
CREATE TABLE IF NOT EXISTS bpa_edp.demo.outlook_attachment_text (
  message_id STRING, attachment_index INT, file_name STRING, mime_type STRING, ext STRING, size_bytes BIGINT,
  method STRING COMMENT 'ai_parse_document (pdf, docx, doc, png, jpg, tif, pptx), xlsx reader, plain text (txt, csv) or none',
  status STRING COMMENT 'read, no text, not supported or error',
  attachment_text STRING COMMENT 'Text read from inside the attachment (first 20000 characters)', char_count INT, note STRING, parsed_at TIMESTAMP)
;
CREATE OR REPLACE FUNCTION bpa_edp.demo.parse_xlsx_safe(content BINARY)
RETURNS ARRAY<ARRAY<STRING>>
LANGUAGE PYTHON
COMMENT 'Reads the first sheet of an .xlsx as rows of text (up to 30 columns). Returns NULL for NULL or non-Excel input instead of failing.'
AS $$
if content is None:
    return None
import zipfile, io, re
import xml.etree.ElementTree as ET
try:
    M = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    z = zipfile.ZipFile(io.BytesIO(content))
    names = z.namelist()
    ss = []
    if 'xl/sharedStrings.xml' in names:
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('{%s}si' % M):
            ss.append(''.join(t.text or '' for t in si.iter('{%s}t' % M)))
    sheets = sorted(n for n in names if n.startswith('xl/worksheets/sheet'))
    if not sheets:
        return None
    def col(ref):
        n = 0
        for ch in re.match(r'[A-Z]+', ref).group(0):
            n = n * 26 + ord(ch) - 64
        return n - 1
    rows = []
    width = 0
    for row in ET.fromstring(z.read(sheets[0])).iter('{%s}row' % M):
        vals = {}
        for c in row.findall('{%s}c' % M):
            t = c.get('t'); v = c.find('{%s}v' % M); i = c.find('{%s}is' % M)
            if t == 'inlineStr' and i is not None:
                val = ''.join(x.text or '' for x in i.iter('{%s}t' % M))
            elif v is None or v.text is None:
                val = None
            elif t == 's':
                val = ss[int(v.text)]
            else:
                val = v.text
            k = col(c.get('r'))
            if k < 30:
                vals[k] = val
        if vals:
            width = max(width, max(vals) + 1)
            rows.append(vals)
    return [[r.get(k) for k in range(width)] for r in rows]
except Exception:
    return None
$$
;
-- A made-up test email (see scripts/fake_email.py). Same shape as the connector's table so it flows through the same view and attachment reader.
CREATE TABLE IF NOT EXISTS bpa_edp.demo.fake_inbound_emails (
  mailbox STRING, outlook_message_id STRING, folder STRING, `from` STRING, subject STRING, unique_body_content STRING, full_body_content STRING, received_at TIMESTAMP,
  attachments ARRAY<STRUCT<content: BINARY, attachment_id: STRING, file_name: STRING, mime_type: STRING, size: BIGINT, attachment_kind: STRING, is_inline: BOOLEAN>>)
;
CREATE OR REPLACE VIEW bpa_edp.demo.inbound_emails AS
SELECT concat(CASE WHEN m.source LIKE 'Outlook%' THEN 'outlook:' ELSE 'test:' END, m.folder) AS file_name, m.received_at AS landed_at,
       m.outlook_message_id AS message_id, m.received_at, m.`from` AS from_name, m.`from` AS from_address, m.subject,
       coalesce(nullif(trim(m.unique_body_content), ''), m.full_body_content) AS body_text,
       m.source,
       coalesce(a.attachments_json,
                to_json(transform(m.attachments, x -> named_struct('name', x.file_name, 'type', x.mime_type, 'size', coalesce(length(x.content), x.size)))),
                '[]') AS attachments_json,
       a.attachment_text
FROM (
  SELECT folder, received_at, outlook_message_id, `from`, subject, unique_body_content, full_body_content, attachments, 'Outlook (live connector)' AS source
  FROM bpa_edp.demo.outlook_inbox
  UNION ALL
  SELECT folder, received_at, outlook_message_id, `from`, subject, unique_body_content, full_body_content, attachments, 'Test email (made up, not from Outlook)' AS source
  FROM bpa_edp.demo.fake_inbound_emails
) m
LEFT JOIN (
  SELECT message_id,
         to_json(transform(sort_array(collect_list(struct(attachment_index, file_name, mime_type, size_bytes, status, method, char_count))),
                           s -> named_struct('name', s.file_name, 'type', s.mime_type, 'size', s.size_bytes, 'status', s.status, 'method', s.method, 'chars', s.char_count))) AS attachments_json,
         nullif(concat_ws('\n\n', collect_list(CASE WHEN status = 'read' THEN concat('[', file_name, ']\n', attachment_text) END)), '') AS attachment_text
  FROM bpa_edp.demo.outlook_attachment_text GROUP BY message_id
) a ON a.message_id = m.outlook_message_id
