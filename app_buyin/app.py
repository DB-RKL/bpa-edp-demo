"""Buy-in log editor: fix invalid Excel cells and review email extractions. Streamlit Databricks App."""
import streamlit as st

import data

st.set_page_config(page_title="Buy-in operations", layout="centered")

# Theme: blue #1F4E79 with tints, amber accent #B7791F, serif headings. Same approach as the Node app: hide the Streamlit chrome, recolour widgets, banner on top.
# Same approach as the reference email-generator app: hide the Streamlit chrome, recolour widgets, banner on top.
st.markdown("""<style>
header, #MainMenu, footer {visibility: hidden;}
.block-container {max-width: 1100px; padding-top: 1.5rem;}
h1, h2, h3, h4, .rl-title {font-family: 'PT Serif', Georgia, 'Times New Roman', serif !important; color: #1F4E79;}
a {color: #2F6AA3;}
.stSpinner > div > div {border-top-color: #1F4E79;}
.rl-banner {background: #1F4E79; color: #FFFFFF; padding: 1.4rem 1.6rem 1.2rem; border-radius: 6px; border-bottom: 5px solid #B7791F; margin-bottom: 0.8rem;}
.rl-eyebrow {letter-spacing: 0.14em; font-size: 0.72rem; text-transform: uppercase; color: #C9D8E8;}
.rl-title {font-size: 1.9rem; line-height: 1.2; margin: 0.15rem 0 0.3rem; color: #FFFFFF !important;}
.rl-sub {color: #E3ECF5; font-size: 0.95rem;}
[data-testid="stExpander"] {border: 1px solid #C9D8E8; border-radius: 6px;}
[data-testid="stExpander"] summary {background: #EEF3F8; color: #1F4E79; font-weight: 600; letter-spacing: 0.03em;}
[data-testid="stMetric"] {background: #EEF3F8; border-left: 4px solid #1F4E79; padding: 0.6rem 0.9rem; border-radius: 4px;}
[data-testid="stMetricValue"] {color: #1F4E79;}
.stButton > button {border: 1px solid #1F4E79; color: #1F4E79; border-radius: 4px;}
.stButton > button:hover {background: #E3ECF5; border-color: #1F4E79; color: #1F4E79;}
.stButton > button[kind="primary"] {background: #1F4E79; color: #FFFFFF;}
.stButton > button[kind="primary"]:hover {background: #2F6AA3; color: #FFFFFF;}
</style>""", unsafe_allow_html=True)
LABELS = {"movement_volume": "Movement volume (members)", "received_date": "Received date"}


def current_user():
    try:
        h = st.context.headers
        return h.get("X-Forwarded-Email") or h.get("X-Forwarded-Preferred-Username") or "unknown"
    except Exception:
        return "unknown"


def flash(msg):
    st.session_state["flash"] = msg
    st.rerun()


def show_flash():
    msg = st.session_state.pop("flash", None)
    if msg:
        st.success(msg)


def recent_table():
    st.subheader("What has been changed recently?")
    try:
        rows = data.recent_corrections()
    except Exception as e:
        st.error(f"Could not load the corrections list: {e}")
        return
    if rows:
        st.dataframe(rows, hide_index=True)
    else:
        st.caption("No corrections have been made yet.")


