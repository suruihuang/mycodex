#!/usr/bin/env python3
"""Gold-standard tools for the mechanism pipeline.

  sample   --records RUN.jsonl --input DATA.csv --exclude DEV_IDS.txt --n 45 --out gold_ids.txt
           Stratified sample: one record per distinct quote, strata = model evidence basis x seen/unseen paper.
  template --input DATA.csv --ids gold_ids.txt --out gold.csv
           Blank annotation sheet with the supplied fields only (no model output), rows shuffled.
  score    --gold gold.csv SYSTEM.jsonl [SYSTEM2.jsonl ...] [--names a,b] [--errors errors.csv]
           Metrics per system, by ID and by distinct quote, with quote-clustered bootstrap CIs,
           seen/unseen split, and paired differences against the first system.
  compare  RUN1.jsonl RUN2.jsonl
           Run-to-run stability: agreement and Cohen's kappa.
  kappa    gold_a.csv gold_b.csv
           Agreement between two annotators.

Gold CSV: ID, gold_labels (primary first, ';'-separated, or not_stated), gold_basis; the template adds
PDB, Mutation DECODED, Quote and Citation. System files: JSONL with ID, mechanism_labels, evidence_basis.
"""
import argparse
import collections
import csv
import json
import math
import random
import re
import sys

BASES = ['explicit_reported', 'author_proposed', 'chemical_inference', 'structure_inference', 'not_assessable']
LABELS = ['electrostatic', 'hydrogen_bonding', 'hydrophobic', 'aromatic', 'steric', 'conformational',
          'covalent_or_metal', 'other']
RANK = {'explicit_reported': 3, 'author_proposed': 2, 'chemical_inference': 1, 'structure_inference': 1,
        'not_assessable': 0}
NAN = float('nan')


# ---------- io ----------
def read_csv(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def read_jsonl(path):
    out = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                out[str(r.get('ID')).strip()] = r
    return out


def parse_labels(x):
    if isinstance(x, list):
        items = x
    else:
        items = re.split(r'[;,]', str(x or ''))
    return [s.strip() for s in items if s.strip() and s.strip() != 'not_stated']


def norm(s):
    return ' '.join(str(s or '').split()).strip('“”"\' ').lower()


def pdb_token(s):
    m = re.search(r'\b(\d[A-Za-z0-9]{3})', str(s or ''))
    return m.group(1).upper() if m else ''


def fmt(x):
    return '–' if x is None or (isinstance(x, float) and math.isnan(x)) else f'{100 * x:.1f}%'


def table(headers, rows):
    out = ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join('---' for _ in headers) + ' |']
    out += ['| ' + ' | '.join(str(c) for c in row) + ' |' for row in rows]
    return '\n'.join(out)


def kappa(a, b):
    n = len(a)
    if n == 0:
        return NAN
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = collections.Counter(a), collections.Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return 1.0 if pe >= 1 else (po - pe) / (1 - pe)


# ---------- metrics ----------
def metrics(items):
    """items: (G, M, gold_basis, pred_basis, weight). G, M: label lists, primary first; [] = not assessable."""
    s = collections.defaultdict(float)
    for G, M, gb, pb, w in items:
        Gs, Ms = set(G), set(M)
        if not G:
            s['na'] += w
            if M:
                s['fab'] += w
        else:
            s['mech'] += w
            if M and M[0] in Gs:
                s['cov'] += w
            if M and M[0] == G[0]:
                s['exact'] += w
            if not M:
                s['missed'] += w
        if M:
            s['pd'] += w * len(Ms)
            s['pn'] += w * len(Ms & Gs)
        if G and M:
            s['both'] += w
            s['bacc'] += w * (pb == gb)
            s['over'] += w * (RANK.get(pb, -1) > RANK.get(gb, -1))

    def r(n, d):
        return s[n] / s[d] if s[d] else NAN
    return {'fabrication': r('fab', 'na'), 'precision': r('pn', 'pd'), 'coverage': r('cov', 'mech'),
            'primary_exact': r('exact', 'mech'), 'missed': r('missed', 'mech'),
            'basis_accuracy': r('bacc', 'both'), 'basis_overclaim': r('over', 'both')}


