"""Local web GUI for `mutmech analyze`: one mutation, a batch CSV, and the history of results.

  python -m mutmech serve [--port 8765]

Listens on 127.0.0.1 only, because inputs and results are private. Standard library only; the page and its assets
are in mutmech/web and load nothing from the network. Analyses run as jobs on a single worker thread, so Codex
calls never run in parallel. Uploaded PDFs and batch CSVs are saved under runs/uploads.

API (JSON): GET /api/rules, POST /api/analyze, POST /api/batch, POST /api/paper/find, POST /api/paper/analyze,
GET /api/jobs/<id>, GET /api/history, GET /api/result?id=<result id>, GET /api/structure?pdb=<entry>[&format=pdb],
GET /api/site?pdb=&mutation=[&paper_number=][&result=<result id>]. A result id is the run folder's path below
runs/analyze. Finding the mutations in a paper makes no LLM call and runs on its own thread, outside the queue.
"""
import argparse, base64, binascii, csv, datetime, glob, http.server, io, itertools, json, os, queue, re, threading, time, urllib.parse

from . import analyze, config, pdbguess, structview

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
ANALYZE = os.path.join(config.RUNS, 'analyze')
UPLOADS = os.path.join(config.RUNS, 'uploads')
TYPES = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
         '.txt': 'text/plain; charset=utf-8'}
MAX_BODY = 60 * 1024 * 1024
RULE_HELP = {
    'routing': 'Keyword, structure and single agent combined; the best method on the first-500 benchmark. 0 or 1 LLM call.',
    'baseline': 'The single-agent baseline skill. 1 LLM call.',
    'v4': 'Rules v4, extractor only, with its validator. 1 LLM call.',
    'stmt': 'Statement rules: splits the quote into statements and classes each for this mutation. 1 LLM call.',
}

JOBS, LOCK, WORK, IDS = {}, threading.Lock(), queue.Queue(), itertools.count(1)
PAUSE = {'until': 0.0, 'text': ''}  # set when Codex reports its usage limit; the queue waits until then


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def result_id(run_dir):
    return os.path.relpath(run_dir, ANALYZE) if run_dir else ''


def public(job):
    end = job['finished'] or time.time()
    return {k: v for k, v in job.items() if k != 'args'} | {
        'elapsed': round(end - job['started'], 1) if job['started'] else 0.0,
        'queue_position': sum(1 for j in JOBS.values() if j['status'] == 'queued' and j['created'] < job['created'])}


def run(job):
    with LOCK:
        job.update(status='running', started=time.time())
    try:
        if job['kind'] == 'find':
            p = pdbguess.paper(job['args']['pdf'], job['args']['pdb'])
            with LOCK:
                job.update(candidates=p['mutations'], pdb=p['pdb'], chosen_by=p['chosen_by'], pdb_candidates=p['pdb_candidates'])
        elif job['kind'] == 'analyze':
            r = analyze.analyze(**job['args'])
            with LOCK:
                job['result_id'] = result_id(r['run_dir'])
            if r.get('usage_limit'):
                pause(r['usage_limit'])
                raise SystemExit(r['status'].split(': ', 1)[1])
        else:
            a = job['args']
            def on_row(s):
                row = s | {'result_id': result_id(os.path.dirname(s['result'])) if s['result'] else ''}
                with LOCK:
                    job['rows'] = [x for x in job['rows'] if x['row'] != s['row']] + [row]

            def on_limit(limit):  # pause this batch and the queue, then let batch() run the row again
                pause(limit)
                with LOCK:
                    job.update(status='paused', paused_until=PAUSE['text'])
                while time.time() < PAUSE['until']:
                    time.sleep(5)
                with LOCK:
                    job.update(status='running', paused_until=None)
            if job['kind'] == 'paper':
                parent, _ = analyze.paper_batch(a['pdf'], a['pdb'], a['picks'], a['rule'], a['dry_run'], on_row, on_limit)
            else:
                parent, _ = analyze.batch(a['path'], a['rule'], a['dry_run'], on_row, on_limit)
            with LOCK:
                job['batch_dir'] = parent
        status, error = 'done', None
    except SystemExit as e:
        status, error = 'error', str(e)
    except Exception as e:  # report any failure on the page instead of killing the worker
        status, error = 'error', f'{type(e).__name__}: {e}'
    with LOCK:
        job.update(status=status, error=error, finished=time.time())


def pause(limit):
    with LOCK:
        PAUSE.update(until=max(PAUSE['until'], limit['retry_at']), text=limit['retry_at_text'])


def worker():
    while True:
        job = WORK.get()
        while time.time() < PAUSE['until']:
            with LOCK:
                job['paused_until'] = PAUSE['text']
            time.sleep(5)
        with LOCK:
            job['paused_until'] = None
        run(job)


