'use strict';
// MutMech Bench: talks to the local JSON API of `python -m mutmech serve`. No external resources.

const THREE = {A: 'Ala', R: 'Arg', N: 'Asn', D: 'Asp', C: 'Cys', Q: 'Gln', E: 'Glu', G: 'Gly', H: 'His', I: 'Ile', L: 'Leu',
  K: 'Lys', M: 'Met', F: 'Phe', P: 'Pro', S: 'Ser', T: 'Thr', W: 'Trp', Y: 'Tyr', V: 'Val'};
const ROUTES = {A: 'one mechanism keyword in the quote', B: 'several mechanism keywords', C: 'no keyword, a cue word such as contact or charge', D: 'no keyword and no cue word'};
const $ = (s) => document.querySelector(s);
let rules = [];

function el(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') n.className = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined && k !== false) n.append(k instanceof Node ? k : String(k));
  return n;
}

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const data = await res.json().catch(() => ({error: `HTTP ${res.status}`}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function when(stamp) {
  const m = /^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/.exec(stamp || '');
  if (!m) return stamp || '';
  const d = new Date(Date.UTC(+m[1], m[2] - 1, +m[3], +m[4], +m[5], +m[6]));
  return d.toLocaleString(undefined, {year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'});
}

function chip(label, first) { return el('span', {class: `chip m-${label}${first ? ' first' : ''}`}, label.replace(/_/g, ' ')); }
function chips(labels) { return el('span', {class: 'chips'}, (labels || []).map((l, i) => chip(l, i === 0))); }
function stateBadge(s) {
  const k = s.startsWith('dry run') ? 'queued' : s === 'ok' ? 'done' : s.startsWith('usage limit') ? 'paused' : s.startsWith('error') || s.startsWith('failed') ? 'error' : s;
  return el('span', {class: `state ${k}`}, s.startsWith('usage limit: ') ? s.slice(13) : s);
}

function residueRegex(mutation, numbers) {
  const m = /\b([A-Z])(\d+)([A-Z])\b/.exec(mutation || '');
  if (!m) return null;
  const three = THREE[m[1]] || m[1];
  const nums = [...new Set([m[2], ...(numbers || []).map(String)])].join('|');
  return new RegExp(`(?<![A-Za-z0-9])(?:${three}|${three.toUpperCase()}|${m[1]})[\\s-]?(?:${nums})(?![0-9])`, 'g');
}

function highlight(text, rx) {
  const frag = document.createDocumentFragment();
  if (!rx) { frag.append(text); return frag; }
  let last = 0;
  for (const m of text.matchAll(rx)) {
    frag.append(text.slice(last, m.index), el('mark', {}, m[0]));
    last = m.index + m[0].length;
  }
  frag.append(text.slice(last));
  return frag;
}

// ---------------------------------------------------------------- views

function show(view) {
  const v = ['analyze', 'paper', 'result', 'batch', 'history'].includes(view) ? view : 'analyze';
  for (const s of document.querySelectorAll('.view')) s.hidden = s.id !== `view-${v}`;
  for (const a of document.querySelectorAll('.tabs a')) {
    if (a.dataset.view === v) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  }
  if (v === 'history') loadHistory();
}
window.addEventListener('hashchange', () => show(location.hash.slice(1)));

async function loadRules() {
  rules = await api('/api/rules');
  $('#rule-list').replaceChildren(...rules.map((r, i) => el('label', {class: 'rule'},
    el('input', {type: 'radio', name: 'rule', value: r.id, id: `rule-${r.id}`, checked: i === 0}), el('b', {}, r.id), el('small', {}, r.help))));
  for (const id of ['#b-rule', '#p-rule']) $(id).replaceChildren(...rules.map((r) => el('option', {value: r.id}, `${r.id}: ${r.name}`)));
}

// ---------------------------------------------------------------- jobs

async function poll(id, render) {
  for (;;) {
    let job;
    try { job = await api(`/api/jobs/${id}`); } catch (e) { render({status: 'error', error: e.message, elapsed: 0}); return null; }
    render(job);
    if (job.status === 'done' || job.status === 'error') return job;
    await new Promise((r) => setTimeout(r, 1000));
  }
}

function renderJob(job) {
  const s = job.summary || {};
  const box = $('#job-box');
  box.className = '';
  box.replaceChildren(
    el('div', {class: 'job-line'}, el('span', {class: `state ${job.status}`}, job.status), el('span', {class: 'elapsed'}, `${(job.elapsed || 0).toFixed(1)} s`),
      job.status === 'queued' && job.queue_position ? el('span', {class: 'muted'}, `${job.queue_position} ahead`) : null,
      job.paused_until ? el('span', {class: 'mol-problem'}, `Codex usage limit reached, queue paused until ${job.paused_until}`) : null),
    el('p', {class: 'job-detail'}, [s.mutation, s.pdb, s.rule, s.source, s.dry_run ? 'dry run' : null].filter(Boolean).join(' · ')),
    job.error ? el('p', {class: 'job-detail err'}, job.error) : null,
    job.result_id ? el('p', {class: 'job-detail'}, el('a', {href: '#result', onclick: (e) => { e.preventDefault(); openResult(job.result_id); }}, 'Open result')) : null);
}

function readFile(file, asText) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(asText ? r.result : String(r.result).split(',')[1] || '');
    r.onerror = () => reject(new Error(`could not read ${file.name}`));
    asText ? r.readAsText(file) : r.readAsDataURL(file);
  });
}

function sourceChanged() {
  const pdf = $('#f-src-pdf').checked;
  $('#f-quote').hidden = pdf; $('#f-pdf').hidden = !pdf; $('#pdf-hint').hidden = !pdf;
}

async function submitAnalyze(e) {
  e.preventDefault();
  const err = $('#form-error'); err.textContent = '';
  const body = {mutation: $('#f-mutation').value.trim(), pdb: $('#f-pdb').value.trim(), citation: $('#f-citation').value.trim(),
    paper_number: $('#f-paper').value.trim(), rule: (document.querySelector('input[name="rule"]:checked') || {}).value || 'routing',
    dry_run: $('#f-dry').checked};
  if (!body.mutation) { err.textContent = 'Give the mutation, for example D364A (chain B).'; $('#f-mutation').focus(); return; }
  try {
    if ($('#f-src-pdf').checked) {
      const f = $('#f-pdf').files[0];
      if (!f) { err.textContent = 'Choose a PDF to upload.'; return; }
      body.pdf_name = f.name; body.pdf_b64 = await readFile(f, false);
    } else {
      body.quote = $('#f-quote').value.trim();
      if (!body.quote) { err.textContent = 'Paste a quote, or switch to PDF upload.'; $('#f-quote').focus(); return; }
    }
    $('#f-submit').disabled = true;
    const {id} = await api('/api/analyze', body);
    const job = await poll(id, renderJob);
    if (job && job.status === 'done' && job.result_id) openResult(job.result_id);
  } catch (ex) {
    err.textContent = ex.message;
  } finally {
    $('#f-submit').disabled = false;
  }
}

// ---------------------------------------------------------------- result

function kv(pairs) {
  return el('dl', {class: 'kv'}, pairs.filter(([, v]) => v !== undefined && v !== null && v !== '').flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, v)]));
}

