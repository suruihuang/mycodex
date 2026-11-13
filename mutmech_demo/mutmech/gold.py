#!/usr/bin/env python3
"""Score MutMech runs against the curators' mechanism tags (CLEANED!D). Read-only on all inputs.

Gold = column D ("Mechanism") of sheet CLEANED in ~/data/Cleaned quotes +Results.xlsx, joined by ID.
Each bracketed tag is mapped to the pipeline's 9 codes by the explicit table TAG_MAP below.
Every record gets one gold state:
  mechanism     at least one tag maps to a mechanism code
  no_mechanism  no mechanism tag, and the curator recorded an effect only or said there is none
                (low/high/no impact, not documented, no mechanism, no effect, no contact, ...)
  unscorable    blank cell, data-problem flags (skipped, wrong mutation, error, TCR/pMHC),
                or only role/meta/contact-without-type tags (note, info, specificity determining, contact, ...)
Metric definitions are imported unchanged from tools/evaluate.py; evidence basis is not scored
because the curators did not record one.

Usage: python3 eval/gold_workbook/score_gold.py OUT_DIR
"""
import collections, csv, glob, json, os, random, re, sys

from . import config
from . import evaluate as ev  # metric definitions, unchanged
import openpyxl  # noqa: E402

WORKBOOK = config.WORKBOOK
INPUT = config.INPUT_CSV
ROOT = os.path.dirname(os.path.dirname(config.INPUT_CSV))  # legacy run folders read by systems() only

HB, EL, HY, AR, ST, CO, CM, OT = ('hydrogen_bonding', 'electrostatic', 'hydrophobic', 'aromatic', 'steric',
                                  'conformational', 'covalent_or_metal', 'other')
TAG_MAP = {
    # mechanism tags -> code
    'hbond': HB, 'hbonds': HB, 'hbond-watermediated': HB, 'hbond-internal': HB, 'hbond-ionmediated': HB,
    'water mediated hbond': HB, 'water-mediated interaction': HB, 'polar': HB, 'polar contact': HB,
    'salt bridge': EL, 'saltbridge': EL, 'salt bridges': EL, 'electrostatic': EL,
    'electrostatic focusing': EL, 'electrostaticfocusing': EL,
    'hydrophobic': HY, 'vanderwaals': HY, 'van der waals': HY, 'van der waal forces': HY,
    'van der waals contacts': HY, 'packing interaction': HY,
    'stacking': AR, 'stacking interaction': AR, 'pi-pi': AR, 'aromatic': AR, 'cation-pi': AR,
    'steric': ST, 'stericnegative': ST,
    'conformational': CO, 'conformational change': CO, 'conformational effect': CO, 'inducedfit': CO,
    'loss of stability': CO,
    'disulfide bond': CM, 'intramolecular disulfide bond': CM, 'ionbinding': CM,
    'charged-hydrophobic': OT,
}
NO_MECH = {'low impact', 'high impact', 'no impact', 'not documented', 'no documentation', 'no mechanism',
           'neutral mutation: no mechanism', 'no effect', 'no contact', 'adds no vanderwaals contacts',
           'backbone only', 'not hbond', 'no hbonds'}
DATA_FLAG = {'skipped', 'wrong mutation', 'error', 'tcr/pmhc'}
# everything else (note, info, specificity determining, scissile peptide bond, contact(s), close contacts,
# interaction, hypothetical, mechanism, state what mechanism affects the mutation, ...) carries no mechanism.
VDW_COUNT = re.compile(r'^(adds|loses) (\d+) vanderwaals contacts$')

SEP_MAP = {'electrostatic': [EL], 'packing': [HY], 'hydrophobic': [HY], 'hydrogen bonding': [HB],
           'hydrogen bonding + van der waals': [HB, HY], 'van der waals': [HY], 'shape complementarity': [ST],
           'not stated': []}


def tags_of(cell):
    return [' '.join(t.split()).lower() for t in re.findall(r'\[([^\]]*)\]', str(cell or ''))]


def gold_from_cell(cell):
    tags = tags_of(cell)
    codes = []
    for t in tags:
        c = TAG_MAP.get(t)
        m = VDW_COUNT.match(t)
        if m and int(m.group(2)) > 0:
            c = HY
        if c and c not in codes:
            codes.append(c)
    if codes:
        return 'mechanism', codes, tags
    if not tags:
        return 'unscorable', [], tags
    if set(tags) & DATA_FLAG:
        return 'unscorable', [], tags
    if set(tags) & NO_MECH:
        return 'no_mechanism', [], tags
    return 'unscorable', [], tags


