"""Score a finished pipeline run on the first-500 benchmark, next to the baseline, the keyword rule and the combined methods.

  python -m mutmech score RUN_DIR METHOD [--answers A.json] [--inputs I.json] [--baseline-run DIR] [--out DIR]

RUN_DIR is a `mutmech pipeline` run folder holding METHOD/batch_*/final.jsonl; a run stopped part way is scored on
its finished records. Defaults for the answers, the inputs and the baseline run come from the [first500] section of
config.toml. Systems, as in the logged first-500 analyses (eval/first500/score_vs_baseline.py and score_stmt.py):
the method; the baseline; the keyword rule; the hybrid (one-keyword quotes take the keyword class, the rest the
model's labels) and routing v0 with no-hint quotes decided by the model, each built from the baseline's labels and
from the method's. Right when the primary label is in mapped_codes. 95% intervals: quote-clustered bootstrap,
2,000 resamples, seed 0, paired differences on the same resamples. For METHOD stmt the report adds the statement
structure: statements per quote, statement and record classes, and agreement by record class.
Writes <out>/<run name>_<method>.md and .json (default out: runs/scores).
"""
import argparse, collections, glob, json, os, random

from . import config, pipeline, routing
from . import gold as sg
ev = sg.ev
RC = ['causal', 'proposed_causal', 'relationship_only', 'no_mechanism_statement']
SIZES = ['1 statement', '2-3 statements', '4-6 statements', '7+ statements']


def read(run, method):
    out = {}
    for f in glob.glob(os.path.join(run, method, 'batch_*', 'final.jsonl')):
        for line in open(f, encoding='utf-8'):
            if line.strip():
                r = json.loads(line)
                out[str(r['ID'])] = r
    return out


def compute(run, method, answers, inputs, baseline_run, structure=None):
    """Labels and right/wrong per system on the records the method has finished."""
    ans = json.load(open(answers, encoding='utf-8'))
    inp = {r['ID']: r for r in json.load(open(inputs, encoding='utf-8'))}
    gold = {a['ID']: a['mapped_codes'] for a in ans}
    recs, base = read(run, method), {i: pipeline.labels(r) for i, r in read(baseline_run, 'baseline').items()}
    pred = {i: pipeline.labels(r) for i, r in recs.items()}
    ids = [a['ID'] for a in ans if a['ID'] in pred]
    if any(i not in base for i in ids):
        raise SystemExit('baseline output missing for some records')
    route = {i: routing.route_of(inp[i]['Quote']) for i in ids}
    kc = {i: routing.keyword_classes(inp[i]['Quote']) for i in ids}
    st = structure or routing.Structure()
    S = {i: (st.contacts(inp[i]) if route[i] in 'BCD' else None) for i in ids}
    systems = {method: pred, 'baseline': base, 'keyword rule': {i: sg.keyword(inp[i]['Quote']) for i in ids},
               'hybrid (baseline)': {i: kc[i] if route[i] == 'A' else base[i] for i in ids},
               'routing no-cue by LLM (baseline)': {i: routing.assemble(inp[i], base[i], S[i], 'llm')['labels'] for i in ids}}
    if method != 'baseline':
        systems[f'hybrid ({method})'] = {i: kc[i] if route[i] == 'A' else pred[i] for i in ids}
        systems[f'routing no-cue by LLM ({method})'] = {i: routing.assemble(inp[i], pred[i], S[i], 'llm')['labels'] for i in ids}
    systems = {n: {i: P[i] for i in ids} for n, P in systems.items()}
    ok = {n: {i: bool(P[i]) and P[i][0] in gold[i] for i in ids} for n, P in systems.items()}
    return {'ids': ids, 'inp': inp, 'gold': gold, 'recs': recs, 'route': route, 'systems': systems, 'ok': ok, 'structure': st}


def intervals(c, pairs):
    clusters = collections.defaultdict(list)
    for i in c['ids']:
        clusters[' '.join(c['inp'][i]['Quote'].split())].append(i)
    keys, rng, draws = sorted(clusters), random.Random(0), collections.defaultdict(list)
    for _ in range(2000):
        s = [i for k in rng.choices(keys, k=len(keys)) for i in clusters[k]]
        for n in c['ok']:
            draws[n].append(100 * sum(c['ok'][n][i] for i in s) / len(s))
        for a, b in pairs:
            draws[(a, b)].append(100 * sum(c['ok'][a][i] - c['ok'][b][i] for i in s) / len(s))
    return clusters, {k: (ev.percentile(d, .025), ev.percentile(d, .975)) for k, d in draws.items()}


