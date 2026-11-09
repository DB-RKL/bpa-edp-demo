// Buy-in operations (Node version). Plain ES modules, no framework.
// Every piece of text from the server (including email bodies) is added as a text node, never as HTML.
const PAGES = [['home', 'Home'], ['fix', 'Fix invalid cells'], ['emails', 'Review emails'], ['inbound', 'Inbound emails'], ['compare', 'Email vs Excel']];
const TITLES = { compare: 'Email vs Excel log', home: 'Home', fix: 'Fix invalid cells', emails: 'Review emails', inbound: 'Inbound emails' };
const state = { page: 'home', flash: null, scheme: 'All schemes', workbook: null, skipped: new Set(), inbound: { emails: null, selected: null, drafts: {} } };
const SVG = 'http://www.w3.org/2000/svg';
if (typeof location !== 'undefined') { const start = location.hash.slice(1); if (PAGES.some(([id]) => id === start)) state.page = start; } // deep links: /#fix, /#emails, /#inbound

function h(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'value') e.value = v;
    else if (v === true) e.setAttribute(k, '');
    else e.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) e.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return e;
}
function icon(name, cls = '') {
  const paths = {
    mail: ['M3 6h18v12H3z', 'M3 7l9 6 9-6'],
    minus: ['M5 12h14'],
    clip: ['M21 11.5l-8.5 8.5a5 5 0 0 1-7-7l9-9a3.5 3.5 0 0 1 5 5l-9 9a2 2 0 0 1-3-3l8-8'],
    check: ['M5 12.5l4.5 4.5L19 7.5'],
    warn: ['M12 4l9 16H3z', 'M12 10v4', 'M12 17.5v.01'],
  }[name];
  const s = document.createElementNS(SVG, 'svg');
  for (const [k, v] of Object.entries({ width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 1.8, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true', class: cls })) s.setAttribute(k, v);
  for (const d of paths) { const p = document.createElementNS(SVG, 'path'); p.setAttribute('d', d); s.append(p); }
  return s;
}
const day = (s) => (s ? String(s).slice(0, 10) : '');
const longDay = (s) => (s ? new Date(`${day(s)}T00:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }) : '');
const longStamp = (s) => (s ? new Date(s).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }) : '');
const stamp = (s) => (s ? String(s).slice(0, 16).replace('T', ' ') : '');
const initials = (name) => (String(name || '?').match(/[A-Za-z]+/g) || ['?']).slice(0, 2).map((w) => w[0].toUpperCase()).join('');

async function api(path, body) {
  const r = await fetch(path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `Request failed (${r.status})`);
  return j;
}

const alertBox = (kind, text) => h('div', { class: `alert ${kind}`, role: kind === 'error' ? 'alert' : null }, text);
const field = (label, input) => h('div', {}, h('label', {}, label), input);
const kv = (k, v, cls = '') => h('div', { class: 'kv' }, h('span', { class: 'k' }, k), h('span', { class: `v ${cls}` }, v));
const checks = (list) => h('ul', { class: 'checks' }, list.map((c) => h('li', { class: c.ok ? 'ok' : 'warn' }, icon(c.ok ? 'check' : 'warn'), h('span', {}, c.text))));
function table(rows, cols) {
  return h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, cols.map(([, t]) => h('th', {}, t)))),
    h('tbody', {}, rows.map((r) => h('tr', {}, cols.map(([k]) => h('td', {}, /date/.test(k) ? day(r[k]) : k.endsWith('_at') ? stamp(r[k]) : r[k] ?? '')))))));
}
const busy = (btn, text, fn) => async () => {
  const old = btn.textContent; btn.disabled = true; btn.textContent = text;
  try { await fn(); } finally { btn.disabled = false; btn.textContent = old; }
};

/** Email text with the figure or date it was read from highlighted. */
function highlighted(text, phrase) {
  const i = phrase ? text.toLowerCase().indexOf(phrase.toLowerCase()) : -1;
  return i < 0 ? [text] : [text.slice(0, i), h('mark', {}, text.slice(i, i + phrase.length)), text.slice(i + phrase.length)];
}
/** Left-hand panel: the email a figure came from, or an honest empty state. */
const fmtSize = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n >= 1024 ? `${Math.round(n / 1024)} KB` : `${n} bytes`);
function sourcePanel({ name, address, when, to, subject, body, phrase, label, attachments, messageId, imports, attachmentText }, emptyText) {
  const head = h('div', { class: 'label' }, icon('mail'), label || 'Source email');
  if (!body) return h('section', { class: 'src' }, head, h('div', { class: 'empty' }, emptyText));
  return h('section', { class: 'src' }, head,
    h('div', { class: 'sender' }, h('div', { class: 'avatar', 'aria-hidden': 'true' }, initials(name)),
      h('div', {}, h('div', { class: 'name' }, name), h('div', { class: 'meta' }, [longStamp(when), to ? ` · to ${to}` : '', address ? ` · ${address}` : ''].join('')))),
    h('div', { class: 'subject' }, subject), h('p', { class: 'body' }, highlighted(body, phrase)),
    attachments?.length ? attachmentList(attachments, messageId, imports || [], attachmentText) : null);
}
/** Attachment chips. For live Outlook emails each one gets View (PDF only) and Download, served by the app from the stored bytes. */
function attachmentList(attachments, messageId, imports, attachmentText) {
  const viewer = h('div', { class: 'docview-wrap' });
  const msg = h('div');
  const url = (i, dl) => `/api/inbound/attachment?message_id=${encodeURIComponent(messageId)}&n=${i}${dl ? '&download=1' : ''}`;
  const list = h('ul', { class: 'attach', 'aria-label': 'Attachments' }, attachments.map((x, i) => {
    const kids = [icon('clip'), h('span', {}, x.name), h('span', { class: 'muted' }, ` ${fmtSize(Number(x.size) || 0)}`)];
    const tag = { read: `text read (${x.chars} characters)`, 'no text': 'no text found in it', 'not supported': 'contents not read (file type)', error: 'could not be read' }[x.status];
    if (tag) kids.push(h('span', { class: 'tag' }, tag));
    if (messageId) {
      if (x.type === 'application/pdf') {
        const view = h('button', { class: 'btn small', type: 'button', 'aria-expanded': 'false' }, 'View');
        view.addEventListener('click', () => {
          const open = viewer.firstChild && viewer.dataset.n === String(i);
          viewer.replaceChildren(); delete viewer.dataset.n; view.setAttribute('aria-expanded', 'false'); view.textContent = 'View';
          if (!open) { viewer.dataset.n = String(i); viewer.append(h('iframe', { class: 'docview', title: `Preview of ${x.name}`, src: url(i, false) })); view.setAttribute('aria-expanded', 'true'); view.textContent = 'Hide'; }
        });
        kids.push(view);
      }
      kids.push(h('a', { class: 'btn small link', href: url(i, true), download: x.name }, 'Download'));
      const done = imports.find((q) => Number(q.n) === i);
      if (done) kids.push(h('span', { class: 'imported' }, 'In volume: ', h('code', {}, done.path.replace('/Volumes/bpa_edp/demo/', ''))));
      else {
        const imp = h('button', { class: 'btn small primary', type: 'button' }, 'Import to volume');
        imp.addEventListener('click', busy(imp, 'Importing', async () => {
          msg.replaceChildren();
          try { const r = await api('/api/inbound/attachment/import', { message_id: messageId, n: i }); setFlash(`${r.already ? 'Already imported' : 'Imported'}: ${x.name} is in ${r.path}`); }
          catch (err) { msg.append(alertBox('error', `Could not import: ${err.message}`)); return; }
          await render();
        }));
        kids.push(imp);
      }
    }
    return h('li', {}, kids);
  }));
  const said = attachmentText ? h('details', { class: 'small' }, h('summary', {}, 'Text read from the attachments'), h('pre', { class: 'email' }, attachmentText)) : null;
  return h('div', {}, list, said, msg, viewer);
}

function setHead(title, subtitle, right) {
  document.getElementById('head').replaceChildren(h('div', { class: 'head' },
    h('div', {}, h('h1', {}, title), subtitle ? h('p', { class: 'subtitle' }, subtitle) : null), right || null));
}
const setFlash = (msg) => { state.flash = msg; };
function renderFlash() {
  const f = document.getElementById('flash'); f.replaceChildren();
  if (state.flash) { f.append(alertBox('success', state.flash)); state.flash = null; }
}

async function recentCorrections() {
  const { rows } = await api('/api/corrections');
  return [h('h2', {}, 'Recent corrections'), rows.length
    ? table(rows, [['edited_at', 'When'], ['edited_by', 'Who'], ['log_id', 'Entry'], ['column_name', 'Column'], ['corrected_value', 'Value'], ['action', 'Action'], ['source', 'Source'], ['reason', 'Reason']])
    : h('p', { class: 'muted' }, 'No corrections have been made yet.')];
}


// ---- Home: the portal front page ------------------------------------------------------------------------------
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
function go(page, workbook = null) { state.page = page; state.workbook = workbook; render(); }
async function pageHome(view) {
  const d = await api('/api/home'), c = d.counts;
  const hour = new Date().getHours();
  setHead(`${hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'}${d.name ? `, ${d.name}` : ''}`, 'Buy-in operations', null);
  const todo = c.cells + c.emails + c.inbound;
  view.append(h('div', { class: 'lead' },
    todo === 0 ? h('p', {}, 'You are all caught up. There is nothing waiting for review.') : [
      c.cells ? h('p', {}, 'You have ', h('strong', {}, plural(c.cells, 'cell')), ' to fix across ', h('strong', {}, plural(c.workbooks_with_work, 'Excel workbook')), '.') : h('p', {}, 'Every invalid cell in the Excel workbooks has a correction.'),
      h('p', { class: 'muted' }, `${plural(c.emails, 'email')} disagree${c.emails === 1 ? 's' : ''} with the spreadsheet and ${plural(c.inbound, 'inbound email')} ${c.inbound === 1 ? 'is' : 'are'} waiting for review.`)]));
  const tile = (n, label, sub, button, page) => {
    const b = h('button', { class: 'btn primary', type: 'button' }, button); b.addEventListener('click', () => go(page));
    return h('div', { class: 'tile' }, h('div', { class: 'num' }, n), h('div', { class: 'tl' }, label), h('div', { class: 'muted' }, sub), h('div', { class: 'actions' }, b));
  };
  view.append(h('div', { class: 'tiles' },
    tile(c.cells, 'cells to fix', `in ${c.workbooks_with_work} of ${c.workbooks} Excel workbooks`, 'Start fixing', 'fix'),
    tile(c.emails, 'emails disagree with the spreadsheet', 'Trustee emails read automatically', 'Review emails', 'emails'),
    tile(c.inbound, 'inbound emails to review', 'Waiting for a decision', 'Open inbound emails', 'inbound')));

  view.append(h('h2', {}, 'Excel workbooks'));
  for (const w of d.workbooks) {
    const done = w.invalid_total - w.to_fix, pct = w.invalid_total ? Math.round((100 * done) / w.invalid_total) : 100;
    const open = h('button', { class: 'btn', type: 'button' }, 'Review'); open.addEventListener('click', () => go('fix', w.file));
    view.append(h('div', { class: 'wb' },
      h('div', {}, h('div', { class: 'wbname' }, w.month), h('div', { class: 'muted' }, `${w.file} · ${plural(w.entries, 'entry', 'entries')}`)),
      h('div', { class: 'wbprog' }, h('div', { class: 'bar2', role: 'img', 'aria-label': `${done} of ${w.invalid_total} invalid cells corrected` }, h('div', { style: `width:${pct}%` })), h('div', { class: 'muted' }, `${done} of ${w.invalid_total} invalid cells corrected`)),
      h('div', { class: 'wbact' }, w.to_fix ? h('span', { class: 'pill amber' }, `${w.to_fix} to fix`) : h('span', { class: 'pill green' }, 'Done'), w.to_fix ? open : null)));
  }
  if (d.kpi) view.append(h('h2', {}, 'At a glance'), h('div', { class: 'tiles' },
    h('div', { class: 'tile' }, h('div', { class: 'num' }, d.kpi.entries), h('div', { class: 'tl' }, 'buy-in entries')),
    h('div', { class: 'tile' }, h('div', { class: 'num' }, `${d.kpi.breach_rate}%`), h('div', { class: 'tl' }, 'SLA breach rate'), h('div', { class: 'muted' }, 'Breaches as a share of received entries')),
    h('div', { class: 'tile' }, h('div', { class: 'num' }, d.kpi.pending), h('div', { class: 'tl' }, 'pending items'), h('div', { class: 'muted' }, 'No received date yet'))),
    h('p', { class: 'muted' }, 'These use the same definitions as the dashboards, so the numbers agree.'));
  view.append(...await recentCorrections());
}

// ---- Page 1: invalid cells --------------------------------------------------------------------------------------
const LABELS = { movement_volume: 'Movement volume (members)', received_date: 'Received date' };
const FIELD_LABELS = { movement_volume: 'Corrected volume', received_date: 'Corrected received date' };
async function pageFix(view) {
  const { cells } = await api('/api/cells');
  const schemes = ['All schemes', ...[...new Set(cells.map((c) => c.scheme))].sort()];
  if (!schemes.includes(state.scheme)) state.scheme = 'All schemes';
  const shown = cells.filter((c) => (state.scheme === 'All schemes' || c.scheme === state.scheme) && (!state.workbook || c.source_file === state.workbook) && !state.skipped.has(`${c.log_id}_${c.column_name}`));
  const filter = h('select', { id: 'scheme-filter', 'aria-label': 'Filter by scheme' }, schemes.map((s) => h('option', { value: s, selected: s === state.scheme }, s)));
  filter.addEventListener('change', () => { state.scheme = filter.value; render(); });
  const clear = state.workbook ? h('button', { class: 'btn small', type: 'button', id: 'clear-workbook' }, `Workbook: ${state.workbook} (show all)`) : null;
  clear?.addEventListener('click', () => { state.workbook = null; render(); });
  setHead(TITLES.fix, `${plural(shown.length, 'cell')} waiting for Buy-in operations`, h('div', { class: 'head-right' }, clear, filter));
  if (!shown.length) view.append(alertBox('success', cells.length ? 'Nothing left to show for this filter. Skipped cards come back when you reload.' : 'Every invalid cell has a correction.'));
  for (const c of shown) {
    const col = c.column_name, id = `${c.log_id}_${col}`;
    const input = h('input', { type: 'text', id: `v_${id}`, value: c.email_value || '', inputmode: col === 'movement_volume' ? 'numeric' : null, 'aria-label': FIELD_LABELS[col] });
    const reason = h('input', { type: 'text', id: `r_${id}`, placeholder: 'Optional note', 'aria-label': 'Reason (optional)' });
    const msg = h('div');
    const save = h('button', { class: 'btn primary', type: 'button' }, 'Save correction');
    save.addEventListener('click', busy(save, 'Saving', async () => {
      msg.replaceChildren();
      try { await api('/api/cells/save', { log_id: c.log_id, column_name: col, value: input.value, reason: reason.value }); }
      catch (e) { msg.append(alertBox('error', e.message)); return; }
      setFlash(`Saved ${LABELS[col].toLowerCase()} ${input.value.trim()} for ${c.log_id}.`); await render();
    }));
    const skip = h('button', { class: 'btn ghost', type: 'button' }, 'Skip for now');
    skip.addEventListener('click', () => { state.skipped.add(id); render(); });
    const em = c.email;
    view.append(h('article', { class: 'card' },
      h('header', { class: 'card-head' }, h('div', {}, h('h2', { class: 'card-title' }, `${c.log_id} · ${c.scheme}`), h('p', { class: 'sub' }, `${LABELS[col]} · notified ${longDay(c.notification_date)}`)), h('span', { class: 'pill red' }, c.pill)),
      h('div', { class: 'card-body' },
        sourcePanel(em ? { name: em.from_name, address: em.from_address, when: em.sent_at, to: em.mailbox, subject: em.subject, body: em.body, phrase: c.highlight, label: c.via === 'outlook' ? 'Source email (Outlook, live connector)' : c.via === 'test' ? 'Source email (TEST EMAIL, made up)' : c.via === 'inbound' ? 'Source email (sample inbound email)' : null } : {}, 'No trustee email is linked to this entry, so there is nothing to compare the cell against.'),
        h('section', { class: 'verify' }, h('div', { class: 'label' }, 'What to verify'),
          kv('Excel log says', c.raw_value ?? '', 'mono'), kv('Column expects', c.expects),
          c.email_value ? kv('Email suggests', c.email_value, 'strong') : kv('Email suggests', em ? 'Not stated in the email' : 'No email found', 'dim'),
          checks(c.checks),
          h('div', { class: 'fields two' }, field(FIELD_LABELS[col], input), field('Reason (optional)', reason)),
          msg, h('div', { class: 'actions' }, save, skip)))));
  }
  view.append(...await recentCorrections());
}

// ---- Page 2: emails that disagree with the log ----------------------------------------------------------------
const STATUS = { 'Excel value invalid: use email value': 'Excel value invalid', 'differs from Excel': 'Differs from Excel', 'not in Excel log': 'Not in Excel log' };
async function pageEmails(view) {
  const { counts, rows } = await api('/api/emails');
  setHead(TITLES.emails, `${rows.length} need a decision. ${counts['matches Excel'] || 0} match the Excel log.`, null);
  if (!rows.length) view.append(alertBox('success', 'No emails are waiting for a decision.'));
  for (const r of rows) {
    const msg = h('div');
    const decide = (action, label, cls, done) => {
      const b = h('button', { class: `btn ${cls}`, type: 'button' }, label);
      b.addEventListener('click', busy(b, 'Saving', async () => {
        try { await api('/api/emails/decision', { log_id: r.log_id, action }); } catch (e) { msg.replaceChildren(alertBox('error', e.message)); return; }
        setFlash(done); await render();
      }));
      return b;
    };
    const em = r.email;
    const list = [em ? { ok: !r.hedged, text: r.hedged ? "The email hedges the number (for example 'approx' or 'around')" : 'The email gives a firm number' } : { ok: false, text: 'The original email text is not available' }];
    view.append(h('article', { class: 'card' },
      h('header', { class: 'card-head' }, h('div', {}, h('h2', { class: 'card-title' }, `${r.log_id || 'No entry'} · ${r.scheme}`), h('p', { class: 'sub' }, `Trustee email from ${r.trustee} · notified ${longDay(r.notified_date)}`)), h('span', { class: 'pill red' }, STATUS[r.review_status] || r.review_status)),
      h('div', { class: 'card-body' },
        sourcePanel(em ? { name: em.from_name, address: em.from_address, when: em.sent_at, to: em.mailbox, subject: em.subject, body: em.body, phrase: r.highlight } : {}, 'The original email text is not available for this entry.'),
        h('section', { class: 'verify' }, h('div', { class: 'label' }, 'What to verify'),
          kv('Excel log says', r.excel_volume || 'Invalid or empty', r.excel_volume ? 'mono' : 'dim'), kv('Email suggests', `${r.members_to_move} members`, 'strong'),
          kv('Notified', longDay(r.notified_date)), kv('Documents received', longDay(r.received_date)), checks(list), msg,
          r.log_id ? h('div', { class: 'actions' }, decide('accept', 'Accept the email value', 'primary', `Accepted ${r.members_to_move} members for ${r.log_id}.`), decide('reject', 'Reject', '', `Rejected the email value for ${r.log_id}.`))
                   : alertBox('info', 'There is no matching Excel entry, so nothing can be corrected here.')))));
  }
  view.append(...await recentCorrections());
}

// ---- Page 3: inbound emails ---------------------------------------------------------------------------------------
const FIELDS = ['scheme', 'trustee', 'movement_volume', 'notification_date', 'received_date'];
const PILL = { 'to review': ['amber', 'To review'], confirmed: ['green', 'Confirmed'], rejected: ['red', 'Rejected'] };
async function pageInbound(view) {
  const st = state.inbound;
  st.emails = (await api('/api/inbound')).emails;
  if (!st.emails.some((e) => e.message_id === st.selected)) st.selected = st.emails[0]?.message_id ?? null;
  const waiting = st.emails.filter((e) => e.review_status === 'to review').length;
  const select = h('select', { id: 'email-select', 'aria-label': 'Choose an email' }, st.emails.map((x) => h('option', { value: x.message_id, selected: x.message_id === st.selected }, `${stamp(x.received_at)} | ${x.review_status} | ${x.subject}`.slice(0, 70))));
  select.addEventListener('change', () => { st.selected = select.value; render(); });
  setHead(TITLES.inbound, `${waiting} to review`, st.emails.length ? h('div', { class: 'head-right' }, select) : null);
  if (!st.emails.length) { view.append(alertBox('info', 'No emails have landed yet. Check the flow and the pipeline run.')); return; }
  const e = st.emails.find((x) => x.message_id === st.selected);
  const draft = st.drafts[e.message_id];
  const phrase = draft?.payload?.movement_volume != null ? (e.body_text.match(new RegExp(`(?:\\b(?:approx\\w*|around|about|roughly|circa)\\s+)?${draft.fields.movement_volume}`, 'i')) || [])[0] : null;
  const verify = h('section', { class: 'verify' }, h('div', { class: 'label' }, 'What to verify'));
  const [pc, pt] = PILL[e.review_status];
  view.append(h('article', { class: 'card' },
    h('header', { class: 'card-head' }, h('div', {}, h('h2', { class: 'card-title' }, e.subject), h('p', { class: 'sub' }, `From ${e.from_name} · ${e.source || 'Sample'}`)), h('span', { class: `pill ${pc}` }, pt)),
    h('div', { class: 'card-body' }, sourcePanel({ name: e.from_name, address: e.from_address, when: e.received_at, subject: e.subject, body: e.body_text, phrase, attachments: JSON.parse(e.attachments_json || '[]'), messageId: e.source && e.source.startsWith('Outlook') ? e.message_id : null, imports: JSON.parse(e.imports_json || '[]'), attachmentText: e.attachment_text, label: e.source && e.source.startsWith('Outlook') ? 'Source email (Outlook, live connector)' : e.source && e.source.startsWith('Test') ? 'Source email (TEST EMAIL, made up)' : 'Source email (sample)' }, ''), verify)));

  if (e.review_status !== 'to review') {
    verify.append(alertBox('info', `This email was ${e.review_status} by ${e.edited_by} at ${stamp(e.edited_at)}.${e.reason ? ` Reason: ${e.reason}` : ''}`));
    if (e.payload_json) verify.append(h('pre', { class: 'json' }, JSON.stringify(JSON.parse(e.payload_json), null, 2)));
    return;
  }
  const format = h('button', { class: 'btn primary', type: 'button', id: 'format' }, 'Format email into payload');
  format.addEventListener('click', async () => {
    format.disabled = true; format.replaceChildren(h('span', { class: 'spinner' }), 'Reading the email');
    try {
      const { payload } = await api('/api/inbound/extract', { message_id: e.message_id });
      st.drafts[e.message_id] = { payload, fields: Object.fromEntries(FIELDS.map((f) => [f, payload[f] == null ? '' : String(payload[f])])), reason: '' };
      await render();
    } catch (err) { format.disabled = false; format.textContent = 'Format email into payload'; verify.prepend(alertBox('error', `Could not read the email: ${err.message}`)); }
  });
  if (!draft) { verify.append(h('p', { class: 'muted' }, 'The model reads the email and drafts the record. You check each field against the email on the left before anything is saved.'), h('div', { class: 'actions' }, format)); return; }

  const conf = draft.payload.confidence;
  verify.append(h('ul', { class: 'checks' }, h('li', { class: conf === 'high' ? 'ok' : 'warn' }, icon(conf === 'high' ? 'check' : 'warn'), h('span', {}, `Model confidence: ${conf}. ${draft.payload.note}`))));
  const inputs = {};
  const mk = (f, label) => { inputs[f] = h('input', { type: 'text', id: `f_${f}`, value: draft.fields[f], 'aria-label': label }); inputs[f].addEventListener('input', () => { draft.fields[f] = inputs[f].value; schedule(); }); return field(label, inputs[f]); };
  const reason = h('input', { type: 'text', id: 'f_reason', value: draft.reason, placeholder: 'Needed to reject', 'aria-label': 'Reason' }); reason.addEventListener('input', () => { draft.reason = reason.value; });
  const problems = h('div'), preview = h('pre', { class: 'json' }), matches = h('div'), msg = h('div');
  const confirm = h('button', { class: 'btn primary', type: 'button', id: 'confirm', disabled: true }, 'Confirm payload');
  const reject = h('button', { class: 'btn', type: 'button', id: 'reject' }, 'Reject');
  verify.append(h('div', { class: 'fields three' }, mk('scheme', 'Scheme'), mk('trustee', 'Trustee'), mk('movement_volume', 'Members moving')),
    h('div', { class: 'fields three' }, mk('notification_date', 'Notified (YYYY-MM-DD)'), mk('received_date', 'Received (YYYY-MM-DD)'), field('Reason (to reject)', reason)),
    problems, matches, h('details', { class: 'small' }, h('summary', {}, 'Payload that will be saved'), preview), msg, h('div', { class: 'actions' }, confirm, reject));
  let timer = null, seq = 0;
  async function check() {
    const mine = ++seq;
    const r = await api('/api/inbound/check', { payload: draft.fields }).catch((err) => ({ clean: {}, problems: [err.message], matches: [] }));
    if (mine !== seq) return; // a newer keystroke is already being checked
    problems.replaceChildren(...r.problems.map((p) => alertBox('warning', p)));
    preview.textContent = JSON.stringify({ ...r.clean, source: 'email', message_id: e.message_id }, null, 2);
    confirm.disabled = r.problems.length > 0;
    matches.replaceChildren(...(r.matches.length
      ? [h('div', { class: 'label', style: 'margin-top:0.9rem' }, 'Excel log entries this email may belong to'),
         table(r.matches, [['log_id', 'Entry'], ['scheme', 'Scheme'], ['notification_date', 'Notified'], ['received_date', 'Received'], ['movement_volume', 'Volume'], ['status', 'Status']])]
      : r.clean.scheme && !r.problems.length ? [h('p', { class: 'muted' }, 'No matching Excel entry found for this scheme.')] : []));
  }
  function schedule() { clearTimeout(timer); timer = setTimeout(check, 350); }
  const submit = (btn, status, done) => btn.addEventListener('click', busy(btn, 'Saving', async () => {
    msg.replaceChildren();
    try { await api('/api/inbound/review', { message_id: e.message_id, status, payload: draft.fields, original: draft.payload, reason: draft.reason }); }
    catch (err) { msg.append(alertBox('error', `Could not save: ${err.message}`)); return; }
    delete st.drafts[e.message_id]; setFlash(done); await render();
  }));
  submit(confirm, 'confirmed', `Confirmed the payload for ${e.subject}.`);
  submit(reject, 'rejected', `Rejected ${e.subject}.`);
  await check();
}


// ---- Page 5: what each email says, checked against the Excel log -------------------------------------------------
const VERDICT = { match: ['v-ok', 'check', 'Correct'], differs: ['v-bad', 'warn', 'Different'], missing_in_log: ['v-miss', 'minus', 'Missing in Excel'],
                  missing_in_email: ['v-miss', 'minus', 'Missing in email'], both_missing: ['v-miss', 'minus', 'Missing in both'] };
const chip = (v) => { const [cls, ic, label] = VERDICT[v]; return h('span', { class: `chip ${cls}` }, icon(ic), label); };
const COLS = [['volume', 'Members'], ['notified', 'Notified'], ['received', 'Received'], ['trustee', 'Trustee'], ['attachment', 'Attached Excel']];
async function pageCompare(view) {
  const d = await api('/api/compare'), t = d.totals;
  setHead(TITLES.compare, `${d.counts.read} emails read, ${d.counts.compared} compared with an Excel entry`, null);
  view.append(h('p', { class: 'lede' }, 'The model reads each trustee email, finds the matching entry in the Excel buy-in log, and checks every field. A field is correct when the email and the log agree, different when they disagree, and missing when one side has no usable value.'));
  const tile = (n, label, sub) => h('div', { class: 'tile' }, h('div', { class: 'num' }, n), h('div', { class: 'tl' }, label), h('div', { class: 'muted' }, sub));
  view.append(h('div', { class: 'tiles four' },
    tile(t.match, 'fields correct', 'Email and Excel agree'), tile(t.differs, 'fields different', 'Email and Excel disagree'),
    tile(t.missing_in_log, 'missing in Excel', 'The email has it, the Excel cell is blank or invalid'), tile(t.missing_in_email, 'missing in the email', 'The Excel log has it, the email does not say')));
  const head = h('tr', {}, [h('th', {}, 'Email'), h('th', {}, 'Excel entry'), ...COLS.map(([, l]) => h('th', {}, l))]);
  const rows = d.emails.map((r) => {
    const byKey = Object.fromEntries(r.fields.map((f) => [f.key, f]));
    const entry = r.status === 'compared' ? h('strong', {}, r.entry.log_id) : h('span', { class: 'muted' }, r.status === 'no_entry' ? 'No entry in the log' : r.status === 'unreadable' ? 'Could not be read' : 'Names no scheme');
    return h('tr', {}, [h('td', {}, r.subject.replace(/^BPA (demo|Convo) - /, '')), h('td', {}, entry),
      ...COLS.map(([k]) => h('td', {}, byKey[k] ? chip(byKey[k].verdict) : h('span', { class: 'muted' }, '-')))]);
  });
  view.append(h('h2', {}, 'All emails at a glance'), h('div', { class: 'table-wrap' }, h('table', { class: 'matrix' }, h('thead', {}, head), h('tbody', {}, rows))));
  view.append(h('h2', {}, 'Field by field'));
  for (const r of d.emails) {
    const body = h('div', { class: 'body-pad' });
    if (r.status === 'compared') {
      body.append(h('p', { class: 'muted' }, `Matched to ${r.entry.log_id}: ${r.how}. Model confidence: ${r.confidence}. ${r.note || ''}`),
        h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['Field', 'Email says', 'Compared with', 'Verdict', 'Note'].map((x) => h('th', {}, x)))),
          h('tbody', {}, r.fields.map((f) => h('tr', {}, [h('td', {}, f.label), h('td', {}, f.email == null ? '(nothing)' : String(f.email)),
            h('td', {}, `${f.otherLabel}: ${f.other == null ? '(blank)' : f.other}`), h('td', {}, chip(f.verdict)), h('td', { class: 'muted' }, f.note || '')]))))));
    } else body.append(h('p', {}, r.status === 'no_entry' ? `${r.scheme}: ${r.how}. This email is missing from the Excel log.` : r.summary));
    view.append(h('details', { class: 'cmp' }, h('summary', {}, `${r.subject}${r.status === 'compared' ? ` (${r.entry.log_id})` : ''}`), body));
  }
  const gap = d.cells.total - d.cells.covered;
  const openFix = h('button', { class: 'btn', type: 'button' }, 'Open Fix invalid cells'); openFix.addEventListener('click', () => go('fix'));
  view.append(h('h2', {}, 'Excel cells with no email behind them'),
    h('p', {}, `${d.cells.covered} of the ${d.cells.total} invalid Excel cells have an email that answers them. ${gap} have no email yet, so they stay missing until a trustee writes in.`), h('div', { class: 'actions' }, openFix),
    h('p', { class: 'muted' }, 'The model can word things differently between runs, so a borderline field (for example a hedged number) may flip between Missing and Different. Emails are read once per app start.'));
}

// ---- Shell ----------------------------------------------------------------------------------------------------------
let renderToken = 0;
async function render() {
  const token = ++renderToken;
  document.getElementById('nav').replaceChildren(...PAGES.map(([id, label]) => {
    const b = h('button', { role: 'tab', type: 'button', 'aria-selected': String(id === state.page) }, label);
    b.addEventListener('click', () => { state.page = id; if (id !== 'fix') state.workbook = null; render(); });
    return b;
  }));
  if (typeof history !== 'undefined') history.replaceState(null, '', `#${state.page}`);
  const view = document.getElementById('view');
  const next = h('div');
  view.replaceChildren(h('p', { class: 'muted' }, h('span', { class: 'spinner' }), 'Loading'));
  try { await ({ home: pageHome, fix: pageFix, emails: pageEmails, inbound: pageInbound, compare: pageCompare })[state.page](next); }
  catch (err) { setHead(TITLES[state.page], null, null); next.replaceChildren(alertBox('error', `Could not load this page: ${err.message}`)); }
  if (token !== renderToken) return; // user moved on while this page was loading
  view.replaceChildren(next); renderFlash();
}

(async () => {
  const logo = document.getElementById('logo');
  const ok = await fetch('/logo.png').then((r) => r.ok && (r.headers.get('content-type') || '').includes('image')).catch(() => false);
  logo.replaceChildren(ok ? h('img', { src: '/logo.png', alt: 'Buy-in operations' }) : h('span', { class: 'wordmark' }, 'Buy-in operations'));
  logo.addEventListener('click', (e) => { e.preventDefault(); state.page = 'home'; state.workbook = null; render(); });
})();

api('/api/me').then(({ user }) => { document.getElementById('who').textContent = `Signed in as ${user}. Synthetic data. Corrections are saved in Databricks only and appear in the dashboards immediately.`; }).catch(() => {});
render();