def load_gold():
    wb = openpyxl.load_workbook(WORKBOOK, read_only=True, data_only=True)
    cells = {}
    for r in wb['CLEANED'].iter_rows(min_row=3, max_col=6, values_only=True):
        if r[0] is not None:
            cells[str(r[0]).strip().removesuffix('.0')] = r[3]
    inp = {r['ID'].strip(): r for r in csv.DictReader(open(INPUT, encoding='utf-8-sig'))}
    gold = {}
    for i, r in inp.items():
        state, codes, tags = gold_from_cell(cells.get(i))
        gold[i] = {'state': state, 'G': codes, 'tags': tags, 'raw': cells.get(i),
                   'quote': ev.norm(r['Quote']) or i, 'pdb': ev.pdb_token(r['PDB']), 'Quote': r['Quote']}
    return gold, inp


def jl(path):
    return {str(r['ID']): r for r in (json.loads(l) for l in open(path, encoding='utf-8') if l.strip())}


def keyword(quote):
    q = str(quote or '')
    rules = [(EL, r'salt[- ]bridge|electrostatic|ionic (?:interaction|bond|pair)'), (HB, r'hydrogen[- ]bond|h-bond'),
             (HY, r'van der waals|hydrophobic'), (AR, r'stacking|cation[- ]?(?:π|pi)\b|aromatic'),
             (ST, r'steric|clash'), (CM, r'disulfide|metal')]
    hits = sorted(((m.start(), lab) for lab, rx in rules for m in [re.search(rx, q, re.I)] if m))
    out = []
    for _, lab in hits:
        if lab not in out:
            out.append(lab)
    return out


def systems(inp):
    S = {}
    pr = json.load(open(os.path.join(ROOT, 'codex-rs/experiment_results/peer_review_2026-10-15/input_records.json')))
    S['sep_first50'] = {str(r['Source ID']): SEP_MAP[str(r['Decoded primary label']).lower()] for r in pr}
    lab = lambda r: [x for x in r['mechanism_labels'] if x != 'not_stated']
    S['dev24'] = {i: lab(r) for i, r in jl(os.path.join(ROOT, 'runs/dev24/mechanisms.jsonl')).items()}
    d24b = {i: lab(r) for i, r in jl(os.path.join(ROOT, 'runs/dev24b/mechanisms.jsonl')).items()}
    S['dev24b'] = dict(d24b)
    S['dev24b_spot1'] = dict(d24b)
    S['dev24b_spot1'].update({i: lab(r) for i, r in jl(os.path.join(ROOT, 'runs/spot1/mechanisms.jsonl')).items()})
    full, basis = {}, {}
    for b in range(1, 7):
        d = os.path.join(ROOT, f'runs/full_v1/batch_{b}')
        if os.path.exists(os.path.join(d, 'final.jsonl')):
            recs = jl(os.path.join(d, 'final.jsonl'))
        else:
            recs = jl(os.path.join(d, 'extract_r0.jsonl'))
            for f in sorted(glob.glob(os.path.join(d, 'extract_r[1-9].jsonl'))):
                recs.update(jl(f))
        for i, r in recs.items():
            full[i] = lab(r)
            basis[i] = r['evidence_basis']
    S['full_v1'] = full
    S['keyword'] = {i: keyword(inp[i]['Quote']) for i in inp}
    return S, basis


def items(gold, pred, ids, by_quote=False):
    sizes = collections.Counter(gold[i]['quote'] for i in ids)
    return [(gold[i]['G'], pred.get(i, []), 'x', 'x', (1 / sizes[gold[i]['quote']]) if by_quote else 1.0) for i in ids]


def boot(gold, preds, ids, n=2000, seed=0):
    clusters = collections.defaultdict(list)
    for i in ids:
        clusters[gold[i]['quote']].append(i)
    keys = sorted(clusters)
    rng = random.Random(seed)
    out = [[] for _ in preds]
    for _ in range(n):
        sample = [i for k in rng.choices(keys, k=len(keys)) for i in clusters[k]]
        for s, p in enumerate(preds):
            out[s].append(ev.metrics(items(gold, p, sample)))
    return out


KEYS = ['fabrication', 'precision', 'coverage', 'missed']
NAMES = {'fabrication': 'Label where gold has none ↓', 'precision': 'Label precision ↑', 'coverage': 'Coverage ↑',
         'missed': 'Missed (no label, gold has one) ↓'}


