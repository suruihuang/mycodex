#!/usr/bin/env python3
"""Evidence routing for mechanism labels, version 0 (the "MutMech Evidence Routing" diagram).

Router, from the quote only:
  A  one keyword class ('aromatic' is dropped when another class is present)
  B  several keyword classes
  C  no keyword, but a cue word (contact, charge, pocket, packing, interact, ...)
  D  no keyword and no cue word
Routes:
  A  labels = the keyword class. A suspected negation is flagged; the LLM check is not built, so the label stays.
  B  candidates = keyword classes. If the PDB contacts confirm exactly one, it is the primary. Otherwise the
     single-agent LLM picks: its first label inside the pool (the confirmed classes when two or more are confirmed,
     else all candidates). Without a usable LLM label, keyword order decides.
  C  labels = the single-agent LLM labels. PDB contacts only flag disagreement; the label is never changed.
  D  the paper gate is not built. --d-fallback picks what D does instead: structure (primary contact type by
     electrostatic > hydrogen bonding > aromatic > hydrophobic > covalent/metal), llm, or abstain.
Every record gets a route, labels (primary first), an evidence level and flags.

Scoring follows eval/pipeline/mutmech.py: A = curator-mechanism records, primary label in the curator set;
C = all scorable records, and no label counts as right where the curators mark none. 95% intervals are
quote-clustered bootstraps (2,000 resamples, seed 0).

Usage:
  python3 -I eval/routing/routing.py ids SPLIT OUT.txt [--routes BCD]
  python3 -I eval/routing/routing.py score SPLIT --llm RUN_DIR [--d-fallback structure|llm|abstain] [--final] [--out DIR]
SPLIT is dev, test or reserve. `ids` lists the records of routes B, C and D by default, which need the LLM.
Scoring test needs --final, reports only the chosen version against the keyword rule, and writes aggregates only
(eval/testset/README.md).
"""
import argparse, collections, datetime, glob, hashlib, json, os, random, re, sys

from . import config
from . import gold as sg
ev = sg.ev

TESTSET = config.TESTSET
CUE = re.compile(r'\bpack|contact|charg|\bpolar|\bh bond|\bhbond|water|\bion(?:ic)?\b|ion pair|repuls|attract|cavity|pocket'
                 r'|conformation|interact', re.I)
# the keyword rule's patterns, one per class; checked against sg.keyword on every input quote at start-up
RX = {sg.EL: r'salt[- ]bridge|electrostatic|ionic (?:interaction|bond|pair)', sg.HB: r'hydrogen[- ]bond|h-bond',
      sg.HY: r'van der waals|hydrophobic', sg.AR: r'stacking|cation[- ]?(?:π|pi)\b|aromatic', sg.ST: r'steric|clash',
      sg.CM: r'disulfide|metal'}
NEG_BEFORE = re.compile(r'\b(?:no|not|without|lacks?|lacking|absence of|neither|nor)\b[^.;]{0,40}$', re.I)
NEG_AFTER = re.compile(r'^[^.;]{0,25}\b(?:is|are|was|were)\s+not\b', re.I)
PRIORITY = [sg.EL, sg.HB, sg.AR, sg.HY, sg.CM]
N_BOOT, SEED = 2000, 0


def keyword_classes(q):
    k = sg.keyword(q)
    rest = [c for c in k if c != sg.AR]
    return rest or k


def route_of(q):
    k = keyword_classes(q)
    if not k:
        return 'C' if CUE.search(q or '') else 'D'
    return 'A' if len(k) == 1 else 'B'


def negation_suspected(q, classes):
    for c in classes:
        for m in re.finditer(RX[c], q, re.I):
            if NEG_BEFORE.search(q[max(0, m.start() - 60):m.start()]) or NEG_AFTER.search(q[m.end():m.end() + 40]):
                return True
    return False


