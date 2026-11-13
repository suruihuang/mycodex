"""Analyse one mutation, or a small batch, from a quote or a paper PDF with a chosen rule and report the mechanism.

Rules:
  routing   (default) evidence routing v0 with no-hint quotes decided by the single agent, the best method on the
            first-500 benchmark. A quote naming one mechanism keyword takes that class with no LLM call. With
            several keywords, the PDB contacts pick the primary when they confirm exactly one, otherwise the single
            agent picks among them. Quotes without a keyword take the single agent's labels.
  baseline  the single-agent baseline skill
  v4        rules v4, extractor only
  stmt      statement rules: the quote is split into statements and each is classed for this mutation
The LLM rules run through Codex exactly as in batch runs, on one record. For a PDF, the passages that name the
residue are found first and given to the rule as its quote. Scanned PDFs need OCR first.

Usage:
  python -m mutmech analyze --mutation "D364A (chain B)" --quote "..." [--pdb 1A22] [--rule stmt]
  python -m mutmech analyze --mutation "D364A (chain B)" --pdf paper.pdf [--pdb 1A22] [--paper-number 164]
  python -m mutmech analyze --batch rows.csv [--rule routing]
  python -m mutmech analyze --pdf paper.pdf --list-mutations [--pdb 1A22]
  python -m mutmech analyze --pdf paper.pdf --pdb 1A22 --mutations "R43A,D164A" [--rule stmt]
A batch CSV has the columns mutation, pdb, and quote or pdf, optionally citation and paper_number; each row gets
its own result folder and the batch a summary.csv. Add --dry-run to stop before any LLM call; --json prints the
whole result record.
"""
import argparse, csv, datetime, json, os, re, shutil

from . import config, pdftext, routing, rulecall, structview

RULES = ('routing', 'baseline', 'v4', 'stmt')
NAMES = {'routing': 'evidence routing v0, no-hint quotes by the single agent', **rulecall.NAMES}


def offsets(pdb, chain):
    """pdb_minus_paper offsets recorded for this entry and chain in the numbering map, when verified."""
    out = []
    try:
        for r in csv.DictReader(open(config.NUMBERING_MAP, encoding='utf-8-sig')):
            if r['PDB'].upper() == pdb.upper() and r['chain'] == chain and r['pdb_minus_paper'].strip():
                out += [int(x) for x in re.findall(r'-?\d+', r['pdb_minus_paper'])]
    except (OSError, KeyError, ValueError):
        pass
    return sorted(set(out))


def build_quote(pdf, wt, num, mut, chain, pdb, paper_numbers):
    texts = pdftext.pages(pdf)
    if sum(len(t.strip()) for t in texts) < 200:
        raise SystemExit(f'{pdf}: no text layer found; run OCR on it first')
    numbers = paper_numbers or sorted({num} | {num - o for o in offsets(pdb, chain)})
    passages = pdftext.find_passages(texts, wt, numbers, mut)
    if not passages:
        raise SystemExit(f'{pdf}: no passage names {wt}{num} under residue numbers {numbers}; '
                         'give the paper\'s number with --paper-number')
    quote = '\n\n'.join(f'[page {p["page"]}] {p["text"]}' for p in passages)
    return quote, passages, numbers


def route(row, run, csv_path, dry_run):
    """Routing v0 as assembled for the first-500 benchmark ('routing no-cue by LLM'): one LLM call at most."""
    q = row['Quote']
    r, k = routing.route_of(q), routing.keyword_classes(q)
    s = structview.structure().contacts(row) if r in 'BCD' else None
    need_llm = r in 'CD' or (r == 'B' and len([c for c in k if s and c in s]) != 1)
    res = {'route': r, 'keyword_classes': k, 'structure_contacts': sorted(s) if s is not None else None,
           'llm_needed': need_llm}
    llm = None
    if need_llm:
        call = rulecall.run('baseline', run, csv_path, dry_run)
        res['llm'] = {k2: v for k2, v in call.items() if k2 not in ('engine', 'tokens', 'versions', 'status')}
        res.update({k2: call[k2] for k2 in ('engine', 'tokens', 'versions') if k2 in call})
        if call['status'] != 'ok':
            res['status'] = call['status']
            if call.get('usage_limit'):
                res['usage_limit'] = call['usage_limit']
            return res
        llm = call['mechanism_labels']
    a = routing.assemble(row, llm, s, 'llm')
    res.update({'status': 'ok', 'mechanism_labels': a['labels'], 'primary': a['labels'][0] if a['labels'] else None,
                'evidence': a['evidence'], 'flags': a['flags']})
    if need_llm:
        res.update({'mechanism': res['llm'].get('mechanism'), 'explanation': res['llm'].get('explanation')})
    return res