def score_block(gold, named_preds, ids, title):
    ids = [i for i in ids if gold[i]['state'] != 'unscorable']
    st = collections.Counter(gold[i]['state'] for i in ids)
    lines = [f'### {title}\n', f'{len(ids)} scorable records ({st["mechanism"]} with a gold mechanism, '
             f'{st["no_mechanism"]} with none), {len({gold[i]["quote"] for i in ids})} distinct quotes.\n']
    names = list(named_preds)
    preds = [named_preds[k] for k in names]
    bs = boot(gold, preds, ids)
    rows = []
    for s, name in enumerate(names):
        m = ev.metrics(items(gold, preds[s], ids))
        cells = []
        for k in KEYS:
            lo = ev.percentile([b[k] for b in bs[s]], .025); hi = ev.percentile([b[k] for b in bs[s]], .975)
            cells.append(f'{ev.fmt(m[k])} [{ev.fmt(lo)}, {ev.fmt(hi)}]')
        n_lab = sum(1 for i in ids if preds[s].get(i))
        rows.append([name, n_lab] + cells)
    lines.append(ev.table(['System', 'Records labelled'] + [NAMES[k] for k in KEYS], rows) + '\n')
    qrows = [[name] + [ev.fmt(ev.metrics(items(gold, preds[s], ids, True))[k]) for k in KEYS] for s, name in enumerate(names)]
    lines.append('By distinct quote (each quote weighted once):\n')
    lines.append(ev.table(['System'] + [NAMES[k] for k in KEYS], qrows) + '\n')
    if len(names) > 1:
        drows = []
        for s in range(1, len(names)):
            cells = []
            for k in KEYS:
                d = [b2[k] - b0[k] for b0, b2 in zip(bs[0], bs[s])]
                p0 = ev.metrics(items(gold, preds[0], ids))[k]; p1 = ev.metrics(items(gold, preds[s], ids))[k]
                cells.append(f'{ev.fmt(p1 - p0)} [{ev.fmt(ev.percentile(d, .025))}, {ev.fmt(ev.percentile(d, .975))}]')
            drows.append([f'{names[s]} − {names[0]}'] + cells)
        lines.append('Paired differences, same bootstrap samples (claim only intervals that exclude 0):\n')
        lines.append(ev.table(['Comparison'] + [NAMES[k] for k in KEYS], drows) + '\n')
    return '\n'.join(lines)


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    gold, inp = load_gold()
    with open(os.path.join(out, 'gold_mapped.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['ID', 'curator_mechanism_cell', 'gold_state', 'gold_codes'])
        for i in inp:
            w.writerow([i, gold[i]['raw'] or '', gold[i]['state'], ';'.join(gold[i]['G'])])
    S, basis = systems(inp)
    rep = ['# Runs scored against the curator mechanism column\n',
           'Gold: `CLEANED` column D of the source workbook, mapped tag by tag (see `score_gold.py`). '
           'Metric definitions from `tools/evaluate.py`; 95% intervals are quote-clustered bootstraps.\n']
    st = collections.Counter(g['state'] for g in gold.values())
    rep.append(f'All 1,133 input rows: {st["mechanism"]} mechanism, {st["no_mechanism"]} no mechanism, {st["unscorable"]} unscorable.\n')
    gc = collections.Counter(c for g in gold.values() for c in g['G'])
    rep.append(ev.table(['Gold code', 'Records'], gc.most_common()) + '\n')
    dev = sorted(S['dev24'], key=int)
    first50 = sorted(S['sep_first50'], key=int)
    full = sorted(S['full_v1'], key=int)
    rep.append(score_block(gold, {'dev24b_spot1': S['dev24b_spot1'], 'dev24b': S['dev24b'], 'dev24': S['dev24'],
                                  'sep_first50': S['sep_first50'], 'keyword': S['keyword']}, dev, 'The 24 development IDs'))
    rep.append(score_block(gold, {'sep_first50': S['sep_first50'], 'keyword': S['keyword']}, first50, 'September first 50 IDs'))
    rep.append(score_block(gold, {'full_v1': S['full_v1'], 'keyword': S['keyword']}, full, 'Full run, batches 1–6'))
    # full run by evidence basis
    rows = []
    for b in ev.BASES:
        ids = [i for i in full if basis[i] == b and gold[i]['state'] != 'unscorable']
        if not ids:
            continue
        mech = [i for i in ids if gold[i]['state'] == 'mechanism']
        none = [i for i in ids if gold[i]['state'] == 'no_mechanism']
        hit = sum(1 for i in mech if S['full_v1'][i] and S['full_v1'][i][0] in gold[i]['G'])
        lab_none = sum(1 for i in none if S['full_v1'][i])
        rows.append([b, len(ids), f'{hit}/{len(mech)}' if b != 'not_assessable' else '–', f'{lab_none}/{len(none)}' if b != 'not_assessable' else f'0/{len(none)}',
                     f'{sum(1 for i in mech if not S["full_v1"][i])}/{len(mech)}' if b == 'not_assessable' else '–'])
    rep.append('### Full run by evidence basis\n')
    rep.append(ev.table(['Model basis', 'Scorable', 'Primary in gold (gold has one)', 'Labelled though gold has none', 'Abstained though gold has one'], rows) + '\n')
    # per gold code recall in the full run
    rows = []
    for c, _ in gc.most_common():
        ids = [i for i in full if c in gold[i]['G']]
        if ids:
            rows.append([c, len(ids), sum(1 for i in ids if c in S['full_v1'][i]), sum(1 for i in ids if c in S['keyword'][i]),
                         sum(1 for i in ids if not S['full_v1'][i])])
    rep.append('### Full run, per gold code\n')
    rep.append(ev.table(['Gold code', 'Records', 'full_v1 has it', 'keyword has it', 'full_v1 abstained'], rows) + '\n')
    # confusion of full-run primary vs gold
    conf = collections.Counter()
    for i in full:
        if gold[i]['state'] == 'mechanism' and S['full_v1'][i] and S['full_v1'][i][0] not in gold[i]['G']:
            conf[(S['full_v1'][i][0], '+'.join(gold[i]['G']))] += 1
    rep.append('### Full run, wrong primary labels (model primary → gold set)\n')
    rep.append(ev.table(['Model primary', 'Gold set', 'Records'], [[a, b, n] for (a, b), n in conf.most_common()]) + '\n')
    # sensitivity: the rules call a hydrogen bond between oppositely charged side chains electrostatic;
    # the curators often tag the same contact [hbond]. Merge the two polar codes in gold and predictions.
    def merged(d):
        out = {}
        for k, v in d.items():
            v = ['polar' if c in (HB, EL) else c for c in v]
            out[k] = list(dict.fromkeys(v))
        return out
    gold_m = {i: dict(g, G=list(dict.fromkeys('polar' if c in (HB, EL) else c for c in g['G']))) for i, g in gold.items()}
    rep.append('## Sensitivity: electrostatic and hydrogen bonding counted as one polar class\n')
    rep.append(score_block(gold_m, {'dev24b_spot1': merged(S['dev24b_spot1']), 'dev24b': merged(S['dev24b']), 'dev24': merged(S['dev24']),
                                    'sep_first50': merged(S['sep_first50']), 'keyword': merged(S['keyword'])}, dev, 'The 24 development IDs, polar merged'))
    rep.append(score_block(gold_m, {'full_v1': merged(S['full_v1']), 'keyword': merged(S['keyword'])}, full, 'Full run, batches 1–6, polar merged'))
    # gold consistency: same quote and same mutation string, different gold codes
    grp = collections.defaultdict(list)
    for i, r in inp.items():
        if gold[i]['state'] != 'unscorable':
            grp[(gold[i]['quote'], ev.norm(r['Mutation DECODED']))].append(i)
    multi = [v for v in grp.values() if len(v) > 1]
    bad = [v for v in multi if len({(gold[i]['state'], frozenset(gold[i]['G'])) for i in v}) > 1]
    rep.append('## Consistency of the curator column\n')
    rep.append(f'Groups of scorable records with the same quote and the same mutation string: {len(multi)}; with different gold: {len(bad)}.\n')
    for v in bad[:20]:
        rep.append('- ' + '; '.join(f"{i}: {gold[i]['raw']}" for i in v))
    rep.append('')
    open(os.path.join(out, 'scores.md'), 'w', encoding='utf-8').write('\n'.join(rep))
    # per-record table for the full run and dev IDs
    with open(os.path.join(out, 'per_record.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['ID', 'gold_state', 'gold_codes', 'curator_cell', 'sep_first50', 'dev24', 'dev24b_spot1', 'full_v1', 'full_v1_basis', 'keyword'])
        for i in sorted(set(full) | set(dev) | set(first50), key=int):
            g = gold[i]
            fmt = lambda s: ';'.join(S[s][i]) if i in S[s] else ''
            w.writerow([i, g['state'], ';'.join(g['G']), g['raw'] or '', fmt('sep_first50'), fmt('dev24'), fmt('dev24b_spot1'),
                        fmt('full_v1'), basis.get(i, ''), ';'.join(S['keyword'][i])])
    print('\n'.join(rep))


if __name__ == '__main__':
    main()
