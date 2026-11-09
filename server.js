// Buy-in operations editor, Node.js version. Zero dependencies (native http and fetch).
// Same tables, same bound-parameter SQL and same server-side checks as the Streamlit app in ../app_buyin.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const SCHEMA = 'bpa_edp.demo';
const MODEL = 'databricks-gpt-oss-120b';
const EDITABLE = new Set(['movement_volume', 'received_date', 'notification_date']);
const ACTIONS = new Set(['apply', 'reject']);
const SOURCES = new Set(['quarantine', 'email']);
const PAYLOAD_FIELDS = ['scheme', 'trustee', 'movement_volume', 'notification_date', 'received_date'];
const PUBLIC = path.join(path.dirname(fileURLToPath(import.meta.url)), 'public');
const PORT = Number(process.env.DATABRICKS_APP_PORT || process.env.PORT || 8000);
const WAREHOUSE = process.env.WAREHOUSE_ID;

class UserError extends Error {}

// ---- Databricks access -----------------------------------------------------------------------------------------
const host = () => {
  const h = process.env.DATABRICKS_HOST || '';
  return h.startsWith('http') ? h.replace(/\/$/, '') : `https://${h}`;
};
let tokenCache = { value: null, exp: 0 };
async function token() {
  if (process.env.TEST_TOKEN) return process.env.TEST_TOKEN; // local testing only
  if (tokenCache.value && Date.now() < tokenCache.exp - 60_000) return tokenCache.value;
  const basic = Buffer.from(`${process.env.DATABRICKS_CLIENT_ID}:${process.env.DATABRICKS_CLIENT_SECRET}`).toString('base64');
  const r = await fetch(`${host()}/oidc/v1/token`, {
    method: 'POST',
    headers: { Authorization: `Basic ${basic}`, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: 'grant_type=client_credentials&scope=all-apis',
  });
  if (!r.ok) throw new Error(`token request failed: ${r.status}`);
  const j = await r.json();
  tokenCache = { value: j.access_token, exp: Date.now() + j.expires_in * 1000 };
  return tokenCache.value;
}

async function api(method, p, body) {
  const r = await fetch(host() + p, {
    method,
    headers: { Authorization: `Bearer ${await token()}`, 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.message || `${method} ${p} failed: ${r.status}`);
  return j;
}

/** Run one statement with bound parameters; returns rows as objects. */
export async function run(sql, params = {}) {
  const parameters = Object.entries(params).map(([name, v]) => ({ name, value: v == null ? null : String(v), type: 'STRING' }));
  let d = await api('POST', '/api/2.0/sql/statements', { warehouse_id: WAREHOUSE, statement: sql, parameters, wait_timeout: '50s' });
  for (let i = 0; i < 60 && ['PENDING', 'RUNNING'].includes(d.status.state); i++) {
    await new Promise((res) => setTimeout(res, 2000));
    d = await api('GET', `/api/2.0/sql/statements/${d.statement_id}`);
  }
  if (d.status.state !== 'SUCCEEDED') throw new Error(d.status.error?.message || d.status.state);
  const cols = d.manifest?.schema?.columns?.map((c) => c.name) || [];
  return (d.result?.data_array || []).map((row) => Object.fromEntries(cols.map((c, i) => [c, row[i]])));
}

// ---- Validation (same rules as the Streamlit app) ---------------------------------------------------------------
function isoDate(s) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
  if (!m) return null;
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
  return d.getUTCFullYear() === +m[1] && d.getUTCMonth() === +m[2] - 1 && d.getUTCDate() === +m[3] ? d : null;
}
const iso = (d) => d.toISOString().slice(0, 10);

/** Returns [true, cleanedText] or [false, message]. */
export function validate(column, value, notificationDate = null) {
  if (!EDITABLE.has(column)) return [false, `${column} cannot be edited here.`];
  const text = value == null ? '' : String(value).trim();
  if (!text) return [false, 'Enter a value.'];
  if (column === 'movement_volume') {
    if (!/^[+-]?\d+$/.test(text)) return [false, 'Volume must be a whole number.'];
    const n = Number(text);
    return n < 0 ? [false, 'Volume cannot be negative.'] : [true, String(n)];
  }
  const d = isoDate(text);
  if (!d) return [false, 'Use the date format YYYY-MM-DD.'];
  if (column === 'received_date' && notificationDate) {
    const n = isoDate(String(notificationDate).slice(0, 10));
    if (n && d < n) return [false, `Received date cannot be before the notification date (${iso(n)}).`];
    if (n && d > new Date(n.getTime() + 365 * 86400000)) return [false, 'Received date is more than a year after notification; check it.'];
  }
  return [true, iso(d)];
}

export function validatePayload(p) {
  const problems = [];
  const clean = { scheme: String(p.scheme ?? '').trim(), trustee: String(p.trustee ?? '').trim() };
  if (!clean.scheme) problems.push('Scheme is required.');
  for (const col of ['movement_volume', 'notification_date', 'received_date']) {
    const raw = p[col];
    if (raw == null || String(raw).trim() === '') { clean[col] = null; continue; }
    const [ok, res] = validate(col, raw, col === 'received_date' ? clean.notification_date : null);
    if (ok) clean[col] = col === 'movement_volume' ? Number(res) : res;
    else { clean[col] = null; problems.push(`${col.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())}: ${res}`); }
  }
  return { clean, problems };
}

// ---- Data access ------------------------------------------------------------------------------------------------
const LINE_JOIN = (alias) => `LEFT JOIN (SELECT es.log_id, max(x.line) AS source_line FROM ${SCHEMA}.email_suggestions es
  JOIN ${SCHEMA}.email_extracted x ON x.scheme <=> es.scheme AND x.trustee <=> es.trustee AND x.members_to_move <=> es.members_to_move
    AND x.notified_date <=> es.notified_date AND x.received_date <=> es.received_date
  WHERE es.log_id IS NOT NULL GROUP BY es.log_id) ln ON ln.log_id = ${alias}.log_id`;

export const unresolvedCells = () => run(`
  SELECT q.log_id, q.scheme, q.column_name, q.raw_value, q.reason, s.notification_date, s.trustee_contact, s.source_file,
         e.members_to_move AS email_volume, e.received_date AS email_received_date, ln.source_line
  FROM ${SCHEMA}.buyin_quarantine q
  JOIN ${SCHEMA}.silver_buyin_log s ON s.log_id = q.log_id
  LEFT JOIN (SELECT log_id, max(members_to_move) AS members_to_move, max(received_date) AS received_date
             FROM ${SCHEMA}.email_suggestions WHERE log_id IS NOT NULL GROUP BY log_id) e ON e.log_id = q.log_id
  ${LINE_JOIN('q')}
  WHERE q.fixed_value IS NULL AND q.column_name IN ('movement_volume', 'received_date')
    AND NOT EXISTS (SELECT 1 FROM ${SCHEMA}.buyin_corrections c WHERE c.log_id = q.log_id AND c.column_name = q.column_name)
  ORDER BY q.log_id, q.column_name`);

export const reviewEmails = () => run(`
  SELECT es.scheme, es.trustee, es.members_to_move, es.notified_date, es.received_date, es.log_id, es.excel_volume, es.review_status, ln.source_line
  FROM ${SCHEMA}.email_suggestions es
  ${LINE_JOIN('es')}
  WHERE es.review_status <> 'matches Excel'
    AND NOT EXISTS (SELECT 1 FROM ${SCHEMA}.buyin_corrections c WHERE c.log_id = es.log_id AND c.source = 'email')
  ORDER BY es.scheme`);

export async function emailCounts() {
  const rows = await run(`SELECT review_status, count(*) AS n FROM ${SCHEMA}.email_suggestions GROUP BY review_status`);
  return Object.fromEntries(rows.map((r) => [r.review_status, Number(r.n)]));
}

export const recentCorrections = (limit = 15) => run(`
  SELECT edited_at, edited_by, log_id, column_name, corrected_value, action, source, reason
  FROM ${SCHEMA}.buyin_corrections ORDER BY edited_at DESC LIMIT ${Number(limit) | 0}`);

export async function saveCorrection(logId, column, value, action, reason, source, editedBy) {
  if (!ACTIONS.has(action) || !SOURCES.has(source) || !EDITABLE.has(column)) throw new UserError('Unsupported action, source or column.');
  if (!logId) throw new UserError('A log entry is required.');
  let corrected = null;
  if (action === 'apply') {
    let notif = null;
    if (column === 'received_date') {
      const rows = await run(`SELECT notification_date FROM ${SCHEMA}.silver_buyin_log WHERE log_id = :log_id`, { log_id: logId });
      notif = rows[0]?.notification_date ?? null;
    }
    const [ok, res] = validate(column, value, notif);
    if (!ok) throw new UserError(res);
    corrected = res;
  }
  await run(`INSERT INTO ${SCHEMA}.buyin_corrections
             SELECT uuid(), :log_id, :column_name, :corrected_value, :action, :reason, :source, :edited_by, current_timestamp()`,
    { log_id: logId, column_name: column, corrected_value: corrected, action, reason: String(reason ?? '').slice(0, 500), source, edited_by: editedBy || 'unknown' });
}

export const inboundEmails = () => run(`
  SELECT e.message_id, e.received_at, e.from_name, e.from_address, e.subject, e.body_text, e.file_name, e.source, e.attachments_json, e.attachment_text,
         (SELECT to_json(collect_list(named_struct('n', i.attachment_index, 'path', i.volume_path, 'by', i.imported_by, 'at', cast(i.imported_at AS STRING))))
          FROM ${SCHEMA}.inbound_attachment_import i WHERE i.message_id = e.message_id) AS imports_json,
         coalesce(r.status, 'to review') AS review_status, r.payload_json, r.edited_by, r.edited_at, r.reason
  FROM ${SCHEMA}.inbound_emails e
  LEFT JOIN ${SCHEMA}.inbound_email_latest r ON r.message_id = e.message_id
  ORDER BY e.received_at DESC`);

const prompt = (subject, sender, body) =>
  'You read one email sent to a pension buy-in operations team and turn it into a record. Reply with ONLY a JSON object, no prose, ' +
  'with these keys: scheme (string, the pension scheme name exactly as written, or null), trustee (string, the name of whoever signed the email if there is a signature, otherwise the sender name), ' +
  'movement_volume (integer number of members moving, or null if no firm number is given), notification_date (YYYY-MM-DD, date the ' +
  'trustees first notified us, or null), received_date (YYYY-MM-DD, date the documents were sent or received, or null), ' +
  'confidence (high, medium or low), note (one short sentence on anything vague, missing or inferred). ' +
  'Never guess: use null when the email does not say. If a date has no year use 2026.\n\n' +
  `From: ${sender}\nSubject: ${subject}\n\n${body}`;

/** ai_query over one email. Never throws on a bad model reply: returns empty fields and a note. */
export async function extractPayload(subject, sender, body) {
  const rows = await run(`SELECT ai_query('${MODEL}', :prompt) AS reply`, { prompt: prompt(subject, sender, body).slice(0, 6000) });
  const raw = rows[0]?.reply || '';
  let obj = {};
  const m = /\{[\s\S]*\}/.exec(raw);
  try { obj = m ? JSON.parse(m[0]) : {}; } catch { obj = {}; }
  const payload = Object.fromEntries(PAYLOAD_FIELDS.map((k) => [k, obj[k] ?? null]));
  payload.confidence = ['high', 'medium', 'low'].includes(obj.confidence) ? obj.confidence : 'low';
  payload.note = obj.note || (Object.keys(obj).length ? '' : 'The model reply could not be read; fill the fields by hand.');
  // Confidence is not left to the model: a hedged number is low, a missing key field caps it at medium.
  if (payload.movement_volume != null && /\b(around|approx\w*|about|roughly|circa|give or take|estimate\w*|ish)\b/i.test(body || '')) {
    payload.confidence = 'low';
    payload.note = `The email hedges the number of members (for example 'around'), so check it. ${payload.note}`;
  } else if (payload.confidence === 'high' && ['movement_volume', 'notification_date', 'received_date'].some((k) => payload[k] == null)) {
    payload.confidence = 'medium';
  }
  return payload;
}

export async function logMatches(scheme, notificationDate) {
  if (!scheme) return [];
  if (!notificationDate) {
    return run(`SELECT log_id, scheme, notification_date, received_date, movement_volume, status
                FROM ${SCHEMA}.silver_buyin_log WHERE scheme = :scheme AND status = 'pending' ORDER BY log_id`, { scheme });
  }
  return run(`SELECT log_id, scheme, notification_date, received_date, movement_volume, status
              FROM ${SCHEMA}.silver_buyin_log WHERE scheme = :scheme AND notification_date = :nd ORDER BY log_id`, { scheme, nd: notificationDate });
}

export async function saveEmailReview(messageId, status, payload, original, reason, editedBy) {
  if (!['confirmed', 'rejected'].includes(status)) throw new UserError('Unsupported status.');
  const known = (await run(`SELECT 1 AS x FROM ${SCHEMA}.inbound_emails WHERE message_id = :m`, { m: messageId })).length;
  if (!messageId || !known) throw new UserError('An email is required.');
  let stored = null;
  if (status === 'confirmed') {
    const { clean, problems } = validatePayload(payload || {});
    if (problems.length) throw new UserError(problems.join(' '));
    stored = JSON.stringify({ ...clean, source: 'email', message_id: messageId });
  } else if (!String(reason ?? '').trim()) throw new UserError('Say why the email is rejected.');
  await run(`INSERT INTO ${SCHEMA}.inbound_email_review
             SELECT uuid(), :message_id, :status, :payload, :original, :reason, :edited_by, current_timestamp()`,
    { message_id: messageId, status, payload: stored, original: JSON.stringify(original || {}), reason: String(reason ?? '').slice(0, 500), edited_by: editedBy || 'unknown' });
}


// ---- Source email and "what to verify" (derived from real data only) ---------------------------------------------
const HEDGE = /\b(around|approx\w*|about|roughly|circa|give or take|estimate\w*|ish)\b/i;

/** Parse one mailbox log line into an email, or null. */
export function parseMailLine(line) {
  const m = /^(\S+)\s+INFO\s+mailbox=(\S+)\s+msg_id=\S+\s+from="([^"<]*?)\s*<([^>]*)>"\s+subject="([^"]*)"\s+body="([\s\S]*)"\s*$/.exec(line || '');
  return m ? { sent_at: m[1], mailbox: m[2], from_name: m[3], from_address: m[4], subject: m[5], body: m[6] } : null;
}

const escapeRe = (t) => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** The phrase in the email body that the figure or date came from, for highlighting. */
export function highlightFor(body, value) {
  if (!body || value == null || value === '') return null;
  const v = String(value).replace(/\.0+$/, '');
  const tries = [`(?:\\b(?:approx\\w*|around|about|roughly|circa)\\s+)?${escapeRe(v)}`];
  const iso = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v);
  if (iso) { // the same date written out in the email: 12 August 2026, 12 Aug 2026, 12/08/2026
    const [, y, mo, d] = iso; const long = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'][+mo - 1];
    tries.push(`0?${+d}(?:st|nd|rd|th)?\\s+(?:of\\s+)?(?:${long}|${long.slice(0, 3)}\\w*)\\s+${y}`, `${d}/${mo}/${y}`);
  }
  for (const t of tries) { const m = new RegExp(t, 'i').exec(body); if (m) return m[0]; }
  return null;
}

/** Everything the card needs besides the raw row. Checks are computed, never typed in by hand. */
export function describeCell(c, link = null) {
  const isVol = c.column_name === 'movement_volume';
  const email = parseMailLine(c.source_line) || link?.email || null;
  const viaInbound = !parseMailLine(c.source_line) && !!link;
  const fromMailbox = isVol ? (c.email_volume == null ? null : String(Math.trunc(Number(c.email_volume)))) : (c.email_received_date ? String(c.email_received_date).slice(0, 10) : null);
  const fromInbound = link ? (isVol ? (link.extracted.movement_volume == null ? null : String(link.extracted.movement_volume)) : (link.extracted.received_date || null)) : null;
  const emailValue = viaInbound ? fromInbound : fromMailbox;
  const checks = [];
  if (!email) checks.push({ ok: false, text: 'No trustee email is linked to this entry' });
  else {
    checks.push({ ok: true, text: viaInbound ? (String(link.email.source || '').startsWith('Outlook') ? 'An email from the Outlook mailbox is linked to this entry' : String(link.email.source || '').startsWith('Test') ? 'A made-up test email is linked to this entry' : 'A sample inbound email is linked to this entry') : 'A trustee email is linked to this entry' });
    if (viaInbound && link.extracted.confidence === 'low') checks.push({ ok: false, text: 'The model is not confident about this email' });
    if (!emailValue) checks.push({ ok: false, text: isVol ? 'The email does not give a firm number of members' : 'The email does not give a received date' });
    if (isVol) {
      checks.push(HEDGE.test(email.body) ? { ok: false, text: "The email hedges the number (for example 'approx' or 'around')" } : { ok: true, text: 'The email gives a firm number' });
      const typed = /\d+/.exec(c.raw_value || '');
      if (typed && emailValue) checks.push(typed[0] === emailValue ? { ok: true, text: 'The email number agrees with the number typed in Excel' } : { ok: false, text: `The email says ${emailValue} but the Excel cell says ${typed[0]}` });
    } else if (emailValue && c.notification_date) {
      checks.push(emailValue >= String(c.notification_date).slice(0, 10) ? { ok: true, text: 'The received date is on or after the notification date' } : { ok: false, text: 'The received date is before the notification date' });
    }
  }
  return {
    log_id: c.log_id, scheme: c.scheme, column_name: c.column_name, raw_value: c.raw_value, notification_date: c.notification_date, source_file: c.source_file,
    pill: c.reason ? c.reason.charAt(0).toUpperCase() + c.reason.slice(1) : 'Invalid',
    expects: isVol ? 'Whole number' : 'Date (YYYY-MM-DD)',
    email_value: emailValue, trustee_contact: c.trustee_contact, email, via: viaInbound ? (String(link.email.source || '').startsWith('Outlook') ? 'outlook' : String(link.email.source || '').startsWith('Test') ? 'test' : 'inbound') : 'mailbox',
    highlight: email ? highlightFor(email.body, isVol ? emailValue : emailValue) : null, checks,
  };
}

const extractCache = new Map(); // message_id -> Promise<payload|null>; one model call per email per server process
const extractedFor = (e) => {
  if (!extractCache.has(e.message_id)) extractCache.set(e.message_id, extractPayload(e.subject, e.from_name, e.body_text).catch(() => { extractCache.delete(e.message_id); return null; }));
  return extractCache.get(e.message_id);
};

/** For cells the mailbox log cannot explain, find an inbound email about the same scheme (and the same notification date when the email gives one). */
export async function inboundLinks(cells, inbound) {
  const open = cells.filter((c) => !parseMailLine(c.source_line));
  const cand = new Map(open.map((c) => [c, inbound.filter((e) => e.subject.toLowerCase().includes(String(c.scheme).toLowerCase()))]));
  const needed = [...new Set([...cand.values()].flat())];
  const done = new Map(await Promise.all(needed.map(async (e) => [e.message_id, await extractedFor(e)])));
  const links = new Map();
  for (const [c, list] of cand) {
    const nd = String(c.notification_date).slice(0, 10);
    const ok = list.map((e) => ({ e, x: done.get(e.message_id) })).filter(({ x }) => x && (!x.notification_date || x.notification_date === nd))
      .sort((a, b) => (b.x.notification_date === nd) - (a.x.notification_date === nd) || String(b.e.received_at).localeCompare(String(a.e.received_at)));
    if (ok[0]) links.set(c, { extracted: ok[0].x, email: { source: ok[0].e.source, sent_at: ok[0].e.received_at, mailbox: null, from_name: ok[0].e.from_name, from_address: ok[0].e.from_address, subject: ok[0].e.subject, body: ok[0].e.body_text } });
  }
  return links;
}

export function describeReviewRow(r) {
  const email = parseMailLine(r.source_line);
  return { ...r, source_line: undefined, email, highlight: email ? highlightFor(email.body, r.members_to_move) : null,
           hedged: email ? HEDGE.test(email.body) : false };
}


// ---- Compare each inbound email with the Excel log ----------------------------------------------------------------
const normName = (s) => String(s ?? '').toLowerCase().replace(/[^a-z0-9]/g, '');
const dayOf = (v) => (v ? String(v).slice(0, 10) : null);
const blank = (v) => v == null || v === '';

/** Verdict for one field: match, differs, missing_in_log, missing_in_email or both_missing. */
export function verdictFor(emailVal, otherVal, equal = (a, b) => String(a) === String(b)) {
  if (blank(emailVal) && blank(otherVal)) return 'both_missing';
  if (blank(emailVal)) return 'missing_in_email';
  if (blank(otherVal)) return 'missing_in_log';
  return equal(emailVal, otherVal) ? 'match' : 'differs';
}

const logRowsFor = (scheme) => run(`
  SELECT s.log_id, s.scheme, s.trustee_contact, s.notification_date, s.received_date, s.movement_volume, s.status, qv.raw_value AS volume_raw, qr.raw_value AS received_raw
  FROM ${SCHEMA}.silver_buyin_log s
  LEFT JOIN ${SCHEMA}.buyin_quarantine qv ON qv.log_id = s.log_id AND qv.column_name = 'movement_volume'
  LEFT JOIN ${SCHEMA}.buyin_quarantine qr ON qr.log_id = s.log_id AND qr.column_name = 'received_date'
  WHERE lower(s.scheme) = lower(:scheme) ORDER BY s.notification_date`, { scheme });

/** Pick the Excel entry an email is about: same scheme and notification date; without a date, the scheme's only pending (or only) entry. */
export function pickEntry(p, rows) {
  if (!rows.length) return { entry: null, how: 'No Excel entry for this scheme' };
  if (p.notification_date) {
    const e = rows.find((r) => dayOf(r.notification_date) === p.notification_date);
    return e ? { entry: e, how: 'Same scheme and notification date' } : { entry: null, how: `No entry for this scheme notified on ${p.notification_date}` };
  }
  const pending = rows.filter((r) => r.status === 'pending');
  if (pending.length === 1) return { entry: pending[0], how: 'The email gives no notification date, so the scheme\'s only pending entry' };
  if (rows.length === 1) return { entry: rows[0], how: 'The email gives no notification date, so the scheme\'s only entry' };
  return { entry: null, how: `The email gives no notification date and the scheme has ${rows.length} entries` };
}

export function compareToLog(p, entry, attachmentText) {
  const fields = [];
  const hedged = p.confidence === 'low' && p.movement_volume != null;
  const lv = entry ? entry.movement_volume : null;
  fields.push({ key: 'volume', label: 'Members moving', email: p.movement_volume, other: lv ?? (entry?.volume_raw ? `"${entry.volume_raw}"` : null), otherLabel: 'Excel log',
    verdict: verdictFor(p.movement_volume, lv, (a, b) => Number(a) === Number(b)),
    note: hedged ? 'The email hedges this number (for example "around")' : (entry && blank(lv) && entry.volume_raw ? `The Excel cell holds "${entry.volume_raw}", which is not a number` : '') });
  fields.push({ key: 'notified', label: 'Notified', email: p.notification_date, other: entry ? dayOf(entry.notification_date) : null, otherLabel: 'Excel log',
    verdict: verdictFor(p.notification_date, entry ? dayOf(entry.notification_date) : null), note: '' });
  const lr = entry ? dayOf(entry.received_date) : null;
  fields.push({ key: 'received', label: 'Documents received', email: p.received_date, other: lr ?? (entry?.received_raw ? `"${entry.received_raw}"` : null), otherLabel: 'Excel log',
    verdict: verdictFor(p.received_date, lr), note: entry && blank(lr) && entry.received_raw ? `The Excel cell holds "${entry.received_raw}", which is not a date` : '' });
  fields.push({ key: 'trustee', label: 'Trustee', email: p.trustee, other: entry ? entry.trustee_contact : null, otherLabel: 'Excel log',
    verdict: verdictFor(p.trustee, entry ? entry.trustee_contact : null, (a, b) => normName(a) === normName(b)), note: '' });
  const m = /Excel sheet 1: (\d+) data rows/.exec(attachmentText || '');
  if (m) fields.push({ key: 'attachment', label: 'Members in the attached Excel', email: p.movement_volume, other: Number(m[1]), otherLabel: 'Attached workbook rows',
    verdict: verdictFor(p.movement_volume, Number(m[1]), (a, b) => Number(a) === Number(b)), note: 'One row per member in the attached workbook' });
  // fields compared with the Excel log only count towards the log totals
  return fields;
}

export async function compareAll() {
  const emails = await inboundEmails();
  const out = await Promise.all(emails.map(async (e) => {
    const p = await extractedFor(e);
    const base = { message_id: e.message_id, subject: e.subject, received_at: e.received_at, source: e.source };
    if (!p) return { ...base, status: 'unreadable', summary: 'The model could not read this email', fields: [] };
    if (!p.scheme) return { ...base, status: 'nothing_to_compare', summary: 'The email names no scheme, so there is nothing to compare', confidence: p.confidence, note: p.note, payload: p, fields: [] };
    const { entry, how } = pickEntry(p, await logRowsFor(p.scheme));
    return { ...base, status: entry ? 'compared' : 'no_entry', scheme: p.scheme, confidence: p.confidence, note: p.note, payload: p, how,
      entry: entry ? { log_id: entry.log_id, status: entry.status } : null, fields: compareToLog(p, entry, e.attachment_text) };
  }));
  const tot = { match: 0, differs: 0, missing_in_log: 0, missing_in_email: 0, both_missing: 0 };
  for (const r of out) if (r.status === 'compared') for (const f of r.fields) if (f.key !== 'attachment') tot[f.verdict]++;
  const cells = await unresolvedCells(); const links = await inboundLinks(cells, emails).catch(() => new Map());
  const covered = cells.filter((c) => parseMailLine(c.source_line) || links.has(c)).length;
  return { emails: out, totals: tot, counts: { read: out.length, compared: out.filter((r) => r.status === 'compared').length,
    no_entry: out.filter((r) => r.status === 'no_entry').length, nothing: out.filter((r) => r.status === 'nothing_to_compare' || r.status === 'unreadable').length },
    cells: { total: cells.length, covered } };
}

// ---- Home (portal front page) ----------------------------------------------------------------------------------
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
export const monthOf = (file) => { const m = /(\d{4})_(\d{2})/.exec(file || ''); return m ? `${MONTHS[+m[2] - 1]} ${m[1]}` : file; };
export const firstName = (email) => { const w = String(email || '').split('@')[0].split(/[._-]/)[0]; return /^[a-z]+$/i.test(w) && w.toLowerCase() !== 'unknown' ? w[0].toUpperCase() + w.slice(1).toLowerCase() : ''; };

export async function homeData(email) {
  const [files, totals, open, emails, inbound, kpi] = await Promise.all([
    run(`SELECT source_file, count(DISTINCT log_id) AS entries FROM ${SCHEMA}.silver_buyin_log GROUP BY source_file ORDER BY source_file`),
    run(`SELECT s.source_file, count(*) AS invalid_total FROM ${SCHEMA}.buyin_quarantine q JOIN ${SCHEMA}.silver_buyin_log s ON s.log_id = q.log_id
         WHERE q.fixed_value IS NULL AND q.column_name IN ('movement_volume', 'received_date') GROUP BY s.source_file`),
    unresolvedCells(), reviewEmails(), inboundEmails().catch(() => []),
    run(`SELECT MEASURE(entries) AS entries, MEASURE(breach_rate_pct) AS breach_rate, MEASURE(pending_items) AS pending FROM ${SCHEMA}.mv_buyin_sla`).catch(() => []),
  ]);
  const total = Object.fromEntries(totals.map((r) => [r.source_file, Number(r.invalid_total)]));
  const left = {}; for (const c of open) left[c.source_file] = (left[c.source_file] || 0) + 1;
  const workbooks = files.map((f) => ({ file: f.source_file, month: monthOf(f.source_file), entries: Number(f.entries), invalid_total: total[f.source_file] || 0, to_fix: left[f.source_file] || 0 }));
  return {
    name: firstName(email), workbooks, kpi: kpi[0] || null,
    counts: { cells: open.length, workbooks_with_work: workbooks.filter((w) => w.to_fix > 0).length, workbooks: workbooks.length, emails: emails.length, inbound: inbound.filter((e) => e.review_status === 'to review').length },
  };
}

// ---- Import an attachment into a Unity Catalog volume ---------------------------------------------------------------
const VOLUME_DIR = '/Volumes/bpa_edp/demo/inbound_attachments';
const DOC_EXT = new Set(['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.csv', '.txt']);
const MAX_IMPORT_BYTES = 20 * 1024 * 1024;

async function putVolumeFile(volPath, buf) {
  const enc = volPath.split('/').map(encodeURIComponent).join('/');
  const r = await fetch(`${host()}/api/2.0/fs/files${enc}?overwrite=false`, {
    method: 'PUT', headers: { Authorization: `Bearer ${await token()}`, 'Content-Type': 'application/octet-stream' }, body: buf });
  if (r.status === 409) throw new UserError('A file with that name is already in the volume.');
  if (!r.ok) throw new Error(`volume upload failed: ${r.status} ${(await r.text()).slice(0, 200)}`);
}

/** Copy one stored attachment of a live Outlook email into the volume, once, and record who did it. */
export async function importAttachment(messageId, n, by) {
  if (!messageId || !/^\d{1,2}$/.test(String(n))) throw new UserError('Choose an email and an attachment number.');
  const done = await run(`SELECT volume_path FROM ${SCHEMA}.inbound_attachment_import WHERE message_id = :m AND attachment_index = cast(:n AS INT)`, { m: messageId, n: String(n) });
  if (done.length) return { already: true, path: done[0].volume_path };
  const rows = await run(`SELECT get(attachments, cast(:n AS INT)).file_name AS file_name, get(attachments, cast(:n AS INT)).content AS content,
                                 date_format(received_at, 'yyyy-MM-dd') AS day
                          FROM ${SCHEMA}.outlook_inbox WHERE outlook_message_id = :m`, { m: messageId, n: String(n) });
  const r = rows[0];
  if (!r || !r.content) throw new UserError('That attachment is not available.');
  const buf = Buffer.from(r.content, 'base64');
  if (buf.length > MAX_IMPORT_BYTES) throw new UserError('That file is larger than 20 MB, which is more than this page imports.');
  const name = String(r.file_name || 'attachment').replace(/[^\w.\- ()]/g, '_').replace(/^\.+/, '').slice(0, 120) || 'attachment';
  const ext = path.extname(name).toLowerCase();
  if (!DOC_EXT.has(ext)) throw new UserError(`Files of type ${ext || '(none)'} are not imported. Allowed: ${[...DOC_EXT].join(', ')}.`);
  if (ext === '.pdf' && buf.subarray(0, 5).toString('latin1') !== '%PDF-') throw new UserError('That file is named .pdf but is not a PDF, so it was not imported.');
  const volPath = `${VOLUME_DIR}/${r.day}/${createHash('sha1').update(messageId).digest('hex').slice(0, 10)}/${name}`;
  await putVolumeFile(volPath, buf);
  const sha = createHash('sha256').update(buf).digest('hex');
  await run(`INSERT INTO ${SCHEMA}.inbound_attachment_import SELECT uuid(), :m, cast(:n AS INT), :f, :p, cast(:s AS BIGINT), :h, :by, current_timestamp()`,
    { m: messageId, n: String(n), f: name, p: volPath, s: String(buf.length), h: sha, by: by || 'unknown' });
  return { already: false, path: volPath, size: buf.length };
}

// ---- HTTP -------------------------------------------------------------------------------------------------------
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png' };
const SECURITY = {
  'Content-Security-Policy': "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; form-action 'self'; frame-ancestors 'self'",
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'same-origin',
};

async function readJson(req) {
  let size = 0; const chunks = [];
  for await (const c of req) { size += c.length; if (size > 100_000) throw new UserError('Request too large.'); chunks.push(c); }
  try { return JSON.parse(Buffer.concat(chunks).toString() || '{}'); } catch { throw new UserError('Invalid JSON.'); }
}

const userOf = (req) => req.headers['x-forwarded-email'] || req.headers['x-forwarded-preferred-username'] || 'unknown';

const routes = {
  'GET /api/me': async (req) => ({ user: userOf(req) }),
  'GET /api/compare': async () => compareAll(),
  'GET /api/home': async (req) => homeData(userOf(req)),
  'GET /api/cells': async () => {
    const [cells, inbound] = await Promise.all([unresolvedCells(), inboundEmails().catch(() => [])]);
    const links = await inboundLinks(cells, inbound).catch(() => new Map());
    return { cells: cells.map((c) => describeCell(c, links.get(c) || null)) };
  },
  'POST /api/cells/save': async (req, body) => {
    // Re-read the cell on the server: the client only names it, and it must still be unresolved.
    const cell = (await unresolvedCells()).find((c) => c.log_id === body.log_id && c.column_name === body.column_name);
    if (!cell) throw new UserError('That cell has already been corrected or does not exist.');
    const [ok, res] = validate(cell.column_name, body.value, cell.notification_date);
    if (!ok) throw new UserError(res);
    const fromEmail = cell.column_name === 'movement_volume' && cell.email_volume && String(res) === String(Math.trunc(Number(cell.email_volume)));
    await saveCorrection(cell.log_id, cell.column_name, res, 'apply', body.reason, fromEmail ? 'email' : 'quarantine', userOf(req));
    return { saved: res };
  },
  'GET /api/emails': async () => { const [counts, rows] = await Promise.all([emailCounts(), reviewEmails()]); return { counts, rows: rows.map(describeReviewRow) }; },
  'POST /api/emails/decision': async (req, body) => {
    const row = (await reviewEmails()).find((r) => r.log_id === body.log_id);
    if (!row || !row.log_id) throw new UserError('That email is not waiting for a decision.');
    if (body.action === 'accept') await saveCorrection(row.log_id, 'movement_volume', row.members_to_move, 'apply', 'Accepted the value extracted from the trustee email', 'email', userOf(req));
    else if (body.action === 'reject') await saveCorrection(row.log_id, 'movement_volume', null, 'reject', 'Rejected the value extracted from the trustee email', 'email', userOf(req));
    else throw new UserError('Unsupported action.');
    return { ok: true };
  },
  'GET /api/corrections': async () => ({ rows: await recentCorrections() }),
  'GET /api/inbound': async () => ({ emails: await inboundEmails() }),
  'POST /api/inbound/extract': async (req, body) => {
    const e = (await inboundEmails()).find((x) => x.message_id === body.message_id);
    if (!e) throw new UserError('Unknown email.');
    return { payload: await extractPayload(e.subject, e.from_name, e.body_text) };
  },
  'POST /api/inbound/check': async (req, body) => {
    const { clean, problems } = validatePayload(body.payload || {});
    return { clean, problems, matches: problems.length ? [] : await logMatches(clean.scheme, clean.notification_date) };
  },
  'POST /api/inbound/attachment/import': async (req, body) => importAttachment(body.message_id, body.n, userOf(req)),
  'POST /api/inbound/review': async (req, body) => {
    await saveEmailReview(body.message_id, body.status, body.payload, body.original, body.reason, userOf(req));
    return { ok: true };
  },
};


/** Serve one stored attachment of a live Outlook email. Only PDFs are shown inline (the browser's PDF viewer); everything else downloads. */
async function sendAttachment(res, url, send) {
  const m = url.searchParams.get('message_id') || '', n = url.searchParams.get('n') || '0';
  if (!m || !/^\d{1,2}$/.test(n)) return send(400, { error: 'Choose an email and an attachment number.' });
  const rows = await run(`SELECT get(attachments, cast(:n AS INT)).file_name AS file_name, get(attachments, cast(:n AS INT)).mime_type AS mime_type,
                                 get(attachments, cast(:n AS INT)).content AS content
                          FROM ${SCHEMA}.outlook_inbox WHERE outlook_message_id = :m`, { m, n });
  const r = rows[0];
  if (!r || !r.content) return send(404, { error: 'That attachment is not available.' });
  const buf = Buffer.from(r.content, 'base64');
  const name = String(r.file_name || 'attachment').replace(/[\r\n"\\]/g, '_').slice(0, 150);
  const pdf = r.mime_type === 'application/pdf' && buf.subarray(0, 5).toString('latin1') === '%PDF-';
  const inline = pdf && url.searchParams.get('download') !== '1';
  res.writeHead(200, {
    'Content-Type': pdf ? 'application/pdf' : 'application/octet-stream',
    'Content-Length': buf.length,
    'Content-Disposition': `${inline ? 'inline' : 'attachment'}; filename*=UTF-8''${encodeURIComponent(name).replace(/['()*]/g, escape)}`,
    'Content-Security-Policy': "frame-ancestors 'self'",
    'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, no-store',
  });
  res.end(buf);
}

export const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  const send = (code, obj, headers = {}) => { res.writeHead(code, { 'Content-Type': 'application/json', ...SECURITY, ...headers }); res.end(JSON.stringify(obj)); };
  try {
    if (req.method === 'GET' && url.pathname === '/api/inbound/attachment') return await sendAttachment(res, url, send);
    const handler = routes[`${req.method} ${url.pathname}`];
    if (handler) return send(200, await handler(req, req.method === 'POST' ? await readJson(req) : null));
    if (url.pathname.startsWith('/api/')) return send(404, { error: 'Not found.' });
    if (req.method !== 'GET') return send(405, { error: 'Method not allowed.' });
    const rel = url.pathname === '/' ? 'index.html' : url.pathname.slice(1);
    const file = path.normalize(path.join(PUBLIC, rel));
    if (!file.startsWith(PUBLIC + path.sep)) return send(404, { error: 'Not found.' });
    const data = await readFile(file).catch(() => null);
    if (!data) return send(404, { error: 'Not found.' });
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream', ...SECURITY });
    res.end(data);
  } catch (e) {
    if (e instanceof UserError) return send(400, { error: e.message });
    console.error(e);
    send(500, { error: `Something went wrong: ${e.message}` });
  }
});

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  server.listen(PORT, '0.0.0.0', () => console.log(`buy-in editor (node) listening on ${PORT}`));
}
