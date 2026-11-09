# Buy-in operations (Node.js)

Node.js version of the buy-in editor. Separate Databricks App (`bpa-buyin-editor-node`); the Streamlit app in `../app_buyin` is unchanged. Zero npm dependencies: native `http` and `fetch`, plain ES modules in the browser.

- Same tables, bound-parameter SQL and server-side checks as the Streamlit app. Decisions made in either app show in the other.
- Pages: Fix invalid cells, Review emails, Inbound emails (Power Automate -> SharePoint -> Lakeflow Connect, `ai_query` drafts the payload).
- Server routes under `/api/*`; the browser only names things (a log id, a message id). Values are re-checked and the target re-read on the server.
- Email text is rendered as text nodes only; a CSP header blocks inline scripts.
- Local test: `TEST_TOKEN=<workspace bearer> DATABRICKS_HOST=<host> WAREHOUSE_ID=<id> PORT=18431 node server.js`.
- Deploy: `python3 -I scripts/deploy_buyin_node_app.py`.