KEYS = ['fabrication', 'precision', 'coverage', 'basis_overclaim', 'basis_accuracy', 'primary_exact']
HEAD = ['Fabrication ↓', 'Label precision ↑', 'Coverage ↑', 'Basis over-claim ↓', 'Basis accuracy', 'Primary exact']


def percentile(xs, q):
    xs = sorted(x for x in xs if not math.isnan(x))
    if not xs:
        return NAN
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


# ---------- subcommands ----------
def cmd_sample(a):
    recs = read_jsonl(a.records)
    inp = {r['ID'].strip(): r for r in read_csv(a.input)}
    excl = set()
    if a.exclude:
        excl = {x.strip() for x in open(a.exclude, encoding='utf-8').read().replace(',', ' ').split() if x.strip()}
    seen = {s.strip().upper() for s in a.seen.split(',') if s.strip()}
    rng = random.Random(a.seed)
    by_quote = collections.defaultdict(list)
    for i, r in recs.items():
        if i in excl or i not in inp:
            continue
        by_quote[norm(inp[i].get('Quote'))].append(i)
    strata = collections.defaultdict(list)
    for ids in by_quote.values():
        i = rng.choice(sorted(ids))
        tag = 'seen' if pdb_token(inp[i].get('PDB')) in seen else 'unseen'
        strata[(recs[i].get('evidence_basis'), tag)].append(i)
    total = sum(len(v) for v in strata.values())
    if total == 0:
        sys.exit('no candidates')
    n = min(a.n, total)
    alloc = {k: min(len(v), max(a.min_per, round(n * len(v) / total))) for k, v in strata.items()}
    while sum(alloc.values()) > n:
        k = max(alloc, key=lambda k: alloc[k] - (a.min_per if alloc[k] > a.min_per else alloc[k]))
        alloc[k] -= 1
    while sum(alloc.values()) < n:
        k = max((k for k in strata if alloc[k] < len(strata[k])), key=lambda k: len(strata[k]) - alloc[k])
        alloc[k] += 1
    chosen = []
    for k, ids in strata.items():
        rng.shuffle(ids)
        used = collections.Counter()
        picks = []
        pool = list(ids)
        while len(picks) < alloc[k] and pool:
            pool.sort(key=lambda i: used[pdb_token(inp[i].get('PDB'))])
            i = pool.pop(0)
            used[pdb_token(inp[i].get('PDB'))] += 1
            picks.append(i)
        chosen += picks
    with open(a.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(sorted(chosen, key=lambda x: int(x) if x.isdigit() else x)) + '\n')
    print(f'wrote {len(chosen)} IDs to {a.out} (from {total} distinct-quote candidates, {len(excl)} excluded)')
    print(table(['Basis (model)', 'Paper', 'Candidates', 'Sampled'],
                [[k[0], k[1], len(strata[k]), alloc[k]] for k in sorted(strata, key=str)]))
    print('Strata are sampled for coverage, not in proportion: report metrics per stratum or reweight.')


def cmd_template(a):
    inp = {r['ID'].strip(): r for r in read_csv(a.input)}
    ids = [x.strip() for x in open(a.ids, encoding='utf-8').read().split() if x.strip()]
    missing = [i for i in ids if i not in inp]
    random.Random(a.seed).shuffle(ids)
    cols = ['ID', 'PDB', 'Mutation DECODED', 'Quote', 'Citation', 'gold_labels', 'gold_basis', 'gold_notes', 'annotator']
    with open(a.out, 'w', newline='', encoding='utf-8-sig') as f:
        wr = csv.writer(f)
        wr.writerow(cols)
        for i in ids:
            if i in inp:
                r = inp[i]
                wr.writerow([i, r.get('PDB', ''), r.get('Mutation DECODED', ''), r.get('Quote', ''), r.get('Citation', ''), '', '', '', ''])
    print(f'wrote {len(ids) - len(missing)} rows to {a.out}' + (f'; not in input: {missing}' if missing else ''))
    print('gold_labels: primary first, separated by ";", from: ' + ', '.join(LABELS) + ' (or not_stated)')
    print('gold_basis: one of ' + ', '.join(BASES))


