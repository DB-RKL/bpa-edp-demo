-- Clean read-only layer over the Outlook table that the user's own pipeline (outlook-emails-bpa) fills: bpa_edp.demo.email_messages.
-- That pipeline is unfiltered (all folders, HTML bodies, subjects with non-breaking spaces), so this view keeps the Inbox only (Sent Items
-- holds a copy of every message), turns the HTML body into text, normalises the subject, and keeps mail whose subject starts with "BPA".
CREATE OR REPLACE FUNCTION bpa_edp.demo.html_to_text(html STRING)
RETURNS STRING
COMMENT 'Plain text from a simple HTML email body: line breaks for block tags, tags removed, common entities decoded, non-breaking spaces turned into spaces'
RETURN trim(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(
  html, r'(?is)<(script|style)[^>]*>.*?</\1>', ''),
  r'(?i)<br\s*/?>|</p>|</div>|</pre>|</tr>|</li>', char(10)),
  r'<[^>]+>', ''),
  '&nbsp;', ' '), '&lt;', '<'), '&gt;', '>'), '&quot;', '"'), '&#39;', ''''), '&amp;', '&'),
  r' ', ' '))
;
CREATE OR REPLACE VIEW bpa_edp.demo.outlook_inbox AS
SELECT mailbox, outlook_message_id, folder, `from`,
       regexp_replace(subject, r' ', ' ') AS subject,
       received_at,
       regexp_replace(regexp_replace(bpa_edp.demo.html_to_text(unique_body_content), r'\n{3,}', concat(char(10), char(10))), r'^\s+|\s+$', '') AS unique_body_content,
       regexp_replace(regexp_replace(bpa_edp.demo.html_to_text(full_body_content), r'\n{3,}', concat(char(10), char(10))), r'^\s+|\s+$', '') AS full_body_content,
       attachments
FROM bpa_edp.demo.email_messages
WHERE folder = 'Inbox' AND lower(regexp_replace(subject, r' ', ' ')) LIKE 'bpa%'