def stmt_section(c, clusters):
    recs, ids, ok = c['recs'], c['ids'], c['ok']['stmt']
    size = {q: SIZES[0] if len(recs[v[0]]['statements']) == 1 else SIZES[1] if len(recs[v[0]]['statements']) <= 3
            else SIZES[2] if len(recs[v[0]]['statements']) <= 6 else SIZES[3] for q, v in clusters.items()}
    qof = {i: q for q, v in clusters.items() for i in v}
    md = ['## Statement structure\n',
          ev.table(['Statements in the quote', 'Quotes', 'Records'],
                   [[z, sum(1 for q in size if size[q] == z), sum(1 for i in ids if size[qof[i]] == z)] for z in SIZES]) + '\n']
    pairs = collections.Counter(l['class'] for i in ids for l in recs[i]['links'])
    md.append(ev.table(['Statement class', 'Record-statement pairs'], [[k, n] for k, n in pairs.most_common()]) + '\n')
    rows = []
    for z in RC:
        x = [i for i in ids if recs[i]['record_class'] == z]
        rows.append([z, len(x), sum(ok[i] for i in x)])
    md.append(ev.table(['Record class', 'Records', 'Primary label right'], rows) + '\n')
    return md


def report(c, run, method, out_dir):
    ids, ok, systems = c['ids'], c['ok'], c['systems']
    pairs = [(method, 'baseline'), (method, 'keyword rule')]
    if method != 'baseline':
        pairs += [(f'hybrid ({method})', 'hybrid (baseline)'), (f'routing no-cue by LLM ({method})', 'routing no-cue by LLM (baseline)')]
    clusters, ci = intervals(c, pairs)
    pct = lambda k, n: f'{k}/{n} ({100 * k / n:.1f}%)' if n else '–'
    md = [f'# {method} on the first-500 benchmark\n',
          f'Run `{run}`: {len(ids)} records finished, {len(clusters)} distinct quotes; every system is scored on these. '
          'Right when the primary label is in the mapped curator codes. Quote-clustered 95% intervals.\n',
          ev.table(['System', 'Primary label right', '95% interval', 'Any label in the curator set'],
                   [[n, pct(sum(ok[n].values()), len(ids)), f'[{ci[n][0]:.1f}, {ci[n][1]:.1f}]',
                     pct(sum(bool(set(systems[n][i]) & set(c['gold'][i])) for i in ids), len(ids))] for n in systems]) + '\n',
          ev.table(['Paired difference', 'Points', '95% interval'],
                   [[f'{a} minus {b}', f'{100 * (sum(ok[a].values()) - sum(ok[b].values())) / len(ids):+.1f}',
                     f'[{ci[(a, b)][0]:+.1f}, {ci[(a, b)][1]:+.1f}]'] for a, b in pairs]) + '\n']
    rows = []
    for code in (sg.HB, sg.HY, sg.EL, sg.CO, sg.ST, sg.CM, sg.AR):
        x = [i for i in ids if c['gold'][i][0] == code]
        if x:
            rows.append([code, len(x)] + [pct(sum(ok[n][i] for i in x), len(x)) for n in (method, 'baseline', 'keyword rule')])
    md += ['## By curator primary code\n', ev.table(['Curator primary', 'Records', method, 'baseline', 'keyword rule'], rows) + '\n']
    if method == 'stmt':
        md += stmt_section(c, clusters)
    conf = collections.Counter((systems[method][i][0] if systems[method][i] else '(empty)', '+'.join(c['gold'][i])) for i in ids if not ok[method][i])
    md += [f'## {method} errors\n', ev.table([f'{method} primary', 'Curator codes', 'Records'], [[a, b, k] for (a, b), k in conf.most_common(12)]) + '\n']
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(out_dir, f'{os.path.basename(run.rstrip("/"))}_{method}')
    text = '\n'.join(md)
    open(stem + '.md', 'w', encoding='utf-8').write(text)
    json.dump({'run': run, 'method': method, 'records': len(ids), 'right': {n: [sum(ok[n].values()), len(ids)] for n in systems},
               'ci95': {(k if isinstance(k, str) else f'{k[0]} minus {k[1]}'): v for k, v in ci.items()},
               'per_record': {i: {n: systems[n][i] for n in systems} | {'gold': c['gold'][i], 'route': c['route'][i]} for i in ids}},
              open(stem + '.json', 'w', encoding='utf-8'), indent=1)
    return text, stem


def main():
    F = config.FIRST500
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run')
    ap.add_argument('method')
    ap.add_argument('--answers', default=F.get('answers'))
    ap.add_argument('--inputs', default=F.get('inputs'))
    ap.add_argument('--baseline-run', default=F.get('baseline_run'))
    ap.add_argument('--out', default=os.path.join(config.RUNS, 'scores'))
    a = ap.parse_args()
    missing = [k for k in ('answers', 'inputs', 'baseline_run') if not getattr(a, k)]
    if missing:
        ap.error(f'set {", ".join(missing)} in [first500] of config.toml or pass them as options')
    c = compute(a.run, a.method, a.answers, a.inputs, a.baseline_run)
    text, stem = report(c, a.run, a.method, a.out)
    print(text)
    print(f'Written: {stem}.md and .json')