class Structure:
    """Contact types between the mutated residue and partner chains in a cached mmCIF entry.

    Same thresholds as the dev analysis of 2026-11-05: salt bridge 4.0 A, N/O pair 3.5 A, C-C 4.0 A, S-S 2.5 A,
    ring centroids 5.5 A or cation to ring 6.0 A. Partners are chains whose sequence differs from the mutated chain.
    Returns None when the wild type cannot be verified at that position."""
    NEG = {('ASP', 'OD1'), ('ASP', 'OD2'), ('GLU', 'OE1'), ('GLU', 'OE2')}
    POS = {('LYS', 'NZ'), ('ARG', 'NE'), ('ARG', 'NH1'), ('ARG', 'NH2'), ('HIS', 'ND1'), ('HIS', 'NE2')}
    RING = {'PHE': ['CG', 'CD1', 'CD2', 'CE1', 'CE2', 'CZ'], 'TYR': ['CG', 'CD1', 'CD2', 'CE1', 'CE2', 'CZ'],
            'TRP': ['CD2', 'CE2', 'CE3', 'CZ2', 'CZ3', 'CH2'], 'HIS': ['CG', 'ND1', 'CD2', 'CE1', 'NE2']}

    def __init__(self):
        import numpy as np
        from Bio.PDB import MMCIFParser, NeighborSearch
        from Bio.SeqUtils import seq1
        self.np, self.NS, self.seq1 = np, NeighborSearch, seq1
        self.parser = MMCIFParser(QUIET=True, auth_chains=True, auth_residues=True)
        self.cifs = {}
        for f in [f for d in config.STRUCTURE_DIRS for f in sorted(glob.glob(os.path.join(d, '**', '*.cif'), recursive=True))]:
            self.cifs.setdefault(os.path.basename(f)[:-4].upper(), f)
        self.cache = {}

    def model(self, code):
        if code not in self.cache:
            m = self.parser.get_structure(code, self.cifs[code])[0]
            atoms = [a for a in m.get_atoms() if a.get_parent().id[0] == ' ']
            seqs = {c.id: ''.join(self.seq1(r.get_resname()) for r in c if r.id[0] == ' ') for c in m}
            self.cache[code] = (m, self.NS(atoms), seqs)
        return self.cache[code]

    @staticmethod
    def pdb_tokens(cell):
        cell = cell.strip()
        if re.fullmatch(r'1\.0E(\d+)', cell):
            return ['1E' + cell.split('E')[1]]
        return [t.upper() for t in re.findall(r'(?<![A-Za-z0-9])(\d[A-Za-z0-9]{3})', cell)]

    @staticmethod
    def mutation(md):
        m = re.search(r'\b([A-Z])(\d+)([A-Z])\b', md) or re.search(r'\b([A-Z])[A-Z](\d+)([A-Z])\b', md)
        ch = re.search(r'chain\s+([A-Za-z0-9]+)', md, re.I)
        return (m.group(1), int(m.group(2)), m.group(3), ch.group(1) if ch else None) if m else None

    def centroid(self, r):
        names = self.RING.get(r.get_resname())
        if not names or not all(n in r for n in names):
            return None
        return self.np.mean([r[n].coord for n in names], axis=0)

    def interactions(self, code, chain, num):
        return set().union(*self.contacts_by_residue(code, chain, num).values())

    def contacts_by_residue(self, code, chain, num):
        """Contact types per partner residue, keyed (chain, number, residue name); interactions() is their union."""
        np = self.np
        m, ns, seqs = self.model(code)
        res = m[chain][(' ', num, ' ')]
        partners = {c for c in seqs if c != chain and seqs[c] != seqs[chain]}
        found, near = collections.defaultdict(set), []
        key = lambda r: (r.get_parent().id, r.id[1], r.get_resname())
        for a in res:
            for b in ns.search(a.coord, 4.5):
                if b.get_parent().get_parent().id in partners:
                    near.append((a, b, a - b))
        if not near:
            return {}
        for a, b, d in near:
            ra, rb, ea, eb = a.get_parent().get_resname(), b.get_parent().get_resname(), a.element, b.element
            k = key(b.get_parent())
            if d <= 4.0 and (((ra, a.get_id()) in self.NEG and (rb, b.get_id()) in self.POS)
                             or ((ra, a.get_id()) in self.POS and (rb, b.get_id()) in self.NEG)):
                found[k].add(sg.EL)
            if d <= 3.5 and ea in 'NO' and eb in 'NO':
                found[k].add(sg.HB)
            if d <= 4.0 and ea == 'C' and eb == 'C':
                found[k].add(sg.HY)
            if d <= 2.5 and ea == 'S' and eb == 'S':
                found[k].add(sg.CM)
        c1 = self.centroid(res)
        for pr in {x for a in res for x in [y.get_parent() for y in ns.search(a.coord, 7.0)] if x.get_parent().id in partners}:
            c2 = self.centroid(pr)
            if c1 is not None and c2 is not None and np.linalg.norm(c1 - c2) <= 5.5:
                found[key(pr)].add(sg.AR)
            if c1 is not None and pr.get_resname() in ('LYS', 'ARG'):
                at = pr['NZ'] if pr.get_resname() == 'LYS' and 'NZ' in pr else (pr['CZ'] if 'CZ' in pr else None)
                if at is not None and np.linalg.norm(c1 - at.coord) <= 6.0:
                    found[key(pr)].add(sg.AR)
            if c2 is not None and res.get_resname() in ('LYS', 'ARG'):
                at = res['NZ'] if res.get_resname() == 'LYS' and 'NZ' in res else (res['CZ'] if 'CZ' in res else None)
                if at is not None and np.linalg.norm(c2 - at.coord) <= 6.0:
                    found[key(pr)].add(sg.AR)
        return {k: v for k, v in found.items() if v}

    def contacts(self, row):
        mu = self.mutation(row['Mutation DECODED'])
        toks = [t for t in self.pdb_tokens(row['PDB']) if t in self.cifs]
        if not mu or not mu[3] or not toks:
            return None
        wt, num, _, ch = mu
        for t in toks:
            m, _, _ = self.model(t)
            if ch in m and (' ', num, ' ') in m[ch]:
                if self.seq1(m[ch][(' ', num, ' ')].get_resname()) == wt:
                    return self.interactions(t, ch, num)
                return None
        return None