def submit(kind, args, summary):
    with LOCK:
        jid = str(next(IDS))
        job = {'id': jid, 'kind': kind, 'status': 'queued', 'created': time.time(), 'started': None, 'finished': None,
               'error': None, 'summary': summary, 'result_id': None, 'rows': [], 'batch_dir': None, 'args': args}
        JOBS[jid] = job
    if kind == 'find':  # no LLM call: run at once instead of waiting behind Codex jobs
        threading.Thread(target=run, args=(job,), daemon=True).start()
    else:
        WORK.put(job)
    return jid


def save_upload(name, data, suffix):
    os.makedirs(UPLOADS, exist_ok=True)
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', os.path.basename(name or 'upload'))[-80:] or 'upload'
    path = os.path.join(UPLOADS, f'{stamp()}-{safe}')
    if not path.endswith(suffix):
        path += suffix
    open(path, 'wb').write(data)
    return path


def upload_pdf(body):
    """Save the base64 PDF of a request under runs/uploads. Returns (path or None, error or None)."""
    if not body.get('pdf_b64'):
        return None, None
    try:
        data = base64.b64decode(body['pdf_b64'], validate=True)
    except (binascii.Error, ValueError):
        return None, 'the PDF upload is not valid base64'
    if not data.startswith(b'%PDF'):
        return None, 'the uploaded file is not a PDF'
    return save_upload(body.get('pdf_name'), data, '.pdf'), None


def history():
    rows = []
    for f in glob.glob(os.path.join(ANALYZE, '*', 'result.json')) + glob.glob(os.path.join(ANALYZE, 'batch-*', '*', 'result.json')):
        try:
            r = json.load(open(f, encoding='utf-8'))
        except (OSError, ValueError):
            continue
        rows.append({'id': result_id(os.path.dirname(f)), 'created': r.get('created', ''), 'pdb': r['input'].get('pdb', ''),
                     'mutation': r['input'].get('mutation', ''), 'source': r['input'].get('source', ''), 'rule': r.get('rule', ''),
                     'primary': r.get('primary'), 'status': r.get('status', ''), 'batch': os.path.dirname(result_id(os.path.dirname(f)))})
    return sorted(rows, key=lambda x: x['created'], reverse=True)[:500]