function rulePanel(r) {
  if (r.route) {
    const llm = !r.llm_needed ? 'not needed' : r.engine ? 'called' : 'needed, not called (dry run)';
    return el('section', {class: 'panel block'}, el('h3', {}, 'Routing'),
      el('p', {}, el('span', {class: 'route-badge'}, r.route), ROUTES[r.route] || ''),
      kv([['Keyword classes', r.keyword_classes && r.keyword_classes.length ? chips(r.keyword_classes) : 'none'],
        ['Structure contacts', r.structure_contacts ? (r.structure_contacts.length ? chips(r.structure_contacts) : 'none at the interface') : 'not verified'],
        ['LLM', llm], ['Evidence', r.evidence], ['Flags', r.flags && r.flags.length ? r.flags.join(', ') : null]]));
  }
  if (r.statements) {
    const rx = residueRegex(r.input.mutation, r.input.paper_numbers_searched);
    return el('section', {class: 'panel block'}, el('h3', {}, 'Statements'),
      kv([['Record class', el('span', {class: 'rc'}, (r.record_class || '').replace(/_/g, ' '))], ['Labels from', r.label_source]]),
      el('div', {class: 'table-wrap'}, el('table', {class: 'data'},
        el('thead', {}, el('tr', {}, ['', 'Span', 'Kind', 'Interactions', 'Relation', 'After substitution', 'Applies', 'Class'].map((h) => el('th', {}, h)))),
        el('tbody', {}, r.statements.map((s) => el('tr', {},
          el('td', {class: 'mono'}, s.sid), el('td', {class: 'span-cell'}, highlight(s.span || '', rx)), el('td', {}, s.kind),
          el('td', {}, (s.interactions || []).length ? chips(s.interactions) : el('span', {class: 'muted'}, 'none')),
          el('td', {}, s.relation), el('td', {}, s.after_substitution), el('td', {}, s.applies),
          el('td', {}, el('span', {class: `cls ${s.class}`}, (s.class || '').replace(/_/g, ' ')))))))));
  }
  if (r.evidence_basis !== undefined) {
    return el('section', {class: 'panel block'}, el('h3', {}, 'Rules v4'),
      kv([['Evidence basis', r.evidence_basis], ['Uncertainty', r.uncertainty], ['Functional effect', r.functional_effect],
        ['Input flags', (r.input_flags || []).join(', ')]]));
  }
  return null;
}