def load_gold(path):
    rows = read_csv(path)
    gold, problems = {}, []
    for r in rows:
        i = str(r.get('ID', '')).strip()
        if not i:
            continue
        G = parse_labels(r.get('gold_labels'))
        gb = str(r.get('gold_basis') or '').strip()
        bad = [x for x in G if x not in LABELS]
        if bad:
            problems.append(f'{i}: unknown label(s) {bad}')
        if gb not in BASES:
            problems.append(f'{i}: gold_basis {gb!r} not in {BASES}')
        if (not G) != (gb == 'not_assessable'):
            problems.append(f'{i}: not_stated labels and not_assessable basis must go together')
        gold[i] = {'G': G, 'gb': gb, 'quote': norm(r.get('Quote')) or i, 'pdb': pdb_token(r.get('PDB'))}
    if problems:
        sys.exit('gold file problems:\n  ' + '\n  '.join(problems))
    return gold


def build_items(gold, pred, ids, by_quote=False):
    sizes = collections.Counter(gold[i]['quote'] for i in ids)
    items = []
    for i in ids:
        p = pred.get(i, {})
        w = 1 / sizes[gold[i]['quote']] if by_quote else 1.0
        items.append((gold[i]['G'], parse_labels(p.get('mechanism_labels')), gold[i]['gb'],
                      p.get('evidence_basis', 'not_assessable'), w))
    return items