def load_result(rid):
    base = os.path.realpath(ANALYZE)
    run = os.path.realpath(os.path.join(base, rid))
    if not run.startswith(base + os.sep) or not os.path.exists(os.path.join(run, 'result.json')):
        return None
    r = json.load(open(os.path.join(run, 'result.json'), encoding='utf-8'))
    p = os.path.join(run, 'call.prompt.md')
    r['prompt'] = open(p, encoding='utf-8').read() if os.path.exists(p) else None
    r['id'] = rid
    return r


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'mutmech'

    def log_message(self, fmt, *a):
        pass

    def send(self, code, body, ctype='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def local_host(self):
        host = (self.headers.get('Host') or '').rsplit(':', 1)[0]
        if host in ('127.0.0.1', 'localhost'):
            return True
        self.send(403, {'error': 'this server answers on 127.0.0.1 only'})
        return False

    def do_GET(self):
        if not self.local_host():
            return
        u = urllib.parse.urlparse(self.path)
        if u.path in ('/', '/index.html') or u.path.startswith('/static/'):
            name = 'index.html' if u.path in ('/', '/index.html') else u.path[len('/static/'):]
            f = os.path.realpath(os.path.join(WEB, name))
            if not f.startswith(os.path.realpath(WEB) + os.sep) or not os.path.isfile(f):
                return self.send(404, {'error': 'not found'})
            return self.send(200, open(f, 'rb').read(), TYPES.get(os.path.splitext(f)[1], 'application/octet-stream'))
        if u.path == '/api/rules':
            return self.send(200, [{'id': k, 'name': analyze.NAMES[k], 'help': RULE_HELP[k]} for k in analyze.RULES])
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path == '/api/structure':
            path = structview.cif_path(q.get('pdb', ''))
            if not path:
                return self.send(404, {'error': f"no cached structure for {q.get('pdb', '')!r}; add its mmCIF to a structure_dirs folder in config.toml"})
            if q.get('format') == 'pdb':
                return self.send(200, structview.pdb_text(q['pdb']).encode('utf-8'), 'chemical/x-pdb; charset=utf-8')
            return self.send(200, open(path, 'rb').read(), 'chemical/x-mmcif; charset=utf-8')
        if u.path == '/api/site':
            r = load_result(q['result']) if q.get('result') else None
            num = q.get('paper_number', '')
            out = structview.site(q.get('pdb', ''), q.get('mutation', ''), int(num) if re.fullmatch(r'-?\d+', num) else None,
                                  (r or {}).get('statements'))
            return self.send(404 if out.get('error') else 200, out)
        if u.path == '/api/history':
            return self.send(200, history())
        if u.path == '/api/result':
            r = load_result(urllib.parse.parse_qs(u.query).get('id', [''])[0])
            return self.send(200, r) if r else self.send(404, {'error': 'no such result'})
        m = re.fullmatch(r'/api/jobs/(\d+)', u.path)
        if m:
            with LOCK:
                job = JOBS.get(m.group(1))
                return self.send(200, public(job)) if job else self.send(404, {'error': 'no such job'})
        self.send(404, {'error': 'not found'})

    def do_POST(self):
        if not self.local_host():
            return
        n = int(self.headers.get('Content-Length') or 0)
        if n > MAX_BODY:
            return self.send(413, {'error': 'request too large'})
        try:
            body = json.loads(self.rfile.read(n) or b'{}')
        except ValueError:
            return self.send(400, {'error': 'body is not JSON'})
        rule = body.get('rule') or 'routing'
        if rule not in analyze.RULES:
            return self.send(400, {'error': f'unknown rule {rule!r}'})
        dry = bool(body.get('dry_run'))
        if self.path == '/api/analyze':
            mutation, quote, pdf = (body.get('mutation') or '').strip(), (body.get('quote') or '').strip(), None
            if not mutation:
                return self.send(400, {'error': 'give the mutation, e.g. D364A (chain B)'})
            pdf, err = upload_pdf(body)
            if err:
                return self.send(400, {'error': err})
            if not pdf and not quote:
                return self.send(400, {'error': 'give a quote or upload a PDF'})
            num = str(body.get('paper_number') or '').strip()
            if num and not re.fullmatch(r'-?\d+', num):
                return self.send(400, {'error': 'paper number must be a whole number'})
            args = {'mutation': mutation, 'quote': None if pdf else quote, 'pdf': pdf, 'pdb': (body.get('pdb') or '').strip(),
                    'citation': (body.get('citation') or '').strip(), 'paper_numbers': [int(num)] if num else None,
                    'rule': rule, 'dry_run': dry}
            jid = submit('analyze', args, {'mutation': mutation, 'pdb': args['pdb'], 'rule': rule, 'dry_run': dry,
                                           'source': 'pdf' if pdf else 'quote'})
            return self.send(202, {'id': jid})
        if self.path == '/api/batch':
            text = (body.get('csv') or '').lstrip('﻿')
            reader = csv.DictReader(io.StringIO(text))
            if 'mutation' not in (reader.fieldnames or []):
                return self.send(400, {'error': 'the CSV needs a header row with mutation, pdb, and quote or pdf'})
            total = sum(1 for _ in reader)
            path = save_upload(body.get('csv_name') or 'batch.csv', text.encode('utf-8'), '.csv')
            jid = submit('batch', {'path': path, 'rule': rule, 'dry_run': dry}, {'rule': rule, 'dry_run': dry, 'rows_total': total})
            return self.send(202, {'id': jid})
        pdb = (body.get('pdb') or '').strip()
        if self.path == '/api/paper/find':
            pdf, err = upload_pdf(body)
            if not pdf and not err and body.get('pdf_id'):  # find again on a PDF already uploaded, with another entry
                pdf = os.path.join(UPLOADS, os.path.basename(body['pdf_id']))
                pdf = pdf if os.path.isfile(pdf) else None
            if err or not pdf:
                return self.send(400, {'error': err or 'upload a PDF'})
            jid = submit('find', {'pdf': pdf, 'pdb': pdb}, {'pdb': pdb, 'pdf': os.path.basename(pdf)})
            return self.send(202, {'id': jid, 'pdf_id': os.path.basename(pdf)})
        if self.path == '/api/paper/analyze':
            pdf = os.path.join(UPLOADS, os.path.basename(body.get('pdf_id') or ''))
            if not body.get('pdf_id') or not os.path.isfile(pdf):
                return self.send(400, {'error': 'find the mutations in an uploaded PDF first'})
            picks = []
            for p in body.get('picks') or []:
                mut, num = str(p.get('mutation') or '').strip(), str(p.get('paper_number') or '').strip()
                if not analyze.routing.Structure.mutation(mut) or (num and not re.fullmatch(r'-?\d+', num)):
                    return self.send(400, {'error': f'cannot read the mutation {mut!r}; write it like "D364A (chain B)"'})
                picks.append({'mutation': mut, 'paper_number': int(num) if num else None})
            if not picks:
                return self.send(400, {'error': 'pick at least one mutation'})
            jid = submit('paper', {'pdf': pdf, 'pdb': pdb, 'picks': picks, 'rule': rule, 'dry_run': dry},
                         {'rule': rule, 'dry_run': dry, 'rows_total': len(picks), 'pdf': os.path.basename(pdf)})
            return self.send(202, {'id': jid})
        self.send(404, {'error': 'not found'})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', type=int, default=8765)
    a = ap.parse_args()
    threading.Thread(target=worker, daemon=True).start()
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', a.port), Handler)
    print(f'MutMech GUI on http://127.0.0.1:{a.port}/  (Ctrl-C to stop)', flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