function provenance(r) {
  const e = r.engine || {}, t = r.tokens || {}, v = r.versions || {};
  return el('aside', {class: 'panel prov'}, el('h3', {}, 'Provenance'),
    kv([['Rule', r.rule], ['Model', e.model || (r.engine ? 'not recorded' : r.status.startsWith('dry run') ? 'no call (dry run)' : 'no LLM call')],
      ['Setting', e.model_setting], ['Effort', e.reasoning_effort], ['Sandbox', e.sandbox],
      ['Network', e.network_access === undefined || e.network_access === null ? null : e.network_access ? 'on' : 'off'],
      ['Approval', e.approval_policy], ['Exit code', e.exit_code],
      ['Input tokens', t.input_tokens !== undefined ? `${t.input_tokens.toLocaleString()} (${(t.cached_input_tokens || 0).toLocaleString()} cached)` : null],
      ['Output tokens', t.output_tokens !== undefined ? t.output_tokens.toLocaleString() : null],
      ...Object.entries(v).map(([k, h]) => [k.replace(/_sha256$/, ''), el('span', {class: 'hash', title: h}, `${h.slice(0, 16)}…`)]),
      ['Thread', e.thread_id ? el('span', {class: 'hash'}, e.thread_id) : null],
      ['Run folder', el('span', {class: 'hash'}, r.run_dir)], ['Created', when(r.created)]]));
}

function renderResult(r) {
  const labels = r.mechanism_labels || [];
  const rx = residueRegex(r.input.mutation, r.input.paper_numbers_searched);
  const primary = r.primary || labels[0];
  const evidence = r.passages && r.passages.length
    ? el('section', {class: 'panel block'}, el('h3', {}, `PDF passages · residue numbers searched ${(r.input.paper_numbers_searched || []).join(', ')}`),
      r.passages.map((p) => el('blockquote', {class: 'passage'}, el('span', {class: 'pg'}, `page ${p.page} · score ${p.score}`), highlight(p.text, rx))))
    : el('section', {class: 'panel block'}, el('h3', {}, 'Quote'), el('p', {class: 'quote-text'}, highlight(r.quote_used || '', rx)));
  const problems = r.validator_problems && r.validator_problems.length
    ? el('section', {class: 'panel block warnings'}, el('h3', {}, `Validator problems: ${r.validator_problems.length}`), el('pre', {class: 'prompt'}, r.validator_problems.join('\n'))) : null;
  const structSlot = el('div', {class: 'struct-slot'});
  if (r.input.pdb && r.input.mutation) structurePanel({pdb: r.input.pdb, mutation: r.input.mutation, paper_number: (r.input.paper_numbers_searched || []).find((n) => String(n) !== ((/\b[A-Z](\d+)[A-Z]\b/.exec(r.input.mutation) || [])[1])), result: r.id}).then((p) => structSlot.replaceChildren(p));
  $('#result').replaceChildren(
    el('header', {class: 'res-head'},
      el('div', {}, el('div', {class: 'res-id'}, el('b', {}, r.input.mutation), r.input.pdb ? el('span', {}, `PDB ${r.input.pdb}`) : null,
        el('span', {}, r.rule), r.input.citation ? el('span', {}, r.input.citation) : null),
        el('div', {class: `primary-label${primary ? ` m-${primary}` : ' none'}`}, primary ? primary.replace(/_/g, ' ') : (r.status.startsWith('dry run') ? 'Dry run: no label' : 'No label')),
        labels.length ? chips(labels) : null),
      el('div', {}, stateBadge(r.status))),
    el('div', {class: 'res-grid'},
      el('div', {class: 'res-main'},
        r.mechanism || r.functional_effect ? el('section', {class: 'panel block'}, el('h3', {}, r.mechanism ? 'Mechanism' : 'Functional effect'), el('p', {}, r.mechanism || r.functional_effect)) : null,
        r.explanation ? el('section', {class: 'panel block'}, el('h3', {}, 'Explanation'), el('p', {}, r.explanation)) : null,
        rulePanel(r), problems, evidence, structSlot,
        r.prompt && r.status.startsWith('dry run') ? el('section', {class: 'panel block'}, el('details', {open: true}, el('summary', {}, 'Prompt that would be sent'), el('pre', {class: 'prompt'}, r.prompt))) : null),
      provenance(r)));
  $('#result').hidden = false; $('#result-empty').hidden = true;
}

