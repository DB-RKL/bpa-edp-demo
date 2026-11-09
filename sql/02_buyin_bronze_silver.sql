CREATE OR REPLACE FUNCTION bpa_edp.demo.parse_xlsx(content BINARY)
RETURNS ARRAY<ARRAY<STRING>>
LANGUAGE PYTHON
AS $$
import zipfile, io, re
import xml.etree.ElementTree as ET
M = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
z = zipfile.ZipFile(io.BytesIO(content))
names = z.namelist()
ss = []
if 'xl/sharedStrings.xml' in names:
    for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('{%s}si' % M):
        ss.append(''.join(t.text or '' for t in si.iter('{%s}t' % M)))
sheet_name = sorted(n for n in names if n.startswith('xl/worksheets/sheet'))[0]
def col(ref):
    n = 0
    for ch in re.match(r'[A-Z]+', ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1
rows = []
for row in ET.fromstring(z.read(sheet_name)).iter('{%s}row' % M):
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
        vals[col(c.get('r'))] = val
    if vals:
        rows.append([vals.get(k) for k in range(11)])
return rows
$$
;
CREATE OR REPLACE TABLE bpa_edp.demo.bronze_buyin_log AS
SELECT regexp_extract(f.path, '[^/]+$', 0) AS source_file,
       f.modificationTime AS source_modified,
       r.pos + 1 AS source_row,
       r.col[0] AS log_id, r.col[1] AS scheme, r.col[2] AS trustee_contact,
       r.col[3] AS notification_date_raw, r.col[4] AS received_date_raw, r.col[5] AS movement_volume_raw,
       r.col[6] AS sla_days_raw, r.col[7] AS days_late_excel_raw,
       r.col[8] AS source, r.col[9] AS entered_by, r.col[10] AS notes
FROM bpa_edp.demo.sp_buyin_logs_raw f
LATERAL VIEW posexplode(bpa_edp.demo.parse_xlsx(f.content)) r AS pos, col
WHERE r.pos > 0
;
CREATE OR REPLACE TABLE bpa_edp.demo.silver_buyin_log AS
WITH typed AS (
  SELECT *,
    COALESCE(
      CASE WHEN try_cast(notification_date_raw AS DOUBLE) IS NOT NULL THEN date_add(DATE'1899-12-30', CAST(notification_date_raw AS DOUBLE) :: INT) END,
      try_to_date(notification_date_raw, 'dd.MM.yyyy')) AS notification_date,
    COALESCE(
      CASE WHEN try_cast(received_date_raw AS DOUBLE) IS NOT NULL THEN date_add(DATE'1899-12-30', CAST(received_date_raw AS DOUBLE) :: INT) END,
      try_to_date(received_date_raw, 'dd.MM.yyyy')) AS received_date,
    try_cast(movement_volume_raw AS INT) AS movement_volume,
    try_cast(sla_days_raw AS INT) AS sla_days
  FROM bpa_edp.demo.bronze_buyin_log
)
SELECT source_file, source_row, log_id, scheme, trustee_contact, source, entered_by, notes,
       notification_date, received_date, movement_volume, sla_days,
       date_trunc('MONTH', notification_date) AS notification_month,
       CASE WHEN received_date IS NULL THEN 'pending' ELSE 'received' END AS status,
       CASE WHEN received_date IS NOT NULL AND notification_date IS NOT NULL
            THEN GREATEST(0, datediff(received_date, notification_date) - sla_days) END AS days_late,
       CASE WHEN received_date IS NOT NULL AND notification_date IS NOT NULL
            THEN datediff(received_date, notification_date) > sla_days END AS sla_breached,
       (try_cast(notification_date_raw AS DOUBLE) IS NULL AND notification_date IS NOT NULL) AS date_fixed_from_text
FROM typed
;
CREATE OR REPLACE TABLE bpa_edp.demo.buyin_quarantine AS
SELECT source_file, source_row, log_id, scheme, 'notification_date' AS column_name, notification_date_raw AS raw_value,
       'not a date' AS reason, CAST(NULL AS STRING) AS fixed_value, current_timestamp() AS detected_at
FROM bpa_edp.demo.bronze_buyin_log
WHERE notification_date_raw IS NOT NULL AND try_cast(notification_date_raw AS DOUBLE) IS NULL AND try_to_date(notification_date_raw, 'dd.MM.yyyy') IS NULL
UNION ALL
SELECT source_file, source_row, log_id, scheme, 'received_date', received_date_raw, 'not a date', NULL, current_timestamp()
FROM bpa_edp.demo.bronze_buyin_log
WHERE received_date_raw IS NOT NULL AND try_cast(received_date_raw AS DOUBLE) IS NULL AND try_to_date(received_date_raw, 'dd.MM.yyyy') IS NULL
UNION ALL
SELECT source_file, source_row, log_id, scheme, 'movement_volume', movement_volume_raw, 'not a number', NULL, current_timestamp()
FROM bpa_edp.demo.bronze_buyin_log
WHERE movement_volume_raw IS NOT NULL AND try_cast(movement_volume_raw AS INT) IS NULL
UNION ALL
SELECT source_file, source_row, log_id, scheme, 'notification_date', notification_date_raw, 'text date, auto-corrected (dd.MM.yyyy)',
       CAST(try_to_date(notification_date_raw, 'dd.MM.yyyy') AS STRING), current_timestamp()
FROM bpa_edp.demo.bronze_buyin_log
WHERE notification_date_raw IS NOT NULL AND try_cast(notification_date_raw AS DOUBLE) IS NULL AND try_to_date(notification_date_raw, 'dd.MM.yyyy') IS NOT NULL