def cmd_score(a):
    gold = load_gold(a.gold)
    names = a.names.split(',') if a.names else [p.rsplit('/', 1)[-1] for p in a.systems]
    if len(names) != len(a.systems):
        sys.exit('--names must match the number of system files')
    preds = [read_jsonl(p) for p in a.systems]
    ids = sorted(gold)
    seen = {s.strip().upper() for s in a.seen.split(',') if s.strip()}
    out = [f'# Scores on {len(ids)} gold records ({len({gold[i]["quote"] for i in ids})} distinct quotes)\n']
    for name, p in zip(names, preds):
        miss = [i for i in ids if i not in p]
        if miss:
            out.append(f'**{name}** has no prediction for {len(miss)} gold IDs; counted as not assessable: {miss[:20]}\n')

    clusters = collections.defaultdict(list)
    for i in ids:
        clusters[gold[i]['quote']].append(i)
    keys = sorted(clusters)
    rng = random.Random(a.seed)
    boots = [[] for _ in preds]
    for _ in range(a.boot):
        sample = [i for k in rng.choices(keys, k=len(keys)) for i in clusters[k]]
        for s, p in enumerate(preds):
            boots[s].append(metrics(build_items(gold, p, sample)))

    point = [metrics(build_items(gold, p, ids)) for p in preds]
    rows = []
    for s, name in enumerate(names):
        cells = []
        for k in KEYS:
            lo = percentile([b[k] for b in boots[s]], 0.025)
            hi = percentile([b[k] for b in boots[s]], 0.975)
            cells.append(f'{fmt(point[s][k])} [{fmt(lo)}, {fmt(hi)}]')
        rows.append([name] + cells)
    out.append('## By record, with 95% quote-clustered bootstrap CIs\n')
    out.append(table(['System'] + HEAD, rows) + '\n')

    out.append('## By distinct quote (each quote weighted once)\n')
    out.append(table(['System'] + HEAD, [[n] + [fmt(metrics(build_items(gold, p, ids, True))[k]) for k in KEYS]
                                        for n, p in zip(names, preds)]) + '\n')

    groups = {'seen papers': [i for i in ids if gold[i]['pdb'] in seen],
              'unseen papers': [i for i in ids if gold[i]['pdb'] not in seen]}
    rows = []
    for g, gids in groups.items():
        for n, p in zip(names, preds):
            m = metrics(build_items(gold, p, gids))
            rows.append([g, len(gids), n] + [fmt(m[k]) for k in KEYS[:4]])
    out.append(f'## Seen ({", ".join(sorted(seen))}) vs unseen papers\n')
    out.append(table(['Group', 'Records', 'System'] + HEAD[:4], rows) + '\n')

    if len(preds) > 1:
        rows = []
        for s in range(1, len(preds)):
            cells = []
            for k in KEYS[:4]:
                d = [b2[k] - b0[k] for b0, b2 in zip(boots[0], boots[s])]
                cells.append(f'{fmt(point[s][k] - point[0][k])} [{fmt(percentile(d, 0.025))}, {fmt(percentile(d, 0.975))}]')
            rows.append([f'{names[s]} − {names[0]}'] + cells)
        out.append('## Paired differences against the first system (same bootstrap samples)\n')
        out.append(table(['Comparison'] + HEAD[:4], rows) + '\n')
        out.append('A difference is only worth claiming when its interval excludes 0.\n')

    na = sum(1 for i in ids if not gold[i]['G'])
    out.append(f'Gold: {na} not assessable, {len(ids) - na} with a mechanism.\n')

    if a.errors:
        with open(a.errors, 'w', newline='', encoding='utf-8-sig') as f:
            wr = csv.writer(f)
            wr.writerow(['system', 'ID', 'error', 'gold_labels', 'gold_basis', 'pred_labels', 'pred_basis', 'your_category'])
            for name, p in zip(names, preds):
                for i in ids:
                    G, gb = gold[i]['G'], gold[i]['gb']
                    M = parse_labels(p.get(i, {}).get('mechanism_labels'))
                    pb = p.get(i, {}).get('evidence_basis', 'not_assessable')
                    errs = []
                    if not G and M:
                        errs.append('fabrication')
                    if G and not M:
                        errs.append('missed')
                    if G and M and M[0] not in G:
                        errs.append('wrong_primary')
                    if G and M and set(M) - set(G):
                        errs.append('extra_label')
                    if G and M and RANK.get(pb, -1) > RANK.get(gb, -1):
                        errs.append('basis_overclaim')
                    if G and M and RANK.get(pb, -1) < RANK.get(gb, -1):
                        errs.append('basis_underclaim')
                    for e in errs:
                        wr.writerow([name, i, e, ';'.join(G) or 'not_stated', gb, ';'.join(M) or 'not_stated', pb, ''])
        out.append(f'Per-record errors written to {a.errors}; fill in your_category for the error analysis.\n')
    print('\n'.join(out))