async function openResult(id) {
  try {
    renderResult(await api(`/api/result?id=${encodeURIComponent(id)}`));
  } catch (e) {
    $('#result').hidden = true; $('#result-empty').hidden = false;
    $('#result-empty').querySelector('p').textContent = `Could not open the result: ${e.message}`;
  }
  if (location.hash !== '#result') location.hash = '#result'; else show('result');
  window.scrollTo(0, 0);
}


// ---------------------------------------------------------------- structure view (3Dmol.js 2.5.3, vendored)

const CHAIN_COLORS = ['#5b8def', '#e0a33a', '#3fb6a8', '#b07ad8', '#d9695f', '#8fae4a', '#7a8794', '#c9839b'];
const SITE_COLOR = '#f59e0b', SITE_BAD = '#d33a2c', NAMED_COLOR = '#14b8a6';
let molLoading = null;

function webglOK() {
  try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch (e) { return false; }
}

function load3Dmol() {
  if (window.$3Dmol) return Promise.resolve();
  molLoading = molLoading || new Promise((resolve, reject) => {
    const s = el('script', {src: '/static/vendor/3Dmol-min.js'});
    s.onload = () => (window.$3Dmol ? resolve() : reject(new Error('3Dmol.js did not load')));
    s.onerror = () => reject(new Error('3Dmol.js could not be loaded from /static/vendor'));
    document.head.append(s);
  });
  return molLoading;
}

function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || '#ffffff'; }

async function structurePanel({pdb, mutation, paper_number, result}) {
  const box = el('section', {class: 'panel block struct'}, el('h3', {}, `Structure · ${pdb || 'no PDB entry'}`));
  const q = new URLSearchParams({pdb: pdb || '', mutation: mutation || ''});
  if (paper_number !== undefined && paper_number !== null && paper_number !== '') q.set('paper_number', paper_number);
  if (result) q.set('result', result);
  let site;
  try { site = await api(`/api/site?${q}`); } catch (e) { box.append(el('p', {class: 'muted'}, e.message)); return box; }
  const color = {};
  site.chains.forEach((c, i) => { color[c.chain] = CHAIN_COLORS[i % CHAIN_COLORS.length]; });
  const view = el('div', {class: 'mol', role: 'img', 'aria-label': `3D structure of ${site.pdb} with the mutation site highlighted`});
  const side = el('div', {class: 'mol-side'},
    el('p', {class: 'mol-note'}, site.note),
    site.problem ? el('p', {class: 'mol-problem', role: 'alert'}, site.problem) : null,
    site.site ? el('p', {class: 'mol-site'}, el('span', {class: 'sw', style: `background:${site.site.matches ? SITE_COLOR : SITE_BAD}`}), site.site.label,
      site.site.observed ? el('span', {class: 'muted'}, ` · deposited ${site.site.observed}`) : null) : null,
    el('h4', {}, 'Chains'),
    el('ul', {class: 'legend'}, site.chains.map((c) => el('li', {}, el('span', {class: 'sw', style: `background:${color[c.chain]}`}),
      el('b', {}, c.chain), ' ', c.protein || el('span', {class: 'muted'}, 'protein not in the numbering map'),
      c.pdb_minus_paper ? el('span', {class: 'muted'}, ` · PDB = paper + ${c.pdb_minus_paper}`) : null))),
    site.neighbours.length ? [el('h4', {}, `Partner residues within 4.5 Å`),
      el('ul', {class: 'nb'}, site.neighbours.filter((n) => n.partner).map((n) => el('li', {},
        el('span', {class: 'sw', style: `background:${color[n.chain]}`}), el('span', {class: 'mono'}, `${n.chain}:${n.resn}${n.resi}`),
        el('span', {class: 'muted'}, ` ${n.distance} Å `), n.contacts.length ? chips(n.contacts) : el('span', {class: 'muted'}, 'no typed contact')))),
      el('p', {class: 'muted small'}, `${site.neighbours.filter((n) => !n.partner).length} residues of the same chain within 4.5 Å are drawn as thin sticks.`)] : null,
    site.named.length ? [el('h4', {}, 'Named in the analysis'), el('ul', {class: 'nb'}, site.named.map((n) => el('li', {},
      el('span', {class: 'sw', style: `background:${NAMED_COLOR}`}), el('span', {class: 'mono'}, `${n.text} → ${n.chain}:${n.resi}`),
      el('span', {class: n.matches ? 'muted' : 'mol-problem'}, n.matches ? ` ${n.resn}` : ` not ${n.text.slice(0, 3)} in the structure (${n.resn || 'missing'})`))))] : null);
  const controls = el('div', {class: 'mol-controls'});
  box.append(el('div', {class: 'mol-grid'}, el('div', {class: 'mol-wrap'}, view, controls), side));
  if (!webglOK()) { view.replaceChildren(el('p', {class: 'mol-msg'}, 'This browser has no WebGL, so the 3D view cannot be drawn. The lists beside it still apply.')); return box; }
  try { await load3Dmol(); } catch (e) { view.replaceChildren(el('p', {class: 'mol-msg'}, e.message)); return box; }
  let text;
  try {
    const res = await fetch(`/api/structure?pdb=${encodeURIComponent(site.pdb)}&format=pdb`);
    if (!res.ok) throw new Error((await res.json()).error);
    text = await res.text();
  } catch (e) { view.replaceChildren(el('p', {class: 'mol-msg'}, e.message)); return box; }
  requestAnimationFrame(() => draw(view, controls, site, text, color));
  return box;
}

