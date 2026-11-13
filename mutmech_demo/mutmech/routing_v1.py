#!/usr/bin/env python3
"""Evidence routing, version 1: version 0 plus two changes in route D, fixed before the first v1 run.

1. Route D splits by format. A quote with PDB atom names (OD1, NH1, OH, ...) is an atom-contact table
   (route D-table): the structure gives the type, as in v0. A quote with no notation is route D-empty.
2. Route D-empty takes the SKEMPI 2.0 binding-energy change (eval/skempi/mutmech_skempi.csv) as the
   mechanism-or-none gate that v0 lacked: ddG below the threshold (default 1.0 kcal/mol) gives no mechanism,
   evidence level 'measured_small_effect'; otherwise the structure gives the type. Without a SKEMPI match
   the structure decides, as in v0.
Routes A, B and C are v0's (eval/routing/routing.py, imported unchanged).

Usage:
  python3 -I eval/routing/routing_v1.py score SPLIT --llm RUN_DIR [--llm RUN_DIR ...] [--threshold 1.0] [--final] [--out DIR]
SPLIT is dev, test, reserve or all. Scoring test needs --final, reports only v1 against the keyword rule and
writes aggregates only (eval/testset/README.md). Scoring all also needs --final: it describes the whole dataset,
half of which the rules were designed on, and adds a by-split table.
"""
import argparse, collections, csv, datetime, hashlib, json, os, random, re, sys

from . import config
from . import routing as v0
from . import gold as sg
ev = sg.ev

SKEMPI_JOIN = os.path.join(config.RUNS, 'skempi', 'mutmech_skempi.csv')
ATOM = re.compile(r'\b(?:OD[12]|OE[12]|NH[12]|NE[12]?|ND[12]|NZ|OG1?|OH|SG|SD|O[GH]\d?|N[ED]\d)\b')
ROUTES = ['A', 'B', 'C', 'D-table', 'D-empty']


def subroute(q):
    r = v0.route_of(q)
    if r != 'D':
        return r
    return 'D-table' if ATOM.search(q or '') else 'D-empty'


def load_skempi():
    out = {}
    for r in csv.DictReader(open(SKEMPI_JOIN, encoding='utf-8')):
        out[r['ID']] = float(r['ddg_median_kcal']) if r['ddg_median_kcal'] else None
    return out


def assemble(row, llm, s, ddg, threshold, d_empty='gate', gate_all=False):
    """One routed record. d_empty: gate (v1), abstain, or structure (v0's behaviour); gate_all applies the
    SKEMPI gate on every route, a sensitivity check only."""
    q = row['Quote'] or ''
    sub = subroute(q)
    if gate_all and ddg is not None and ddg < threshold:
        return {'route': sub, 'labels': [], 'evidence': 'measured_small_effect', 'flags': ['skempi_small_effect']}
    if sub in ('A', 'B', 'C'):
        rec = v0.assemble(row, llm, s, 'structure')
        rec['route'] = sub
        return rec
    flags = [] if s is not None else ['no_verified_structure']
    struct = [c for c in v0.PRIORITY if s and c in s][:1]
    typed = {'labels': struct, 'evidence': 'structure_inferred' if struct else 'insufficient'}
    if sub == 'D-table':
        return {'route': sub, 'labels': struct, 'evidence': 'stated_as_contacts' if struct else 'insufficient', 'flags': flags}
    if d_empty == 'abstain':
        return {'route': sub, 'labels': [], 'evidence': 'insufficient', 'flags': flags}
    if d_empty == 'structure':
        return {'route': sub, **typed, 'flags': flags}
    if ddg is None:
        return {'route': sub, **typed, 'flags': flags + ['no_skempi']}
    if ddg < threshold:
        return {'route': sub, 'labels': [], 'evidence': 'measured_small_effect', 'flags': flags + ['skempi_small_effect']}
    return {'route': sub, **typed, 'flags': flags + ['skempi_large_effect']}


def paired(gold, ok_a, ok_b, ids):
    clusters = collections.defaultdict(list)
    for i in ids:
        clusters[gold[i]['quote']].append(i)
    keys = sorted(clusters)
    rng = random.Random(v0.SEED)
    d = []
    for _ in range(v0.N_BOOT):
        s = [i for k in rng.choices(keys, k=len(keys)) for i in clusters[k]]
        d.append(100 * sum(ok_b[i] - ok_a[i] for i in s) / len(s))
    return 100 * sum(ok_b[i] - ok_a[i] for i in ids) / len(ids), ev.percentile(d, .025), ev.percentile(d, .975)