def page_fix(user):
    st.subheader("Which spreadsheet cells need fixing?")
    st.write("These cells in the Excel buy-in logs could not be read (text in a number or date column). "
             "Enter the right value and save it. The correction is stored in Databricks and the SLA figures update straight away. "
             "The Excel file on SharePoint is not changed.")
    show_flash()
    try:
        cells = data.unresolved_cells()
    except Exception as e:
        st.error(f"Could not load the invalid cells: {e}")
        return
    st.metric("Cells waiting for a value", len(cells))
    if not cells:
        st.success("Every invalid cell has a correction.")
    for c in cells:
        key = f"{c['log_id']}_{c['column_name']}"
        col = c["column_name"]
        with st.container(border=True):
            st.markdown(f"**{c['log_id']}** - {c['scheme']} - {LABELS.get(col, col)}")
            st.write(f"Value in the Excel log: `{c['raw_value']}` ({c['reason']}). Notified: {str(c['notification_date'])[:10]}.")
            if col == "movement_volume" and c.get("email_volume"):
                st.info(f"The trustee email for this entry says {c['email_volume']} members.")
            if col == "received_date" and c.get("email_received_date"):
                st.info(f"The trustee email for this entry says received on {str(c['email_received_date'])[:10]}.")
            with st.form(key):
                if col == "movement_volume":
                    start = int(float(c["email_volume"])) if c.get("email_volume") else None
                    val = st.number_input("Corrected volume", min_value=0, step=1, value=start, key=f"v_{key}")
                else:
                    val = st.text_input("Corrected received date (YYYY-MM-DD)", value=str(c.get("email_received_date") or "")[:10], key=f"v_{key}")
                reason = st.text_input("Reason (optional)", key=f"r_{key}")
                submitted = st.form_submit_button("Save correction")
            if submitted:
                ok, res = data.validate(col, val, c["notification_date"])
                if not ok:
                    st.error(res)
                else:
                    try:
                        src = "email" if (c.get("email_volume") and col == "movement_volume" and str(res) == str(int(float(c["email_volume"])))) else "quarantine"
                        data.save_correction(c["log_id"], col, res, "apply", reason, src, user)
                    except Exception as e:
                        st.error(f"Could not save: {e}")
                    else:
                        flash(f"Saved {LABELS.get(col, col).lower()} {res} for {c['log_id']}.")
    st.divider()
    recent_table()


def page_emails(user):
    st.subheader("Which emails disagree with the spreadsheet?")
    st.write("Trustee emails are read automatically. Most match the Excel log. The ones below need a person to decide.")
    show_flash()
    try:
        counts = data.email_counts()
        rows = data.review_emails()
    except Exception as e:
        st.error(f"Could not load the email review list: {e}")
        return
    a, b = st.columns(2)
    a.metric("Emails matching the Excel log", counts.get("matches Excel", 0))
    b.metric("Emails needing a decision", len(rows))
    if not rows:
        st.success("No emails are waiting for a decision.")
    for r in rows:
        with st.container(border=True):
            st.markdown(f"**{r['scheme']}** - from {r['trustee']}")
            excel = r["excel_volume"] if r["excel_volume"] else "invalid or empty"
            st.write(f"The email says {r['members_to_move']} members to move (notified {str(r['notified_date'])[:10]}, received {str(r['received_date'])[:10]}). "
                     f"Excel log entry: {r['log_id'] or 'no matching entry'}, volume {excel}. Status: {r['review_status']}.")
            if not r["log_id"]:
                st.info("There is no matching Excel entry, so nothing can be corrected here.")
                continue
            c1, c2, _ = st.columns([2, 1, 6])
            if c1.button("Accept the email value", key=f"acc_{r['log_id']}"):
                try:
                    data.accept_email(r["log_id"], r["members_to_move"], user)
                except Exception as e:
                    st.error(f"Could not save: {e}")
                else:
                    flash(f"Accepted {r['members_to_move']} members for {r['log_id']}.")
            if c2.button("Reject", key=f"rej_{r['log_id']}"):
                try:
                    data.reject_email(r["log_id"], user)
                except Exception as e:
                    st.error(f"Could not save: {e}")
                else:
                    flash(f"Rejected the email value for {r['log_id']}.")
    st.divider()
    recent_table()


