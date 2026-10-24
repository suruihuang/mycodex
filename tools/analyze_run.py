#!/usr/bin/env python3
"""Describe a mechanism-extraction run. Needs no gold standard.

Usage:
  python3 analyze_run.py RUN_DIR --input DATA.csv [--records FILE] [--group pdb|citation] [--out report.md]

Uses RUN_DIR/mechanisms.jsonl if it exists (or --records), otherwise the newest
record per ID from RUN_DIR/batch_*/extract_r*.jsonl. Review and revision logs are
read from the batch folders. Writes a Markdown report to --out or stdout.
"""
import argparse
import collections
import csv
import glob
import json
import os
import re
import sys

EFFECT = re.compile(r'fold|kcal|on-rate|off-rate|on rate|off rate|af.?finity|af.nity|dissociation|association|'
                    r'\bk_?d\b|ic50|activity|binding energy|ΔΔ?G', re.I)
INTERACTION = re.compile(r'hydrogen|h-bond|salt bridge|ionic|electrostatic|van der waals|hydrophobic|packing|'
                         r'stack|cation|aromatic|contact|interact|steric|clash|disulfide|metal|buri', re.I)
KEYWORDS = [
    ('hydrogen_bonding', re.compile(r'hydrogen[- ]bond|h-bond', re.I)),
    ('electrostatic', re.compile(r'salt[- ]bridge|electrostatic|ionic (?:interaction|bond|pair)', re.I)),
    ('hydrophobic', re.compile(r'van der waals|hydrophobic', re.I)),
    ('aromatic', re.compile(r'stacking|cation[- ]?(?:π|pi)\b|aromatic', re.I)),
    ('steric', re.compile(r'steric|clash', re.I)),
]
BASES = ['explicit_reported', 'author_proposed', 'chemical_inference', 'structure_inference', 'not_assessable']


def jl(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def order(path):
    b = re.search(r'batch_(\d+)', path)
    r = re.search(r'_r(\d+)\.jsonl$', path)
    return (int(b.group(1)) if b else -1, int(r.group(1)) if r else -1)


def norm(s):
    return ' '.join(str(s or '').split()).strip('“”"\' ').lower()


def pct(n, d):
    return f'{100 * n / d:.0f}%' if d else '–'


def table(headers, rows):
    out = ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join('---' for _ in headers) + ' |']
    for row in rows:
        out.append('| ' + ' | '.join(str(c).replace('|', '/') for c in row) + ' |')
    return '\n'.join(out)


def cut(s, n=140):
    s = ' '.join(str(s or '').split())
    return s if len(s) <= n else s[:n] + '…'


def na_kind(q):
    t = str(q or '').strip().strip('“”"\' ')
    if t.startswith('(') or len(t) < 60:
        return 'no evidence text'
    if EFFECT.search(t) and not INTERACTION.search(t):
        return 'effect only'
    return 'has interaction text'


def group_key(rec, mode):
    if mode == 'citation':
        c = ' '.join(str(rec.get('Citation') or '').split())
        return c[:60] or '(no citation)'
    m = re.search(r'\b(\d[A-Za-z0-9]{3})', str(rec.get('PDB') or ''))
    return m.group(1).upper() if m else '(no PDB)'


def labels(rec):
    return [x for x in (rec.get('mechanism_labels') or []) if x != 'not_stated']


