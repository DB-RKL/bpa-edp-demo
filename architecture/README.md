# Target architecture

`after.dot` is the source; redraw with `dot -Tpng -Gdpi=140 after.dot -o after.png` (and `-Tsvg` for `after.svg`).

The diagram shows where each source lands and what reads it:

- **Sources:** Excel buy-in logs on SharePoint, trustee emails (a mailbox), Dynamics 365 / Dataverse planner data, and data that already lives in Fabric.
- **Ingestion:** Lakeflow Connect for SharePoint, Outlook and Dynamics 365; OneLake federation to read Fabric tables in place; `ai_query` to turn emails into records, with a person confirming each one.
- **Unity Catalog:** bronze (raw, everything as text), a quarantine table for cells that cannot be read, silver (typed, joined, SLA recalculated) and thin gold tables, with metric views holding the shared definitions.
- **Consumers:** an AI/BI dashboard, Genie, review apps, and Power BI through DirectQuery on the SQL warehouse.

Dashed outlines mark pieces that are optional or stand-ins in the demo. The diagram is a design sketch; the README says what is built.