def analyze(mutation, quote=None, pdf=None, pdb='', citation='', paper_numbers=None, rule='routing', dry_run=False,
            parent=None):
    if rule not in RULES:
        raise SystemExit(f'rule {rule!r} is not available; choose from {", ".join(RULES)}')
    if (quote is None) == (pdf is None):
        raise SystemExit('give exactly one of --quote or --pdf')
    mu = routing.Structure.mutation(mutation)
    if not mu:
        raise SystemExit(f'cannot read the mutation {mutation!r}; write it like "D364A (chain B)"')
    wt, num, mut, chain = mu
    passages, numbers = [], None
    if pdf:
        quote, passages, numbers = build_quote(pdf, wt, num, mut, chain, pdb, paper_numbers)
        citation = citation or os.path.basename(pdf)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    base = os.path.join(parent or os.path.join(config.RUNS, 'analyze'), f'{stamp}-{(pdb or "nopdb").upper()}-{wt}{num}{mut}')
    run, n = base, 1
    while os.path.exists(run):
        n += 1
        run = f'{base}-{n}'
    os.makedirs(os.path.join(run, 'batch_a1'))
    row = {'ID': '1', 'PDB': pdb, 'Mutation DECODED': mutation, 'Quote': quote, 'Citation': citation}
    csv_path = os.path.join(run, 'input.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        w.writeheader()
        w.writerow(row)
    open(os.path.join(run, 'batch_a1', 'ids.txt'), 'w').write('1\n')
    shutil.copy(config.NUMBERING_MAP, os.path.join(run, 'numbering_map.csv'))
    result = {'rule': NAMES[rule], 'created': stamp, 'run_dir': run,
              'input': {'mutation': mutation, 'pdb': pdb, 'citation': citation, 'source': 'pdf' if pdf else 'quote',
                        'pdf': os.path.abspath(pdf) if pdf else None, 'paper_numbers_searched': numbers},
              'passages': passages, 'quote_used': quote}
    result.update(route(row, run, csv_path, dry_run) if rule == 'routing' else rulecall.run(rule, run, csv_path, dry_run))
    json.dump(result, open(os.path.join(run, 'result.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return result


def summary(n, g, res):
    return {'row': n, 'mutation': g('mutation'), 'pdb': g('pdb'), 'source': 'pdf' if g('pdf') else 'quote',
            'status': res['status'], 'route': res.get('route', ''), 'record_class': res.get('record_class', ''),
            'labels': ', '.join(res.get('mechanism_labels') or []),
            'result': os.path.join(res['run_dir'], 'result.json') if res['run_dir'] else ''}


def batch(path, rule, dry_run, on_row=None, on_limit=None):
    """Analyse every row of a batch CSV in order; on_row(summary_row) is called after each row. Returns the summary rows.

    When a row hits the Codex usage limit, on_limit(usage_limit) is called; it should wait until the retry time, and
    the row is then run again (on_row sees it twice, same row number). Without on_limit the batch stops there."""
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    base = parent = os.path.join(config.RUNS, 'analyze', f'batch-{stamp}')
    n = 1
    while True:  # two batches can start in the same second
        try:
            os.makedirs(parent)
            break
        except FileExistsError:
            n += 1
            parent = f'{base}-{n}'
    out = []
    on_row = on_row or (lambda s: print(f"row {s['row']}: {s['mutation']}  {s['status']}  {s['labels']}", flush=True))
    for n, r in enumerate(csv.DictReader(open(path, encoding='utf-8-sig')), 1):
        g = lambda k: (r.get(k) or '').strip() or None
        while True:
            try:
                res = analyze(g('mutation') or '', g('quote'), g('pdf'), g('pdb') or '', g('citation') or '',
                              [int(g('paper_number'))] if g('paper_number') else None, rule, dry_run, parent)
            except SystemExit as e:
                res = {'status': f'error: {e}', 'run_dir': ''}
            if not (res.get('usage_limit') and on_limit):
                break
            on_row(summary(n, g, res))
            on_limit(res['usage_limit'])
        out.append(summary(n, g, res))
        on_row(out[-1])
        if res.get('usage_limit'):
            break
    with open(os.path.join(parent, 'summary.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]) if out else ['row'])
        w.writeheader()
        w.writerows(out)
    return parent, out


def paper_batch(pdf, pdb, picks, rule, dry_run, on_row=None, on_limit=None):
    """Analyse mutations chosen from one paper as a batch. picks: dicts with mutation (PDB numbering, with chain)
    and paper_number. The rows go through batch() with the PDF as their evidence."""
    os.makedirs(os.path.join(config.RUNS, 'uploads'), exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path = os.path.join(config.RUNS, 'uploads', f'{stamp}-paper-picks.csv')
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['mutation', 'pdb', 'pdf', 'paper_number', 'citation'])
        w.writeheader()
        for p in picks:
            w.writerow({'mutation': p['mutation'], 'pdb': pdb, 'pdf': os.path.abspath(pdf), 'citation': os.path.basename(pdf),
                        'paper_number': p.get('paper_number') or ''})
    return batch(path, rule, dry_run, on_row, on_limit)


def choose(cands, names):
    """Candidates named as written in the paper (R64A) or in PDB numbering (D364A, or "D364A (chain B)")."""
    out = []
    for name in [x.strip() for x in names.split(',') if x.strip()]:
        key = name.replace(' ', '').upper()
        c = next((c for c in cands if key in (c['written'].upper(), c['pdb_mutation'].upper(), c['mutation'].replace(' ', '').upper())), None)
        if c is None:
            raise SystemExit(f'{name} is not among the mutations found in the paper; list them with --list-mutations')
        out.append({'mutation': c['mutation'], 'paper_number': c['paper_number']})
    return out


def show(r):
    print(f"Rule: {r['rule']}    Status: {r['status']}")
    if r.get('engine'):
        print(f"Model: {r['engine'].get('model')}    Input tokens: {r.get('tokens', {}).get('input_tokens')}")
    if r.get('route'):
        sc = r['structure_contacts']
        print(f"Route: {r['route']}    Keyword classes: {', '.join(r['keyword_classes']) or 'none'}    "
              f"Structure contacts: {', '.join(sc) if sc is not None else 'not verified'}    "
              f"LLM needed: {'yes' if r['llm_needed'] else 'no'}")
    if r['passages']:
        print(f"Passages from the PDF (residue numbers searched {r['input']['paper_numbers_searched']}):")
        for p in r['passages']:
            print(f"  page {p['page']}, score {p['score']}: {p['text'][:160]}")
    for s in r.get('statements') or []:
        print(f"  {s['sid']} [{s['class']}] {', '.join(s['interactions'] or []) or 'no interaction'}; {s['relation']}, "
              f"{s['after_substitution']}, applies {s['applies']}: {(s['span'] or '')[:100]}")
    if r.get('record_class'):
        print(f"Record class: {r['record_class']}    Labels from: {r['label_source']}")
    if r.get('mechanism_labels') is not None:
        print(f"Mechanism: {', '.join(r['mechanism_labels'])}  (primary {r['primary']})")
        if r.get('mechanism'):
            print(f"Description: {r['mechanism']}")
        if r.get('explanation'):
            print(f"Explanation: {r['explanation']}")
    if r.get('validator_problems'):
        print(f"Validator problems: {len(r['validator_problems'])}")
    print(f"Record: {os.path.join(r['run_dir'], 'result.json')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--mutation', help='e.g. "D364A (chain B)", in PDB numbering')
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument('--quote')
    src.add_argument('--pdf')
    src.add_argument('--batch', help='CSV with mutation, pdb, and quote or pdf per row')
    ap.add_argument('--pdb', default='')
    ap.add_argument('--citation', default='')
    ap.add_argument('--paper-number', type=int, action='append', help="the residue's number in the paper, if it differs")
    ap.add_argument('--rule', default='routing', choices=RULES)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--list-mutations', action='store_true', help='with --pdf: list the mutations the paper mentions, no LLM call')
    ap.add_argument('--mutations', help='with --pdf: analyse these mutations from the paper as a batch, e.g. "R43A,D164A"')
    a = ap.parse_args()
    if a.pdf and (a.list_mutations or a.mutations):
        from . import findmut, pdbguess
        p = pdbguess.paper(a.pdf, a.pdb)
        cands = p['mutations']
        if a.list_mutations:
            if a.json:
                print(json.dumps(p, ensure_ascii=False, indent=1))
                return
            if not a.pdb:
                print('PDB entries proposed from the paper (no LLM call, no network):')
                print(pdbguess.table(p['pdb_candidates']) if p['pdb_candidates'] else '  none found; give the entry with --pdb')
                print(f"Using {p['pdb'] or 'no entry'} ({p['chosen_by']}).\n")
            print(findmut.table(cands))
            return
        parent, _ = paper_batch(a.pdf, p['pdb'], choose(cands, a.mutations), a.rule, a.dry_run)
        print(f'Summary: {os.path.join(parent, "summary.csv")}')
        return
    if a.batch:
        parent, _ = batch(a.batch, a.rule, a.dry_run)
        print(f'Summary: {os.path.join(parent, "summary.csv")}')
        return
    if not a.mutation:
        ap.error('--mutation is required with --quote or --pdf')
    r = analyze(a.mutation, a.quote, a.pdf, a.pdb, a.citation, a.paper_number, a.rule, a.dry_run)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        show(r)
