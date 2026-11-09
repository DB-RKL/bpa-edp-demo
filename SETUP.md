# Setup

The build order below is the order used when this was put together. A clean rebuild from scratch has not been re-run end to end, so treat it as a guide.

## 1. Workspace and catalog
1. An Azure Databricks workspace with Unity Catalog and serverless compute, plus a SQL warehouse.
2. Copy `scripts/workspace.example.json` to `scripts/workspace.json` and fill in your workspace host and warehouse id. The helpers authenticate with an Azure CLI token for your tenant (`az account get-access-token --resource 2ff814a6-3304-4ab8-85cb-cd0e6f879c1d`).
3. Create the catalog `bpa_edp` with a managed location, the schema `demo`, and a volume `scheme_docs`. Upload `docs/out/*` into the volume.

## 2. Sources (each one is optional)
- **SharePoint logs:** create a Unity Catalog SharePoint connection (sign-in or app), upload `buyin/*.xlsx` to a `buyin_logs` folder, set the site URL in `scripts/create_pipelines.py`, and run it.
- **Dataverse / Dynamics 365:** needs a Dataverse environment with Azure Synapse Link to a data lake, with the incremental update folder structure switched on. See `scripts/dataverse_*.py` and `scripts/create_d365_pipeline.py`.
- **Outlook:** needs a Microsoft 365 tenant with an Exchange Online mailbox and an Entra app with the Microsoft Graph **Application** permissions `Mail.Read` and `User.Read.All`, with admin consent. Create the Unity Catalog Outlook connection yourself, so the secret never touches a script. If you add permissions later, edit the connection to fetch a fresh token. See `scripts/create_outlook_pipeline.py`.
- **Fabric via OneLake:** create a storage credential (service principal), a OneLake connection per Fabric workspace and a foreign catalog per lakehouse. The service principal must be a member of the Fabric workspace, and the workspace setting "Authenticate with OneLake user-delegated SAS tokens" must be on.

## 3. Data layer
1. `python3 -I scripts/run_sql.py sql/01_build.sql`, then `sql/02_buyin_bronze_silver.sql`, `sql/03_buyout_planner_gold.sql`, `sql/04_metric_views.sql` and `sql/05_dataverse_gold.sql`.
2. `python3 -I scripts/apply_corrections_views.py` (runs `sql/06_corrections_views.sql`). It turns silver and gold into views that apply corrections.
3. After step 2, **do not re-run** `sql/02` or `sql/03`: they create tables and will fail or overwrite the views. To refresh from SharePoint afterwards, use `sql/02b_refresh_bronze.sql`.
4. For the planner data from Dataverse: `scripts/apply_planner_views.py`. For inbound emails and attachments: `sql/08` to `sql/12` and `scripts/refresh_outlook.py`.

## 4. Apps and reports
- **Node app:** `python3 -I scripts/deploy_buyin_node_app.py`. It creates the app, grants its service principal access and deploys `app_buyin_node/`. Run it locally with `TEST_TOKEN=<token> DATABRICKS_HOST=<host> WAREHOUSE_ID=<id> node server.js`.
- **Streamlit app:** `python3 -I scripts/deploy_buyin_app.py`.
- **Dashboards and Genie:** `dashboard/make_dashboard_buyin.py`, `scripts/create_genie.py`.
- **Power BI:** `scripts/create_pbi_model.py`, then `scripts/create_pbi_report.py`. The model needs `Implementation = "2.0"` in the Databricks.Catalogs options, or Power BI returns a 400 after sign-in.

## Gotchas found along the way
- `INSERT ... VALUES (uuid(), ...)` fails; use `INSERT ... SELECT uuid(), ...`.
- A pipeline that fails retries itself about once a minute and keeps using compute. Stop it after a failed run.
- `ai_parse_document` rejected an `.xlsx` file in testing, so `sql/10b_attachment_text_refresh.sql` reads `.xlsx` with a separate function and reads `.txt` and `.csv` as plain text (it does not send those two to `ai_parse_document`).
- App URLs reject an Azure AD token. Use a Databricks user token when calling a deployed app from a script.
- Anything created on a shared sandbox may be deleted on a schedule. Set an expiry tag you control on the resource group.