def assemble(row, llm, s, d_fallback):
    """One routed record. llm: the LLM labels for this record or None; s: structure contact set or None."""
    q = row['Quote'] or ''
    k, r, flags = keyword_classes(q), route_of(q), []
    if r in 'AB' and negation_suspected(q, k):
        flags.append('negation_suspected')
    if r in 'BCD' and s is None:
        flags.append('no_verified_structure')
    if r == 'A':
        return {'route': r, 'labels': k, 'evidence': 'stated', 'flags': flags}
    if r == 'B':
        conf = [c for c in k if s and c in s]
        if len(conf) == 1:
            primary = conf[0]
            flags.append('primary_by_structure')
        else:
            pool = conf if len(conf) >= 2 else k
            pick = next((c for c in (llm or []) if c in pool), None)
            primary = pick or pool[0]
            flags.append('primary_by_llm' if pick else 'primary_by_keyword_order')
        return {'route': r, 'labels': [primary] + [c for c in k if c != primary], 'evidence': 'stated', 'flags': flags}
    if r == 'C':
        if llm is None:
            return {'route': r, 'labels': [], 'evidence': 'insufficient', 'flags': flags + ['llm_missing']}
        if s is not None and llm and llm[0] not in s:
            flags.append('structure_disagrees')
        return {'route': r, 'labels': llm, 'evidence': 'inferred' if llm else 'insufficient', 'flags': flags}
    flags.append('paper_gate_not_built')
    if d_fallback == 'structure':
        labels = [c for c in PRIORITY if s and c in s][:1]
        return {'route': r, 'labels': labels, 'evidence': 'structure_inferred' if labels else 'insufficient', 'flags': flags}
    if d_fallback == 'llm':
        if llm is None:
            flags.append('llm_missing')
        return {'route': r, 'labels': llm or [], 'evidence': 'inferred' if llm else 'insufficient', 'flags': flags}
    return {'route': r, 'labels': [], 'evidence': 'insufficient', 'flags': flags}