def load_records(args):
    path = args.records or os.path.join(args.run, 'mechanisms.jsonl')
    if os.path.exists(path):
        return {str(r.get('ID')): r for r in jl(path)}, path
    recs = {}
    for f in sorted(glob.glob(os.path.join(args.run, 'batch_*', 'extract_r*.jsonl')), key=order):
        for r in jl(f):
            recs[str(r.get('ID'))] = r
    return recs, 'batch_*/extract_r*.jsonl (newest per ID)'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('run')
    ap.add_argument('--input', required=True)
    ap.add_argument('--records')
    ap.add_argument('--group', choices=['pdb', 'citation'], default='pdb')
    ap.add_argument('--out')
    args = ap.parse_args()

    with open(args.input, newline='', encoding='utf-8-sig') as f:
        total = sum(1 for _ in csv.DictReader(f))
    recs, source = load_records(args)
    R = list(recs.values())
    if not R:
        sys.exit('no records found')
    out = []
    w = out.append

    w('# Run analysis\n')
    w(f'Records: **{len(R)} of {total}** input rows ({pct(len(R), total)}). Source: `{source}`.\n')

    # 1. evidence basis and labels
    basis = collections.Counter(r.get('evidence_basis') for r in R)
    w('## 1. Evidence basis\n')
    w(table(['Basis', 'Records', 'Share'], [[b, basis[b], pct(basis[b], len(R))] for b in BASES if basis[b]]) + '\n')
    prim = collections.Counter((labels(r) or ['not_stated'])[0] for r in R)
    combos = collections.Counter(' + '.join(labels(r)) for r in R if len(labels(r)) > 1)
    w('## 2. Mechanism labels\n')
    w(table(['Primary label', 'Records', 'Share'], [[k, v, pct(v, len(R))] for k, v in prim.most_common()]) + '\n')
    w(f'Records with 2+ labels: **{sum(len(labels(r)) > 1 for r in R)}**.\n')
    if combos:
        w(table(['Label set', 'Records'], combos.most_common(10)) + '\n')

    # 3. by group
    groups = collections.defaultdict(list)
    for r in R:
        groups[group_key(r, args.group)].append(r)
    rows = []
    for g, rs in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:20]:
        b = collections.Counter(r.get('evidence_basis') for r in rs)
        fl = collections.Counter(x for r in rs for x in (r.get('input_flags') or []))
        rows.append([g, len(rs), pct(b['not_assessable'], len(rs)), pct(b['explicit_reported'], len(rs)),
                     pct(b['chemical_inference'], len(rs)), fl.most_common(1)[0][0] if fl else '–'])
    w(f'## 3. By {args.group} (largest 20 of {len(groups)})\n')
    w(table([args.group.upper(), 'Records', 'Not assessable', 'Explicit', 'Chemical inf.', 'Top flag'], rows) + '\n')

    # 4. not assessable split
    na = [r for r in R if r.get('evidence_basis') == 'not_assessable']
    kinds = collections.Counter(na_kind(r.get('Quote')) for r in na)
    w(f'## 4. Not assessable: {len(na)} records\n')
    w(table(['Kind', 'Records', 'What it means'], [
        ['no evidence text', kinds['no evidence text'], 'curator note or very short quote; only the paper can help'],
        ['effect only', kinds['effect only'], 'quote reports an effect but names no interaction'],
        ['has interaction text', kinds['has interaction text'], 'quote names an interaction: check these by hand'],
    ]) + '\n')
    check = [r for r in na if na_kind(r.get('Quote')) == 'has interaction text']
    if check:
        w('First 10 to check by hand:\n')
        for r in check[:10]:
            w(f"- **{r.get('ID')}** {r.get('Mutation DECODED')}: {cut(r.get('Quote'))}  \n  _uncertainty:_ {cut(r.get('uncertainty'), 120)}")
        w('')

    # 5. flags
    fl = collections.Counter(x for r in R for x in (r.get('input_flags') or []))
    w('## 5. Input flags (data problems)\n')
    w(table(['Flag', 'Records', 'Share'], [[k, v, pct(v, len(R))] for k, v in fl.most_common()]) + '\n')
    mm = [r for r in R if 'mutation_mismatch' in (r.get('input_flags') or [])]
    if mm:
        w('Mutation mismatches (candidate data errors): ' + ', '.join(str(r.get('ID')) for r in mm[:40]) + '\n')

    # 6. keyword audit
    w('## 6. Keyword audit\n')
    w('Not errors by themselves: each line is a place where the quote and the labels point in different directions.\n')
    rows, examples = [], []
    for lab, rx in KEYWORDS:
        miss = [r for r in R if rx.search(str(r.get('Quote') or '')) and lab not in labels(r)]
        unnamed = [r for r in R if lab in labels(r) and r.get('evidence_basis') == 'explicit_reported'
                   and not rx.search(str(r.get('Quote') or ''))]
        rows.append([lab, len(miss), len(unnamed)])
        if miss:
            examples.append(f"- {lab}, named but not labelled: " + ', '.join(str(r.get('ID')) for r in miss[:15]))
        if unnamed:
            examples.append(f"- {lab}, labelled explicit without the word in the quote: " + ', '.join(str(r.get('ID')) for r in unnamed[:15]))
    w(table(['Label', 'Quote names it, label absent', 'Explicit label, word absent'], rows) + '\n')
    if examples:
        w('\n'.join(examples) + '\n')

    # 7. consistency and quote reuse
    by_quote = collections.defaultdict(list)
    by_pair = collections.defaultdict(list)
    for r in R:
        by_quote[norm(r.get('Quote'))].append(r)
        by_pair[(norm(r.get('Quote')), norm(r.get('Mutation DECODED')))].append(r)
    sizes = [len(v) for v in by_quote.values()]
    multi = [v for v in by_pair.values() if len(v) > 1]
    incons = [v for v in multi if len({(frozenset(labels(x)), x.get('evidence_basis')) for x in v}) > 1]
    w('## 7. Quote reuse and consistency\n')
    w(f'Distinct quotes: **{len(by_quote)}** for {len(R)} records (mean {len(R) / len(by_quote):.1f}, max {max(sizes)} records per quote).\n')
    w(f'Same quote and same mutation appearing more than once: **{len(multi)}** groups; inconsistent: **{len(incons)}**.\n')
    for v in incons[:15]:
        w('- ' + '; '.join(f"{x.get('ID')}: {labels(x) or ['not_stated']} {x.get('evidence_basis')}" for x in v))
    if incons:
        w('')

    # 8. review loop
    issues, verdict = [], {}
    for f in sorted(glob.glob(os.path.join(args.run, 'batch_*', 'review_r*.jsonl')), key=order):
        for v in jl(f):
            verdict[str(v.get('ID'))] = v.get('verdict')
            for iss in v.get('issues') or []:
                issues.append((str(v.get('ID')), iss))
    decisions, refl = collections.Counter(), []
    for f in sorted(glob.glob(os.path.join(args.run, 'batch_*', 'revisions_r*.jsonl')), key=order):
        for r in jl(f):
            for resp in r.get('responses') or []:
                decisions[resp.get('decision')] += 1
                if resp.get('decision') == 'decline' and 'reflection' in str(resp.get('reason', '')).lower():
                    refl.append(str(r.get('ID')))
    w('## 8. Review loop\n')
    w(f"Records flagged at least once: **{len({i for i, _ in issues})}**; issues raised: **{len(issues)}**.\n")
    if issues:
        w(table(['Error type', 'Issues'], collections.Counter(i.get('error_type') for _, i in issues).most_common()) + '\n')
    if decisions:
        w(table(['Extractor response', 'Count'], decisions.most_common()) + '\n')
    w(f"Declines that cite reflections: **{len(refl)}** {('(' + ', '.join(refl) + ')') if refl else ''}\n")
    w(f"Final verdicts: {dict(collections.Counter(verdict.get(str(r.get('ID')), 'no review') for r in R))}\n")

    text = '\n'.join(out)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f'wrote {args.out}')
    else:
        print(text)


if __name__ == '__main__':
    main()