def read_ids(split):
    if split == 'all':
        return [i for s in ('dev', 'test', 'reserve') for i in v0.read_split(s)]
    return v0.read_split(split)


def cmd_score(a):
    if a.split in ('test', 'all') and not a.final:
        sys.exit('The test set is scored once per final method. Freeze the routing first, then add --final.')
    gold, inp = sg.load_gold()
    v0.check_patterns(inp)
    ids = read_ids(a.split)
    llm = {}
    for d in a.llm:
        llm.update(v0.read_llm(d))
    sk = load_skempi()
    st = v0.Structure()
    S = {i: (st.contacts(inp[i]) if v0.route_of(inp[i]['Quote']) in 'BCD' else None) for i in ids}
    T = a.threshold
    def build(t=T, d_empty='gate', gate_all=False):
        return {i: assemble(inp[i], llm.get(i), S[i], sk.get(i), t, d_empty, gate_all) for i in ids}

    routed = build()
    systems = {'routing v1': {i: routed[i]['labels'] for i in ids}, 'keyword rule': {i: sg.keyword(inp[i]['Quote']) for i in ids}}
    if a.split != 'test':
        systems['routing v0'] = {i: v0.assemble(inp[i], llm.get(i), S[i], 'structure')['labels'] for i in ids}
        systems['v1, D-empty abstains'] = {i: r['labels'] for i, r in build(d_empty='abstain').items()}
        for t in (0.5, 1.5):
            if t != T:
                systems[f'v1, threshold {t} kcal/mol'] = {i: r['labels'] for i, r in build(t=t).items()}
        systems['v1, SKEMPI gate on every route'] = {i: r['labels'] for i, r in build(gate_all=True).items()}
    scored = [i for i in ids if gold[i]['state'] != 'unscorable']
    mech = [i for i in scored if gold[i]['state'] == 'mechanism']
    none = [i for i in scored if gold[i]['state'] == 'no_mechanism']
    right = v0.right
    ok = {n: {i: right(gold[i], P[i]) for i in scored} for n, P in systems.items()}
    ci_c, ci_a = v0.boot(gold, ok, scored), v0.boot(gold, ok, mech)
    matched = sum(1 for i in scored if sk.get(i) is not None)

    md = [f'# Routing v1 on {a.split}\n',
          f"Run {datetime.date.today().isoformat()} with `eval/routing/routing_v1.py`. Routes A, B and C are v0's; LLM labels from "
          f"{', '.join(f'`{d}`' for d in a.llm)}. Route D splits into D-table (atom-contact notation, structure gives the type) and "
          f'D-empty (SKEMPI gate: ddG below {T} kcal/mol gives no mechanism, else the structure gives the type). '
          f'{len(scored)} scorable records ({len(mech)} curator mechanism, {len(none)} curator none); {matched} have a SKEMPI ddG.\n',
          '## Accuracy\n',
          '**A**: curator-mechanism records, primary label in the curator set. **C**: all scorable records, no label is right '
          'where the curators mark none. 95% quote-clustered bootstrap intervals.\n']
    rows = []
    for n in systems:
        rows.append([n, f'{v0.pct(sum(ok[n][i] for i in mech), len(mech))} {v0.ci(ci_a[n])}',
                     f'{v0.pct(sum(ok[n][i] for i in scored), len(scored))} {v0.ci(ci_c[n])}',
                     f'{sum(1 for i in none if not systems[n][i])}/{len(none)}'])
    md.append(ev.table(['System', 'A', 'C', 'Curator none left blank'], rows) + '\n')
    comps = [('keyword rule', 'routing v1')] + ([('routing v0', 'routing v1')] if a.split != 'test' else [])
    for x, y in comps:
        d, lo, hi = paired(gold, ok[x], ok[y], scored)
        md.append(f'Paired difference in C, {y} minus {x}: {d:+.1f} points [{lo:+.1f}, {hi:+.1f}].\n')
    md.append('## By route\n')
    rows = []
    for r in ROUTES:
        x = [i for i in scored if routed[i]['route'] == r]
        m = [i for i in x if gold[i]['state'] == 'mechanism']
        row = [r, sum(1 for i in ids if routed[i]['route'] == r), len(x), len(x) - len(m),
               v0.pct(sum(ok['routing v1'][i] for i in m), len(m)), v0.pct(sum(ok['routing v1'][i] for i in x), len(x))]
        if a.split != 'test':
            row.append(v0.pct(sum(ok['routing v0'][i] for i in x), len(x)))
        rows.append(row)
    md.append(ev.table(['Route', 'Records', 'Scorable', 'Curator none', 'A, v1', 'C, v1'] + (['C, v0'] if a.split != 'test' else []), rows) + '\n')
    if a.split == 'all':
        md.append('## By split\n')
        md.append('The routing rules were designed on dev, so the dev rows are in-sample.\n')
        rows = []
        for s in ('dev', 'test', 'reserve'):
            x = [i for i in v0.read_split(s) if gold[i]['state'] != 'unscorable']
            m = [i for i in x if gold[i]['state'] == 'mechanism']
            rows.append([s, len(x)] + [v0.pct(sum(ok[n][i] for i in x), len(x)) for n in ('routing v1', 'routing v0', 'keyword rule')]
                        + [v0.pct(sum(ok['routing v1'][i] for i in m), len(m))])
        md.append(ev.table(['Split', 'Scorable', 'C, v1', 'C, v0', 'C, keyword rule', 'A, v1'], rows) + '\n')
    md.append('## By evidence level\n')
    rows = []
    for e in ('stated', 'stated_as_contacts', 'inferred', 'structure_inferred', 'measured_small_effect', 'insufficient'):
        x = [i for i in scored if routed[i]['evidence'] == e]
        m = [i for i in x if gold[i]['state'] == 'mechanism']
        if x:
            rows.append([e, len(x), len(x) - len(m), v0.pct(sum(ok['routing v1'][i] for i in m), len(m)),
                         v0.pct(sum(ok['routing v1'][i] for i in x), len(x))])
    md.append(ev.table(['Evidence level', 'Scorable', 'Curator none', 'A', 'C'], rows) + '\n')
    text = '\n'.join(md)
    out = a.out or os.path.join(config.RUNS, 'routing', f'{a.split}_v1')
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, 'results.md'), 'w', encoding='utf-8').write(text)
    summary = {'split': a.split, 'threshold_kcal': T, 'llm_run': a.llm, 'date': datetime.date.today().isoformat(),
               'script_sha256': hashlib.sha256(open(os.path.abspath(__file__), 'rb').read()).hexdigest(),
               'routing_v0_sha256': hashlib.sha256(open(v0.__file__, 'rb').read()).hexdigest(),
               'skempi_join_sha256': hashlib.sha256(open(SKEMPI_JOIN, 'rb').read()).hexdigest(),
               'scorable': len(scored), 'mechanism': len(mech), 'none': len(none), 'skempi_matched': matched,
               'systems': {n: {'A': [sum(ok[n][i] for i in mech), len(mech)], 'C': [sum(ok[n][i] for i in scored), len(scored)],
                               'A_ci95': ci_a[n], 'C_ci95': ci_c[n]} for n in systems},
               'routes': dict(collections.Counter(routed[i]['route'] for i in ids))}
    json.dump(summary, open(os.path.join(out, 'results.json'), 'w', encoding='utf-8'), indent=1)
    if a.split != 'test':
        with open(os.path.join(out, 'per_record.csv'), 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            split_of = {i: s for s in ('dev', 'test', 'reserve') for i in v0.read_split(s)}
            w.writerow(['ID', 'split', 'route', 'labels', 'evidence', 'flags', 'skempi_ddg_kcal', 'structure_contacts', 'llm_labels',
                        'gold_state', 'gold_codes', 'right_C'])
            for i in ids:
                g = gold[i]
                w.writerow([i, split_of[i], routed[i]['route'], ';'.join(routed[i]['labels']), routed[i]['evidence'], ';'.join(routed[i]['flags']),
                            '' if sk.get(i) is None else sk[i], '' if S[i] is None else ';'.join(sorted(S[i])),
                            ';'.join(llm.get(i, [])), g['state'], ';'.join(g['G']),
                            '' if g['state'] == 'unscorable' else int(right(g, routed[i]['labels']))])
    print(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('score')
    p.add_argument('split', choices=['dev', 'test', 'reserve', 'all'])
    p.add_argument('--llm', required=True, action='append', help='pipeline run folder with baseline/batch_*/final.jsonl (routes B and C); repeat to merge runs')
    p.add_argument('--threshold', type=float, default=1.0, help='SKEMPI ddG gate for route D-empty, kcal/mol')
    p.add_argument('--final', action='store_true')
    p.add_argument('--out')
    cmd_score(ap.parse_args())


if __name__ == '__main__':
    main()