def right(g, M):
    return bool(M and M[0] in g['G']) if g['state'] == 'mechanism' else not M


def read_split(name):
    return [x.strip() for x in open(os.path.join(TESTSET, f'{name}_ids.txt'), encoding='utf-8') if x.strip()]


def read_llm(run_dir):
    out = {}
    for f in sorted(glob.glob(os.path.join(run_dir, 'baseline', 'batch_*', 'final.jsonl'))):
        for line in open(f, encoding='utf-8'):
            if line.strip():
                r = json.loads(line)
                out[str(r['ID'])] = [x for x in (r.get('mechanism_labels') or []) if x != 'not_stated']
    return out


def boot(gold, oks, ids):
    """oks: {name: {id: bool}}; returns {name: (lo, hi)} of the mean over ids, quote-clustered."""
    clusters = collections.defaultdict(list)
    for i in ids:
        clusters[gold[i]['quote']].append(i)
    keys = sorted(clusters)
    rng = random.Random(SEED)
    draws = collections.defaultdict(list)
    for _ in range(N_BOOT):
        s = [i for k in rng.choices(keys, k=len(keys)) for i in clusters[k]]
        for name, ok in oks.items():
            draws[name].append(sum(ok[i] for i in s) / len(s))
    return {n: (ev.percentile(d, .025), ev.percentile(d, .975)) for n, d in draws.items()}


def pct(k, n):
    return f'{k}/{n} ({100 * k / n:.1f}%)' if n else '–'


def ci(t):
    return f'[{100 * t[0]:.1f}, {100 * t[1]:.1f}]'


def check_patterns(inp):
    bad = [i for i, r in inp.items()
           if {c for c, rx in RX.items() if re.search(rx, r['Quote'] or '', re.I)} != set(sg.keyword(r['Quote']))]
    if bad:
        sys.exit(f'RX no longer matches sg.keyword on {len(bad)} quotes, e.g. {bad[:5]}')


def cmd_ids(a):
    gold, inp = sg.load_gold()
    ids = [i for i in read_split(a.split) if route_of(inp[i]['Quote']) in a.routes]
    with open(a.out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(ids) + '\n')
    print(f'{len(ids)} {a.split} records in routes {", ".join(a.routes)} written to {a.out}:',
          dict(collections.Counter(route_of(inp[i]['Quote']) for i in ids)))