function draw(view, controls, site, text, color) {
  const v = $3Dmol.createViewer(view, {backgroundColor: cssVar('--panel')});
  v.addModel(text, 'pdb');
  for (const c of site.chains) v.setStyle({chain: c.chain}, {cartoon: {color: color[c.chain], opacity: 0.9}});
  const s = site.site;
  const at = s ? {chain: s.chain, resi: s.resi} : null;
  for (const n of site.neighbours) v.addStyle({chain: n.chain, resi: n.resi}, {stick: {color: color[n.chain], radius: n.partner ? 0.2 : 0.1}});
  for (const n of site.named) v.addStyle({chain: n.chain, resi: n.resi}, {stick: {color: NAMED_COLOR, radius: 0.24}});
  if (s && s.present) v.addStyle(at, {stick: {color: s.matches ? SITE_COLOR : SITE_BAD, radius: 0.32}});
  let labels = true, surface = false;
  const drawLabels = () => {
    v.removeAllLabels();
    if (labels && s && s.present) v.addLabel(s.label, {fontSize: 13, fontColor: '#ffffff', backgroundColor: s.matches ? '#7a4a00' : '#7a1a12', backgroundOpacity: 0.9}, at);
    if (labels) for (const n of site.neighbours.filter((x) => x.partner)) v.addLabel(`${n.chain}:${n.resn}${n.resi}`, {fontSize: 11, fontColor: '#ffffff', backgroundColor: '#24323a', backgroundOpacity: 0.75}, {chain: n.chain, resi: n.resi, atom: 'CA'});
    v.render();
  };
  const focus = () => { v.zoomTo(at && s.present ? {chain: s.chain, resi: s.resi, byres: true, expand: 6} : {}); v.render(); };
  const mk = (t, f, pressed) => el('button', {type: 'button', 'aria-pressed': pressed === undefined ? null : String(pressed), onclick: f}, t);
  const bLabels = mk('Labels', () => { labels = !labels; bLabels.setAttribute('aria-pressed', String(labels)); drawLabels(); }, true);
  const bSurf = mk('Surface', () => {
    surface = !surface; bSurf.setAttribute('aria-pressed', String(surface));
    if (surface) v.addSurface($3Dmol.SurfaceType.VDW, {opacity: 0.55, colorscheme: {prop: 'chain', map: color}}); else v.removeAllSurfaces();
    v.render();
  }, false);
  controls.replaceChildren(mk('Focus on site', focus), mk('Whole structure', () => { v.zoomTo(); v.render(); }), bLabels, bSurf,
    mk('Save PNG', () => { v.render(); const a = el('a', {href: v.pngURI(), download: `${site.pdb}-${s ? `${s.chain}${s.resi}` : 'structure'}.png`}); document.body.append(a); a.click(); a.remove(); }));
  drawLabels();
  focus();
}

// ---------------------------------------------------------------- batch and history

