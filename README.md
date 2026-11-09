# Buy-in operations on Databricks (reference build)

A worked example of bringing the data behind a pension buy-in process into Databricks, checking it, joining it with buy-out data, and putting a person in the loop for what can't be settled automatically. **All data is synthetic.** It is a reference build for a demo, not production code.

## The problem it models
Buy-in activity is tracked in Excel logs on SharePoint. Staff re-key trustee emails into them by hand, planner data sits in Dynamics 365 / Dataverse, and buy-out data lives somewhere else. One bad cell ("approx 120" in a volume column, "TBC" in a date column) can fail a load, and nobody can see the whole journey of a scheme from one place.

## What it does
- **Ingests** the Excel logs (Lakeflow Connect for SharePoint), the planner data (Lakeflow Connect for Dynamics 365, via an Azure Synapse Link export), a mailbox (Lakeflow Connect for Outlook, a Beta connector) and Fabric tables (OneLake federation, read in place).
- **Keeps bad cells from breaking the load.** Bronze keeps every cell as text. Cells that can't be read as a number or date go to a quarantine table instead of failing the run.
- **Joins** buy-in activity with buy-out and planner data into one row per scheme (silver), with thin gold tables and metric views so a rate such as "SLA breach rate" is defined once.
- **Reads emails and attachments.** `ai_query` turns an email into a record. `ai_parse_document` reads PDF, Word and image attachments, and a small function reads Excel attachments.
- **Puts a person in the loop** through two small apps (Node.js and Streamlit) where someone confirms an email's value, rejects it, or imports an attachment into a Unity Catalog volume. Every decision is stored with who and when.

## How the email-to-Excel check works
This is the "Email vs Excel" page in the Node app (`compareAll` in `app_buyin_node/server.js`).

1. **Excel side.** The workbooks are copied from SharePoint into `bronze_buyin_log`. The view `silver_buyin_log` types them (bad cells become empty; the originals stay in `buyin_quarantine`) and layers on any correction made in the app.
2. **Email side.** The Outlook pipeline lands the mailbox. The view `outlook_inbox` keeps the Inbox and turns HTML into text. For each email the app asks `ai_query` for a record: scheme, trustee (from the signature), members, notified date, received date, confidence and a note. It must leave a field empty if the email doesn't say. The result is cached per app process.
3. **Matching.** The app finds the log rows with the same scheme. With a notification date in the email it takes the row with that date; without one it takes the scheme's only pending row, or its only row. Otherwise the email stays unmatched.
4. **Field checks.** Members are compared as numbers, dates as text, trustee names ignoring case and punctuation, and an attached Excel's row count against the member count in the email.

| Email has it | Log has it | Result |
|---|---|---|
| Yes | Yes, equal | Correct |
| Yes | Yes, not equal | Different |
| Yes | No (blank or invalid) | Missing in Excel |
| No | Yes | Missing in email |
| No | No | Missing in both |

Things to know: the log side includes corrections made in the app, so accepting an email's value turns that field Correct. The model can word things differently between runs. Dates are compared as the model wrote them. The Excel copy is only as fresh as the last pipeline run, and no schedule is set.

## Repository layout
| Path | What it is |
|---|---|
| `sql/` | Tables and views: bronze, quarantine, silver, gold, metric views, corrections, inbound email and attachment layers |
| `scripts/` | Python helpers that create pipelines, load sample data, deploy the apps and rehearse changes. `run_sql.py`, `wsapi.py` and `q.py` are the shared helpers |
| `app_buyin_node/` | Node.js app with no npm dependencies: Home, Fix invalid cells, Review emails, Inbound emails, Email vs Excel |
| `app_buyin/` | The Streamlit version of the first three pages |
| `app/` | An earlier pricing-assumptions app |
| `dashboard/` | Scripts that build the AI/BI dashboards |
| `connectors/` | An untested Lakeflow Connect pipeline definition |
| `buyin/`, `docs/`, `sample_emails/` | Synthetic Excel logs, scheme documents, and sample emails with attachments |
| `architecture/` | The target-architecture diagram |
| `SETUP.md` | Build order and configuration |
| `POWER_AUTOMATE_FLOW.md` | An optional flow that saves emails to SharePoint |

## Before you run anything
Identifiers in this repository have been replaced with placeholders (`YOUR-TENANT`, `YOUR-SITE`, `YOUR_WAREHOUSE_ID`, `<SANDBOX_TENANT_ID>` and similar). Replace them with your own values. Scripts read credentials from `~/.bpa-edp/`, which is outside the repository; nothing secret is stored here. Several scripts assume the repository is checked out at `~/bpa-edp-demo`.

## Status
Built and exercised against a real workspace with scripted tests and a headless browser render. The apps have not been through a formal browser test suite. A clean rebuild of the whole chain from this repository has not been re-run end to end, so expect to fix small things. The Outlook connector is in Beta, and Fabric and Dynamics 365 need their own environments.