def cmd_score(a):
    if a.split == 'test' and not a.final:
        sys.exit('The test set is scored once per final method. Freeze the routing first, then add --final.')
    gold, inp = sg.load_gold()
    check_patterns(inp)
    ids = read_split(a.split)
    llm = read_llm(a.llm)
    st = Structure()
    S = {i: (st.contacts(inp[i]) if route_of(inp[i]['Quote']) in 'BCD' else None) for i in ids}
    routed = {i: assemble(inp[i], llm.get(i), S[i], a.d_fallback) for i in ids}
    need = [i for i in ids if routed[i]['route'] in 'BC' or (routed[i]['route'] == 'D' and a.d_fallback == 'llm')]
    missing = [i for i in need if gold[i]['state'] != 'unscorable' and i not in llm]
    scored = [i for i in ids if gold[i]['state'] != 'unscorable']
    mech = [i for i in scored if gold[i]['state'] == 'mechanism']
    none = [i for i in scored if gold[i]['state'] == 'no_mechanism']
    kw = {i: sg.keyword(inp[i]['Quote']) for i in ids}
    systems = {'routing v0': {i: routed[i]['labels'] for i in ids}, 'keyword rule': kw}
    # alternatives on the same records, for the freeze decision; never on test, where only the frozen version is scored
    for fb in (('structure', 'llm', 'abstain') if a.split != 'test' else ()):
        if fb != a.d_fallback:
            systems[f'routing v0, D fallback {fb}'] = {i: assemble(inp[i], llm.get(i), S[i], fb)['labels'] for i in ids}
    if a.split != 'test':
        systems['routing v0, B without LLM pick'] = {i: assemble(inp[i], None, S[i], a.d_fallback)['labels']
                                                     if routed[i]['route'] == 'B' else routed[i]['labels'] for i in ids}
    ok = {n: {i: right(gold[i], P[i]) for i in scored} for n, P in systems.items()}
    ci_c = boot(gold, ok, scored)
    ci_a = boot(gold, ok, mech)
    diff = {}
    clusters = collections.defaultdict(list)
    for i in scored:
        clusters[gold[i]['quote']].append(i)
    keys = sorted(clusters)
    rng = random.Random(SEED)
    d = []
    for _ in range(N_BOOT):
        s = [i for k in rng.choices(keys, k=len(keys)) for i in clusters[k]]
        d.append(100 * sum(ok['routing v0'][i] - ok['keyword rule'][i] for i in s) / len(s))
    diff = (ev.percentile(d, .025), ev.percentile(d, .975))

    md = [f'# Routing v0 on {a.split}\n',
          f"Run {datetime.date.today().isoformat()} with `mutmech routing`; LLM labels from `{a.llm}` "
          f'(single-agent baseline skill). Route D fallback: **{a.d_fallback}** (the paper gate is not built). '
          'Not built either: the LLM check of suspected negations (flag only). '
          f'{len(scored)} scorable records: {len(mech)} curator mechanism, {len(none)} curator none.\n']
    if missing:
        md.append(f'**{len(missing)} scorable records that need an LLM label have none** (they count as no label): '
                  + (', '.join(missing[:30]) if a.split != 'test' else 'IDs withheld on test') + '\n')
    md.append('## Accuracy\n')
    md.append('**A**: curator-mechanism records, primary label in the curator set. **C**: all scorable records, '
              'no label is right where the curators mark none. 95% quote-clustered bootstrap intervals.\n')
    rows = []
    for n in systems:
        a_ok = sum(ok[n][i] for i in mech)
        c_ok = sum(ok[n][i] for i in scored)
        rows.append([n, f'{pct(a_ok, len(mech))} {ci(ci_a[n])}', f'{pct(c_ok, len(scored))} {ci(ci_c[n])}',
                     f"{sum(1 for i in none if not systems[n][i])}/{len(none)}"])
    md.append(ev.table(['System', 'A', 'C', 'Curator none left blank'], rows) + '\n')
    md.append(f'Paired difference in C, routing v0 minus keyword rule: '
              f'{100 * (sum(ok["routing v0"].values()) - sum(ok["keyword rule"].values())) / len(scored):+.1f} points '
              f'[{diff[0]:+.1f}, {diff[1]:+.1f}].\n')
    md.append('## By route\n')
    rows = []
    for r in 'ABCD':
        x = [i for i in scored if routed[i]['route'] == r]
        m = [i for i in x if gold[i]['state'] == 'mechanism']
        rows.append([r, len([i for i in ids if routed[i]['route'] == r]), len(x), len(x) - len(m),
                     pct(sum(ok['routing v0'][i] for i in m), len(m)), pct(sum(ok['keyword rule'][i] for i in m), len(m)),
                     pct(sum(ok['routing v0'][i] for i in x), len(x)), pct(sum(ok['keyword rule'][i] for i in x), len(x))])
    md.append(ev.table(['Route', 'Records', 'Scorable', 'Curator none', 'A, routing', 'A, keyword', 'C, routing', 'C, keyword'], rows) + '\n')
    md.append('## By evidence level\n')
    rows = []
    for e in ('stated', 'inferred', 'structure_inferred', 'insufficient'):
        x = [i for i in scored if routed[i]['evidence'] == e]
        m = [i for i in x if gold[i]['state'] == 'mechanism']
        if x:
            rows.append([e, len(x), pct(sum(ok['routing v0'][i] for i in m), len(m)), pct(sum(ok['routing v0'][i] for i in x), len(x))])
    md.append(ev.table(['Evidence level', 'Scorable', 'A', 'C'], rows) + '\n')
    md.append('## Flags\n')
    fl = collections.Counter(f for i in scored for f in routed[i]['flags'])
    rows = []
    for f, n in fl.most_common():
        x = [i for i in scored if f in routed[i]['flags']]
        rows.append([f, n, pct(sum(ok['routing v0'][i] for i in x), len(x))])
    md.append(ev.table(['Flag', 'Scorable records', 'C among them'], rows) + '\n')
    if a.split != 'test':
        llm_ids = [i for i in scored if i in llm]
        if llm_ids:
            md.append('## Single-agent LLM on its own, on the records it labelled\n')
            rows = []
            for r in 'BCD':
                x = [i for i in llm_ids if routed[i]['route'] == r]
                m = [i for i in x if gold[i]['state'] == 'mechanism']
                rows.append([r, len(x), pct(sum(right(gold[i], llm[i]) for i in m), len(m)), pct(sum(ok['routing v0'][i] for i in m), len(m)),
                             pct(sum(right(gold[i], llm[i]) for i in x), len(x)), pct(sum(ok['routing v0'][i] for i in x), len(x))])
            md.append(ev.table(['Route', 'Scorable', 'A, LLM alone', 'A, routing', 'C, LLM alone', 'C, routing'], rows) + '\n')
    text = '\n'.join(md)
    out = a.out or os.path.join(config.RUNS, 'routing', f'{a.split}_v0')
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, 'results.md'), 'w', encoding='utf-8').write(text)
    summary = {'split': a.split, 'd_fallback': a.d_fallback, 'llm_run': a.llm, 'date': datetime.date.today().isoformat(),
               'script_sha256': hashlib.sha256(open(os.path.abspath(__file__), 'rb').read()).hexdigest(),
               'score_gold_sha256': hashlib.sha256(open(sg.__file__, 'rb').read()).hexdigest(),
               'scorable': len(scored), 'mechanism': len(mech), 'none': len(none), 'missing_llm': len(missing),
               'systems': {n: {'A': [sum(ok[n][i] for i in mech), len(mech)], 'C': [sum(ok[n][i] for i in scored), len(scored)],
                               'A_ci95': ci_a[n], 'C_ci95': ci_c[n]} for n in systems},
               'routes': dict(collections.Counter(routed[i]['route'] for i in ids))}
    json.dump(summary, open(os.path.join(out, 'results.json'), 'w', encoding='utf-8'), indent=1)
    if a.split != 'test':
        import csv
        with open(os.path.join(out, 'per_record.csv'), 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(['ID', 'route', 'labels', 'evidence', 'flags', 'structure_contacts', 'llm_labels', 'keyword_labels',
                        'gold_state', 'gold_codes', 'right_C'])
            for i in ids:
                g = gold[i]
                w.writerow([i, routed[i]['route'], ';'.join(routed[i]['labels']), routed[i]['evidence'], ';'.join(routed[i]['flags']),
                            '' if S[i] is None else ';'.join(sorted(S[i])), ';'.join(llm.get(i, [])) if i in llm else '',
                            ';'.join(kw[i]), g['state'], ';'.join(g['G']), '' if g['state'] == 'unscorable' else int(right(g, routed[i]['labels']))])
    print(text)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('ids')
    p.add_argument('split', choices=['dev', 'test', 'reserve'])
    p.add_argument('out')
    p.add_argument('--routes', default='BCD', help='routes to list, e.g. BC when route D uses the structure fallback')
    p = sub.add_parser('score')
    p.add_argument('split', choices=['dev', 'test', 'reserve'])
    p.add_argument('--llm', required=True, help='pipeline run folder with baseline/batch_*/final.jsonl')
    p.add_argument('--d-fallback', choices=['structure', 'llm', 'abstain'], default='structure')
    p.add_argument('--final', action='store_true')
    p.add_argument('--out')
    a = ap.parse_args()
    (cmd_ids if a.cmd == 'ids' else cmd_score)(a)


if __name__ == '__main__':
    main()
