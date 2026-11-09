# Inbound email: Power Automate to SharePoint to Databricks

What it shows: a trustee email arrives in a mailbox, a flow saves it as a file in SharePoint, Lakeflow Connect lands it in Databricks, and the buy-in editor app's **Inbound emails** page turns it into a record for a person to confirm.
Only standard connectors are used (Office 365 Outlook, SharePoint, Content Conversion). Nothing in the flow holds a Databricks credential.

## What is built and what is not
| Piece | State |
|---|---|
| Databricks landing table, parsing view, review table, app page | Built and tested with the six sample emails below, loaded as seed data |
| Power Automate flow | NOT built (needs your Outlook and SharePoint sign-in) |
| SharePoint folder `inbound_emails` | NOT created |
| Pipeline `bpa_sharepoint_inbound_email` | Script written, NOT run |

## 1. Create the folder
In SharePoint site `YOUR-SITE`, Documents library, create a folder named `inbound_emails`.

## 2. Build the flow (make.powerautomate.com)
Create an **Instant cloud flow** with the trigger **For a selected message (Office 365 Outlook)**. For a hands-off version use **When a new email arrives (V3)** on a folder named `BPA demo` instead; the expressions below are the same except that the trigger fields come from `triggerOutputs()?['body/...']` in both cases.

1. **Html to text** (Content Conversion). Content: the trigger's `Body`.
2. **Compose**, named `Compose`. Paste this as the input, then fix the dynamic content if the designer re-writes it:
```json
{
  "message_id": "@{triggerOutputs()?['body/id']}",
  "received_at": "@{triggerOutputs()?['body/receivedDateTime']}",
  "from_name": "@{triggerOutputs()?['body/from']}",
  "from_address": "@{triggerOutputs()?['body/from']}",
  "subject": "@{triggerOutputs()?['body/subject']}",
  "body_text": "@{body('Html_to_text')}"
}
```
3. **Create file (SharePoint)**.
   - Site address: `https://YOUR-TENANT.sharepoint.com/sites/YOUR-SITE`
   - Folder path: `/Shared Documents/inbound_emails`
   - File name: `@{formatDateTime(utcNow(),'yyyy-MM-dd_HHmmss')}_@{guid()}.json`
   - File content: `@{outputs('Compose')}`

Keep the six property names exactly as written: the Databricks view reads them by name. The flow does not need to be perfect about `from_name`; the app takes the trustee from the email body and signature.

## 3. Send the sample emails to yourself
These are synthetic and match schemes in the buy-in log. Each is written to behave differently in the review page.
**Email 1.** To yourself. Subject: `RE: Hollin Pension Scheme 6 - buy-in documents`

> Hi team,
> 
> The trustees have now signed off the member data pack for Hollin Pension Scheme 6. We sent it across on 12 August 2026 and it covers 93 members moving to the insurer.
> 
> Thanks,
> D. Patel

**Email 2.** To yourself. Subject: `Jesmond Pension Scheme 5 - member movement confirmation`

> Hello,
> 
> Please note the final number of members moving for Jesmond Pension Scheme 5 is 142. We were first notified on 2026-08-20 and the full documents reached you on 28/08/2026.
> 
> Regards,
> D. Patel

**Email 3.** To yourself. Subject: `Carrow Pension Scheme 5 update`

> Morning,
> 
> Just a quick one. For Carrow Pension Scheme 5 we are looking at around 300 members, give or take a few until the final cleanse is done. Original notification was 7 August.
> 
> B. Okafor

**Email 4.** To yourself. Subject: `Aldwych Pension Scheme 5 - volumes`

> Hi,
> 
> Following our call, Aldwych Pension Scheme 5 will move ninety members. We notified you on the sixteenth of September 2026 and sent everything over on the 25th of September.
> 
> A. Hughes

**Email 5.** To yourself. Subject: `RE: RE: quick question`

> Thanks, that works for us. Can we speak tomorrow about the numbers?
> 
> C. Lindqvist

**Email 6.** To yourself. Subject: `Delamere Pension Scheme 6 - member movement update`

> Trustees confirm 273 members to move. Notified 2026-09-14, documents received 2026-09-22.
> 
> D. Patel

What each one shows:
1. No notification date in the email: the page leaves it empty, flags medium confidence and lists the scheme's pending log entries (BI-0003).
2. Everything stated, with dates in two formats.
3. "Around 300": the page marks it low confidence. The model sometimes returns 300 and sometimes nothing; both are handled.
4. Numbers and dates written in words.
5. A reply with no scheme or numbers: the page will not let you confirm it. Reject it with a reason.
6. A clean email in the format the mailbox log already uses.

## 4. Land it in Databricks
```
python3 -I scripts/create_inbound_pipeline.py --replace-seed
```
`--replace-seed` drops the seed table (same name as the pipeline's table). Check `SELECT * FROM bpa_edp.demo.inbound_emails`.
Run it by hand after each flow run; no schedule is set.

## 5. Review in the app
https://bpa-buyin-editor-0000000000000000.0.azure.databricksapps.com, sidebar **Inbound emails**. Pick an email, **Format email into payload**, check or edit the fields, **Confirm payload** or **Reject** (a reason is required). Decisions are saved in `bpa_edp.demo.inbound_email_review` with who and when.

## Limits
- The confirmed payload is stored for review; it is not yet written back into the buy-in log. That is a deliberate next step, not a gap in the demo.
- Confidence is checked in code (hedged numbers are low, missing key fields cap it at medium); the model's own confidence is not trusted.
- Each run of the model on an email is a fresh call, so wording of the note can differ between runs.
- The app page has not been clicked through in a browser. Its data functions were run against the live workspace.
- Whether the app's service principal can call the model endpoint is not verified; if the button errors, grant it access to `databricks-gpt-oss-120b`.