def page_inbound(user):
    import json
    st.subheader("What did the trustee email say?")
    st.write("A Power Automate flow saves each trustee email to SharePoint and Lakeflow Connect lands it in Databricks. "
             "Pick one, let the model draft the record, check it against the email, then confirm or reject it.")
    show_flash()
    try:
        emails = data.inbound_emails()
    except Exception as e:
        st.error(f"Could not load the inbound emails: {e}")
        return
    todo = [e for e in emails if e["review_status"] == "to review"]
    a, b, c = st.columns(3)
    a.metric("Emails landed", len(emails))
    b.metric("Waiting for review", len(todo))
    c.metric("Confirmed", sum(1 for e in emails if e["review_status"] == "confirmed"))
    if not emails:
        st.info("No emails have landed yet. Check the flow and the pipeline run.")
        return
    labels = {e["message_id"]: f"{str(e['received_at'])[:16].replace('T', ' ')}  |  {e['review_status']}  |  {e['subject']}" for e in emails}
    with st.expander("SECTION - Email input", expanded=True):
        mid = st.selectbox("Email", list(labels), format_func=lambda k: labels[k])
        e = next(x for x in emails if x["message_id"] == mid)
        st.markdown(f"**{e['subject']}**")
        st.caption(f"From {e['from_name']} ({e['from_address']}), {str(e['received_at'])[:16].replace('T', ' ')}  |  file {e['file_name']}")
        st.text(e["body_text"])
    st.write("\n")
    st.subheader("What should the record look like?")
    with st.expander("SECTION - Payload", expanded=True):
        if e["review_status"] != "to review":
            st.info(f"This email was {e['review_status']} by {e['edited_by']} at {str(e['edited_at'])[:16]}."
                    + (f" Reason: {e['reason']}" if e["reason"] else ""))
            if e["payload_json"]:
                st.json(json.loads(e["payload_json"]))
            return
        key = f"payload_{mid}"
        if st.button("Format email into payload", type="primary"):
            with st.spinner("Reading the email"):
                try:
                    p, raw = data.extract_payload(e["subject"], e["from_name"], e["body_text"])
                except Exception as ex:
                    st.error(f"Could not read the email: {ex}")
                else:
                    st.session_state[key] = p
                    for f in data.PAYLOAD_FIELDS:
                        st.session_state[f"{key}_{f}"] = "" if p.get(f) is None else str(p[f])
        p = st.session_state.get(key)
        if p is None:
            st.caption("Nothing drafted yet.")
            return
        {"high": st.success, "medium": st.warning, "low": st.error}[p["confidence"]](f"Model confidence: {p['confidence']}. {p['note']}")
        c1, c2, c3 = st.columns([5, 4, 3])
        d1, d2, d3 = st.columns([4, 4, 4])
        edited = {
            "scheme": c1.text_input("Scheme", key=f"{key}_scheme"),
            "trustee": c2.text_input("Trustee", key=f"{key}_trustee"),
            "movement_volume": c3.text_input("Members moving", key=f"{key}_movement_volume"),
            "notification_date": d1.text_input("Notified (YYYY-MM-DD)", key=f"{key}_notification_date"),
            "received_date": d2.text_input("Documents received (YYYY-MM-DD)", key=f"{key}_received_date"),
        }
        clean, problems = data.validate_payload(edited)
        for pr in problems:
            st.warning(pr)
        clean.update({"source": "email", "message_id": mid})
        reason = d3.text_input("Reason (to reject)", key=f"{key}_reason")
        st.caption("Payload that will be saved")
        st.json(clean)
        try:
            hits = data.log_matches(clean.get("scheme"), clean.get("notification_date"))
        except Exception:
            hits = []
        if hits:
            st.caption("Excel log entries this email may belong to (same scheme and notification date, or the scheme's pending entries if the email gives no notification date)")
            st.dataframe(hits, hide_index=True)
        elif clean.get("scheme"):
            st.caption("No matching Excel entry found for this scheme.")
        b1, b2, _ = st.columns([2, 1, 6])
        if b1.button("Confirm payload", type="primary", disabled=bool(problems)):
            try:
                data.save_email_review(mid, "confirmed", edited, p, reason, user)
            except Exception as ex:
                st.error(f"Could not save: {ex}")
            else:
                flash(f"Confirmed the payload for {e['subject']}.")
        if b2.button("Reject"):
            try:
                data.save_email_review(mid, "rejected", edited, p, reason, user)
            except Exception as ex:
                st.error(f"Could not save: {ex}")
            else:
                flash(f"Rejected {e['subject']}.")


user = current_user()
st.markdown("""<div class="rl-banner"><div class="rl-eyebrow">Buy-in operations</div>
<div class="rl-title">Buy-in operations</div>
<div class="rl-sub">Check what arrives from trustees, fix what the spreadsheets get wrong, and keep one version of the numbers.</div></div>""", unsafe_allow_html=True)
st.caption(f"Signed in as {user}. Synthetic data. Corrections are saved in Databricks only and appear in the dashboards immediately.")
page = st.radio("Page", ["Fix invalid cells", "Review emails", "Inbound emails"], horizontal=True, label_visibility="collapsed")
if page == "Fix invalid cells":
    page_fix(user)
elif page == "Review emails":
    page_emails(user)
else:
    page_inbound(user)