function renderBatch(job) {
  const s = job.summary || {};
  $('#batch-status').replaceChildren(el('div', {class: 'job-line'}, el('span', {class: `state ${job.status}`}, job.status),
    el('span', {class: 'elapsed'}, `${(job.elapsed || 0).toFixed(1)} s`), el('span', {class: 'muted'}, `${(job.rows || []).length} of ${s.rows_total ?? '?'} rows · ${s.rule}${s.dry_run ? ' · dry run' : ''}`)),
  job.error ? el('p', {class: 'job-detail err'}, job.error) : null);
  const t = $('#batch-table'); t.hidden = false;
  t.tBodies[0].replaceChildren(...(job.rows || []).map((r) => el('tr', {},
    el('td', {}, r.row), el('td', {}, r.mutation || ''), el('td', {}, r.pdb || ''), el('td', {}, r.source), el('td', {}, stateBadge(r.status)),
    el('td', {}, r.route || ''), el('td', {}, (r.record_class || '').replace(/_/g, ' ')), el('td', {}, r.labels ? chips(r.labels.split(', ')) : ''),
    el('td', {}, r.result_id ? el('a', {href: '#result', onclick: (e) => { e.preventDefault(); openResult(r.result_id); }}, 'Open') : ''))));
}

async function submitBatch(e) {
  e.preventDefault();
  const err = $('#batch-error'); err.textContent = '';
  const f = $('#b-file').files[0];
  if (!f) { err.textContent = 'Choose a CSV file.'; return; }
  const btn = e.target.querySelector('button'); btn.disabled = true;
  try {
    const {id} = await api('/api/batch', {csv: await readFile(f, true), csv_name: f.name, rule: $('#b-rule').value, dry_run: $('#b-dry').checked});
    await poll(id, renderBatch);
  } catch (ex) { err.textContent = ex.message; } finally { btn.disabled = false; }
}

async function loadHistory() {
  const body = $('#history-table').tBodies[0];
  try {
    const rows = await api('/api/history');
    body.replaceChildren(...(rows.length ? rows.map((r) => {
      const open = () => openResult(r.id);
      return el('tr', {tabindex: '0', onclick: open, onkeydown: (e) => { if (e.key === 'Enter') open(); }},
        el('td', {}, when(r.created)), el('td', {}, r.pdb), el('td', {}, r.mutation), el('td', {}, r.rule),
        el('td', {}, r.primary ? chip(r.primary, false) : el('span', {class: 'muted'}, 'none')), el('td', {}, stateBadge(r.status)));
    }) : [el('tr', {}, el('td', {colspan: '6', class: 'muted'}, 'No results yet.'))]));
  } catch (e) {
    body.replaceChildren(el('tr', {}, el('td', {colspan: '6', class: 'muted'}, `Could not load history: ${e.message}`)));
  }
}

// ---------------------------------------------------------------- paper: find mutations, pick, analyze

let paper = {pdf_id: null, pdb: '', cands: [], picked: []};

function scClass(s) { return s === 'wild type matches structure' ? 'match' : s === 'mismatch' ? 'mismatch' : 'unchecked'; }

function updateCount() {
  const n = document.querySelectorAll('#paper-table tbody input.pick:checked').length;
  $('#p-count').textContent = `${n} selected`;
  for (const tr of $('#paper-table').tBodies[0].querySelectorAll('tr[data-i]')) tr.classList.toggle('picked', tr.querySelector('input.pick').checked);
}

function renderCandidates() {
  const rx = (c) => residueRegex(`${c.wild_type}${c.paper_number}${c.mutant}`, [c.paper_number]);
  $('#paper-table').tBodies[0].replaceChildren(...paper.cands.map((c, i) => el('tr', {'data-i': i},
    el('td', {}, el('input', {type: 'checkbox', class: 'pick', 'aria-label': `Select ${c.written}`, onchange: updateCount})),
    el('td', {class: 'mono', title: c.forms.map((f) => `${f[0]} ×${f[1]}`).join(', ')}, c.written),
    el('td', {}, el('input', {class: 'cell mut', value: c.pdb_mutation, 'aria-label': `PDB mutation for ${c.written}`})),
    el('td', {}, el('input', {class: 'cell chain', value: c.chain || '', 'aria-label': `Chain for ${c.written}`})),
    el('td', {}, el('span', {class: `sc ${scClass(c.structure)}`}, c.structure), c.ambiguous_chain ? el('div', {class: 'muted'}, 'several chains match') : null),
    el('td', {}, c.count), el('td', {}, c.pages.join(', ')),
    el('td', {}, el('details', {class: 'ctx'}, el('summary', {}, `${c.contexts.length} sentence${c.contexts.length === 1 ? '' : 's'}`),
      c.contexts.map((x) => el('p', {}, el('span', {class: 'pg'}, `p${x.page}`), highlight(x.text, rx(c)))))),
    el('td', {class: 'res-cell'}, ''),
    el('td', {}, el('button', {type: 'button', class: 'small', 'aria-expanded': 'false', onclick: (e) => toggleStructure(e.currentTarget, i)}, 'Structure')))));
  $('#paper-picks').hidden = !paper.cands.length;
  updateCount();
}