def cmd_compare(a):
    p1, p2 = read_jsonl(a.run1), read_jsonl(a.run2)
    ids = sorted(set(p1) & set(p2), key=lambda x: int(x) if x.isdigit() else x)
    if not ids:
        sys.exit('no IDs in common')
    L1 = [frozenset(parse_labels(p1[i].get('mechanism_labels'))) for i in ids]
    L2 = [frozenset(parse_labels(p2[i].get('mechanism_labels'))) for i in ids]
    P1 = [(parse_labels(p1[i].get('mechanism_labels')) or ['not_stated'])[0] for i in ids]
    P2 = [(parse_labels(p2[i].get('mechanism_labels')) or ['not_stated'])[0] for i in ids]
    B1 = [p1[i].get('evidence_basis') for i in ids]
    B2 = [p2[i].get('evidence_basis') for i in ids]
    same = [l1 == l2 and b1 == b2 for l1, l2, b1, b2 in zip(L1, L2, B1, B2)]
    print(f'# Stability on {len(ids)} shared records\n')
    print(table(['Measure', 'Value'], [
        ['Identical label set and basis', fmt(sum(same) / len(ids))],
        ['Identical label set', fmt(sum(x == y for x, y in zip(L1, L2)) / len(ids))],
        ['Identical basis', fmt(sum(x == y for x, y in zip(B1, B2)) / len(ids))],
        ["Cohen's kappa, primary label", f'{kappa(P1, P2):.2f}'],
        ["Cohen's kappa, basis", f'{kappa(B1, B2):.2f}'],
    ]))
    flips = [(i, sorted(l1), b1, sorted(l2), b2) for i, l1, l2, b1, b2, s in zip(ids, L1, L2, B1, B2, same) if not s]
    if flips:
        print(f'\n{len(flips)} records changed (first 30):')
        for i, l1, b1, l2, b2 in flips[:30]:
            print(f'- {i}: {l1 or ["not_stated"]} {b1} -> {l2 or ["not_stated"]} {b2}')


def cmd_kappa(a):
    g1, g2 = load_gold(a.gold_a), load_gold(a.gold_b)
    ids = sorted(set(g1) & set(g2), key=lambda x: int(x) if x.isdigit() else x)
    if not ids:
        sys.exit('no IDs in common')
    P1 = [(g1[i]['G'] or ['not_stated'])[0] for i in ids]
    P2 = [(g2[i]['G'] or ['not_stated'])[0] for i in ids]
    B1 = [g1[i]['gb'] for i in ids]
    B2 = [g2[i]['gb'] for i in ids]
    print(f'# Annotator agreement on {len(ids)} records\n')
    print(table(['Measure', 'Value'], [
        ['Identical label set', fmt(sum(set(g1[i]['G']) == set(g2[i]['G']) for i in ids) / len(ids))],
        ["Cohen's kappa, primary label", f'{kappa(P1, P2):.2f}'],
        ["Cohen's kappa, basis", f'{kappa(B1, B2):.2f}'],
    ]))
    dis = [i for i in ids if set(g1[i]['G']) != set(g2[i]['G']) or g1[i]['gb'] != g2[i]['gb']]
    if dis:
        print('\nDisagreements to adjudicate:')
        for i in dis:
            print(f"- {i}: A {g1[i]['G'] or ['not_stated']} {g1[i]['gb']} | B {g2[i]['G'] or ['not_stated']} {g2[i]['gb']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('sample')
    s.add_argument('--records', required=True)
    s.add_argument('--input', required=True)
    s.add_argument('--exclude')
    s.add_argument('--n', type=int, default=45)
    s.add_argument('--min-per', type=int, default=3)
    s.add_argument('--seen', default='1A22,1A4Y')
    s.add_argument('--seed', type=int, default=0)
    s.add_argument('--out', required=True)
    t = sub.add_parser('template')
    t.add_argument('--input', required=True)
    t.add_argument('--ids', required=True)
    t.add_argument('--seed', type=int, default=0)
    t.add_argument('--out', required=True)
    c = sub.add_parser('score')
    c.add_argument('--gold', required=True)
    c.add_argument('systems', nargs='+')
    c.add_argument('--names')
    c.add_argument('--seen', default='1A22,1A4Y')
    c.add_argument('--boot', type=int, default=2000)
    c.add_argument('--seed', type=int, default=0)
    c.add_argument('--errors')
    m = sub.add_parser('compare')
    m.add_argument('run1')
    m.add_argument('run2')
    k = sub.add_parser('kappa')
    k.add_argument('gold_a')
    k.add_argument('gold_b')
    a = ap.parse_args()
    {'sample': cmd_sample, 'template': cmd_template, 'score': cmd_score, 'compare': cmd_compare,
     'kappa': cmd_kappa}[a.cmd](a)


if __name__ == '__main__':
    main()
