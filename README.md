# Buy-in operations app

A small Databricks App for reviewing trustee emails against an Excel buy-in log. It has no npm dependencies: a Node.js server (`server.js`) using the built-in `http` and `fetch`, and a plain ES-module front end in `public/`. **All the data it was built against is synthetic.**

## Pages
| Page | What it does |
|---|---|
| Home | A summary of what is waiting: invalid cells per Excel workbook, emails that disagree with the log, inbound emails to review, and the headline SLA figures |
| Fix invalid cells | Excel cells that could not be read (for example "approx 120" in a volume column). Each card shows the source email beside what to verify; save a corrected value, or skip |
| Review emails | Emails whose extracted value disagrees with the log. Accept or reject |
| Inbound emails | Emails landed from an Outlook mailbox. The model drafts a record, you edit and confirm or reject it. Attachments can be viewed (PDF), downloaded, or imported into a Unity Catalog volume |
| Email vs Excel | Every email is read by the model, matched to its row in the log, and each field is marked Correct, Different, Missing in Excel, Missing in email, or Missing in both |

Corrections, review decisions and imports are stored as new rows with who and when. The Excel files themselves are never changed.

## How the email-versus-Excel check works
1. For each email, the server asks `ai_query` (`databricks-gpt-oss-120b`) for a record: scheme, trustee (from the signature), members, notified date, received date, confidence and a note. The model must leave a field empty if the email does not say. The result is cached per server process. Code lowers confidence when a number is hedged ("around 300") and caps it at medium when a key field is missing.
2. It finds the rows in `silver_buyin_log` with the same scheme. With a notification date in the email it takes the row with that date. Without one it takes the scheme's only pending row, or its only row. Otherwise the email stays unmatched.
3. Members are compared as numbers, dates as text, trustee names ignoring case and punctuation, and an attached Excel's row count against the member count in the email.

| Email has it | Log has it | Result |
|---|---|---|
| Yes | Yes, equal | Correct |
| Yes | Yes, not equal | Different |
| Yes | No (blank or invalid) | Missing in Excel |
| No | Yes | Missing in email |
| No | No | Missing in both |

Notes: the log side includes corrections made in this app, so accepting an email's value turns that field Correct. The model can word things differently between runs. Dates are compared as the model wrote them.

## What it expects in your workspace
The app does not create any data. It reads and writes tables in `bpa_edp.demo` (set by `SCHEMA` at the top of `server.js`) and expects these to exist:

| Object | Used for |
|---|---|
| `silver_buyin_log`, `buyin_quarantine` | The Excel log as loaded, and the cells that could not be read |
| `email_suggestions`, `email_extracted` | Emails already matched to log entries |
| `inbound_emails` | The email list: id, sender, subject, body, source, attachments JSON, attachment text |
| `outlook_inbox` | The Outlook table with its attachments (the app reads attachment bytes from here) |
| `mv_buyin_sla` | A metric view with `entries`, `breach_rate_pct` and `pending_items` |
| `buyin_corrections` (written) | One row per correction: log id, column, value, action, source, who, when |
| `inbound_email_review` (written), `inbound_email_latest` | Review decisions, and a view of the latest one per email |
| `inbound_attachment_import` (written) | An audit row for each imported attachment |
| Volume `bpa_edp.demo.inbound_attachments` | Where imported attachments are written |

It also calls the model endpoint `databricks-gpt-oss-120b` and runs SQL on the warehouse named in `app.yaml`. The column names the queries use are in `server.js`; the SQL that builds these objects is not part of this repository.

## Run and deploy
- **Deploy:** put your warehouse id in `app.yaml`, then create and deploy a Databricks App from this folder (`databricks apps create` / `databricks apps deploy`, or the workspace UI). Give the app's service principal `USE CATALOG`, `USE SCHEMA`, `SELECT` on the objects above, `MODIFY` on the three tables it writes, `READ VOLUME` and `WRITE VOLUME` on the volume, and `CAN_USE` on the warehouse.
- **Sign-in:** Databricks Apps supplies `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID` and `DATABRICKS_CLIENT_SECRET`. The signed-in user comes from the `X-Forwarded-Email` header.
- **Local:** `TEST_TOKEN=<workspace token> DATABRICKS_HOST=<host> WAREHOUSE_ID=<id> PORT=8000 node server.js`. Node 20 or later.
- **Logo (optional):** put a `logo.png` in `public/` and it shows in the top bar. Without one the bar shows the text "Buy-in operations".

## Design and safety notes
- The browser only names things (a log id, a message id). The server re-reads the target, validates the value again, and uses bound SQL parameters.
- Email text is added to the page as text nodes only, and a content-security-policy header blocks inline scripts.
- Attachments are previewed inline only if they are really PDFs. Imports are limited to document types and 20 MB.
- Checked with scripted API tests, a fake-DOM click-through and a headless render, and scanned with the Impeccable design detector. It has not been through a formal browser test suite.