async function toggleStructure(btn, i) {
  const tr = btn.closest('tr');
  const next = tr.nextElementSibling;
  if (next && next.classList.contains('struct-row')) { next.remove(); btn.setAttribute('aria-expanded', 'false'); return; }
  const c = paper.cands[i], mut = tr.querySelector('input.mut').value.trim(), ch = tr.querySelector('input.chain').value.trim();
  const td = el('td', {colspan: '10'}, el('p', {class: 'muted'}, 'Loading the structure…'));
  tr.after(el('tr', {class: 'struct-row'}, td));
  btn.setAttribute('aria-expanded', 'true');
  td.replaceChildren(await structurePanel({pdb: paper.pdb, mutation: ch ? `${mut} (chain ${ch})` : mut, paper_number: c.paper_number, result: tr.dataset.result || null}));
}

function renderPdbBox() {
  const box = $('#paper-pdb');
  const cands = paper.pdbCands || [];
  if (!paper.pdb) {
    box.replaceChildren(el('p', {class: 'mol-problem'}, 'No PDB entry was found in the paper text, its file name or the local structure cache. Type the entry below and find again.'),
      pdbTyper());
    box.hidden = false;
    return;
  }
  const chosen = cands.find((c) => c.pdb === paper.pdb);
  const sel = el('select', {id: 'p-pdb-pick', 'aria-label': 'PDB entry used'}, cands.map((c) => el('option', {value: c.pdb, selected: c.pdb === paper.pdb},
    `${c.pdb} · ${c.evidence} · ${c.sources.join(', ')}`)));
  if (!chosen) sel.prepend(el('option', {value: paper.pdb, selected: true}, `${paper.pdb} · typed`));
  sel.addEventListener('change', () => refind(sel.value));
  box.replaceChildren(
    el('div', {class: 'pdb-line'}, el('label', {class: 'field'}, el('span', {}, `PDB entry ${paper.chosenBy === 'best candidate' ? '(best candidate, chosen automatically)' : `(${paper.chosenBy})`}`), sel), pdbTyper()),
    chosen ? el('ul', {class: 'legend pdb-chains'}, chosen.chains.map((c) => el('li', {}, el('b', {}, c.chain), ' ', c.protein || el('span', {class: 'muted'}, 'protein not in the numbering map'),
      c.offset ? el('span', {class: 'muted'}, ` · PDB = paper + ${c.offset} (${c.offset_source})`) : null))) : null,
    chosen && chosen.note ? el('p', {class: 'hint'}, `Structure cache title ${chosen.note}.`) : null);
  box.hidden = false;
}

function pdbTyper() {
  const inp = el('input', {id: 'p-pdb-type', placeholder: 'e.g. 1A22', 'aria-label': 'Type a PDB entry', autocomplete: 'off', class: 'pdb-type'});
  return el('div', {class: 'pdb-typer'}, inp, el('button', {type: 'button', onclick: () => inp.value.trim() && refind(inp.value.trim())}, 'Use this entry'));
}

async function runFind(body, label) {
  const r = await api('/api/paper/find', body);
  const job = await poll(r.id, (j) => $('#paper-status').replaceChildren(el('div', {class: 'job-line'},
    el('span', {class: `state ${j.status}`}, j.status), el('span', {class: 'elapsed'}, `${(j.elapsed || 0).toFixed(1)} s`),
    j.candidates ? el('span', {class: 'muted'}, `${j.candidates.length} mutations found in ${label}${j.pdb ? `, placed on ${j.pdb}` : ''}`) : null),
    j.error ? el('p', {class: 'job-detail err'}, j.error) : null));
  if (job && job.status === 'done') {
    paper = {pdf_id: r.pdf_id || paper.pdf_id, label, pdb: job.pdb, chosenBy: job.chosen_by, pdbCands: job.pdb_candidates, cands: job.candidates, picked: []};
    renderPdbBox();
    renderCandidates();
  }
}

async function submitFind(e) {
  e.preventDefault();
  const err = $('#paper-error'); err.textContent = '';
  const f = $('#p-file').files[0];
  if (!f) { err.textContent = 'Choose a paper PDF.'; return; }
  $('#p-find').disabled = true;
  try { await runFind({pdf_name: f.name, pdf_b64: await readFile(f, false), pdb: $('#p-pdb').value.trim()}, f.name); }
  catch (ex) { err.textContent = ex.message; } finally { $('#p-find').disabled = false; }
}

async function refind(pdb) {
  $('#paper-error').textContent = '';
  try { await runFind({pdf_id: paper.pdf_id, pdb}, paper.label); } catch (ex) { $('#paper-error').textContent = ex.message; }
}

function renderPicked(job) {
  const rows = {};
  for (const tr of $('#paper-table').tBodies[0].querySelectorAll('tr[data-i]')) rows[tr.dataset.i] = tr;
  paper.picked.forEach((i, n) => {
    const r = (job.rows || [])[n];
    const cell = rows[i].querySelector('.res-cell');
    if (!r) {
      const st = job.status === 'error' ? 'error' : n === (job.rows || []).length && job.status === 'running' ? 'running' : 'queued';
      cell.replaceChildren(el('span', {class: `state ${st}`}, st));
      return;
    }
    const labels = r.labels ? r.labels.split(', ') : [];
    if (r.result_id) rows[i].dataset.result = r.result_id;
    cell.replaceChildren(labels.length ? chip(labels[0], true) : stateBadge(r.status), ' ',
      r.result_id ? el('a', {href: '#result', onclick: (ev) => { ev.preventDefault(); openResult(r.result_id); }}, 'Open') : null);
  });
}

async function submitPicks(e) {
  e.preventDefault();
  const err = $('#paper-run-error'); err.textContent = '';
  const rows = [...$('#paper-table').tBodies[0].querySelectorAll('tr[data-i]')].filter((tr) => tr.querySelector('input.pick').checked);
  if (!rows.length) { err.textContent = 'Select at least one mutation.'; return; }
  paper.picked = rows.map((tr) => +tr.dataset.i);
  const picks = rows.map((tr) => {
    const c = paper.cands[+tr.dataset.i], mut = tr.querySelector('input.mut').value.trim(), ch = tr.querySelector('input.chain').value.trim();
    return {mutation: ch ? `${mut} (chain ${ch})` : mut, paper_number: c.paper_number};
  });
  for (const tr of $('#paper-table').tBodies[0].querySelectorAll('tr[data-i]')) tr.querySelector('.res-cell').replaceChildren();
  $('#p-analyze').disabled = true;
  try {
    const r = await api('/api/paper/analyze', {pdf_id: paper.pdf_id, pdb: paper.pdb, picks, rule: $('#p-rule').value, dry_run: $('#p-dry').checked});
    await poll(r.id, (j) => {
      renderPicked(j);
      $('#paper-status').replaceChildren(el('div', {class: 'job-line'}, el('span', {class: `state ${j.status}`}, j.status),
        el('span', {class: 'elapsed'}, `${(j.elapsed || 0).toFixed(1)} s`), el('span', {class: 'muted'}, `${(j.rows || []).length} of ${picks.length} analysed`),
        j.paused_until ? el('span', {class: 'mol-problem'}, `Codex usage limit reached, paused until ${j.paused_until}`) : null),
      j.error ? el('p', {class: 'job-detail err'}, j.error) : null);
    });
  } catch (ex) { err.textContent = ex.message; } finally { $('#p-analyze').disabled = false; }
}

$('#paper-form').addEventListener('submit', submitFind);
$('#paper-run').addEventListener('submit', submitPicks);
$('#p-all').addEventListener('change', (e) => { for (const b of document.querySelectorAll('#paper-table input.pick')) b.checked = e.target.checked; updateCount(); });
$('#analyze-form').addEventListener('submit', submitAnalyze);
$('#batch-form').addEventListener('submit', submitBatch);
$('#h-refresh').addEventListener('click', loadHistory);
for (const r of document.querySelectorAll('input[name="source"]')) r.addEventListener('change', sourceChanged);
loadRules().catch((e) => { $('#form-error').textContent = `Could not load the rules: ${e.message}`; });
const deep = new URLSearchParams(location.search).get('result');
if (deep) openResult(deep); else show(location.hash.slice(1));
